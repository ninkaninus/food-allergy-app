"""
Fælles opsætning for hele suiten.

Den vigtigste opgave: **testene må aldrig kalde det rigtige Open Food
Facts.** `tests/test_auth.py` gjorde det, og OFF svarer 429 efter et par
kald i træk — så gav en ukendt stregkode `error` i stedet for `unknown`,
og `test_unknown_barcode_returns_no_verdicts` fejlede. Den test er én af
de fire invariant-tests, og CI udgiver kun et image, hvis de er grønne.
En rød CI, der skyldes OFF's humør og ikke koden, lærer folk at trykke
»kør igen« — og så er porten reelt væk.

Stubben svarer som OFF gør på en stregkode, den ikke kender: found=False
UDEN fejl. Netop den skelnen er hele pointen i `_ensure_product()`.
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
os.environ.setdefault("CHECK_PWNED_PASSWORDS", "0")
# Peger et dødt sted hen, så et glemt kald fejler hurtigt i stedet for
# at gå på nettet. Stubben nedenfor betyder, at det normalt ikke sker.
os.environ.setdefault("OFF_BASE_URL", "http://127.0.0.1:9")
# Suiten kører på SQLite, og det skal siges udtrykkeligt siden 0.21.1:
# uden DATABASE_URL nægter app/db.py at starte frem for at opfinde en tom
# database. Præcis dét er meningen — men en testkørsel er netop det ene
# sted, hvor en frisk, tom database er det rigtige.
os.environ.setdefault("TILLAD_SQLITE", "1")

import pytest
from sqlalchemy import event

from app.off import Lookup

# SQLite håndhæver som udgangspunkt INGEN fremmednøgler — det skal slås
# til pr. forbindelse. Uden det her så en upload af et deklarationsfoto
# for en stregkode, appen ikke kender, ud til at virke i testene, mens
# den samme kode fejlede med IntegrityError mod produktionens Postgres
# (se ReviewItem's docstring i app/models.py for den samme lektie i en
# anden tabel, opdaget ved en flytning i 0.16.1). Registreres FØR nogen
# test åbner en forbindelse — se _sqlite_fk_paa herunder.
from app.db import engine as _engine

if _engine.dialect.name == "sqlite":
    @event.listens_for(_engine, "connect")
    def _sqlite_fk_paa(dbapi_con, con_record):
        dbapi_con.execute("PRAGMA foreign_keys=ON")


@pytest.fixture(autouse=True, scope="session")
def _ingen_rigtig_off():
    """Ingen test når nettet, medmindre den selv erstatter stubben."""
    import app.off as off
    import app.main as main

    async def stub(ean: str, timeout: float = 8.0) -> Lookup:
        return Lookup(found=False, error=None)

    aegte = off.fetch_product
    off.fetch_product = stub
    main.off.fetch_product = stub
    yield
    off.fetch_product = aegte
    main.off.fetch_product = aegte
