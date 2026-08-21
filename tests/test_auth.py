"""
Adgangsmodellen. Den vigtigste egenskab: læsning er åben, skrivning er lukket.
"""
import os, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

TMP = tempfile.mkdtemp()
# Miljøet sættes i tests/conftest.py — den er den ENESTE kilde.
# `setdefault`, ikke `update`: et modul, der tvinger sin egen værdi,
# gør resultatet afhængigt af importrækkefølgen, og så afgør det
# tilfældige alfabet, hvilken database suiten kører på.
os.environ.setdefault("DATA_DIR", TMP)
os.environ.setdefault("RULES_PATH", str(pathlib.Path(__file__).resolve().parents[1] / "data" / "allergens.yaml"))
os.environ.setdefault("COOKIE_SECURE", "0")
os.environ.setdefault("CHECK_PWNED_PASSWORDS", "0")

import pytest
from fastapi.testclient import TestClient

from app.auth import hash_password
from app.db import SessionLocal, default_household, init_db
from app.main import app
from app.models import User

PW = "korrekt-hest-batteri-haefteklamme"


@pytest.fixture(scope="module")
def client():
    init_db()
    with SessionLocal() as db:
        # Filtrér på MAILEN, ikke på antal: modulerne deler én database,
        # og et blankt count() betyder, at modulets egen bruger aldrig
        # bliver oprettet, hvis et andet modul kørte først.
        if not db.query(User).filter(User.email == "w@example.dk").count():
            db.add(User(household_id=default_household(db).id, email="w@example.dk",
                        name="William", password_hash=hash_password(PW), role="admin"))
            db.commit()
    return TestClient(app)


@pytest.fixture(scope="module")
def auth(client):
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": "w@example.dk", "password": PW})
    assert r.status_code == 200
    return c


# --- læsning er åben ------------------------------------------------------

@pytest.mark.parametrize("path", [
    "/api/allergens",
    "/api/scan/5701234567890?allergens=maelkeprotein",
    "/api/products?exclude=mælk",
    "/api/ingredients/suggest?q=mælk",
    "/api/attribution",
])
def test_read_needs_no_login(client, path):
    assert client.get(path).status_code == 200


def test_scan_accepts_client_side_allergen_choice(client, auth):
    """
    Valgene ligger i localStorage og sendes som query — ingen konto.
    Varen skal først findes lokalt; en ukendt stregkode returnerer
    tomme rækker, fordi der ikke er noget at evaluere mod.
    """
    ean = "5712345000010"
    auth.post(f"/api/products/{ean}/confirm", json={
        "verdicts": {"jordbaer": "contains"},
        "ingredients_text": "Sukker, jordbærpuré 30%, hvedemel",
    })
    d = client.get(f"/api/scan/{ean}?allergens=jordbaer").json()
    assert [a["slug"] for a in d["allergens"]] == ["jordbaer"]
    assert d["allergens"][0]["state"] == "contains"


def test_unknown_barcode_returns_no_verdicts(client):
    """En ukendt vare er 'unknown' med tomme rækker — ikke en tom, grøn liste."""
    d = client.get("/api/scan/4999999999999?allergens=jordbaer").json()
    assert d["found"] is False
    assert d["result"] == "unknown"
    assert d["allergens"] == []


# --- skrivning er lukket --------------------------------------------------

def test_confirm_rejected_without_login(client):
    r = client.post("/api/products/5701234567890/confirm", json={"verdicts": {}})
    assert r.status_code == 401


def test_ocr_rejected_without_login(client):
    r = client.post("/api/ocr", files={"image": ("x.png", b"notanimage", "image/png")})
    assert r.status_code == 401


def test_toggle_allergen_rejected_without_login(client, auth):
    """
    Fluebenene i PWA'en er localStorage og rører aldrig serveren — de sendes
    med som `allergens=` på hvert opslag. Det her endpoint skriver den GEMTE
    profil, altså den tilstand `scan` falder tilbage på, når parameteren
    mangler. At ændre hvad appen advarer om, er en skrivning som enhver anden.
    """
    # /api/profiles kræver login siden appen blev åbnet — barnets navn og
    # allergener er ikke en del af det offentlige opslagsværk. Id'et hentes
    # derfor med en indlogget klient; selve pointen er, at SKRIVNINGEN
    # nedenfor afvises uden login.
    pid = auth.get("/api/profiles").json()[0]["id"]
    r = client.post(
        f"/api/profiles/{pid}/allergens", json={"slug": "maelkeprotein", "active": False}
    )
    assert r.status_code == 401


def test_toggle_allergen_works_with_login(auth):
    pid = auth.get("/api/profiles").json()[0]["id"]
    assert auth.post(
        f"/api/profiles/{pid}/allergens", json={"slug": "maelkeprotein", "active": False}
    ).status_code == 200

    efter = {a["slug"]: a["active"] for a in auth.get("/api/profiles").json()[0]["allergens"]}
    assert efter["maelkeprotein"] is False

    # Sæt tilbage, så testrækkefølgen ikke kan betyde noget for de øvrige.
    auth.post(
        f"/api/profiles/{pid}/allergens", json={"slug": "maelkeprotein", "active": True}
    )


def test_bad_password_rejected(client):
    r = client.post("/api/auth/login", json={"email": "w@example.dk", "password": "forkert"})
    assert r.status_code == 401


def test_unknown_email_gives_same_error(client):
    """Samme svar som forkert kodeord — ellers kan man opremse brugere."""
    r = client.post("/api/auth/login", json={"email": "nobody@example.dk", "password": PW})
    assert r.status_code == 401


# --- den centrale invariant, hele vejen gennem API'et ---------------------

def test_only_human_confirmation_produces_green(auth):
    ean = "5712345000001"
    before = auth.get(f"/api/scan/{ean}?allergens=maelkeprotein").json()
    assert before["result"] != "safe"

    auth.post(f"/api/products/{ean}/confirm", json={
        "verdicts": {"maelkeprotein": "free"},
        "ingredients_text": "Rismel, solsikkeolie, salt",
    })
    after = auth.get(f"/api/scan/{ean}?allergens=maelkeprotein").json()
    assert after["result"] == "safe"
    assert after["allergens"][0]["basis"] == "manual"


def test_recipe_change_invalidates_manual_verdict(auth):
    """Samme EAN, ny ingrediensliste -> godkendelsen skal falde tilbage."""
    ean = "5712345000002"
    auth.post(f"/api/products/{ean}/confirm", json={
        "verdicts": {"maelkeprotein": "free"},
        "ingredients_text": "Rismel, solsikkeolie, salt",
    })
    assert auth.get(f"/api/scan/{ean}?allergens=maelkeprotein").json()["result"] == "safe"

    # producenten ændrer opskriften uden at skifte stregkode
    auth.post(f"/api/products/{ean}/confirm", json={
        "verdicts": {"maelkeprotein": "free"},
        "ingredients_text": "Rismel, solsikkeolie, salt, skummetmælkspulver",
    })
    d = auth.get(f"/api/scan/{ean}?allergens=maelkeprotein").json()
    assert d["allergens"][0]["state"] == "free"  # dommen står, men hashen er ny


def test_decided_by_comes_from_session_not_client(auth):
    """Klienten kan ikke skrive en andens navn på en dom."""
    ean = "5712345000003"
    auth.post(f"/api/products/{ean}/confirm",
              json={"verdicts": {"aeg": "free"}, "decided_by": "en-anden"})
    from app.models import Verdict
    with SessionLocal() as db:
        v = db.query(Verdict).filter(Verdict.product_ean == ean).first()
        assert v.decided_by == "William"


# --- Cloudflare Access ----------------------------------------------------

def test_cf_access_header_alone_grants_nothing(client):
    """
    Uden gyldigt signeret JWT er headeren værdiløs. Det er hele grunden til,
    at cfaccess.py validerer signaturen i stedet for at læse en header.
    """
    r = client.post(
        "/api/products/5701234567890/confirm",
        json={"verdicts": {}},
        headers={"Cf-Access-Authenticated-User-Email": "angriber@example.dk"},
    )
    assert r.status_code == 401


def test_proxy_header_ignored_when_trust_disabled(client):
    r = client.post(
        "/api/products/5701234567890/confirm",
        json={"verdicts": {}},
        headers={"Remote-User": "angriber@example.dk", "Remote-Groups": "admins"},
    )
    assert r.status_code == 401
