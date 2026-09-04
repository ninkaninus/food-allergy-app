"""
Butiks-søgningen (/api/soeg) deler domslogik med scan-skærmen, og det
vigtigste her er det, den IKKE må: vise en vare som sikker, når den
manuelle dom er forældet, eller når motoren ville advare.

(0.25.0 fjernede den gamle godkendt-liste fra regnearket — se
_drop_imported_product_tabellen() i app/db.py. Søgningen er nu en flad
liste over de scannede varer alene.)
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
from app.models import Allergen, Product, Verdict


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
        vare("5799990000006", "Listepålæg Skinke", "Svinekød, salt, krydderier")

        # Grøn: manuel FREE-dom med MATCHENDE hash -> ægte 'safe'
        db.add(Verdict(household_id=hh.id, product_ean="5799990000003",
                       allergen_id=maelk.id, state="free", basis="manual",
                       ingredients_hash=ingredients_hash(t3)))
        # Gammel: manuel FREE-dom, men opskriften har ÆNDRET sig siden
        db.add(Verdict(household_id=hh.id, product_ean="5799990000004",
                       allergen_id=maelk.id, state="free", basis="manual",
                       ingredients_hash="00000000000000000000000000000000"))
        db.commit()
    return TestClient(app)


def _hent(client, **params):
    r = client.get("/api/soeg", params={"allergens": "maelkeprotein", **params})
    assert r.status_code == 200
    return r.json()["varer"]


def test_soegning_paa_navn_rammer_alle_broed(client):
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
    # "uscannet" var en gyldig status, dengang arket fandtes — nu findes
    # der ingen uscannede rækker, og værdien er ikke længere gyldig.
    r = client.get("/api/soeg", params={"status": "uscannet"})
    assert r.status_code == 400


def test_facetter_taeller_status_uden_arket(client):
    r = client.get("/api/soeg", params={"allergens": "maelkeprotein", "q": "testbrød"})
    f = r.json()["facetter"]
    assert set(f.keys()) == {"status"}
    assert f["status"]["alle"] == 4
    assert f["status"]["safe"] == 1
    assert f["status"]["unsafe"] == 1
    assert f["status"]["uafklaret"] == 2
    assert "kategori" not in f
    assert "grupper" not in r.json()


def test_fri_for_skjuler_varer_hvor_allergenet_er_fundet(client):
    """Men det er IKKE et løfte om at resten er fri — de ukendte bliver
    stående med deres egen farve, og det er hele pointen."""
    uden = {p["navn"] for p in _hent(client, q="testbrød", fri_for="maelkeprotein")}
    assert "Testbrød Hvid" not in uden          # mælk fundet -> væk
    assert "Testbrød Rug" in uden               # ukendt -> stadig med
    assert all(p["status"] != "safe" or p["navn"] == "Testbrød Grøn"
               for p in _hent(client, q="testbrød", fri_for="maelkeprotein"))


def test_soegning_folder_aeoeaa(client):
    """'palaeg' skal finde 'Listepålæg' — ellers skal man ramme æ/ø/å
    præcist på et telefontastatur i en butik."""
    assert {p["navn"] for p in _hent(client, q="palaeg")} == {"Listepålæg Skinke"}


def test_svaret_er_en_flad_liste_uden_arkfelter(client):
    """0.25.0: ingen grupper/hylder, ingen kategori, ingen liste_id/
    paa_listen — det gamle regneark er væk, og hver vare har en EAN."""
    v = _hent(client, q="testbrød")[0]
    assert set(v.keys()) == {"ean", "navn", "maerke", "billede", "status",
                              "stale", "problemer", "spor"}
    assert v["ean"]


def test_svaret_er_sorteret_det_gode_foerst(client):
    navne = [p["navn"] for p in _hent(client, q="testbrød")]
    # safe (Grøn) foran de uafklarede (Rug, Gammel), unsafe (Hvid) sidst
    assert navne.index("Testbrød Grøn") < navne.index("Testbrød Rug")
    assert navne.index("Testbrød Rug") < navne.index("Testbrød Hvid")
    assert navne[-1] == "Testbrød Hvid"


def test_kobling_ruten_findes_ikke_laengere(client):
    """POST /api/liste/{id}/stregkode hørte til arket — den er fjernet
    sammen med resten af mekanismen, ikke kun rækkerne."""
    r = client.post("/api/liste/1/stregkode", json={"ean": "5799990000001"})
    assert r.status_code == 404


def test_product_visningsnavn_foelger_navn_manuelt():
    """
    Reglen bor på modellen (Product.visningsnavn), ikke kun i
    _visningsnavn() i app/main.py — se test_filter_products_bruger_
    visningsnavn herunder for hvorfor det er sat der, ikke kun i en
    hjælpefunktion, der kan glemmes ét sted mens den huskes et andet.
    """
    from app.models import Product as P
    p = P(ean="0", name="Open Food Facts' gæt")
    assert p.visningsnavn == "Open Food Facts' gæt"
    p.navn_manuelt = "Familiens eget navn"
    assert p.visningsnavn == "Familiens eget navn", "navn_manuelt vandt ikke i visningsnavn"


def test_filter_products_bruger_visningsnavn(client):
    """
    `filter_products()` (app/ingredients.py, bruges af /api/products, som
    »Fri for«-fanen kalder) returnerede før `p.name` rå — en vare, familien
    selv har navngivet (product.navn_manuelt), stod dér som »Uden navn«,
    selvom scan-skærmen og /api/soeg viste navnet fint.
    """
    from app import ingredients as ix

    ean = "5799990000099"
    with SessionLocal() as db:
        db.add(Product(ean=ean, name=None, navn_manuelt="Familiens Eget Navn",
                       ingredients_text="Vand, ualmindeligtsjaeldeningrediens99"))
        db.flush()
        ix.index_product(db, ean, None, [], "Vand, ualmindeligtsjaeldeningrediens99")
        db.commit()
        rows = ix.filter_products(db, include=["ualmindeligtsjaeldeningrediens99"], limit=50)
    assert len(rows) == 1, "testens egen ingrediens matchede uventet flere varer"
    assert rows[0]["ean"] == ean
    assert rows[0]["name"] == "Familiens Eget Navn", (
        "filter_products() viser stadig p.name rå i stedet for p.visningsnavn"
    )
