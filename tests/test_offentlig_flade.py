"""
Kontrakten for den offentlige flade.

AllergiScan er et ÅBENT opslagsværk: alle må scanne en vare og se, hvad
familien har bekræftet. Men hvem barnet er, og hvad det reagerer på, er
ikke en del af det opslagsværk — det er helbredsoplysninger om et
navngivet, mindreårigt menneske.

Filen her er den eneste sted, den grænse står skrevet som kode. Flytter
nogen en rute fra den ene liste til den anden, skal det være med vilje.
"""
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp())
os.environ.setdefault(
    "RULES_PATH",
    str(pathlib.Path(__file__).resolve().parents[1] / "data" / "allergens.yaml"),
)
os.environ.setdefault("COOKIE_SECURE", "0")
os.environ.setdefault("CHECK_PWNED_PASSWORDS", "0")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import hash_password
from app.db import RULES, SessionLocal, default_household, init_db
from app.main import app
from app.models import Product, Profile, Scan, User

PW = "korrekt-hest-batteri-haefteklamme"
EAN = "5700000000048"


@pytest.fixture(scope="module")
def opsat():
    init_db()
    with SessionLocal() as db:
        if not db.query(User).filter(User.email == "flade@example.dk").count():
            db.add(User(household_id=default_household(db).id, email="flade@example.dk",
                        name="Flade", password_hash=hash_password(PW), role="curator"))
        if db.get(Product, EAN) is None:
            db.add(Product(ean=EAN, name="Testvare", source="off",
                           ingredients_text="Hvedemel, vand, salt."))
        db.commit()
    yield
    with SessionLocal() as db:
        for row in db.scalars(select(Scan).where(Scan.product_ean == EAN)):
            db.delete(row)
        p = db.get(Product, EAN)
        if p is not None:
            db.delete(p)
        db.commit()


def _anonym():
    return TestClient(app)


def _indlogget():
    c = TestClient(app)
    assert c.post("/api/auth/login",
                  json={"email": "flade@example.dk", "password": PW}).status_code == 200
    return c


# --- det, der SKAL være offentligt --------------------------------------
# Fjernes noget herfra, holder appen op med at være det, den er til for.

@pytest.mark.parametrize("sti", [
    "/",
    "/healthz",
    "/api/version",
    "/api/allergens",
    "/api/changelog",
    "/api/attribution",
    f"/api/scan/{EAN}?allergens=maelkeprotein",
    "/api/soeg?q=test",
    "/api/products",
    # BEVIDST offentligt: forslagene er afledt af familiens eget korpus,
    # men de er ordlisten, en fremmed skal kunne søge i.
    "/api/ingredients/suggest?q=mel",
])
def test_offentligt_uden_login(opsat, sti):
    assert _anonym().get(sti).status_code == 200, f"{sti} er ikke længere offentlig"


def test_anonymt_opslag_roeber_ikke_barnets_profil(opsat):
    """
    Fundet ved gennemgang før udgivelse: UDEN `?allergens=` faldt svaret
    tilbage på barnets gemte profil. En anonym kalder fik dermed både
    `profile.name` og præcis de fire allergener, barnet reagerer på —
    på den ene rute, hele appen handler om.

    Testen sender med vilje INGEN allergens-parameter. Den gamle udgave
    gjorde, og det var netop dét, der skjulte lækket.
    """
    d = _anonym().get(f"/api/scan/{EAN}").json()
    assert d.get("profile") is None, "barnets navn ligger på en offentlig rute"
    slugs = {a["slug"] for a in d.get("allergens", [])}
    assert slugs == set(RULES.allergens), (
        "svaret røber hvilke allergener barnet reagerer på — "
        f"{len(slugs)} af {len(RULES.allergens)} vurderet"
    )


def test_familien_faar_stadig_barnets_profil(opsat):
    """
    Modprøven: for de indloggede skal opslaget stadig være personligt —
    ellers har rettelsen ovenfor taget funktionen med sig.
    """
    from app.models import Allergen, ProfileAllergen

    # Slå ét allergen fra, så profilens valg er synligt forskelligt fra
    # "alle 17" og ikke bare tilfældigvis er det samme sæt.
    with SessionLocal() as db:
        prof = db.scalar(select(Profile).where(
            Profile.household_id == default_household(db).id))
        a = db.scalar(select(Allergen).where(Allergen.slug == "lupin"))
        pa = db.scalar(select(ProfileAllergen).where(
            ProfileAllergen.profile_id == prof.id, ProfileAllergen.allergen_id == a.id))
        pa.active = False
        db.commit()

    try:
        d = _indlogget().get(f"/api/scan/{EAN}").json()
        assert d.get("profile") and d["profile"].get("name"), "familien mistede profilen"
        slugs = {x["slug"] for x in d["allergens"]}
        assert "lupin" not in slugs, "profilens fravalg blev ignoreret"
        assert slugs != set(RULES.allergens), "der blev ikke skelnet mellem familie og fremmed"
    finally:
        # Testmodulerne deler én database — slå den tilbage til, ellers
        # fejler test_profil_allergener's "frisk profil har alt slået til".
        with SessionLocal() as db:
            prof = db.scalar(select(Profile).where(
                Profile.household_id == default_household(db).id))
            a = db.scalar(select(Allergen).where(Allergen.slug == "lupin"))
            db.scalar(select(ProfileAllergen).where(
                ProfileAllergen.profile_id == prof.id,
                ProfileAllergen.allergen_id == a.id)).active = True
            db.commit()


# --- det, der ALDRIG må være offentligt ---------------------------------

@pytest.mark.parametrize("sti,hvorfor", [
    ("/api/profiles", "barnets navn og hvilke allergener det reagerer på"),
    ("/api/queue", "hvilke stregkoder familien har scannet, og hvornår"),
    ("/api/diagnostik", "serversti, antal brugere, rå fejltekst fra OFF"),
])
def test_familiens_egne_ting_kraever_login(opsat, sti, hvorfor):
    assert _anonym().get(sti).status_code == 401, f"{sti} udstiller {hvorfor}"
    assert _indlogget().get(sti).status_code == 200, f"{sti} virker ikke for familien"


def test_fotoruten_er_bevidst_offentlig(opsat):
    """
    `GET /api/products/{ean}/foto/{slags}` er ÅBEN, og det er et valg,
    ikke en forglemmelse: fotoet af deklarationen ER dokumentationen bag
    en bekræftelse, og et opslagsværk, hvor man ikke kan se etiketten,
    er halvt.

    Prisen skal stå her, så den ikke bliver glemt: stregkoder kan
    opremses, billederne er taget i familiens køkken og i butikker, og
    `taget_af` ligger i databasen (men sendes ikke med i svaret).

    Skal den lukkes, er det ÉN linje — `_: User = Depends(require_user)`
    på `hent_foto` — og så flyttes testen her ned til listen ovenfor.
    """
    r = _anonym().get(f"/api/products/{EAN}/foto/deklaration")
    assert r.status_code in (200, 404), r.status_code
    assert "taget_af" not in r.text


@pytest.mark.parametrize("sti", ["/docs", "/redoc", "/openapi.json"])
def test_api_kortet_er_slaaet_fra(sti):
    """Et komplet kort over alle ruter — også de skrivende — er ikke offentligt."""
    assert _anonym().get(sti).status_code == 404


# --- en fremmed må læse, ikke skrive ------------------------------------

def test_anonymt_opslag_skriver_ikke_i_dagbogen(opsat):
    with SessionLocal() as db:
        foer = db.query(Scan).filter(Scan.product_ean == EAN).count()

    assert _anonym().get(f"/api/scan/{EAN}?allergens=maelkeprotein").status_code == 200

    with SessionLocal() as db:
        assert db.query(Scan).filter(Scan.product_ean == EAN).count() == foer, \
            "en fremmed skrev i barnets fødevaredagbog"


def test_familiens_eget_opslag_foerer_dagbogen(opsat):
    with SessionLocal() as db:
        foer = db.query(Scan).filter(Scan.product_ean == EAN).count()

    assert _indlogget().get(f"/api/scan/{EAN}?allergens=maelkeprotein").status_code == 200

    with SessionLocal() as db:
        assert db.query(Scan).filter(Scan.product_ean == EAN).count() == foer + 1


def test_profile_id_i_url_bliver_ignoreret(opsat):
    """
    Var i drift: profile_id kom fra query-strengen og blev slået op uden
    at tjekke husstanden, så en fremmed kunne vælge, hvilket barn linjen
    blev skrevet på.
    """
    r = _indlogget().get(f"/api/scan/{EAN}?allergens=maelkeprotein&profile_id=999999")
    assert r.status_code == 200, "et ukendt profile_id må ikke vælte opslaget"
    with SessionLocal() as db:
        senest = db.scalars(
            select(Scan).where(Scan.product_ean == EAN).order_by(Scan.id.desc())
        ).first()
        hh = default_household(db)
        assert senest.household_id == hh.id
        assert senest.profile_id != 999999


# --- brute force mod login ----------------------------------------------

def test_login_spaerrer_afsenderen_efter_faa_forsoeg(opsat):
    """Spærren skal ramme, FØR argon2 kører igen (64 MiB pr. forsøg)."""
    import app.auth as a
    a._FORSOEG.clear()
    c = TestClient(app)
    krop = {"email": "flade@example.dk", "password": "forkert-adgangskode-her"}
    h = {"CF-Connecting-IP": "203.0.113.7"}

    koder = [c.post("/api/auth/login", json=krop, headers=h).status_code for _ in range(7)]
    assert koder[0] == 401, koder
    assert 429 in koder, f"ingen spærre efter syv forsøg: {koder}"
    a._FORSOEG.clear()


def test_en_fremmed_kan_ikke_laase_familien_ude(opsat):
    """
    Den vigtigste egenskab. Spærren nøgles på afsenderens IP, ikke på
    mailen — ellers kunne enhver på internettet gætte forkert på
    familiens mailadresse og dermed spærre dem ude af deres egen app,
    mens de står i Netto.

    Bag Cloudflare Tunnel er `request.client.host` cloudflared's IP og
    dermed ENS for alle, så den rigtige afsender skal komme fra
    CF-Connecting-IP.
    """
    import app.auth as a
    a._FORSOEG.clear()

    angriber = TestClient(app)
    forkert = {"email": "flade@example.dk", "password": "forkert-adgangskode-her"}
    for _ in range(60):
        angriber.post("/api/auth/login", json=forkert,
                      headers={"CF-Connecting-IP": "198.51.100.9"})

    familien = TestClient(app)
    r = familien.post("/api/auth/login",
                      json={"email": "flade@example.dk", "password": PW},
                      headers={"CF-Connecting-IP": "192.0.2.55"})
    assert r.status_code == 200, (
        f"familien blev låst ude af en fremmed ({r.status_code}) — "
        "spærren nøgles forkert"
    )
    a._FORSOEG.clear()


def test_ukendt_afsender_deler_spand_med_hoejere_loft(opsat):
    """
    Mangler CF-Connecting-IP, falder alle kaldere sammen i cloudflared's
    IP. Den spand må ikke have det hårde loft — så ville fem vilkårlige
    forsøg låse familien ude, netop dét spærren er nøglet efter afsender
    for at undgå.
    """
    import app.auth as a
    a._FORSOEG.clear()
    c = TestClient(app)
    krop = {"email": "flade@example.dk", "password": "forkert-adgangskode-her"}

    koder = [c.post("/api/auth/login", json=krop).status_code for _ in range(a.IP_MAKS + 3)]
    assert 429 not in koder, (
        "den delte spand fik det hårde loft — familien kan låses ude af "
        f"tilfældig trafik: {koder}"
    )
    a._FORSOEG.clear()


def test_spaerren_kan_ikke_nulstilles_ved_at_fylde_den(opsat):
    """
    Var i drift i to udgaver: først blev HELE tælleren tømt ved loftet,
    derefter blev "de ældste" smidt ud — og angriberens egen spærring er
    den ældste. Begge veje kunne en angriber nulstille sin spærring med
    nogle tusinde billige requests.
    """
    import app.auth as a
    a._FORSOEG.clear()

    for _ in range(a.IP_MAKS + 1):
        a.forsoeg_fejlede("203.0.113.99")
    assert a.spaerret("203.0.113.99") > 0

    for i in range(a._LOFT + 100):
        a.forsoeg_fejlede(f"10.0.{i // 256}.{i % 256}")

    assert a.spaerret("203.0.113.99") > 0, \
        "spærringen forsvandt, da tælleren blev fyldt op"
    a._FORSOEG.clear()


def test_taelleren_holder_sit_loft_ogsaa_naar_alt_er_spaerret(opsat):
    """
    Et botnet med fem forsøg pr. IP giver lutter spærrede nøgler. Sprang
    oprydningen dem over, var loftet ikke et loft — og oprydningen blev
    selv dyrere for hvert forsøg.
    """
    import app.auth as a
    a._FORSOEG.clear()
    for i in range(a._LOFT + 500):
        noegle = f"10.1.{i // 256}.{i % 256}"
        for _ in range(a.IP_MAKS + 1):
            a.forsoeg_fejlede(noegle)
    assert len(a._FORSOEG) <= a._LOFT + 1, \
        f"tælleren voksede uden loft: {len(a._FORSOEG)} nøgler"
    a._FORSOEG.clear()


# --- de tre kanaler, en gennemgang fandt EFTER de åbenlyse ---------------
# Alle tre udstillede noget om familien uden at gå gennem en rute, nogen
# tænkte på som "en rute". De står her, fordi de er lette at genindføre.

def test_forsiden_indeholder_ikke_barnets_allergener():
    """
    `GET /` serverer index.html til enhver. Stod barnets allergensæt som
    default i JavaScriptet, var det udstillet i klartekst — uden at nogen
    behøvede en browser, endsige at køre koden.
    """
    html = _anonym().get("/").text
    for slug in ("maelkeprotein", "aeg", "jordbaer", "banan"):
        assert f"'{slug}'" not in html, (
            f"{slug} står hårdkodet i den offentlige forside"
        )


def test_fotosvar_til_anonym_indeholder_ikke_et_menneskes_navn(opsat):
    """`taget_af` er en VOKSENS navn. Det er sporbarhed i databasen —
    ikke noget, en fremmed skal kunne læse ud af et scan-svar."""
    r = _anonym().get(f"/api/scan/{EAN}")
    assert "taget_af" not in r.text, "en voksens navn fulgte med i svaret"


def test_soegesvar_til_anonym_indeholder_ikke_et_menneskes_navn(opsat):
    r = _anonym().get("/api/soeg?q=test")
    assert "taget_af" not in r.text
    assert "decided_by" not in r.text
