"""
Den udloggede dagplejer skal få det SAMME svar som familien.

Vedligeholderens beslutning, 3. september 2026 (docs/plan-hvad-kan-jeg-
koebe.md): dagplejeren kan både være logget ind og ikke logget ind, og
svaret skal være det samme — med den ene undtagelse, at den udloggede
selv skal kende allergenerne og indtaste dem.

Fejlen, der gjorde det usandt, sad i frontend: en frisk telefon uden
login blev TAVST sat til alle 17 allergener. Og fordi en samlet dom
kræver, at ALLE vurderede allergener er manuelt bekræftet frie
(`aggregate()`), blev et rugbrød, familien selv havde godkendt for
mælkeprotein og æg, ikke bare gråt for hende — det blev RØDT, fordi
motoren finder gluten i rugmel.

Suiten var blind for det: `tests/test_soeg.py` sender altid `allergens`
eksplicit og ser derfor aldrig alle-17-stien. Testene herunder holder
begge stier oppe mod hinanden, på BEGGE indgange til domslogikken —
`/api/scan/{ean}` og `/api/soeg`, som deler `_verdict_rows()`.

Og den ene ting, der ikke må vippe den anden vej: et tomt allergensæt må
ALDRIG komme til at betyde "tjek ingenting". Alle 17 over-advarer, hvilket
er den ufarlige retning; et tomt sæt ville under-advare.
"""
import os
import pathlib
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp())
os.environ.setdefault(
    "RULES_PATH",
    str(pathlib.Path(__file__).resolve().parents[1] / "data" / "allergens.yaml"),
)
os.environ.setdefault("COOKIE_SECURE", "0")
os.environ.setdefault("CHECK_PWNED_PASSWORDS", "0")

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal, default_household, init_db
from app.main import app
from app.matcher import ingredients_hash
from app.models import Allergen, Product, User, Verdict

# Rugbrødet fra planens tabel: familien har bekræftet mælkeprotein og æg
# mod den fysiske pakke. Gluten er hverken bekræftet eller relevant for
# barnet — men motoren finder det i rugmelet, og det er hele pointen.
EAN_RUGBROED = "5799990011001"
TEKST_RUGBROED = "Rugmel, vand, salt"

# En vare med mælk i listen. Den skal blive ved med at være rød, uanset
# hvor smalt sættet er — ellers er "svaret er det samme" blevet til
# "svaret er mildere".
EAN_MED_MAELK = "5799990011002"
TEKST_MED_MAELK = "Hvedemel, skummetmælkspulver, gær, salt"

# Ingen dom overhovedet. Et smalt sæt må ikke kunne gøre den grøn.
EAN_UDEN_DOM = "5799990011003"
TEKST_UDEN_DOM = "Vand, sukker, citronsyre"

FAMILIENS_SAET = "maelkeprotein,aeg"


@pytest.fixture(scope="module")
def client():
    init_db()
    with SessionLocal() as db:
        hh = default_household(db)

        def vare(ean, navn, tekst):
            if db.get(Product, ean) is None:
                db.add(Product(ean=ean, name=navn, brand="Testbageren",
                               ingredients_text=tekst,
                               ingredients_hash=ingredients_hash(tekst)))

        vare(EAN_RUGBROED, "Prøve-Rugbrød", TEKST_RUGBROED)
        vare(EAN_MED_MAELK, "Prøve-Franskbrød", TEKST_MED_MAELK)
        vare(EAN_UDEN_DOM, "Prøve-Saftevand", TEKST_UDEN_DOM)

        for slug in ("maelkeprotein", "aeg"):
            a = db.scalar(select(Allergen).where(Allergen.slug == slug))
            findes = db.scalar(
                select(Verdict).where(
                    Verdict.household_id == hh.id,
                    Verdict.product_ean == EAN_RUGBROED,
                    Verdict.allergen_id == a.id,
                )
            )
            if findes is None:
                db.add(Verdict(
                    household_id=hh.id, product_ean=EAN_RUGBROED, allergen_id=a.id,
                    state="free", basis="manual",
                    ingredients_hash=ingredients_hash(TEKST_RUGBROED),
                ))
        db.commit()
    return TestClient(app)


@pytest.fixture(scope="module")
def familien(client):
    """Indlogget klient — familiens egen telefon."""
    from app.auth import hash_password

    pw = "korrekt-hest-batteri-haefteklamme"
    with SessionLocal() as db:
        hh = default_household(db)
        if not db.query(User).filter(User.email == "saet@example.dk").count():
            db.add(User(household_id=hh.id, email="saet@example.dk", name="Forælder",
                        password_hash=hash_password(pw), role="admin", source="local"))
            db.commit()
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": "saet@example.dk", "password": pw})
    assert r.status_code == 200, r.text
    return c


def _rk(svar: dict) -> list[tuple]:
    """Dommen, række for række — det, de to identiteter skal være enige om."""
    return [(a["slug"], a["state"], a["basis"]) for a in svar["allergens"]]


def _fra_listen(svar: dict, ean: str) -> dict:
    return next(v for v in svar["varer"] if v.get("ean") == ean)


# --- fejlen, trin 0 retter ------------------------------------------------

def test_alle_17_gjorde_familiens_eget_rugbroed_roedt(client):
    """
    Dette ER fejlen, og den står her, fordi den er let at genindføre:
    fjerner nogen vagten i frontend og lader appen gætte igen, er det
    dette svar, dagplejeren får.

    `allergens` udeladt = alle 17, præcis som en frisk telefon sendte før
    0.23.1. Varen er ikke bare grå — den er rød på gluten i rugmelet.
    """
    d = client.get(f"/api/scan/{EAN_RUGBROED}").json()
    assert d["result"] == "unsafe"
    roede = [a["slug"] for a in d["allergens"] if a["state"] == "contains"]
    assert "gluten" in roede
    # og mælkeprotein/æg står stadig som bekræftet frie — det er ikke dem,
    # der vælter dommen. Det er de allergener, ingen har spurgt om.
    assert ("maelkeprotein", "free", "manual") in _rk(d)


def test_udlogget_med_familiens_saet_faar_praecis_samme_dom_som_familien(client, familien):
    """
    Akseptkriteriet, ordret: har hun valgt de samme allergener som
    familiens delte sæt, er dommen bit-for-bit den samme.
    """
    anonym = client.get(f"/api/scan/{EAN_RUGBROED}", params={"allergens": FAMILIENS_SAET}).json()
    indlogget = familien.get(f"/api/scan/{EAN_RUGBROED}", params={"allergens": FAMILIENS_SAET}).json()

    assert _rk(anonym) == _rk(indlogget)
    assert anonym["result"] == indlogget["result"] == "safe"
    # Grøn kommer fra bekræftelsesruten, ikke fra motoren — begge rækker
    # er MANUAL, og det er den eneste vej til "safe".
    assert all(basis == "manual" for _, _, basis in _rk(anonym))


def test_samme_paa_den_anden_indgang_listen(client, familien):
    """
    `/api/soeg` deler `_verdict_rows()` med scan-skærmen, og fejlen ramte
    begge. Facetten »Sikre« talte 0 for den udloggede.
    """
    p = {"q": "prøve-rugbrød", "allergens": FAMILIENS_SAET}
    anonym = client.get("/api/soeg", params=p).json()
    indlogget = familien.get("/api/soeg", params=p).json()

    assert _fra_listen(anonym, EAN_RUGBROED) == _fra_listen(indlogget, EAN_RUGBROED)
    assert _fra_listen(anonym, EAN_RUGBROED)["status"] == "safe"
    assert anonym["facetter"]["status"]["safe"] >= 1

    # og med alle 17 (det gamle tavse gæt) er den samme vare rød
    alle17 = client.get("/api/soeg", params={"q": "prøve-rugbrød"}).json()
    assert _fra_listen(alle17, EAN_RUGBROED)["status"] == "unsafe"


# --- et tomt sæt må aldrig betyde "tjek ingenting" ------------------------

@pytest.mark.parametrize("saet", ["", "   ", ",", " , ", "findes-ikke", "gluten-agtigt"],
                         ids=["tom", "mellemrum", "komma", "komma-mellemrum",
                              "ukendt", "naesten"])
@pytest.mark.parametrize("indgang", ["scan", "soeg"])
def test_tomt_allergensaet_afvises_paa_BEGGE_indgange(client, indgang, saet):
    """
    Den farlige retning. Serveren skal blive ved med at afvise, også hvis
    nogen en dag fjerner vagten i frontend — og den skal gøre det, FØR
    den slår varen op, så et tomt sæt hverken koster et OFF-kald eller
    ligner et svar.
    """
    sti = f"/api/scan/{EAN_RUGBROED}" if indgang == "scan" else "/api/soeg"
    r = client.get(sti, params={"allergens": saet})
    assert r.status_code == 400, r.text
    assert "allergener" in r.json()["detail"]


def test_et_smalt_saet_goer_ikke_en_roed_vare_mildere(client):
    """
    "Samme svar som familien" må ikke smitte af på selve dommen. Står
    mælk i listen, er varen rød — også når sættet kun er de to
    allergener, dagplejeren har tastet ind.
    """
    d = client.get(f"/api/scan/{EAN_MED_MAELK}", params={"allergens": FAMILIENS_SAET}).json()
    assert d["result"] == "unsafe"
    assert ("maelkeprotein", "contains", "text_match") in _rk(d)


def test_et_smalt_saet_kan_ikke_goere_motoren_groen(client):
    """
    Invarianten, set fra denne side: en vare uden en eneste manuel dom
    bliver ikke sikker, hvor smalt sættet end er. Fandt motoren
    ingenting, er svaret UNKNOWN — ikke "fri".
    """
    for saet in ("maelkeprotein", FAMILIENS_SAET, "jordbaer"):
        d = client.get(f"/api/scan/{EAN_UDEN_DOM}", params={"allergens": saet}).json()
        assert d["result"] == "unverified", saet
        assert all(state == "unknown" for _, state, _ in _rk(d)), saet
