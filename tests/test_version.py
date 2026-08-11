"""
Version og release notes følges ad — det er reglen fra CLAUDE.md, og den
håndhæves her: bumper man VERSION uden en changelog-post (eller omvendt),
fejler suiten, og så bygges der intet image.
"""
import os
import pathlib
import re
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp())
os.environ.setdefault(
    "RULES_PATH",
    str(pathlib.Path(__file__).resolve().parents[1] / "data" / "allergens.yaml"),
)
os.environ.setdefault("COOKIE_SECURE", "0")

from fastapi.testclient import TestClient

from app.main import app
from app.version import VERSION


def test_version_endpoint_er_semver():
    with TestClient(app) as c:
        r = c.get("/api/version")
    assert r.status_code == 200
    assert r.json()["version"] == VERSION
    assert re.fullmatch(r"\d+\.\d+\.\d+", VERSION)


def test_changelog_har_post_for_denne_version():
    """Den mekaniske halvdel af reglen: ingen version uden nyheder."""
    with TestClient(app) as c:
        r = c.get("/api/changelog")
    assert r.status_code == 200
    assert f"## {VERSION}" in r.text


def test_diagnostik_viser_database_og_taellinger():
    with TestClient(app) as c:
        r = c.get("/api/diagnostik")
    assert r.status_code == 200
    d = r.json()
    assert d["database"]["motor"] == "sqlite"
    assert d["database"]["skrivbar"] is True
    assert isinstance(d["database"]["produkter"], int)
    assert "kan_naas" in d["off"]
