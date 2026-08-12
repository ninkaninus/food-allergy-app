"""
Additiv mini-migrering.

Baggrund: `create_all` opretter kun tabeller, der mangler helt. En ny
kolonne på en tabel, der allerede findes, laver den aldrig — og så giver
et ellers uskyldigt deploy "no such column" på jeres database. Det skete
mellem 0.9.0 og 0.10.0 med `imported_product.valideret_mod`.
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

from sqlalchemy import Column, MetaData, String, Table, create_engine, inspect, text


def test_manglende_kolonne_tilfoejes_uden_at_roere_data(tmp_path, monkeypatch):
    """Simulerer den virkelige situation: en gammel tabel med FÆRRE
    kolonner end modellen, og rækker i den, som ikke må gå tabt."""
    import app.db as dbmod

    url = f"sqlite:///{tmp_path}/gammel.db"
    eng = create_engine(url)

    # "Gammel" udgave af imported_product: uden valideret_mod
    gammel = MetaData()
    Table(
        "imported_product", gammel,
        Column("id", String, primary_key=True),
        Column("navn", String),
    ).create(eng)
    with eng.begin() as con:
        con.execute(text("INSERT INTO imported_product (id, navn) VALUES ('1', 'Listebrød')"))

    monkeypatch.setattr(dbmod, "engine", eng)
    dbmod.tilfoej_manglende_kolonner()

    kolonner = {c["name"] for c in inspect(eng).get_columns("imported_product")}
    assert "valideret_mod" in kolonner
    assert "kategori" in kolonner
    with eng.connect() as con:
        assert con.execute(text("SELECT navn FROM imported_product")).scalar() == "Listebrød"


def test_koersel_to_gange_er_harmloes(tmp_path, monkeypatch):
    import app.db as dbmod
    from app.models import Base

    eng = create_engine(f"sqlite:///{tmp_path}/frisk.db")
    Base.metadata.create_all(eng)
    monkeypatch.setattr(dbmod, "engine", eng)
    dbmod.tilfoej_manglende_kolonner()
    dbmod.tilfoej_manglende_kolonner()   # må ikke fejle på anden kørsel
