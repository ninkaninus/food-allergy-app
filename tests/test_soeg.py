"""
Butiks-søgningen (/api/soeg) deler domslogik med scan-skærmen, og det
vigtigste her er det, den IKKE må: vise en vare som sikker, når den
manuelle dom er forældet, eller når motoren ville advare.
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

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal, default_household, init_db
from app.main import app
from app.matcher import ingredients_hash
from app.models import Allergen, ImportedProduct, Product, Verdict


@pytest.fixture(scope="module")
def client():
    init_db()
    with SessionLocal() as db:
        hh = default_household(db)
        maelk = db.scalar(select(Allergen).where(Allergen.slug == "maelkeprotein"))

        def vare(ean, navn, tekst):
            db.add(Product(ean=ean, name=navn, brand="Testbageren",
                           ingredients_text=tekst, ingredients_hash=ingredients_hash(tekst)))
            return tekst

        vare("5799990000001", "Testbrød Hvid", "Hvedemel, mælk, gær, salt")
        vare("5799990000002", "Testbrød Rug", "Rugmel, vand, surdej, salt")
        t3 = vare("5799990000003", "Testbrød Grøn", "Rugmel, vand, salt")
        t4 = vare("5799990000004", "Testbrød Gammel", "Rugmel, vand, bygmalt")

        # Grøn: manuel FREE-dom med MATCHENDE hash -> ægte 'safe'
        db.add(Verdict(household_id=hh.id, product_ean="5799990000003",
                       allergen_id=maelk.id, state="free", basis="manual",
                       ingredients_hash=ingredients_hash(t3)))
        # Gammel: manuel FREE-dom, men opskriften har ÆNDRET sig siden
        db.add(Verdict(household_id=hh.id, product_ean="5799990000004",
                       allergen_id=maelk.id, state="free", basis="manual",
                       ingredients_hash="00000000000000000000000000000000"))
        # Den gamle godkendt-liste: egne hyldenavne, ingen EAN
        db.add(ImportedProduct(household_id=hh.id, kategori="Brød", navn="Listebrød Grov",
                               producent="Bagerens", valideret_mod="mælk og æg"))
        db.add(ImportedProduct(household_id=hh.id, kategori="Pålæg", navn="Listepålæg Skinke",
                               producent="Slagteren"))
        db.commit()
    return TestClient(app)


@pytest.fixture(scope="module")
def auth(client):
    """Indlogget klient — koblingen er en skrivning og kræver login."""
    from app.auth import hash_password
    from app.db import SessionLocal, default_household
    from app.models import User

    pw = "korrekt-hest-batteri-haefteklamme"
    with SessionLocal() as db:
        hh = default_household(db)
        # Filtrér på MAILEN, ikke på antal: modulerne deler én database,
        # og et blankt count() betyder, at modulets egen bruger aldrig
        # bliver oprettet, hvis et andet modul kørte først.
        if not db.query(User).filter(User.email == "w@example.dk").count():
            db.add(User(household_id=hh.id, email="w@example.dk", name="William",
                        password_hash=hash_password(pw), role="admin", source="local"))
            db.commit()
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": "w@example.dk", "password": pw})
    assert r.status_code == 200, r.text
    return c


def _hent(client, **params):
    r = client.get("/api/soeg", params={"allergens": "maelkeprotein", **params})
    assert r.status_code == 200
    return r.json()["varer"]


def test_soegning_paa_kategoriord_rammer_alle_broed(client):
    navne = {p["navn"] for p in _hent(client, q="testbrød")}
    assert navne == {"Testbrød Hvid", "Testbrød Rug", "Testbrød Grøn", "Testbrød Gammel"}


def test_kun_sikre_viser_kun_manuelt_bekraeftede(client):
    hits = _hent(client, q="testbrød", status="safe")
    assert [p["navn"] for p in hits] == ["Testbrød Grøn"]


def test_ikke_tilladt_viser_varen_med_allergenet(client):
    hits = _hent(client, q="testbrød", status="unsafe")
    assert [p["navn"] for p in hits] == ["Testbrød Hvid"]
    assert "Mælkeprotein" in hits[0]["problemer"]


def test_foraeldet_dom_er_ALDRIG_sikker(client):
    """Opskriften ændrede sig efter godkendelsen — varen må ikke stå som
    sikker, uanset at der findes en manuel FREE-dom. Samme regel som
    scan-skærmen, og den vigtigste egenskab ved hele listen."""
    sikre = {p["navn"] for p in _hent(client, q="testbrød", status="safe")}
    assert "Testbrød Gammel" not in sikre
    uafklarede = {p["navn"]: p for p in _hent(client, q="testbrød", status="uafklaret")}
    assert "Testbrød Gammel" in uafklarede
    assert uafklarede["Testbrød Gammel"]["stale"] is True


def test_uafklaret_samler_resten(client):
    navne = {p["navn"] for p in _hent(client, q="testbrød", status="uafklaret")}
    assert navne == {"Testbrød Rug", "Testbrød Gammel"}


def test_tom_soegning_og_ugyldig_status(client):
    assert _hent(client, q="findesikke-xyzzy") == []
    r = client.get("/api/soeg", params={"status": "grøn"})
    assert r.status_code == 400


# --- facetter og kategori-filtre --------------------------------------------

def test_facetter_taeller_som_i_en_webshop(client):
    r = client.get("/api/soeg", params={"allergens": "maelkeprotein", "q": "brød"})
    f = r.json()["facetter"]
    # status-tal er talt UDEN status-filteret, så knapperne kan vise antal
    assert f["status"]["alle"] == 5           # fire scannede + ét listebrød
    assert f["status"]["safe"] == 1
    assert f["status"]["unsafe"] == 1
    assert f["status"]["uscannet"] == 1
    assert {x["vaerdi"] for x in f["kategori"]} == {"Brød"}
    assert [x["antal"] for x in f["kategori"]] == [1]


def test_listen_er_med_i_soegningen_men_aldrig_sikker(client):
    navne = {p["navn"]: p for p in _hent(client, q="liste")}
    assert "Listebrød Grov" in navne
    assert navne["Listebrød Grov"]["status"] == "uscannet"
    assert navne["Listebrød Grov"]["ean"] is None
    assert navne["Listebrød Grov"]["valideret_mod"] == "mælk og æg"
    # og den kan ikke snige sig ind under "kun sikre"
    assert "Listebrød Grov" not in {p["navn"] for p in _hent(client, q="liste", status="safe")}


def test_kategori_facet_filtrerer(client):
    navne = {p["navn"] for p in _hent(client, kategori="Pålæg")}
    assert navne == {"Listepålæg Skinke"}


def test_fri_for_skjuler_varer_hvor_allergenet_er_fundet(client):
    """Men det er IKKE et løfte om at resten er fri — de ukendte bliver
    stående med deres egen farve, og det er hele pointen."""
    uden = {p["navn"] for p in _hent(client, q="testbrød", fri_for="maelkeprotein")}
    assert "Testbrød Hvid" not in uden          # mælk fundet -> væk
    assert "Testbrød Rug" in uden               # ukendt -> stadig med
    assert all(p["status"] != "safe" or p["navn"] == "Testbrød Grøn"
               for p in _hent(client, q="testbrød", fri_for="maelkeprotein"))


def test_soegning_folder_aeoeaa(client):
    """'palaeg' skal finde 'Pålæg' — ellers skal man ramme æ/ø/å præcist
    på et telefontastatur i en butik."""
    assert {p["navn"] for p in _hent(client, q="palaeg")} == {"Listepålæg Skinke"}


# --- én liste: arket og de scannede varer er samme liste -------------------

def test_scannet_vare_og_arkraekke_bliver_EEN_linje(client):
    """Har I scannet noget, der står på arket, må det ikke stå to gange —
    det var hele pointen med at slå listerne sammen."""
    from app.db import SessionLocal, default_household
    from app.models import ImportedProduct, Product
    from app.matcher import ingredients_hash

    with SessionLocal() as db:
        hh = default_household(db)
        t = "Rugmel, vand, salt"
        db.add(Product(ean="5799990000005", name="Listebrød Grov Skiveskåret",
                       brand="Bagerens", ingredients_text=t,
                       ingredients_hash=ingredients_hash(t)))
        db.commit()

    traef = _hent(client, q="listebrød grov")
    assert len(traef) == 1, [t["navn"] for t in traef]
    v = traef[0]
    assert v["scannet"] is True and v["paa_listen"] is True
    assert v["ean"] == "5799990000005"
    # arven fra arket: den scannede vare havner i den rigtige gruppe
    assert v["kategori"] == "Brød"
    # og dommen er stadig motorens/menneskets — ikke arkets
    assert v["status"] != "safe"


def test_to_taerskler_for_match():
    """Kategori-arv må gerne være løs; påstanden om SAMME vare må ikke.

    Uden det ville "Testbrød Hvid" sluge arkets "Testbrød Grøn" — de
    deler mærke og halvdelen af navnet — og en række ville forsvinde
    fra listen, uden at nogen bad om det."""
    from app.main import _match_liste, _ord_maengde
    from app.models import ImportedProduct

    ark = ImportedProduct(id=1, household_id=1, navn="Testbrød Grøn",
                          producent="Bagerens", kategori="Brød")
    indeks = {}
    for w in _ord_maengde(ark.navn, ark.producent):
        indeks.setdefault(w, []).append(ark)

    # samme vare: arkets ord går fuldt op i varens navn
    ip, samme = _match_liste("Testbrød Grøn Skiveskåret", "Bagerens", indeks)
    assert ip is ark and samme is True

    # nabovare: nok til at arve hylden, ikke nok til at være den samme
    ip, samme = _match_liste("Testbrød Hvid", "Bagerens", indeks)
    assert ip is ark and samme is False

    # ingen fællesnævner: hverken hylde eller sammenlægning
    ip, samme = _match_liste("Kikærtepasta", "Andet Mærke", indeks)
    assert ip is None and samme is False


def test_grupper_er_hylder_med_antal(client):
    r = client.get("/api/soeg", params={"allergens": "maelkeprotein"})
    grupper = r.json()["grupper"]
    navne = [g["navn"] for g in grupper]
    assert "Brød" in navne
    # Uden kategori står sidst — det er ikke en hylde, den mangler bare en
    assert navne[-1] == "Uden kategori"
    broed = next(g for g in grupper if g["navn"] == "Brød")
    assert broed["antal"] == len(broed["varer"]) or len(broed["varer"]) == 6
    assert all(v["kategori"] == "Brød" for v in broed["varer"])


# --- kobling til stregkode: dét, der giver arkets rækker værdi -------------

def test_kobling_kraever_login(client):
    from app.db import SessionLocal, default_household
    from app.models import ImportedProduct
    with SessionLocal() as db:
        ip = db.query(ImportedProduct).filter(
            ImportedProduct.navn == "Listepålæg Skinke").one()
        ip_id = ip.id
    r = client.post(f"/api/liste/{ip_id}/stregkode", json={"ean": "5799990000009"})
    assert r.status_code in (401, 403)


def test_koblet_raekke_bliver_een_linje_med_dom(client, auth):
    """Efter koblingen er arkets række og den scannede vare samme linje —
    og dommen er stadig motorens, ikke arkets."""
    from app.db import SessionLocal, default_household
    from app.matcher import ingredients_hash
    from app.models import ImportedProduct, Product

    ean = "5799990000010"
    with SessionLocal() as db:
        hh = default_household(db)
        t = "Svinekød, salt, mælkeprotein"
        db.add(Product(ean=ean, name="Helt Andet Navn", brand="Ukendt",
                       ingredients_text=t, ingredients_hash=ingredients_hash(t)))
        ip = ImportedProduct(household_id=hh.id, kategori="Pålæg",
                             navn="Arkets Skinke", producent="Slagteren")
        db.add(ip)
        db.commit()
        ip_id = ip.id

    r = auth.post(f"/api/liste/{ip_id}/stregkode", json={"ean": ean})
    assert r.status_code == 200, r.text

    traef = [v for v in _hent(client, q="helt andet navn")]
    assert len(traef) == 1
    v = traef[0]
    assert v["ean"] == ean and v["paa_listen"] is True
    assert v["kategori"] == "Pålæg"
    # koblingen er IKKE en dom — mælkeprotein står stadig i teksten
    assert v["status"] == "unsafe"

    # og arkets række dukker ikke op som sin egen linje mere
    assert "Arkets Skinke" not in {x["navn"] for x in _hent(client, q="arkets skinke")}


def test_samme_stregkode_kan_ikke_bruges_to_gange(client, auth):
    from app.db import SessionLocal, default_household
    from app.models import ImportedProduct
    with SessionLocal() as db:
        hh = default_household(db)
        ip = ImportedProduct(household_id=hh.id, navn="En Anden Vare", kategori="Diverse")
        db.add(ip)
        db.commit()
        ip_id = ip.id
    r = auth.post(f"/api/liste/{ip_id}/stregkode", json={"ean": "5799990000010"})
    assert r.status_code == 409
    assert "Arkets Skinke" in r.json()["detail"]


def test_kobling_kan_fjernes_igen(client, auth):
    from app.db import SessionLocal
    from app.models import ImportedProduct
    with SessionLocal() as db:
        ip = db.query(ImportedProduct).filter(
            ImportedProduct.navn == "Arkets Skinke").one()
        ip_id = ip.id
    assert auth.post(f"/api/liste/{ip_id}/stregkode", json={"ean": None}).status_code == 200
    assert "Arkets Skinke" in {v["navn"] for v in _hent(client, q="arkets skinke")}
