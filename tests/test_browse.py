"""
Gennemse-listen (/api/browse) deler domslogik med scan-skærmen, og det
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
    r = client.get("/api/browse", params={"allergens": "maelkeprotein", **params})
    assert r.status_code == 200
    return r.json()["products"]


def test_soegning_paa_kategoriord_rammer_alle_broed(client):
    navne = {p["name"] for p in _hent(client, q="testbrød")}
    assert navne == {"Testbrød Hvid", "Testbrød Rug", "Testbrød Grøn", "Testbrød Gammel"}


def test_kun_sikre_viser_kun_manuelt_bekraeftede(client):
    hits = _hent(client, q="testbrød", status="safe")
    assert [p["name"] for p in hits] == ["Testbrød Grøn"]


def test_ikke_tilladt_viser_varen_med_allergenet(client):
    hits = _hent(client, q="testbrød", status="unsafe")
    assert [p["name"] for p in hits] == ["Testbrød Hvid"]
    assert "Mælkeprotein" in hits[0]["problemer"]


def test_foraeldet_dom_er_ALDRIG_sikker(client):
    """Opskriften ændrede sig efter godkendelsen — varen må ikke stå som
    sikker, uanset at der findes en manuel FREE-dom. Samme regel som
    scan-skærmen, og den vigtigste egenskab ved hele listen."""
    sikre = {p["name"] for p in _hent(client, q="testbrød", status="safe")}
    assert "Testbrød Gammel" not in sikre
    uafklarede = {p["name"]: p for p in _hent(client, q="testbrød", status="uafklaret")}
    assert "Testbrød Gammel" in uafklarede
    assert uafklarede["Testbrød Gammel"]["stale"] is True


def test_uafklaret_samler_resten(client):
    navne = {p["name"] for p in _hent(client, q="testbrød", status="uafklaret")}
    assert navne == {"Testbrød Rug", "Testbrød Gammel"}


def test_tom_soegning_og_ugyldig_status(client):
    assert _hent(client, q="findesikke-xyzzy") == []
    r = client.get("/api/browse", params={"status": "grøn"})
    assert r.status_code == 400
