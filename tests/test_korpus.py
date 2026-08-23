"""
GET /api/korpus — grundlaget for at måle OCR-arbejdet mod familiens egne
fotos i stedet for mod opdigtet tekst. Se ROADMAP.md og
.claude/skills/ocr-deklarationer/SKILL.md.

Ruten er ren læsning og ændrer intet — den kan derfor aldrig gøre en vare
grøn, og hører ikke til i allergen-domænet.
"""
import io
import json
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
from sqlalchemy import select

from app.auth import hash_password
from app.db import SessionLocal, default_household, init_db
from app.main import app
from app.models import Product, ProductPhoto, User

PW = "korrekt-hest-batteri-haefteklamme"

# Fire varer, én for hver kombination korpusset skal skelne imellem.
EAN_KUN_FOTO = "5701111100001"          # foto, ingen deklaration
EAN_OFF_TEKST = "5701111100002"         # deklaration fra OFF, intet foto
EAN_MENNESKELAEST = "5701111100003"     # foto + menneskeverificeret deklaration
EAN_INGEN_AF_DELENE = "5701111100004"   # hverken foto eller deklaration


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (180, 40, 60)).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def opsat():
    init_db()
    with SessionLocal() as db:
        hh = default_household(db)
        if not db.query(User).filter(User.email == "korpus-familie@example.dk").count():
            db.add(User(household_id=hh.id, email="korpus-familie@example.dk",
                        name="Familie", password_hash=hash_password(PW), role="curator"))
        if not db.query(User).filter(User.email == "korpus-bidragyder@example.dk").count():
            db.add(User(household_id=hh.id, email="korpus-bidragyder@example.dk",
                        name="Bidragyder", password_hash=hash_password(PW),
                        role="contributor"))
        db.commit()

        if db.get(Product, EAN_OFF_TEKST) is None:
            db.add(Product(ean=EAN_OFF_TEKST, name="OFF-vare", source="off",
                           ingredients_text="Hvedemel, vand, salt."))
        if db.get(Product, EAN_MENNESKELAEST) is None:
            db.add(Product(ean=EAN_MENNESKELAEST, name="Rettet vare", source="manual",
                           ingredients_text="Mælk, sukker."))
        if db.get(Product, EAN_INGEN_AF_DELENE) is None:
            db.add(Product(ean=EAN_INGEN_AF_DELENE, name="Tom vare", source="off"))
        db.commit()

    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": "korpus-bidragyder@example.dk",
                                            "password": PW}).status_code == 200
    r = c.post(f"/api/products/{EAN_KUN_FOTO}/foto?slags=deklaration",
               files={"image": ("d.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200, r.text
    r = c.post(f"/api/products/{EAN_MENNESKELAEST}/foto?slags=deklaration",
               files={"image": ("d.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200, r.text

    yield

    with SessionLocal() as db:
        for ean in (EAN_KUN_FOTO, EAN_OFF_TEKST, EAN_MENNESKELAEST, EAN_INGEN_AF_DELENE):
            for foto in db.scalars(select(ProductPhoto).where(ProductPhoto.product_ean == ean)):
                db.delete(foto)
            p = db.get(Product, ean)
            if p is not None:
                db.delete(p)
        db.commit()


def _anonym():
    return TestClient(app)


def _som_bidragyder():
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": "korpus-bidragyder@example.dk",
                                            "password": PW}).status_code == 200
    return c


def _som_familie():
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": "korpus-familie@example.dk",
                                            "password": PW}).status_code == 200
    return c


def test_anonym_kan_ikke_hente_korpus(opsat):
    assert _anonym().get("/api/korpus").status_code == 401


def test_bidragyder_kan_hente_korpus(opsat):
    """Kernen i opgaven: en dedikeret lav-rettighed-konto til OCR-arbejdet
    skal kunne læse korpusset, uden at kunne bekræfte noget som helst."""
    r = _som_bidragyder().get("/api/korpus")
    assert r.status_code == 200, r.text


def test_familien_kan_ogsaa_hente_korpus(opsat):
    assert _som_familie().get("/api/korpus").status_code == 200


def _find(varer, ean):
    for v in varer:
        if v["ean"] == ean:
            return v
    raise AssertionError(f"{ean} er ikke med i korpusset")


def test_korpus_medtager_kun_varer_med_foto_eller_deklaration(opsat):
    varer = _som_familie().get("/api/korpus").json()
    eaner = {v["ean"] for v in varer}
    assert EAN_KUN_FOTO in eaner
    assert EAN_OFF_TEKST in eaner
    assert EAN_MENNESKELAEST in eaner
    assert EAN_INGEN_AF_DELENE not in eaner, (
        "en vare uden foto og uden deklaration hører ikke til i et OCR-korpus"
    )


def test_deklaration_gik_gennem_bekraeftelse_skelner_faktisk(opsat):
    """Feltet skelner mellem `product.source == "off"` og `"manual"` —
    IKKE mellem "facit" og "ikke facit" (se docstringen for korpus() i
    app/main.py for hvorfor det ikke er nok til det)."""
    varer = _som_familie().get("/api/korpus").json()

    off_vare = _find(varer, EAN_OFF_TEKST)
    assert off_vare["deklaration"] == "Hvedemel, vand, salt."
    assert off_vare["deklaration_gik_gennem_bekraeftelse"] is False

    rettet_vare = _find(varer, EAN_MENNESKELAEST)
    assert rettet_vare["deklaration"] == "Mælk, sukker."
    assert rettet_vare["deklaration_gik_gennem_bekraeftelse"] is True

    kun_foto = _find(varer, EAN_KUN_FOTO)
    assert kun_foto["deklaration"] is None
    assert len(kun_foto["fotos"]) == 1
    assert kun_foto["fotos"][0]["slags"] == "deklaration"
    assert kun_foto["fotos"][0]["url"].startswith(f"/api/products/{EAN_KUN_FOTO}/foto/")


def test_taget_af_er_aldrig_med(opsat):
    """`taget_af`/`taget_af_user_id` er en voksens navn og er irrelevant
    for OCR-arbejdet — feltet må ALDRIG stå i svaret, uanset hvem der
    spørger (heller ikke familien selv, som ellers ser det andre steder,
    fx /api/scan)."""
    for klient in (_som_bidragyder(), _som_familie()):
        r = klient.get("/api/korpus")
        assert r.status_code == 200
        rå = json.dumps(r.json())
        assert "taget_af" not in rå, "taget_af lækker gennem /api/korpus"
