"""
Klient til OCR-containeren, med Tesseract som faldskærm.

Rækkefølgen er ikke tilfældig. OCR er hovedvejen for jer: målt på 60 af
familiens varer kender Open Food Facts kun hver tiende med ingrediensliste.
Derfor må en nede OCR-container ikke betyde "ingen OCR" — så falder vi
tilbage til Tesseract i appens eget image. Dårligere, men ikke dødt.

Grænsen mellem de to lag: containeren leverer tegn, appen lægger
betydning på (sektionsudklip og oprydning her, allergener i matcher.py).
"""

from __future__ import annotations

import os

import httpx

from .ocr import efterbehandl, read_declaration

OCR_URL = os.getenv("OCR_URL", "http://ocr:8000")
OCR_TIMEOUT = float(os.getenv("OCR_TIMEOUT", "60"))


def _fra_tjeneste(data: bytes) -> dict | None:
    """Rå tekst fra OCR-containeren, eller None hvis den ikke svarer."""
    try:
        r = httpx.post(
            f"{OCR_URL}/ocr",
            files={"image": ("foto.jpg", data, "application/octet-stream")},
            timeout=OCR_TIMEOUT,
        )
        r.raise_for_status()
        svar = r.json()
    except Exception:
        return None
    if not svar.get("ok") or not (svar.get("text") or "").strip():
        return None
    return svar


def laes_deklaration(data: bytes) -> dict:
    """
    Læser en varedeklaration. Returnerer samme form som read_declaration,
    plus 'engine' så frontend og logs kan se, hvilken vej der blev brugt.
    """
    svar = _fra_tjeneste(data)
    if svar is not None:
        ud = efterbehandl(svar["text"], svar.get("confidence", 0.0))
        ud["engine"] = svar.get("engine", "rapidocr")
        ud["linjer"] = svar.get("linjer", 0)
        return ud

    ud = read_declaration(data)
    ud["engine"] = "tesseract"
    if ud.get("ok"):
        ud["hint"] = (ud.get("hint", "") + " (OCR-tjenesten svarede ikke — "
                      "brugte den indbyggede læsning, som er svagere.)").strip()
    return ud
