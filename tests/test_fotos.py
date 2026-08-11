"""
Billeder af forsiden og deklarationen.

Vigtigst: et billede er dokumentation, ikke bevis. Det må aldrig kunne
gøre en vare grøn — kun et menneske, der har læst emballagen, kan det.
"""
import io
import os
import pathlib
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

TMP = tempfile.mkdtemp()
os.environ.setdefault("DATA_DIR", TMP)
os.environ.setdefault(
    "RULES_PATH",
    str(pathlib.Path(__file__).resolve().parents[1] / "data" / "allergens.yaml"),
)
os.environ.setdefault("COOKIE_SECURE", "0")
os.environ.setdefault("CHECK_PWNED_PASSWORDS", "0")

from fastapi.testclient import TestClient
from PIL import Image

from app.auth import hash_password
from app.db import SessionLocal, default_household, init_db
from app.main import app
from app.models import User, Verdict

PW = "korrekt-hest-batteri-haefteklamme"
EAN = "5701234500001"


def _jpeg(bredde=2400, hoejde=1800, farve=(180, 40, 60)):
    buf = io.BytesIO()
    Image.new("RGB", (bredde, hoejde), farve).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def client():
    init_db()
    with SessionLocal() as db:
        if not db.query(User).count():
            db.add(User(household_id=default_household(db).id, email="w@example.dk",
                        name="William", password_hash=hash_password(PW),
                        role="admin", source="local"))
            db.commit()
    return TestClient(app)


@pytest.fixture(scope="module")
def auth(client):
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": "w@example.dk", "password": PW})
    assert r.status_code == 200, r.text
    return c


def test_upload_kraever_login(client):
    r = client.post(f"/api/products/{EAN}/foto?slags=front",
                    files={"image": ("f.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code in (401, 403)


def test_foto_gemmes_skaleres_og_kan_hentes(auth, client):
    r = auth.post(f"/api/products/{EAN}/foto?slags=deklaration",
                  files={"image": ("d.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200, r.text
    fotos = r.json()["fotos"]
    assert "deklaration" in fotos
    # 2400 px ned til 1600 — en deklaration skal kunne læses, ikke fylde disken
    assert max(fotos["deklaration"]["bredde"], fotos["deklaration"]["hoejde"]) == 1600

    # åben læsning, som resten af appen
    h = client.get(f"/api/products/{EAN}/foto/deklaration")
    assert h.status_code == 200
    assert h.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(h.content)).size[0] == 1600


def test_ukendt_stregkode_faar_lov_at_have_billeder(auth):
    """Netop dér, hvor OFF ikke kender varen, er billedet mest værd."""
    ny = "5701234599999"
    assert auth.post(f"/api/products/{ny}/foto?slags=front",
                     files={"image": ("f.jpg", _jpeg(), "image/jpeg")}).status_code == 200
    d = auth.get(f"/api/scan/{ny}?allergens=maelkeprotein").json()
    assert "front" in d["fotos"]


def test_billede_goer_ikke_varen_groen(auth):
    """Invarianten, oversat til billeder: dokumentation er ikke bevis."""
    d = auth.get(f"/api/scan/{EAN}?allergens=maelkeprotein").json()
    assert d["result"] != "safe"
    with SessionLocal() as db:
        assert db.query(Verdict).filter(Verdict.product_ean == EAN).count() == 0


def test_nyt_foto_erstatter_det_gamle(auth, client):
    foer = client.get(f"/api/products/{EAN}/foto/deklaration").content
    auth.post(f"/api/products/{EAN}/foto?slags=deklaration",
              files={"image": ("d2.jpg", _jpeg(farve=(20, 90, 200)), "image/jpeg")})
    efter = client.get(f"/api/products/{EAN}/foto/deklaration").content
    assert foer != efter
    # stadig kun ét billede pr. slags — stien tages fra appen, ikke fra
    # modulets egen TMP: i fuld kørsel er det et andet testmodul, der har
    # sat DATA_DIR først.
    from app.db import DATA_DIR
    assert len(list((DATA_DIR / "billeder").glob(f"{EAN}_deklaration*"))) == 1


def test_ugyldig_slags_og_sti_afvises(auth, client):
    assert auth.post(f"/api/products/{EAN}/foto?slags=../../etc",
                     files={"image": ("x.jpg", _jpeg(), "image/jpeg")}).status_code == 400
    assert client.get(f"/api/products/{EAN}/foto/..%2F..%2Fetc%2Fpasswd").status_code in (400, 404)


def test_foto_kan_slettes(auth, client):
    assert auth.delete(f"/api/products/{EAN}/foto/front").status_code == 200
    assert client.get(f"/api/products/{EAN}/foto/front").status_code == 404
