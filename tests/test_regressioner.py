"""
Regressioner fundet ved gennemgangen 21. august 2026.

Hver test her svarer til en fejl, der var i drift — ikke til en teoretisk
mulighed. Kommentaren over hver siger, hvad familien oplevede.
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
os.environ.setdefault("OFF_BASE_URL", "http://127.0.0.1:9")   # ingen OFF i testen

import pytest
from fastapi.testclient import TestClient

from app.auth import hash_password, verify_password
from app.db import SessionLocal, default_household, init_db
from app.main import app
from sqlalchemy import select

from app.models import Product, ReviewItem, User, Verdict

PW = "korrekt-hest-batteri-haefteklamme"
EANS = ["5700000000017", "5700000000024"]


@pytest.fixture(scope="module")
def auth():
    init_db()
    with SessionLocal() as db:
        # Filtrér på MAILEN, ikke på antal: modulerne deler én database,
        # og et blankt count() betyder, at modulets egen bruger aldrig
        # bliver oprettet, hvis et andet modul kørte først.
        if not db.query(User).filter(User.email == "w@example.dk").count():
            db.add(User(household_id=default_household(db).id, email="w@example.dk",
                        name="William", password_hash=hash_password(PW), role="admin"))
        db.add(Product(ean="5700000000017", name="Rugbrød", ingredients_text=None, source="off"))
        db.commit()
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": "w@example.dk", "password": PW}).status_code == 200
    yield c
    # Ryd op efter os. Testmodulerne deler én database (DATA_DIR sættes af
    # det modul, der importeres først), og test_soeg tæller facetter over
    # ALLE varer — lader vi vores to rækker blive stående, fejler den.
    with SessionLocal() as db:
        for ean in EANS:
            for model in (Verdict, ReviewItem):
                for row in db.scalars(select(model).where(model.product_ean == ean)):
                    db.delete(row)
            p = db.get(Product, ean)
            if p is not None:
                db.delete(p)
        db.commit()


# --- køen må ikke gøre en bekræftet vare uskannbar ----------------------
# Var i drift: unique-constrainten er (husstand, EAN) uanset status, men
# _queue() ledte kun efter "pending". Efter en bekræftelse gav næste
# scanning 500 — netop på de varer, familien havde gjort arbejdet på.

def test_bekraeftet_vare_kan_scannes_igen(auth):
    A = "maelkeprotein,aeg"
    assert auth.get(f"/api/scan/5700000000017?allergens={A}").status_code == 200
    assert auth.post("/api/products/5700000000017/confirm",
                     json={"verdicts": {"maelkeprotein": "free"}}).status_code == 200
    # Den her gav 500 før rettelsen.
    r = auth.get(f"/api/scan/5700000000017?allergens={A}")
    assert r.status_code == 200, "en bekræftet vare blev uskannbar"
    with SessionLocal() as db:
        rows = db.query(ReviewItem).filter(ReviewItem.product_ean == "5700000000017").all()
    assert len(rows) == 1, "køen fik en dublet i stedet for at genåbne"


# --- en tom OFF-værdi må ikke slette et menneskes arbejde ---------------
# Var i drift: _ensure_product skrev res["ingredients_text"] ubetinget, og
# OFF kender ~10 % af varerne med liste. Den tastede deklaration forsvandt
# ved næste genhentning, og arbejdet skulle gøres om.

def test_off_uden_tekst_overskriver_ikke_tastet_deklaration(auth, monkeypatch):
    """
    Bemærk `found=True`: OFF SKAL kende varen, ellers returnerer
    `_ensure_product` på `if not res.get("found")` og når aldrig de
    linjer, rettelsen ændrede. Med found=False bestod testen også på den
    gamle kode — altså uden at teste noget som helst.

    "Fundet, men uden ingrediensliste" er netop normaltilfældet: OFF
    kender kun ~10 % af familiens varer med liste.
    """
    import asyncio

    import app.main as m
    from app.off import Lookup

    ean = "5700000000024"
    with SessionLocal() as db:
        db.add(Product(ean=ean, name="Hjemmetastet", source="manual",
                       ingredients_text="Hvedemel, vand, gær, salt."))
        db.commit()

    async def tom_men_fundet(e, timeout=8.0):
        return Lookup(found=True, error=None, name=None, brand=None, quantity=None,
                      image_url=None, ingredients_text=None, ingredients_lang=None,
                      off_allergen_tags=[], off_trace_tags=[])

    monkeypatch.setattr(m.off, "fetch_product", tom_men_fundet)

    async def hent():
        with SessionLocal() as db:
            await m._ensure_product(db, ean, refresh=True)
            db.commit()
            return db.get(Product, ean)

    p = asyncio.run(hent())
    assert p.ingredients_text == "Hvedemel, vand, gær, salt.", "tastet deklaration blev slettet"
    assert p.name == "Hjemmetastet", "et tomt navn fra OFF overskrev vores"
    # source hører til hele rækken (ODbL-tællingen i attribution()).
    assert p.source == "off"


# --- et manuelt navn må ikke forsvinde, når OFF lærer varen at kende ----
# Var i drift: curator skrev "Skyr med jordbær" på en EAN, OFF ikke
# kendte, via POST /api/products/{ean}/navn. `_ensure_product()` skrev
# `p.name = res["name"] or p.name` — og fordi OFF's felt OG familiens
# navn lå i samme kolonne, overskrev OFF's gæt familiens navn den dag
# varen blev fundet, uden nogen vej tilbage (openConfirm() viser kun et
# navnefelt, når navnet ER tomt).

def test_manuelt_navn_overlever_genhentning_fra_off(monkeypatch):
    """
    `product.navn_manuelt` er en EGEN kolonne (se app/models.py),
    `_ensure_product()` rører den aldrig, og `_visningsnavn()` lader den
    vinde over `product.name` (OFF's eget, ODbL-afledte felt).
    """
    import asyncio

    import app.main as m
    from app.off import Lookup

    ean = "5700000000031"
    with SessionLocal() as db:
        db.add(Product(ean=ean, source="manual", navn_manuelt="Skyr med jordbær"))
        db.commit()

    async def fundet_med_navn(e, timeout=8.0):
        return Lookup(found=True, error=None, name="OFF's eget gæt", brand="Et mærke",
                      quantity=None, image_url=None, ingredients_text=None,
                      ingredients_lang=None, off_allergen_tags=[], off_trace_tags=[])

    monkeypatch.setattr(m.off, "fetch_product", fundet_med_navn)

    async def hent():
        with SessionLocal() as db:
            await m._ensure_product(db, ean, refresh=True)
            db.commit()
            return db.get(Product, ean)

    try:
        p = asyncio.run(hent())
        assert p.name == "OFF's eget gæt", "OFF's navn skal stadig gemmes i sit eget felt"
        assert p.navn_manuelt == "Skyr med jordbær", "OFF overskrev familiens eget navn"
        assert m._visningsnavn(p) == "Skyr med jordbær", (
            "visningen skal vise familiens navn, ikke OFF's gæt"
        )
    finally:
        with SessionLocal() as db:
            p = db.get(Product, ean)
            if p is not None:
                db.delete(p)
            db.commit()


# --- proxy-tilliden skal fejle LUKKET -----------------------------------
# Var i drift: `if TRUSTED_PROXY_HOSTS and peer not in ...` sprang
# kontrollen over ved tom liste, så en header alene gav skriveadgang.

def test_tom_proxy_liste_giver_ikke_adgang(monkeypatch):
    import app.auth as a
    monkeypatch.setattr(a, "TRUST_PROXY_AUTH", True)
    monkeypatch.setattr(a, "TRUSTED_PROXY_HOSTS", set())
    c = TestClient(app)
    r = c.post("/api/products/5700000000017/confirm",
               json={"verdicts": {"maelkeprotein": "free"}},
               headers={"Remote-User": "angriber@example.dk", "Remote-Groups": "admins"})
    assert r.status_code == 401, "en header alene gav skriveadgang"


# --- en beskadiget hash skal give 401, ikke 500 -------------------------

def test_ugyldig_hash_giver_falsk_ikke_undtagelse():
    assert verify_password("ikke-en-argon2-hash", "hvadsomhelst") is False
