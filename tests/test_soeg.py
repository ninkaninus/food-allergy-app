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
        # Den gamle godkendt-liste: egne hyldenavne og butikker, ingen EAN
        db.add(ImportedProduct(household_id=hh.id, kategori="Brød", navn="Listebrød Grov",
                               producent="Bagerens", butik="Netto", valideret_mod="mælk og æg"))
        db.add(ImportedProduct(household_id=hh.id, kategori="Pålæg", navn="Listepålæg Skinke",
                               producent="Slagteren", butik="Rema"))
        db.commit()
    return TestClient(app)


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


# --- facetter og butiks-filtre --------------------------------------------

def test_facetter_taeller_som_i_en_webshop(client):
    r = client.get("/api/soeg", params={"allergens": "maelkeprotein", "q": "brød"})
    f = r.json()["facetter"]
    # status-tal er talt UDEN status-filteret, så knapperne kan vise antal
    assert f["status"]["alle"] == 5           # fire scannede + ét listebrød
    assert f["status"]["safe"] == 1
    assert f["status"]["unsafe"] == 1
    assert f["status"]["liste"] == 1
    assert {x["vaerdi"] for x in f["kategori"]} == {"Brød"}
    assert [x["antal"] for x in f["kategori"]] == [1]


def test_listen_er_med_i_soegningen_men_aldrig_sikker(client):
    navne = {p["navn"]: p for p in _hent(client, q="liste")}
    assert "Listebrød Grov" in navne
    assert navne["Listebrød Grov"]["status"] == "liste"
    assert navne["Listebrød Grov"]["ean"] is None
    assert navne["Listebrød Grov"]["valideret_mod"] == "mælk og æg"
    # og den kan ikke snige sig ind under "kun sikre"
    assert "Listebrød Grov" not in {p["navn"] for p in _hent(client, q="liste", status="safe")}


def test_kategori_facet_filtrerer(client):
    navne = {p["navn"] for p in _hent(client, kategori="Pålæg")}
    assert navne == {"Listepålæg Skinke"}


def test_butik_facet_filtrerer(client):
    navne = {p["navn"] for p in _hent(client, butik="Netto")}
    assert navne == {"Listebrød Grov"}


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
