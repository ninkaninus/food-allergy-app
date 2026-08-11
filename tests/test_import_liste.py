"""
Import af den gamle godkendt-liste (regneark uden EAN).

Det vigtigste, testene skal holde fast i: importen laver OPSLAGSRÆKKER,
aldrig domme. Verdict-tabellen skal være urørt efter import — listen
kender ingen stregkoder, og grøn kræver stadig et menneske med pakken
i hånden.
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
os.environ.setdefault("COOKIE_SECURE", "0")

from openpyxl import Workbook
from sqlalchemy import func, select

from app.cli import import_liste
from app.db import SessionLocal, default_household, init_db
from app.main import _gammel_liste_hint
from app.models import ImportedProduct, Verdict


def _ark(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Kiks P"
    ws.append(["Beskrivelse", "Producent", "Billede", "Butik", "Link", "I valgt butik", "Valideret"])
    ws.append(["Digestive", "Rema 1000", None, "Rema1000", "https://x", "Ja", "x"])
    ws.append(["Marie kiks", "Coop", None, "Super Brugsen", None, "Ja", None])
    ws.append([None, None, None, None, None, None, None])   # tom række springes over

    e = wb.create_sheet("Erstatningsprodukter")
    e.append(["Beskrivelse", "Producent", "Billede", "Butik", "Bruges  fx som erstatning for", "Link", "I valgt butik", "Valideret"])
    e.append(["Block (Smør)", "Naturlig", None, "Rema1000", "Smør", "https://y", "Ja", "x"])

    m = wb.create_sheet("MasterData")   # skal ignoreres
    m.append(["Butikker"])
    m.append(["Netto"])

    sti = tmp_path / "liste.xlsx"
    wb.save(sti)
    return str(sti)


def test_import_og_genimport(tmp_path):
    init_db()
    fil = _ark(tmp_path)
    import_liste(fil)
    import_liste(fil)   # genimport må ikke duplikere

    with SessionLocal() as db:
        hh = default_household(db)
        rows = list(db.scalars(
            select(ImportedProduct).where(ImportedProduct.household_id == hh.id)
        ))
        assert len(rows) == 3
        digestive = next(r for r in rows if r.navn == "Digestive")
        assert digestive.producent == "Rema 1000"
        assert digestive.valideret is True
        assert digestive.kategori == "Kiks P"
        marie = next(r for r in rows if r.navn == "Marie kiks")
        assert marie.valideret is False
        smoer = next(r for r in rows if r.navn == "Block (Smør)")
        assert smoer.erstatning_for == "Smør"
        assert not any(r.kategori == "MasterData" for r in rows)


def test_import_skaber_ingen_domme(tmp_path):
    """Invariantens naboklausul: listen har ingen EAN og må aldrig blive
    til domme. Grøn kræver stadig et menneske."""
    init_db()
    with SessionLocal() as db:
        foer = db.scalar(select(func.count()).select_from(Verdict))
    import_liste(_ark(tmp_path))
    with SessionLocal() as db:
        efter = db.scalar(select(func.count()).select_from(Verdict))
    assert efter == foer


def test_hint_matcher_paa_navn_og_producent(tmp_path):
    init_db()
    import_liste(_ark(tmp_path))
    with SessionLocal() as db:
        hh = default_household(db)
        # to betydende ord fælles ("marie" + "kiks")
        hits = _gammel_liste_hint(db, hh.id, "Marie kiks med fuldkorn", "Coop")
        assert any(h["navn"] == "Marie kiks" for h in hits)
        # ét ord + producentmatch
        hits = _gammel_liste_hint(db, hh.id, "Digestive", "Rema 1000")
        assert any(h["navn"] == "Digestive" for h in hits)
        # ingenting til fælles
        assert _gammel_liste_hint(db, hh.id, "Piskefløde", "Arla") == []
