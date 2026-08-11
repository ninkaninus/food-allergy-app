"""
OCR-klienten: containeren først, Tesseract som faldskærm.

Det vigtigste her er faldskærmen. OCR er hovedvejen for familien —
Open Food Facts kender kun hver tiende af deres varer med ingrediensliste
— så en nede OCR-container må ikke betyde "ingen OCR".
"""
import os
import pathlib
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp())
os.environ.setdefault(
    "RULES_PATH",
    str(pathlib.Path(__file__).resolve().parents[1] / "data" / "allergens.yaml"),
)

from app import ocr_klient
from app.ocr import efterbehandl


def test_efterbehandl_klipper_sektion_ud():
    """Delt af begge veje: rå tekst -> deklaration."""
    r = efterbehandl("Ingredienser: Hvedemel, sukker.\nNæringsindhold pr. 100 g", 91.0)
    assert r["ok"]
    assert r["text"].startswith("Hvedemel")
    assert r["found_section"]
    assert r["confidence"] == 91.0


def test_bruger_tjenesten_naar_den_svarer(monkeypatch):
    monkeypatch.setattr(
        ocr_klient, "_fra_tjeneste",
        lambda data: {"ok": True, "text": "Ingredienser: mælk, sukker",
                      "confidence": 96.0, "engine": "rapidocr", "linjer": 2},
    )
    r = ocr_klient.laes_deklaration(b"noget")
    assert r["engine"] == "rapidocr"
    assert "mælk" in r["text"]
    assert r["confidence"] == 96.0


def test_falder_tilbage_til_tesseract_naar_tjenesten_er_nede(monkeypatch):
    monkeypatch.setattr(ocr_klient, "_fra_tjeneste", lambda data: None)
    monkeypatch.setattr(
        ocr_klient, "read_declaration",
        lambda data: {"ok": True, "text": "Hvedemel", "confidence": 71.0,
                      "found_section": False, "raw": "Hvedemel", "hint": "Læs teksten igennem."},
    )
    r = ocr_klient.laes_deklaration(b"noget")
    assert r["engine"] == "tesseract"
    assert r["text"] == "Hvedemel"
    # brugeren skal kunne se, at det var den svagere vej
    assert "svagere" in r["hint"]


def test_tom_tekst_fra_tjenesten_udloeser_faldskaerm(monkeypatch):
    """Svarer tjenesten 'ok' men uden tekst, er den ubrugelig — prøv Tesseract."""
    kaldt = {"n": 0}

    def falsk_read(data):
        kaldt["n"] += 1
        return {"ok": True, "text": "Hvedemel", "confidence": 70.0,
                "found_section": False, "raw": "Hvedemel", "hint": "ok"}

    monkeypatch.setattr(ocr_klient.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("nede")))
    monkeypatch.setattr(ocr_klient, "read_declaration", falsk_read)
    r = ocr_klient.laes_deklaration(b"noget")
    assert kaldt["n"] == 1
    assert r["engine"] == "tesseract"
