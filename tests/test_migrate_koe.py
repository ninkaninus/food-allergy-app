"""
Køen skal kunne huske en stregkode, vi IKKE har et produkt for.

Det er hele pointen med `reason="not_found"`: Open Food Facts kender
ikke varen, så der er ingen produktrække — men I skal stadig kunne se
"den her skal fotograferes" i køen.

SQLite håndhævede aldrig fremmednøglen, så fejlen lå skjult indtil
databasen skulle flyttes til Postgres, hvor 14 rigtige køposter ikke
kunne indsættes.
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

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.cli import migrate
from app.models import Base, Household, Product, ReviewItem


def _kilde(tmp_path, med_forældreløs_dom=False):
    url = f"sqlite:///{tmp_path}/kilde.db"
    eng = create_engine(url)
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        hh = Household(name="Test", token="t")
        s.add(hh)
        s.flush()
        s.add(Product(ean="5701234567890", name="Kendt vare"))
        # køpost for en stregkode UDEN produkt — det normale tilfælde
        s.add(ReviewItem(household_id=hh.id, product_ean="749301437831",
                         reason="not_found"))
        if med_forældreløs_dom:
            from app.models import Allergen, Verdict
            a = Allergen(slug="x", name_da="X")
            s.add(a)
            s.flush()
            s.add(Verdict(household_id=hh.id, product_ean="000000000000",
                          allergen_id=a.id, state="free", basis="manual"))
        s.commit()
    return url


def test_koepost_uden_produkt_migreres(tmp_path):
    """Det tilfælde, der fejlede i produktion."""
    maal = f"sqlite:///{tmp_path}/maal.db"
    migrate(_kilde(tmp_path), maal)

    eng = create_engine(maal)
    with Session(eng) as s:
        assert s.scalar(select(func.count()).select_from(ReviewItem)) == 1
        assert s.scalar(select(ReviewItem.product_ean)) == "749301437831"


def test_ægte_brudt_reference_stopper_foer_flytning(tmp_path):
    """En dom uden produkt ER en fejl — så skal migreringen sige det
    tydeligt og lade begge databaser urørte."""
    maal = f"sqlite:///{tmp_path}/maal2.db"
    with pytest.raises(SystemExit) as e:
        migrate(_kilde(tmp_path, med_forældreløs_dom=True), maal)
    assert "ikke påbegyndt" in str(e.value)

    eng = create_engine(maal)
    with Session(eng) as s:
        # intet flyttet — heller ikke tabellerne før den brudte
        assert s.scalar(select(func.count()).select_from(Product)) == 0
