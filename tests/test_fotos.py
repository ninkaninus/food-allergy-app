"""
Billeder af forsiden og deklarationen.

Vigtigst: et billede er dokumentation, ikke bevis. Det må aldrig kunne
gøre en vare grøn — kun et menneske, der har læst emballagen, kan det.
"""
import io
import os
import pathlib
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

TMP = tempfile.mkdtemp()
os.environ.setdefault("DATA_DIR", TMP)
os.environ.setdefault(
    "RULES_PATH",
    str(pathlib.Path(__file__).resolve().parents[1] / "data" / "allergens.yaml"),
)
os.environ.setdefault("COOKIE_SECURE", "0")
os.environ.setdefault("CHECK_PWNED_PASSWORDS", "0")

from fastapi.testclient import TestClient
from PIL import Image

from sqlalchemy import select

from app.auth import hash_password
from app.db import SessionLocal, default_household, init_db
from app.main import _foto_svar, app
from app.models import Product, ProductPhoto, User, Verdict

PW = "korrekt-hest-batteri-haefteklamme"
EAN = "5701234500001"


def _jpeg(bredde=2400, hoejde=1800, farve=(180, 40, 60)):
    buf = io.BytesIO()
    Image.new("RGB", (bredde, hoejde), farve).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def client():
    init_db()
    with SessionLocal() as db:
        # Filtrér på MAILEN, ikke på antal: modulerne deler én database,
        # og et blankt count() betyder, at modulets egen bruger aldrig
        # bliver oprettet, hvis et andet modul kørte først.
        if not db.query(User).filter(User.email == "w@example.dk").count():
            db.add(User(household_id=default_household(db).id, email="w@example.dk",
                        name="William", password_hash=hash_password(PW),
                        role="admin", source="local"))
        # To hjælpere, ikke én — ellers beviser en "kan ikke slette den
        # andens foto"-test intet, fordi der ikke ER nogen anden.
        if not db.query(User).filter(User.email == "hjaelper@example.dk").count():
            db.add(User(household_id=default_household(db).id, email="hjaelper@example.dk",
                        name="Hjælper Én", password_hash=hash_password(PW),
                        role="contributor", source="local"))
        if not db.query(User).filter(User.email == "hjaelper2@example.dk").count():
            db.add(User(household_id=default_household(db).id, email="hjaelper2@example.dk",
                        name="Hjælper To", password_hash=hash_password(PW),
                        role="contributor", source="local"))
        db.commit()
    return TestClient(app)


@pytest.fixture(scope="module")
def auth(client):
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": "w@example.dk", "password": PW})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture(scope="module")
def bidragyder(client):
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": "hjaelper@example.dk", "password": PW})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture(scope="module")
def bidragyder2(client):
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": "hjaelper2@example.dk", "password": PW})
    assert r.status_code == 200, r.text
    return c


def test_upload_kraever_login(client):
    r = client.post(f"/api/products/{EAN}/foto?slags=front",
                    files={"image": ("f.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code in (401, 403)


def test_deklaration_beholder_sin_oploesning(auth, client):
    """Deklarationen skal kunne LÆSES igen — den må ikke skaleres ned til
    forsidens størrelse. 2400 px er under loftet og skal overleve."""
    r = auth.post(f"/api/products/{EAN}/foto?slags=deklaration",
                  files={"image": ("d.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200, r.text
    fotos = r.json()["fotos"]
    assert max(fotos["deklaration"]["bredde"], fotos["deklaration"]["hoejde"]) == 2400

    # åben læsning, som resten af appen
    h = client.get(f"/api/products/{EAN}/foto/deklaration")
    assert h.status_code == 200
    assert h.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(h.content)).size[0] == 2400


def test_forsiden_skaleres_ned(auth):
    """Forsiden skal kun kunne genkendes, ikke læses."""
    r = auth.post(f"/api/products/{EAN}/foto?slags=front",
                  files={"image": ("f.jpg", _jpeg(), "image/jpeg")})
    f = r.json()["fotos"]["front"]
    assert max(f["bredde"], f["hoejde"]) == 1600


def test_miniature_er_lille_saa_listen_ikke_haenter_fuldbilledet(auth, client):
    """Uden miniaturen ville et tryk på en vare hente flere MB over
    mobildata, netop mens man står i butikken."""
    auth.post(f"/api/products/{EAN}/foto?slags=deklaration",
              files={"image": ("d.jpg", _jpeg(), "image/jpeg")})
    mini = client.get(f"/api/products/{EAN}/foto/deklaration?mini=1")
    fuld = client.get(f"/api/products/{EAN}/foto/deklaration")
    assert mini.status_code == 200
    assert max(Image.open(io.BytesIO(mini.content)).size) == 480
    assert len(mini.content) < len(fuld.content) / 4


def test_ukendt_stregkode_faar_lov_at_have_billeder(auth):
    """Netop dér, hvor OFF ikke kender varen, er billedet mest værd."""
    ny = "5701234599999"
    assert auth.post(f"/api/products/{ny}/foto?slags=front",
                     files={"image": ("f.jpg", _jpeg(), "image/jpeg")}).status_code == 200
    d = auth.get(f"/api/scan/{ny}?allergens=maelkeprotein").json()
    assert "front" in d["fotos"]


def test_ukendt_stregkode_faar_en_produktraekke_og_er_synlig_i_soegningen(auth, client):
    """
    VIGTIGST: en vare, appen ikke kender, skal kunne have et foto uden at
    fejle — `product_ean` er en RIGTIG fremmednøgle (se app/models.py), så
    uden en `product`-række ville selve indsættelsen af billedet fejle på
    Postgres, selvom SQLite (uden PRAGMA foreign_keys=ON) ikke ville have
    fanget det. Rækken skal desuden gøre varen synlig i /api/soeg — en
    vare med reason="not_found" var før usynlig i hele appen.
    """
    ny = "5701234500099"
    assert auth.post(f"/api/products/{ny}/foto?slags=deklaration",
                     files={"image": ("d.jpg", _jpeg(), "image/jpeg")}).status_code == 200

    with SessionLocal() as db:
        p = db.get(Product, ny)
        assert p is not None, "der blev ikke oprettet nogen product-række"
        assert p.name is None, "en oprettet-af-foto-række skal IKKE have et gættet navn"
        assert p.source != "off", "rækken må ikke lade som om den kommer fra Open Food Facts"

    d = client.get("/api/soeg?status=alle&limit=200").json()
    assert ny in {v["ean"] for v in d["varer"]}, "varen er usynlig i søgningen"


def test_billede_goer_ikke_varen_groen(auth):
    """Invarianten, oversat til billeder: dokumentation er ikke bevis."""
    d = auth.get(f"/api/scan/{EAN}?allergens=maelkeprotein").json()
    assert d["result"] != "safe"
    with SessionLocal() as db:
        assert db.query(Verdict).filter(Verdict.product_ean == EAN).count() == 0


def test_nyt_foto_ligger_ved_siden_af_det_gamle(auth, client):
    """
    Siden 0.21.0 erstatter et nyt foto IKKE det gamle: opskriften kan
    være ændret mellem to besøg, og en bidragyder skal altid kunne lægge
    et billede til uden at overskrive en andens arbejde. Ingen automatisk
    udsmidning — en curator rydder selv op.
    """
    from app.db import DATA_DIR

    def fulde_billeder():
        return [p for p in (DATA_DIR / "billeder").glob(f"{EAN}_deklaration_*.jpg")
                if "_mini" not in p.name]

    foer = auth.get(f"/api/scan/{EAN}?allergens=maelkeprotein").json()["fotos"]["deklaration"]
    gammelt_indhold = client.get(
        f"/api/products/{EAN}/foto/deklaration/{foer['id']}").content
    antal_foer = len(fulde_billeder())

    r = auth.post(f"/api/products/{EAN}/foto?slags=deklaration",
                  files={"image": ("d2.jpg", _jpeg(farve=(20, 90, 200)), "image/jpeg")})
    assert r.status_code == 200, r.text
    nyt_id = r.json()["foto_id"]
    assert nyt_id != foer["id"], "det nye foto fik samme id som det gamle"

    # det gamle er urørt: samme fil på disken, uændret indhold
    stadig = client.get(f"/api/products/{EAN}/foto/deklaration/{foer['id']}")
    assert stadig.status_code == 200
    assert stadig.content == gammelt_indhold, "det gamle billede blev ændret"

    # GET uden id giver det NYESTE
    efter = auth.get(f"/api/scan/{EAN}?allergens=maelkeprotein").json()["fotos"]["deklaration"]
    assert efter["id"] == nyt_id, "GET uden id gav ikke det nyeste foto"
    nyeste_direkte = client.get(f"/api/products/{EAN}/foto/deklaration").content
    nyeste_med_id = client.get(f"/api/products/{EAN}/foto/deklaration/{nyt_id}").content
    assert nyeste_direkte == nyeste_med_id

    # det GAMLE billede ligger stadig på disken — der kom ét til, intet
    # forsvandt. (Absolut tal er ikke robust: modulets øvrige tests
    # uploader også til samme EAN/slags.)
    assert len(fulde_billeder()) == antal_foer + 1, "det gamle fuldbillede forsvandt fra disken"


def test_ugyldig_slags_og_sti_afvises(auth, client):
    assert auth.post(f"/api/products/{EAN}/foto?slags=../../etc",
                     files={"image": ("x.jpg", _jpeg(), "image/jpeg")}).status_code == 400
    assert client.get(f"/api/products/{EAN}/foto/..%2F..%2Fetc%2Fpasswd").status_code in (400, 404)


def test_foto_kan_slettes(auth, client):
    from app.db import DATA_DIR
    foto_id = auth.get(f"/api/scan/{EAN}?allergens=maelkeprotein").json()["fotos"]["front"]["id"]
    assert auth.delete(f"/api/products/{EAN}/foto/front/{foto_id}").status_code == 200
    assert client.get(f"/api/products/{EAN}/foto/front").status_code == 404
    # også miniaturen — ellers ligger der forældede filer tilbage
    assert not list((DATA_DIR / "billeder").glob(f"{EAN}_front_*"))


# --- ejerskab: en bidragyder må slette sit EGET, ikke andres ------------

def test_bidragyder_kan_slette_eget_foto(bidragyder, client):
    ny = "5701234500010"
    r = bidragyder.post(f"/api/products/{ny}/foto?slags=front",
                        files={"image": ("f.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200, r.text
    foto_id = r.json()["foto_id"]
    assert bidragyder.delete(f"/api/products/{ny}/foto/front/{foto_id}").status_code == 200
    assert client.get(f"/api/products/{ny}/foto/front/{foto_id}").status_code == 404


def test_bidragyder_kan_ikke_slette_en_andens_foto(bidragyder, bidragyder2):
    """
    To hjælpere kan hedde det samme i to husstande, eller bare have samme
    fornavn — `taget_af` er kun en visningsstreng. Ejerskabet afgøres af
    `taget_af_user_id`.
    """
    ny = "5701234500011"
    r = bidragyder.post(f"/api/products/{ny}/foto?slags=front",
                        files={"image": ("f.jpg", _jpeg(), "image/jpeg")})
    foto_id = r.json()["foto_id"]
    d = bidragyder2.delete(f"/api/products/{ny}/foto/front/{foto_id}")
    assert d.status_code == 403, "en bidragyder kunne slette en andens billede"


def test_curator_kan_slette_et_hvilket_som_helst_foto(bidragyder, auth):
    """Curator/admin rydder op ved gennemgang — uanset hvem der tog det."""
    ny = "5701234500012"
    r = bidragyder.post(f"/api/products/{ny}/foto?slags=front",
                        files={"image": ("f.jpg", _jpeg(), "image/jpeg")})
    foto_id = r.json()["foto_id"]
    assert auth.delete(f"/api/products/{ny}/foto/front/{foto_id}").status_code == 200
    from app.db import DATA_DIR
    assert not list((DATA_DIR / "billeder").glob(f"{ny}_front_*")), (
        "begge filer (fuld + miniature) skal være væk"
    )


# --- navngivning af en vare, familien selv har fundet på --------------

def test_curator_kan_navngive_en_ukendt_vare(auth):
    ny = "5701234500013"
    auth.post(f"/api/products/{ny}/foto?slags=front",
              files={"image": ("f.jpg", _jpeg(), "image/jpeg")})
    r = auth.post(f"/api/products/{ny}/navn", json={"name": "Skyr med jordbær"})
    assert r.status_code == 200, r.text
    d = auth.get(f"/api/scan/{ny}?allergens=maelkeprotein").json()
    assert d["product"]["name"] == "Skyr med jordbær"


def test_bidragyder_kan_ikke_navngive_en_vare(bidragyder):
    """Navngivning er familiens beslutning, ligesom bekræftelsen — begge
    kræver require_curator. En bidragyder må dokumentere, ikke afgøre."""
    ny = "5701234500014"
    bidragyder.post(f"/api/products/{ny}/foto?slags=front",
                    files={"image": ("f.jpg", _jpeg(), "image/jpeg")})
    r = bidragyder.post(f"/api/products/{ny}/navn", json={"name": "Forsøg"})
    assert r.status_code == 403


def test_navngivning_opretter_varen_hvis_den_ikke_findes(auth):
    """
    Før dette gav rejsen 404 — men frontend gemmer navnet FØR dommene
    (se saveConfirm()), så en forælder, der navngav OG tastede en hel
    deklaration ind på en ukendt EAN, mistede alt arbejdet på netop den
    404. Ligesom /confirm og gem_foto skal /navn kunne oprette varen selv.
    """
    ny = "5701234599998"
    r = auth.post(f"/api/products/{ny}/navn", json={"name": "X"})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        p = db.get(Product, ny)
        assert p is not None
        assert p.navn_manuelt == "X"


def test_ukendt_vare_navn_deklaration_og_domme_lander_i_en_gemning(auth):
    """
    Hele forløbet, changeloggen sælger: en vare Open Food Facts aldrig
    har hørt om, navngivet ud fra forsidefotoet, med en hel deklaration
    tastet ind og allergenerne afgjort — alt i én gemning, uden at nogen
    af de tre skrivninger vælter de andre.
    """
    ny = "5701234599997"
    with SessionLocal() as db:
        assert db.get(Product, ny) is None, "varen må ikke findes i forvejen"

    r_navn = auth.post(f"/api/products/{ny}/navn", json={"name": "Skyr med jordbær"})
    assert r_navn.status_code == 200, r_navn.text

    r_confirm = auth.post(
        f"/api/products/{ny}/confirm",
        json={
            "verdicts": {"jordbaer": "contains"},
            "ingredients_text": "Skyr, jordbær, sukker",
        },
    )
    assert r_confirm.status_code == 200, r_confirm.text

    with SessionLocal() as db:
        p = db.get(Product, ny)
        assert p is not None
        assert p.navn_manuelt == "Skyr med jordbær"
        assert p.ingredients_text == "Skyr, jordbær, sukker"
        v = db.scalar(select(Verdict).where(Verdict.product_ean == ny))
        assert v is not None and v.state == "contains"


def test_navnet_gemmes_ikke_i_offs_eget_felt(auth):
    """
    `product.name` er Open Food Facts' eget felt (ODbL-afledt, se
    NOTICE.md) — familiens eget navn hører til `navn_manuelt`, ellers
    ville _ensure_product() kunne overskrive familiens arbejde med et
    OFF-navn (se test_manuelt_navn_overlever_genhentning_fra_off i
    tests/test_regressioner.py).
    """
    ny = "5701234500016"
    auth.post(f"/api/products/{ny}/foto?slags=front",
              files={"image": ("f.jpg", _jpeg(), "image/jpeg")})
    r = auth.post(f"/api/products/{ny}/navn", json={"name": "Skyr med jordbær"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Skyr med jordbær"
    with SessionLocal() as db:
        p = db.get(Product, ny)
        assert p.navn_manuelt == "Skyr med jordbær"
        assert p.name is None, "det manuelle navn lækkede ind i OFF's eget felt"


def test_scan_svar_siger_om_navnet_er_familiens_eget(auth):
    """
    `openConfirm()` skal kunne skelne, om det viste navn kan RETTES
    (familiens eget, `navn_manuelt`) eller ej (Open Food Facts' gæt) —
    ellers er en tastefejl i familiens eget navn permanent for evigt, fra
    sekundet den blev gemt.
    """
    ny = "5701234500020"
    auth.post(f"/api/products/{ny}/navn", json={"name": "Skyr med jordbær"})
    d = auth.get(f"/api/scan/{ny}?allergens=maelkeprotein").json()
    assert d["product"]["navn_er_vores"] is True

    off_navn = "5701234500021"
    with SessionLocal() as db:
        db.add(Product(ean=off_navn, name="Et OFF-navn", source="off"))
        db.commit()
    d2 = auth.get(f"/api/scan/{off_navn}?allergens=maelkeprotein").json()
    assert d2["product"]["navn_er_vores"] is False


def test_mislykket_gemning_efterlader_ingen_forloerne_filer(auth):
    """
    `gem_foto()` skrev begge JPEG'er til disken FØR db.commit(). Fejlede
    commit'en, var filerne uopnåelige for altid — ingen databaserække
    pegede på dem, og et nyt forsøg fik et helt nyt, tilfældigt filnavn
    (se _foto_filnavne()), så det gamle par aldrig ville blive fundet
    eller ryddet op igen.
    """
    from app.db import DATA_DIR, SessionLocal as EgentligSessionLocal
    from app.main import app, get_session

    def braekket_session():
        db = EgentligSessionLocal()

        def boom():
            raise RuntimeError("databasen er væk")

        db.commit = boom
        try:
            yield db
        finally:
            db.close()

    ny = "5701234500022"
    app.dependency_overrides[get_session] = braekket_session
    try:
        with pytest.raises(RuntimeError):
            auth.post(f"/api/products/{ny}/foto?slags=deklaration",
                      files={"image": ("d.jpg", _jpeg(), "image/jpeg")})
    finally:
        app.dependency_overrides.pop(get_session, None)

    tiloversblevne = list((DATA_DIR / "billeder").glob(f"{ny}_deklaration_*"))
    assert not tiloversblevne, f"forældreløse filer efter fejlet commit: {tiloversblevne}"


def test_navn_afviser_tomt_og_for_langt(auth):
    """
    `navn[:400]` afkortede før tavst — nu skal et for langt navn afvises
    (422), og et tomt navn ligeså (min_length=1). Kun whitespace er
    stadig fanget af handlerens egen 400 (Field ser mellemrum som indhold).
    """
    ny = "5701234500017"
    auth.post(f"/api/products/{ny}/foto?slags=front",
              files={"image": ("f.jpg", _jpeg(), "image/jpeg")})
    assert auth.post(f"/api/products/{ny}/navn", json={"name": ""}).status_code == 422
    assert auth.post(f"/api/products/{ny}/navn", json={"name": "x" * 401}).status_code == 422
    assert auth.post(f"/api/products/{ny}/navn", json={"name": "   "}).status_code == 400
    r = auth.post(f"/api/products/{ny}/navn", json={"name": "x" * 400})
    assert r.status_code == 200, r.text


# --- alle billeder, ikke kun det nyeste ---------------------------------

def test_foto_svar_tiebreak_matcher_hent_foto(auth):
    """
    _foto_svar() sorterede før KUN på taget_at, uden id som tiebreak —
    hent_foto() bruger (taget_at DESC, id DESC). Ved to billeder med
    samme sekund-præcise tidsstempel skal de to ruter pege på SAMME
    billede, ikke to forskellige.
    """
    from app.main import _billedmappe

    ny = "5701234500018"
    with SessionLocal() as db:
        hh = default_household(db)
        db.add(Product(ean=ny, source="manual"))
        db.flush()
        f1 = ProductPhoto(household_id=hh.id, product_ean=ny, slags="front", fil="a.jpg")
        f2 = ProductPhoto(household_id=hh.id, product_ean=ny, slags="front", fil="b.jpg")
        db.add(f1)
        db.add(f2)
        db.flush()
        f2.taget_at = f1.taget_at   # tving et rigtigt tidsstempel-sammenfald
        db.commit()
        db.refresh(f1)
        db.refresh(f2)
        stoerste_id = max(f1.id, f2.id)

        svar = _foto_svar(db, hh.id, ny)
        assert svar["front"]["id"] == stoerste_id, (
            "_foto_svar() valgte ikke den højeste id ved samme tidsstempel"
        )

    (_billedmappe() / "a.jpg").write_bytes(_jpeg(farve=(10, 10, 10)))
    (_billedmappe() / "b.jpg").write_bytes(_jpeg(farve=(20, 20, 20)))

    r = auth.get(f"/api/products/{ny}/foto/front")
    assert r.status_code == 200
    med_id = auth.get(f"/api/products/{ny}/foto/front/{stoerste_id}")
    assert r.content == med_id.content, (
        "GET uden id gav et ANDET billede end den højeste id ved samme tidsstempel"
    )


def test_alle_fotos_ruten_lister_flere_billeder_af_samme_slags(auth, client):
    """
    Kernen i hovedopgaven: intet endepunkt udleverede før et `foto_id`
    for et ÆLDRE billede — GET .../fotos er den vej.
    """
    ny = "5701234500019"
    id1 = auth.post(f"/api/products/{ny}/foto?slags=deklaration",
                    files={"image": ("d1.jpg", _jpeg(), "image/jpeg")}).json()["foto_id"]
    id2 = auth.post(f"/api/products/{ny}/foto?slags=deklaration",
                    files={"image": ("d2.jpg", _jpeg(), "image/jpeg")}).json()["foto_id"]

    d = client.get(f"/api/products/{ny}/fotos").json()
    assert set(d.keys()) == {"nyeste", "alle"}
    ider = {f["id"] for f in d["alle"]["deklaration"]}
    assert {id1, id2} <= ider, "et ældre billede mangler i /fotos"
    assert d["nyeste"]["deklaration"]["id"] == id2, "'nyeste' skal stadig kun være det seneste"
    # front er tom, men skal stå med, så frontend ikke skal gætte på nøglen
    assert d["alle"]["front"] == []


def test_alle_fotos_kan_slette_foelger_ejerskab(auth, bidragyder, client):
    """
    `kan_slette` skal afspejle PRÆCIS den regel, slet_foto() selv
    håndhæver — curator/admin alt, en bidragyder kun sit eget. Beregnet
    server-side, så grænsefladen aldrig kan vise en knap, et klik ville
    få 403 på.
    """
    ny = "5701234500021"
    foto_id = bidragyder.post(
        f"/api/products/{ny}/foto?slags=front",
        files={"image": ("f.jpg", _jpeg(), "image/jpeg")},
    ).json()["foto_id"]

    som_ejer = {f["id"]: f["kan_slette"] for f in
                bidragyder.get(f"/api/products/{ny}/fotos").json()["alle"]["front"]}
    assert som_ejer[foto_id] is True, "bidragyderen kan ikke slette sit eget billede"

    som_curator = {f["id"]: f["kan_slette"] for f in
                   auth.get(f"/api/products/{ny}/fotos").json()["alle"]["front"]}
    assert som_curator[foto_id] is True, "curator kan ikke slette et andet menneskes billede"

    som_fremmed = {f["id"]: f["kan_slette"] for f in
                   client.get(f"/api/products/{ny}/fotos").json()["alle"]["front"]}
    assert som_fremmed[foto_id] is False, "en anonym kalder fik kan_slette=true"


def test_alle_fotos_er_offentlig_men_skjuler_navnet_for_en_fremmed(auth, client):
    """Samme afvejning som de øvrige fotoruter (se test_offentlig_flade.py):
    åben læsning, men `taget_af` er kun for familien."""
    ny = "5701234500022"
    auth.post(f"/api/products/{ny}/foto?slags=front",
              files={"image": ("f.jpg", _jpeg(), "image/jpeg")})
    anon = client.get(f"/api/products/{ny}/fotos")
    assert anon.status_code == 200
    assert "taget_af" not in anon.text
    som_familie = auth.get(f"/api/products/{ny}/fotos").json()
    assert som_familie["alle"]["front"][0].get("taget_af") == "William"


# --- fjernes en hjælper, skal hendes fotos blive stående -----------------

def test_slettet_bruger_blokerer_ikke_sletning_af_fotorows(client):
    """
    `taget_af_user_id` har `ondelete="SET NULL"` (0.21.0). Fjernes en
    hjælper en dag, skal hendes billeder blive stående som dokumentation
    — IKKE forhindre, at brugeren rent faktisk kan slettes.
    """
    ny = "5701234500023"
    with SessionLocal() as db:
        hh = default_household(db)
        u = User(household_id=hh.id, email="engangshjaelper@example.dk",
                 name="Engangshjælper", password_hash=hash_password(PW),
                 role="contributor", source="local")
        db.add(u)
        db.add(Product(ean=ny, source="manual"))
        db.flush()
        f = ProductPhoto(household_id=hh.id, product_ean=ny, slags="front", fil="engang.jpg",
                         taget_af="Engangshjælper", taget_af_user_id=u.id)
        db.add(f)
        db.commit()
        uid, foto_id = u.id, f.id

    with SessionLocal() as db:
        db.delete(db.get(User, uid))
        db.commit()   # må IKKE fejle med en IntegrityError

    with SessionLocal() as db:
        f2 = db.get(ProductPhoto, foto_id)
        assert f2 is not None, "fotorækken forsvandt sammen med brugeren, der tog den"
        assert f2.taget_af_user_id is None, "ondelete=SET NULL satte ikke feltet til NULL"
        assert f2.taget_af == "Engangshjælper", "navnestrengen skal stå urørt"


def test_exif_og_gps_forlader_ikke_serveren(auth):
    """
    Et telefonfoto bærer GPS-koordinater, kameramodel og ofte ejerens
    navn i EXIF. Familien fotograferer i deres eget køkken, og
    fotoruterne er ÅBNE — et billede kan hentes af enhver, der kender
    stregkoden. Slap EXIF med ud, ville hjemmets position være
    offentlig.

    I dag strippes det, fordi `gem_foto()` genkoder billedet med PIL og
    aldrig sender `exif=` med til `save()`. Det er en egenskab ved en
    kodelinje, der IKKE er der — og præcis den slags forsvinder ved en
    uskyldig ændring ("bevar orienteringen", "behold metadata"). Derfor
    denne test: den fejler, hvis nogen tilføjer den linje.
    """
    import io

    from PIL import Image
    from PIL.ExifTags import GPS
    from PIL.ExifTags import Base as Tag

    billede = Image.new("RGB", (1200, 900), (205, 195, 175))
    ex = Image.Exif()
    ex[Tag.Make.value] = "Apple"
    ex[Tag.Model.value] = "iPhone 15"
    ex[Tag.Artist.value] = "Fornavn Efternavn"
    ex[Tag.ImageDescription.value] = "koekkenet hjemme"
    ex.get_ifd(0x8825).update({
        GPS.GPSLatitudeRef.value: "N",
        GPS.GPSLatitude.value: (55.0, 40.0, 33.72),
        GPS.GPSLongitudeRef.value: "E",
        GPS.GPSLongitude.value: (12.0, 34.0, 12.34),
    })
    raa = io.BytesIO()
    billede.save(raa, "JPEG", quality=95, exif=ex)
    original = raa.getvalue()
    # Modprøve: markørerne SKAL være i det, vi sender op — ellers
    # beviser testen ingenting.
    assert Image.open(io.BytesIO(original)).getexif().get_ifd(0x8825), "fikstureret har ingen GPS"

    ean = "5701234599001"
    r = auth.post(f"/api/products/{ean}/foto?slags=deklaration",
                  files={"image": ("telefon.jpg", original, "image/jpeg")})
    assert r.status_code == 200, r.text
    foto_id = r.json()["foto_id"]

    hentet = auth.get(f"/api/products/{ean}/foto/deklaration/{foto_id}")
    assert hentet.status_code == 200
    ud = hentet.content

    e = Image.open(io.BytesIO(ud)).getexif()
    assert not dict(e), f"EXIF fulgte med billedet ud: {dict(e)}"
    assert not dict(e.get_ifd(0x8825)), "GPS-blokken fulgte med billedet ud"
    for markoer in (b"Apple", b"iPhone", b"Fornavn", b"koekkenet"):
        assert markoer not in ud, f"{markoer!r} stod stadig i de rå bytes"
