"""
Migreringskommandoen: alle rækker skal med over, og et ikke-tomt mål
skal afvises — det er dine domme og brugere, den flytter.
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
from app.models import Base, Household, Product, User


def _kilde_med_data(tmp_path):
    url = f"sqlite:///{tmp_path}/kilde.db"
    eng = create_engine(url)
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        hh = Household(name="Test", token="testtoken")
        s.add(hh)
        s.flush()
        s.add(User(household_id=hh.id, email="a@b.dk", name="A",
                   password_hash="x", role="admin", source="local"))
        s.add(Product(ean="5701234567890", name="Testvare"))
        s.commit()
    return url


def test_migrate_flytter_alle_raekker(tmp_path):
    kilde = _kilde_med_data(tmp_path)
    maal = f"sqlite:///{tmp_path}/maal.db"
    migrate(kilde, maal)

    eng = create_engine(maal)
    with Session(eng) as s:
        assert s.scalar(select(func.count()).select_from(Household)) == 1
        assert s.scalar(select(func.count()).select_from(User)) == 1
        assert s.scalar(select(func.count()).select_from(Product)) == 1
        assert s.scalar(select(User.email)) == "a@b.dk"


def test_migrate_naegter_ikke_tomt_maal(tmp_path):
    kilde = _kilde_med_data(tmp_path)
    maal = f"sqlite:///{tmp_path}/optaget.db"
    migrate(kilde, maal)
    with pytest.raises(SystemExit):
        migrate(kilde, maal)   # anden kørsel: målet har rækker nu
