"""
Additiv mini-migrering.

Baggrund: `create_all` opretter kun tabeller, der mangler helt. En ny
kolonne på en tabel, der allerede findes, laver den aldrig — og så giver
et ellers uskyldigt deploy "no such column" på jeres database. Det skete
mellem 0.9.0 og 0.10.0 med `imported_product.valideret_mod` — den tabel
er selv fjernet igen i 0.25.0 (se _drop_imported_product_tabellen() i
app/db.py), så testen her demonstrerer nu samme mekanik på `product`, som
faktisk fik `navn_manuelt` tilføjet på præcis denne måde (se kommentaren
på Product.navn_manuelt i app/models.py).
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

import pytest
from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    inspect,
    text,
)


def test_manglende_kolonne_tilfoejes_uden_at_roere_data(tmp_path, monkeypatch):
    """Simulerer den virkelige situation: en gammel tabel med FÆRRE
    kolonner end modellen, og rækker i den, som ikke må gå tabt."""
    import app.db as dbmod

    url = f"sqlite:///{tmp_path}/gammel.db"
    eng = create_engine(url)

    # "Gammel" udgave af product: uden navn_manuelt (tilføjet mellem
    # 0.9.0 og 0.10.0 — se app/models.py).
    gammel = MetaData()
    Table(
        "product", gammel,
        Column("ean", String, primary_key=True),
        Column("name", String),
    ).create(eng)
    with eng.begin() as con:
        con.execute(text("INSERT INTO product (ean, name) VALUES ('5701234500001', 'Listebrød')"))

    monkeypatch.setattr(dbmod, "engine", eng)
    dbmod.tilfoej_manglende_kolonner()

    kolonner = {c["name"] for c in inspect(eng).get_columns("product")}
    assert "navn_manuelt" in kolonner
    # `source` har en skalar default ("off") på modellen — den skal
    # være BACKFILLET på den eksisterende række, ikke kun NULL.
    assert "source" in kolonner
    with eng.connect() as con:
        assert con.execute(text("SELECT name FROM product")).scalar() == "Listebrød"
        assert con.execute(text("SELECT source FROM product")).scalar() == "off"


def test_koersel_to_gange_er_harmloes(tmp_path, monkeypatch):
    import app.db as dbmod
    from app.models import Base

    eng = create_engine(f"sqlite:///{tmp_path}/frisk.db")
    Base.metadata.create_all(eng)
    monkeypatch.setattr(dbmod, "engine", eng)
    dbmod.tilfoej_manglende_kolonner()
    dbmod.tilfoej_manglende_kolonner()   # må ikke fejle på anden kørsel


def test_foto_unik_constraint_fjernes_uden_datatab(tmp_path, monkeypatch):
    """
    0.21.0: UniqueConstraint(household_id, product_ean, slags) er fjernet
    fra ProductPhoto (se app/models.py) — en bidragyder skal ALTID kunne
    lægge et nyt billede til, uden at det gamle forsvinder. `create_all()`
    rører aldrig en tabel, der allerede findes, så begrænsningen skal
    fjernes eksplicit fra en database, der blev oprettet før 0.21.0.

    Simulerer den ægte opgraderingssituation: en gammel product_photo med
    begrænsningen stadig siddende, og en række i den, som ikke må gå tabt.
    SQLite har ingen ALTER TABLE ... DROP CONSTRAINT, så vejen er en
    tabelgenopbygning — se _fjern_foto_unik_constraint() i app/db.py.
    """
    import app.db as dbmod

    eng = create_engine(f"sqlite:///{tmp_path}/gammel_foto.db")

    gammel = MetaData()
    Table(
        "product_photo", gammel,
        Column("id", Integer, primary_key=True),
        # `index=True` — IKKE pynt. Uden de to indeks bestod denne test på
        # kode, der ødelagde enhver rigtig database: SQLite flytter ikke
        # indeks med ved ALTER TABLE ... RENAME, så ombygningen fejlede på
        # et navnesammenstød, som en håndskrevet tabel uden indeks aldrig
        # kunne fremkalde. Fikstureret skal have den form, produktionen
        # har — ellers beviser en grøn test ingenting.
        Column("household_id", Integer, index=True),
        Column("product_ean", String(20), index=True),
        Column("slags", String(16)),
        Column("fil", String(200)),
        Column("bredde", Integer),
        Column("hoejde", Integer),
        Column("taget_af", String(120)),
        Column("taget_at", DateTime),
        UniqueConstraint("household_id", "product_ean", "slags"),
    ).create(eng)
    assert {x["name"] for x in inspect(eng).get_indexes("product_photo")} == {
        "ix_product_photo_household_id", "ix_product_photo_product_ean"
    }, "fikstureret ligner ikke den database, appen selv laver"
    with eng.begin() as con:
        con.execute(text(
            "INSERT INTO product_photo (household_id, product_ean, slags, fil, taget_at) "
            "VALUES (1, '5701234500001', 'front', 'foerste.jpg', '2026-01-01 12:00:00')"
        ))

    # Begrænsningen virker på den GAMLE tabel — modprøven, så testen
    # rent faktisk beviser noget.
    with pytest.raises(Exception):
        with eng.begin() as con:
            con.execute(text(
                "INSERT INTO product_photo (household_id, product_ean, slags, fil) "
                "VALUES (1, '5701234500001', 'front', 'andet.jpg')"
            ))

    monkeypatch.setattr(dbmod, "engine", eng)
    # Samme rækkefølge som init_db(): kolonnen skal med FØR ombygningen,
    # ellers mangler den i den nye tabel.
    dbmod.tilfoej_manglende_kolonner()
    dbmod._fjern_foto_unik_constraint()

    kolonner = {c["name"] for c in inspect(eng).get_columns("product_photo")}
    assert "taget_af_user_id" in kolonner, "kolonnen forsvandt under ombygningen"
    assert not inspect(eng).get_unique_constraints("product_photo"), (
        "den gamle begrænsning findes stadig efter ombygningen"
    )
    assert {x["name"] for x in inspect(eng).get_indexes("product_photo")} == {
        "ix_product_photo_household_id", "ix_product_photo_product_ean"
    }, "indeksene overlevede ikke ombygningen — opslag pr. vare bliver et fuldt tabelscan"

    with eng.begin() as con:
        # Samme (husstand, vare, slags) må nu gerne ligge to gange.
        con.execute(text(
            "INSERT INTO product_photo (household_id, product_ean, slags, fil, taget_at) "
            "VALUES (1, '5701234500001', 'front', 'nyt.jpg', '2026-01-02 09:00:00')"
        ))
        filer = con.execute(text(
            "SELECT fil FROM product_photo WHERE product_ean='5701234500001' ORDER BY id"
        )).scalars().all()
    assert filer == ["foerste.jpg", "nyt.jpg"], "den gamle række gik tabt under ombygningen"

    # Harmløs at køre igen — fx et deploy, der starter appen to gange.
    dbmod._fjern_foto_unik_constraint()


def _gammel_fototabel(eng):
    """product_photo, som 0.20.0's create_all() faktisk byggede den:
    med begrænsningen OG med de to indeks fra `index=True`."""
    md = MetaData()
    Table(
        "product_photo", md,
        Column("id", Integer, primary_key=True),
        Column("household_id", Integer, index=True),
        Column("product_ean", String(20), index=True),
        Column("slags", String(16)),
        Column("fil", String(200)),
        Column("bredde", Integer),
        Column("hoejde", Integer),
        Column("taget_af", String(120)),
        Column("taget_at", DateTime),
        UniqueConstraint("household_id", "product_ean", "slags"),
    ).create(eng)
    with eng.begin() as con:
        con.execute(text(
            "INSERT INTO product_photo (household_id, product_ean, slags, fil, taget_at) "
            "VALUES (1, '5701234500001', 'front', 'mormors_foto.jpg', '2026-01-01 12:00:00')"
        ))


def test_afbrudt_ombygning_ruller_helt_tilbage(tmp_path, monkeypatch):
    """
    Fejler ombygningen midtvejs, skal databasen bagefter være PRÆCIS som
    før — rækker og indeks i behold.

    Det er den her, der gør fejlen ufarlig i stedet for fatal. Første
    udgave af migreringen omdøbte tabellen og fejlede så på et
    indeksnavn; pysqlite committer DDL uden for transaktionen, så
    omdøbningen stod fast, familiens fotos lå i en tabel ingen kiggede
    i, og NÆSTE opstart lykkedes med en tom tabel. Ingen fejlmeddelelse,
    ingen fotos.

    Ombygningen kører derfor på en rå forbindelse med et eksplicit
    BEGIN. Her sprænges den bevidst efter DROP og RENAME — det farligste
    tidspunkt — og databasen skal stå uændret bagefter.
    """
    import app.db as dbmod
    from app.models import ProductPhoto

    eng = create_engine(f"sqlite:///{tmp_path}/afbrudt.db")
    _gammel_fototabel(eng)
    monkeypatch.setattr(dbmod, "engine", eng)
    dbmod.tilfoej_manglende_kolonner()

    class Sprængladning:
        """Fyrer, når ombygningen når til indeksene — efter DROP + RENAME."""
        def __iter__(self):
            raise RuntimeError("simuleret nedbrud midt i ombygningen")

    monkeypatch.setattr(ProductPhoto.__table__, "indexes", Sprængladning())
    with pytest.raises(RuntimeError):
        dbmod._fjern_foto_unik_constraint()

    i = inspect(eng)
    assert not i.has_table("product_photo_ny"), "skrabetabellen blev efterladt"
    assert not i.has_table("product_photo_gammel"), "en halv ombygning blev efterladt"
    assert i.get_unique_constraints("product_photo"), (
        "databasen er halvt ændret — rollback tog ikke det hele"
    )
    assert {x["name"] for x in i.get_indexes("product_photo")} == {
        "ix_product_photo_household_id", "ix_product_photo_product_ean"
    }, "indeksene forsvandt ved rollback"
    with eng.connect() as con:
        filer = con.execute(text("SELECT fil FROM product_photo")).scalars().all()
    assert filer == ["mormors_foto.jpg"], "fotorækken gik tabt ved et rollback"


def test_appen_naegter_at_starte_paa_en_halv_ombygning(tmp_path, monkeypatch):
    """
    En database, hvor en TIDLIGERE udgave af migreringen nåede at omdøbe
    tabellen og så gik ned, må ikke starte stiltiende.

    Det var det virkelig farlige: `create_all()` så en `product_photo`,
    der fandtes, migreringen fandt ingen begrænsning på den tomme tabel
    og gik hjem, healthchecket blev grønt — og appen så ud, som om
    familien aldrig havde taget et billede. Rækkerne ligger der endnu.
    En opstart, der stopper og siger hvor, er langt bedre.
    """
    import app.db as dbmod

    eng = create_engine(f"sqlite:///{tmp_path}/halv.db")
    _gammel_fototabel(eng)
    with eng.begin() as con:
        con.execute(text("ALTER TABLE product_photo RENAME TO product_photo_gammel"))
    monkeypatch.setattr(dbmod, "engine", eng)

    with pytest.raises(RuntimeError) as fejl:
        dbmod._vagt_mod_afbrudt_fotoombygning()
    besked = str(fejl.value)
    assert "product_photo_gammel" in besked, "beskeden siger ikke hvilken tabel"
    assert "1 fotorække" in besked, "beskeden siger ikke hvor meget der står på spil"
