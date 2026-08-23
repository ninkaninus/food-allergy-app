"""
Kommandolinjen. Kun det, der ikke allerede dækkes andre steder: at
`adduser` afviser en rolle, ingen vagt i appen kender noget til.
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

import pytest

from app.cli import adduser
from app.models import GYLDIGE_ROLLER


def test_adduser_afviser_ukendt_rolle():
    """
    `adduser x y viewr` må ikke stille et spørgsmål om adgangskode først
    — så tror man, oprettelsen lykkedes, indtil den fejler bagefter.
    Rollen tjekkes derfor FØR getpass overhovedet kaldes; lykkes den
    ikke, hænger testen på et input, der aldrig kommer.
    """
    with pytest.raises(SystemExit) as e:
        adduser("ny@example.dk", "Ny", role="viewr")
    besked = str(e.value)
    assert "viewr" in besked
    for rolle in GYLDIGE_ROLLER:
        assert rolle in besked, f"{rolle} nævnes ikke i fejlbeskeden"


def test_adduser_kender_de_tre_rigtige_roller():
    assert GYLDIGE_ROLLER == {"contributor", "curator", "admin"}
