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

import pytest

from app.off import Lookup


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
