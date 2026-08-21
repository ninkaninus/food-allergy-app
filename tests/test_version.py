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


def _overskrifter() -> list[str]:
    with TestClient(app) as c:
        r = c.get("/api/changelog")
    assert r.status_code == 200
    return re.findall(r"^## (\d+\.\d+\.\d+)", r.text, re.M)


def test_changelog_har_post_for_denne_version():
    """Den mekaniske halvdel af reglen: ingen version uden nyheder."""
    assert VERSION in _overskrifter()


def test_nyeste_post_er_denne_version():
    """
    Substring-testen alene fangede ikke, at posten skal stå ØVERST —
    »Nyheder« viser nyeste først, så en post længere nede læses som
    gammel nyt.
    """
    assert _overskrifter()[0] == VERSION


def test_ingen_dublet_overskrifter():
    """
    Var i drift: to sektioner hed »## 0.16.0«, fordi en ændring blev
    udgivet uden versionsbump. Begge blev vist i »Nyheder«, og man kunne
    ikke se på versionsnummeret, om telefonen havde rettelsen.
    """
    h = _overskrifter()
    assert len(h) == len(set(h)), f"samme version står to gange: {h}"


def test_diagnostik_kraever_login():
    """Serversti, antal brugere og rå OFF-fejl er ikke offentlige."""
    with TestClient(app) as c:
        assert c.get("/api/diagnostik").status_code == 401


def test_diagnostik_viser_database_og_taellinger():
    from app.auth import hash_password
    from app.db import SessionLocal, default_household
    from app.models import User

    pw = "korrekt-hest-batteri-haefteklamme"
    with SessionLocal() as db:
        if not db.query(User).filter(User.email == "diag@example.dk").count():
            db.add(User(household_id=default_household(db).id, email="diag@example.dk",
                        name="Diag", password_hash=hash_password(pw), role="curator"))
            db.commit()
    with TestClient(app) as c:
        assert c.post("/api/auth/login",
                      json={"email": "diag@example.dk", "password": pw}).status_code == 200
        r = c.get("/api/diagnostik")
    assert r.status_code == 200
    d = r.json()
    assert d["database"]["motor"] == "sqlite"
    assert d["database"]["skrivbar"] is True
    assert isinstance(d["database"]["produkter"], int)
    assert "kan_naas" in d["off"]
