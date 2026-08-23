"""
Kontrakten for den offentlige flade.

AllergiScan er et ÅBENT opslagsværk: alle må scanne en vare og se, hvad
familien har bekræftet. Men hvem barnet er, og hvad det reagerer på, er
ikke en del af det opslagsværk — det er helbredsoplysninger om et
navngivet, mindreårigt menneske.

Filen her er den eneste sted, den grænse står skrevet som kode. Flytter
nogen en rute fra den ene liste til den anden, skal det være med vilje.
"""
import io
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
from PIL import Image
from sqlalchemy import select

from app.auth import hash_password
from app.db import RULES, SessionLocal, default_household, init_db
from app.main import app
from app.models import Household, Product, Profile, User

PW = "korrekt-hest-batteri-haefteklamme"
EAN = "5700000000048"


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (180, 40, 60)).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def opsat():
    init_db()
    with SessionLocal() as db:
        # Filtrér på MAILEN, ikke på antal: modulerne deler én database.
        if not db.query(User).filter(User.email == "flade@example.dk").count():
            db.add(User(household_id=default_household(db).id, email="flade@example.dk",
                        name="Flade", password_hash=hash_password(PW), role="curator"))
        # En inviteret bidragyder — bedsteforælder eller dagplejer. Rollen
        # er hele pointen med filen her: hun må fotografere, ikke bekræfte.
        if not db.query(User).filter(User.email == "mormor@example.dk").count():
            db.add(User(household_id=default_household(db).id, email="mormor@example.dk",
                        name="Mormor", password_hash=hash_password(PW), role="contributor"))
        if not db.query(User).filter(User.email == "admin-flade@example.dk").count():
            db.add(User(household_id=default_household(db).id, email="admin-flade@example.dk",
                        name="Admin", password_hash=hash_password(PW), role="admin"))
        if db.get(Product, EAN) is None:
            db.add(Product(ean=EAN, name="Testvare", source="off",
                           ingredients_text="Hvedemel, vand, salt."))
        db.commit()
    yield
    with SessionLocal() as db:
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


def _som_bidragyder():
    c = TestClient(app)
    assert c.post("/api/auth/login",
                  json={"email": "mormor@example.dk", "password": PW}).status_code == 200
    return c


def _som_admin():
    c = TestClient(app)
    assert c.post("/api/auth/login",
                  json={"email": "admin-flade@example.dk", "password": PW}).status_code == 200
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
    tilbage på barnets gemte profil. En anonym kalder fik dermed præcis
    de fire allergener, barnet reagerer på — på den ene rute, hele appen
    handler om. (Profilen har ikke længere et navn at lække, se
    Profile.name i app/models.py — men den må stadig ikke stå der.)

    Testen sender med vilje INGEN allergens-parameter. Den gamle udgave
    gjorde, og det var netop dét, der skjulte lækket.
    """
    d = _anonym().get(f"/api/scan/{EAN}").json()
    assert d.get("profile") is None, "profilen ligger på en offentlig rute"
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
        assert d.get("profile") and d["profile"].get("id"), "familien mistede profilen"
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

FAMILIENS_EGNE_RUTER = [
    ("/api/queue", "hvilke stregkoder familien har scannet, og hvornår"),
    ("/api/diagnostik", "serversti, antal brugere, rå fejltekst fra OFF"),
]


@pytest.mark.parametrize("sti,hvorfor", FAMILIENS_EGNE_RUTER)
def test_familiens_egne_ting_kraever_login(opsat, sti, hvorfor):
    assert _anonym().get(sti).status_code == 401, f"{sti} udstiller {hvorfor}"
    assert _indlogget().get(sti).status_code == 200, f"{sti} virker ikke for familien"


@pytest.mark.parametrize("sti,hvorfor", FAMILIENS_EGNE_RUTER)
def test_en_bidragyder_ser_ikke_familiens_egne_ting(opsat, sti, hvorfor):
    """
    De to blev lukket med require_user i 0.19.0, dengang de eneste
    indloggede var de to voksne. Med inviterede bidragydere (rollen
    `contributor`) skal de kræve require_curator — ellers kunne en
    inviteret fotograf hente familiens scan-historik eller serverdetaljer.

    `/api/profiles` står bevidst IKKE i denne liste — se
    test_allergensaettet_er_familiens_delte_indstilling: uden et navn på
    profilen (se Profile.name) er der intet at skjule for en bidragyder,
    og hun SKAL kunne hente det samme allergensæt som familien, ellers
    kan hun komme til at tjekke for det forkerte.
    """
    assert _som_bidragyder().get(sti).status_code in (401, 403), (
        f"{sti} er tilgængelig for en bidragyder, som ikke er familien: {hvorfor}"
    )


def test_allergensaettet_er_familiens_delte_indstilling(opsat):
    """
    `/api/profiles` er fortsat `require_user`, uændret — nettoændringen
    er, at `name` er fjernet fra svaret (se Profile.name i app/models.py).
    Uden et navn er der ikke noget tilbage at skjule for en bidragyder —
    og hun SKAL have adgang til det samme allergensæt som familien:
    fejlklassen, `ux-gennemgang` fandt (en hjælper der glemmer at slå de
    rigtige fire allergener til, og appen tjekker for det forkerte uden
    at nogen opdager det), fjernes netop ved at hun ikke vælger selv.
    """
    r = _anonym().get("/api/profiles")
    assert r.status_code == 401
    # require_user's besked skal være neutral — den bruges også af
    # /api/ocr og foto-uploaden, og "log ind for at gemme billeder"
    # ville være en underlig ting at læse, når man bad om allergener.
    assert "billeder" not in r.json()["detail"].lower()

    for klient in (_indlogget(), _som_bidragyder(), _som_admin()):
        r = klient.get("/api/profiles")
        assert r.status_code == 200, "en logget ind bruger må kunne hente sættet"
        felter = set(r.json()[0])
        assert felter == {"id", "allergens"}, (
            f"uventede felter i /api/profiles: {felter - {'id', 'allergens'}}"
        )


ADMIN_EGNE_RUTER = [
    ("/api/auth/users", "hvem der er inviteret, og med hvilken rolle"),
]


@pytest.mark.parametrize("sti,hvorfor", ADMIN_EGNE_RUTER)
def test_admin_ting_kraever_admin(opsat, sti, hvorfor):
    assert _anonym().get(sti).status_code == 401, f"{sti} udstiller {hvorfor}"
    assert _indlogget().get(sti).status_code in (401, 403), (
        f"{sti} er tilgængelig for en almindelig familiebruger (curator): {hvorfor}"
    )
    assert _som_bidragyder().get(sti).status_code in (401, 403), (
        f"{sti} er tilgængelig for en bidragyder: {hvorfor}"
    )
    assert _som_admin().get(sti).status_code == 200, f"{sti} virker ikke for admin"


def test_brugerlisten_laekker_ikke_adgangskodehash(opsat):
    """
    Listen findes for at gøre en invitation til en beslutning man kan se
    — den må aldrig blive en vej til at læse en hash eller husstands-id.
    """
    r = _som_admin().get("/api/auth/users")
    assert r.status_code == 200
    assert "password_hash" not in r.text
    assert "household_id" not in r.text
    assert "source" not in r.text
    felter = {k for u in r.json() for k in u}
    assert felter == {"id", "email", "name", "role", "active", "last_login"}


# --- en bidragyder må fotografere og køre OCR, ikke bekræfte -------------

def test_bidragyder_kan_uploade_foto_og_koere_ocr(opsat):
    """
    Kernen i »inviterede bidragydere«: en navngiven, inviteret person må
    dokumentere en vare med et foto og se, om det var læsbart — men kan
    ikke gøre den grøn. Se test_bidragyder_kan_ikke_bekraefte_eller_slette.
    """
    c = _som_bidragyder()
    r = c.post(f"/api/products/{EAN}/foto?slags=deklaration",
               files={"image": ("d.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200, r.text

    r = c.post("/api/ocr", files={"image": ("d.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200, r.text


def test_taget_af_er_kun_for_familien_ikke_for_bidragyderen(opsat):
    """
    `taget_af` er en VOKSENS navn og skal kun ekko'es tilbage til dem,
    der rent faktisk bekræfter en vare og har brug for at vide, hvis
    billede de kigger på — curator/admin. "Indlogget" dækker siden
    0.20.0 også en bidragyder, og hun har intet brug for at se sit eget
    navn i svaret.
    """
    c = _som_bidragyder()
    r = c.post(f"/api/products/{EAN}/foto?slags=deklaration",
               files={"image": ("d.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200, r.text

    som_bidragyder = c.get(f"/api/scan/{EAN}?allergens=maelkeprotein").json()
    assert "taget_af" not in som_bidragyder["fotos"]["deklaration"]

    som_familie = _indlogget().get(f"/api/scan/{EAN}?allergens=maelkeprotein").json()
    assert som_familie["fotos"]["deklaration"].get("taget_af") == "Mormor"


def test_anonym_kan_ikke_uploade_foto_eller_koere_ocr(opsat):
    assert _anonym().post(
        f"/api/products/{EAN}/foto?slags=deklaration",
        files={"image": ("d.jpg", _jpeg(), "image/jpeg")},
    ).status_code == 401
    assert _anonym().post(
        "/api/ocr", files={"image": ("d.jpg", _jpeg(), "image/jpeg")}
    ).status_code == 401


def test_bidragyder_kan_ikke_bekraefte_eller_slette(opsat):
    """
    `State.FREE` sættes ét sted i hele appen: `confirm`, bag
    `require_curator`. En inviteret bidragyder er ikke familien og må
    hverken gøre en vare grøn eller slette familiens dokumentation.

    Statuskoden er PRÆCIS 403, ikke bare "401 eller 403": en bidragyder
    ER logget ind, så `require_curator` afviser på ROLLEN, ikke på
    fraværet af en session. `saveConfirm()` i frontend skelner nu netop
    på det tal for at vise den rigtige besked — se
    test_saveconfirm_skelner_401_fra_403.
    """
    c = _som_bidragyder()
    r = c.post(f"/api/products/{EAN}/confirm",
               json={"verdicts": {"maelkeprotein": "free"}})
    assert r.status_code == 403, "en bidragyder kunne bekræfte en vare"
    # "Din konto må kun læse" var usandt for en bidragyder — hun må
    # skrive fotos. Beskeden skal navngive det, hun rent faktisk mangler.
    assert "må kun læse" not in r.json()["detail"]
    assert "familien" in r.json()["detail"].lower()

    r = c.delete(f"/api/products/{EAN}/foto/deklaration")
    assert r.status_code == 403, "en bidragyder kunne slette et foto"


def test_bidragyder_kan_ikke_aendre_allergensaettet_paa_serveren(opsat):
    """
    Det tunge modstykke til test_bidragyder_kan_ikke_aendre_familiens_allergensaet:
    en bidragyder må SE familiens allergensæt (`GET /api/profiles`), men
    `POST /api/profiles/{id}/allergens` er stadig `require_curator` — hun
    kan ikke ændre, hvad familien tjekker for, på deres vegne.
    """
    profil_id = _indlogget().get("/api/profiles").json()[0]["id"]
    r = _som_bidragyder().post(
        f"/api/profiles/{profil_id}/allergens",
        json={"slug": "maelkeprotein", "active": False},
    )
    assert r.status_code == 403, "en bidragyder kunne ændre familiens allergensæt"


def test_toggle_allergen_tjekker_husstanden(opsat):
    """
    `profile_id` kommer fra klienten. Uden et husstandstjek kunne enhver
    logget ind familiebruger sende et profile_id, der hører til en ANDEN
    husstand, og ændre DERES allergensæt — eller ramme et rent
    opdigtet id og få en 500 i stedet for en pæn 404.
    """
    with SessionLocal() as db:
        anden = Household(name="En anden husstand", token="x" * 24)
        db.add(anden)
        db.flush()
        fremmed = Profile(household_id=anden.id, name="")
        db.add(fremmed)
        db.commit()
        fremmed_id = fremmed.id

    r = _indlogget().post(
        f"/api/profiles/{fremmed_id}/allergens",
        json={"slug": "maelkeprotein", "active": False},
    )
    assert r.status_code == 404, "en profil fra en ANDEN husstand kunne ændres"

    r2 = _indlogget().post(
        "/api/profiles/999999/allergens",
        json={"slug": "maelkeprotein", "active": False},
    )
    assert r2.status_code == 404, "et opdigtet profile_id gav ikke en pæn 404"


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

def test_scan_tabellen_er_fjernet_helt(opsat):
    """
    Fødevaredagbogen (hvad blev slået op, hvornår, for hvilken profil) er
    FJERNET i 0.20.0, ikke migreret — se _drop_scan_tabellen() i
    app/db.py. Familien scanner ikke alt, barnet spiser, så en delvis log
    over opslag ville ikke bare være svag som efterforskningsværktøj —
    den ville VILDLEDE: man kigger i den efter en reaktion, ser
    ingenting, og konkluderer forkert, at synderen ikke var der. Den var
    også den mest følsomme rest af persondata i basen.

    Erstatter test_anonymt_opslag_skriver_ikke_i_dagbogen og
    test_familiens_eget_opslag_foerer_dagbogen, som begge testede en
    tabel, der ikke findes mere.
    """
    from sqlalchemy import inspect as sql_inspect

    from app.db import engine

    assert "scan" not in sql_inspect(engine).get_table_names(), (
        "scan-tabellen findes stadig efter init_db() — se _drop_scan_tabellen()"
    )

    # Et opslag — anonymt eller familiens eget — må virke normalt. Der er
    # ingen tabel at skrive en historik til, men testen fanger det, hvis
    # nogen en dag genindfører den ved et uheld.
    assert _anonym().get(f"/api/scan/{EAN}?allergens=maelkeprotein").status_code == 200
    assert _indlogget().get(f"/api/scan/{EAN}?allergens=maelkeprotein").status_code == 200
    assert "scan" not in sql_inspect(engine).get_table_names()


def test_profile_id_i_url_bliver_ignoreret(opsat):
    """
    Var i drift: profile_id kom fra query-strengen og blev slået op uden
    at tjekke husstanden, så en fremmed kunne vælge, hvilket barn linjen
    i fødevaredagbogen blev skrevet på. Beviset lå i den dagbog, som er
    fjernet i 0.20.0 (se test_scan_tabellen_er_fjernet_helt) — men
    `scan()` i app/main.py har aldrig taget imod parameteren (den står
    ikke i funktionens signatur), så et ukendt profile_id kan hverken
    vælte opslaget eller smitte af på personaliseringen.
    """
    med = _indlogget().get(f"/api/scan/{EAN}?profile_id=999999")
    uden = _indlogget().get(f"/api/scan/{EAN}")
    assert med.status_code == 200, "et ukendt profile_id må ikke vælte opslaget"
    assert med.json()["allergens"] == uden.json()["allergens"], (
        "et ukendt profile_id i URL'en ændrede den personaliserede visning"
    )


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
    # Fundet ved gennemgang: et kode-eksempel i en kommentar brugte
    # navnene i løbende tekst ("...fri for mælk, æg, jordbær og banan"),
    # som tilfældigvis ER familiens rigtige sæt (se CLAUDE.md). Tjekket
    # ovenfor fanger kun slugs i anførselstegn, ikke navne i en sætning.
    assert "mælk, æg, jordbær og banan" not in html, (
        "familiens fire allergener står som eksempel i klartekst et sted"
    )


# --- blokeren fundet af ux-gennemgang: en bidragyder må ikke kunne -------
# gennemføre bekræftelsesritualet -----------------------------------------
#
# `openConfirm()` vogtede kun på `!USER`, og en bidragyder ER logget ind.
# Kæden var: "Fotografér deklaration" -> ocrGuard() lukker igennem
# (korrekt, /api/ocr er require_user) -> openConfirm() åbner panelet ->
# alle chips kan trykkes grønne -> "Gem dom" -> serveren svarer 403, som
# saveConfirm() dengang behandlede som 401 og viste "Din session er
# udløbet" — usandt, og hun fik aldrig at vide, om varen blev gemt.
#
# Der findes ingen JS-testkører i repoet (frontend er én fil uden
# byggetrin, se CLAUDE.md), så testene herunder er en statisk kontrol af
# den samme art som test_forsiden_indeholder_ikke_barnets_allergener: de
# beviser IKKE, at browseren rent faktisk lader panelet være lukket — de
# beviser, at KILDEN stadig har vagten, i den rækkefølge der gør den
# virksom. Det tunge, faktiske bevis er backend-testen nedenfor: uden
# require_curator på confirm er JS-vagten kosmetik.

def _funktionskrop(html: str, start_markoer: str, slut_markoer: str) -> str:
    start = html.index(start_markoer) + len(start_markoer)
    slut = html.index(slut_markoer, start)
    return html[start:slut]


def test_bidragyder_kan_ikke_faa_bekraeftelsespanelet_til_at_aabne():
    html = _anonym().get("/").text

    krop = _funktionskrop(html, "function openConfirm(){", "\nconst CHIP_TEKST")
    vagt = krop.find("KAN_BEKRAEFTE")
    aabner = krop.find("$('#confirmPanel').hidden = false")
    assert vagt != -1, "openConfirm() tjekker ikke længere KAN_BEKRAEFTE"
    assert aabner != -1, "openConfirm() åbner ikke længere #confirmPanel her"
    assert vagt < aabner, (
        "KAN_BEKRAEFTE-vagten står EFTER panelet åbnes — en bidragyder "
        "(logget ind, men uden lov til at bekræfte) kan nå at se panelet"
    )

    # Automatikken efter et OCR-foto må heller ikke omgå vagten ved selv
    # at kalde openConfirm() ubetinget.
    handler = _funktionskrop(
        html,
        "$('#ocrFile').onchange = $('#ocrPick').onchange = async e => {",
        "\n};",
    )
    assert "KAN_BEKRAEFTE" in handler, (
        "OCR-håndteringen tjekker ikke KAN_BEKRAEFTE — en bidragyder kan "
        "få bekræftelsespanelet åbnet af automatikken efter et foto"
    )
    assert handler.find("KAN_BEKRAEFTE") < handler.find("openConfirm()"), (
        "KAN_BEKRAEFTE tjekkes EFTER openConfirm() kaldes i OCR-håndteringen"
    )


def test_saveconfirm_skelner_401_fra_403():
    """
    401 (ingen session) og 403 (logget ind, men uden lov) krævede før
    samme, forkerte besked: "Din session er udløbet." En bidragyder, der
    på en eller anden vej trykker "Gem dom", skal have at vide at intet
    blev gemt — ikke bedt om at logge ind igen på en session, der er fin.
    """
    html = _anonym().get("/").text
    krop = _funktionskrop(html, "$('#saveConfirm').onclick = async () => {", "\n};")
    assert "r.status === 401" in krop and "r.status === 403" in krop, (
        "saveConfirm() behandler ikke længere 401 og 403 hver for sig"
    )
    # Besked-teksten for 403 står mellem det tjek og resten af funktionen.
    stk_403 = krop[krop.index("r.status === 403"):]
    linje = stk_403.split("return;")[0]
    assert "udløbet" not in linje, (
        "en 403 (bidragyder uden lov) får stadig beskeden om en udløbet session"
    )
    assert "ikke bekræfte" in linje or "kan sende billeder" in linje


def test_bidragyder_kan_ikke_aendre_familiens_allergensaet():
    """
    Del B af 0.20.0: allergensættet er familiens DELTE indstilling, hentet
    fra serveren, når nogen er logget ind (se refreshAuth() og
    effektivAllergener()). En bidragyder skal kunne SE det — hun skal
    tjekke for det samme som familien — men ikke ÆNDRE det, for så ville
    hun kunne vælge forkert på familiens vegne.

    Samme forbehold som de andre statiske tests: ingen JS-testkører i
    repoet, så det her beviser kildens form, ikke browseradfærd. Det
    tunge beviser er backend-testen: `POST /api/profiles/{id}/allergens`
    kræver `require_curator`, og en bidragyder får 403 derfra.
    """
    html = _anonym().get("/").text
    krop = _funktionskrop(html, "function paintPrefChips(){", "\n\n/* ---------- auth")
    assert "skrivebeskyttet" in krop and "contributor" in krop, (
        "paintPrefChips() tjekker ikke længere rollen, før chipsene skrives"
    )
    # Chippen skal have `disabled`, og skriveadgangen (onclick, der kalder
    # /api/profiles/.../allergens) skal stå bag samme flag.
    dot = krop.find("disabled")
    fetch_kald = krop.find("/api/profiles/")
    skriv_gate = krop.find("if(!skrivebeskyttet)")
    assert dot != -1 and fetch_kald != -1 and skriv_gate != -1, (
        "chip-oprydningen eller skriveadgangen er flyttet — tjek forudsætningerne i denne test"
    )
    assert skriv_gate < fetch_kald, (
        "skrivning til serveren sker uden for if(!skrivebeskyttet)-blokken"
    )


def test_rollevaelgeren_lover_ikke_at_skjule_allergensaettet():
    """
    BLOKERER fundet af kodegennemgang: teksten, en admin træffer sin
    beslutning ud fra, sagde »ser ikke barnets profil« — men det er netop
    hvad en contributor GØR, med vilje (se
    test_bidragyder_kan_ikke_aendre_familiens_allergensaet). Rettelsen er
    i TEKSTEN, ikke ruten: rulles ruten tilbage, genindfører man
    fejlklassen, punkt B blev bygget for at fjerne.
    """
    html = _anonym().get("/").text
    assert "ser ikke barnets profil" not in html, (
        "rollevælgeren lover stadig noget, koden ikke gør"
    )
    assert "Kan se, hvilke allergener" in html or "kan se, hvilke allergener" in html, (
        "rollevælgeren siger ikke længere, at en bidragyder kan se allergensættet"
    )


def test_visslab_rydder_fotokvitteringen():
    """
    KRITISK fundet af kodegennemgang: `#fotoKvittering` stod ikke i
    visSlab()s liste over ting, der hørte til den FORRIGE vare. Mormor
    fotograferer vare A, scanner vare B — og kvitteringen til A står
    stadig under B's kort, som om den var B's.
    """
    html = _anonym().get("/").text
    krop = _funktionskrop(html, "function visSlab(r, forklaring){", "\n}")
    assert "#fotoKvittering" in krop, (
        "visSlab() rydder ikke længere #fotoKvittering — se lookup()/render()"
    )


def test_gemfoto_giver_401_videre_i_stedet_for_daarligt_signal():
    """
    KRITISK fundet af kodegennemgang: `gemFoto()` oversatte ALLE
    fejlstatusser til "prøv igen, når du har bedre signal" — inklusive
    401 (en udløbet session, SESSION_DAYS=30). En dagplejer i Netto ville
    stå og prøve igen og igen mod et problem, et nyt login løser med det
    samme.
    """
    html = _anonym().get("/").text
    krop = _funktionskrop(html, "async function gemFoto(fil, slags){", "\n}")
    assert "status:r.status" in krop.replace(" ", ""), (
        "gemFoto() giver ikke længere HTTP-statussen videre til kalderen"
    )

    for start, slut in (
        ("$('#frontFile').onchange = async e => {", "\n};"),
        ("if(!KAN_BEKRAEFTE){", "\n  }"),
    ):
        handler = _funktionskrop(html, start, slut)
        assert "svar.status === 401" in handler, (
            f"401 behandles ikke særskilt i handleren, der starter med: {start!r}"
        )
        assert "udløbet" in handler.lower() or "logget ud" in handler.lower(), (
            f"ingen menneskelig 401-besked i handleren, der starter med: {start!r}"
        )


def test_prefhint_navngiver_fravalgte_allergener():
    """
    Advarsel fra kodegennemgang: et nyt allergen i regelsættet lægges nu
    til SLUKKET på ALLE indloggede telefoner (init_db() sætter
    active=False med vilje) — hvor en tom localStorage før gav alle 17.
    Rækkevidden af det gamle valg voksede uden at nogen tog det om.
    #prefHint skal sige, hvad der er fravalgt, når sættet er mindre end
    alle allergenerne.
    """
    html = _anonym().get("/").text
    krop = _funktionskrop(html, "function paintPrefChips(){", "\n\n/* ---------- auth")
    assert "fravalgt" in krop, "paintPrefChips() navngiver ikke længere de fravalgte allergener"


def test_fotosvar_til_anonym_indeholder_ikke_et_menneskes_navn(opsat):
    """`taget_af` er en VOKSENS navn. Det er sporbarhed i databasen —
    ikke noget, en fremmed skal kunne læse ud af et scan-svar."""
    r = _anonym().get(f"/api/scan/{EAN}")
    assert "taget_af" not in r.text, "en voksens navn fulgte med i svaret"


def test_soegesvar_til_anonym_indeholder_ikke_et_menneskes_navn(opsat):
    r = _anonym().get("/api/soeg?q=test")
    assert "taget_af" not in r.text
    assert "decided_by" not in r.text
