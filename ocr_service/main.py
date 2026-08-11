"""
OCR-tjeneste — pixels til tegn. Intet andet.

Kører i sin EGEN container, af tre grunde:

1. onnxruntime er native kode. Et segfault her må ikke tage web-appen
   og databasen med sig.
2. Web-appens image bliver ved med at være lille og hurtigt at rulle ud;
   modellerne (~800 MB) ligger for sig.
3. OCR er CPU-tungt og kan få sin egen begrænsning uden at sulte appen.

Tjenesten kender INTET til dansk orddannelse, allergener eller domme.
Den returnerer rå tekst og konfidens; al betydning lægges på i appen
(app/ocr.py: sektionsudklip, oprydning — og matcher.py: allergenerne).
Den grænse er med vilje: sikkerhedslogikken bor ét sted.
"""

from __future__ import annotations

import io
import time

from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image, ImageOps

app = FastAPI(title="AllergiScan OCR", version="1.0.0")

MAX_SIDE = 3200          # samme normalisering som Tesseract-vejen i appen
_engine = None


def engine():
    """Indlæses dovent: containeren skal svare på /healthz med det samme."""
    global _engine
    if _engine is None:
        from rapidocr import RapidOCR

        _engine = RapidOCR()
    return _engine


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/klar")
def klar():
    """Er modellerne indlæst? Første OCR-kald tager ~5 s ekstra uden."""
    return {"klar": _engine is not None}


@app.post("/ocr")
async def ocr(image: UploadFile = File(...)):
    data = await image.read()
    if len(data) > 12 * 1024 * 1024:
        raise HTTPException(413, "Billedet er for stort (max 12 MB).")
    try:
        img = Image.open(io.BytesIO(data))
    except Exception as e:
        return {"ok": False, "error": f"Kunne ikke læse billedet: {e}"}

    # EXIF-rotation skal med — telefoner gemmer stående billeder liggende.
    # PP-OCR klarer selv tekst på tværs, så ingen OSD-gymnastik her.
    img = ImageOps.exif_transpose(img).convert("RGB")
    w, h = img.size
    if max(w, h) > MAX_SIDE:
        f = MAX_SIDE / max(w, h)
        img = img.resize((int(w * f), int(h * f)), Image.LANCZOS)

    t0 = time.time()
    try:
        import numpy as np

        res = engine()(np.array(img))
    except Exception as e:
        return {"ok": False, "error": f"OCR fejlede: {e}"}

    if not res or not res.txts:
        return {"ok": True, "text": "", "confidence": 0.0, "linjer": 0,
                "engine": "rapidocr", "sekunder": round(time.time() - t0, 2)}

    scores = [float(s) for s in (res.scores or [])]
    return {
        "ok": True,
        # Linjer adskilt med newline: appens sektionsudklip og oprydning
        # regner med linjeskift, præcis som Tesseracts output.
        "text": "\n".join(res.txts),
        "confidence": round(100 * sum(scores) / len(scores), 1) if scores else 0.0,
        "linjer": len(res.txts),
        "engine": "rapidocr",
        "sekunder": round(time.time() - t0, 2),
    }
