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


def i_spalter(boxes, txts) -> list[str]:
    """
    Linjer i LÆSEREKKEFØLGE, ikke i højderækkefølge.

    Etiketter har næsten altid flere spalter, og OCR'en returnerer
    boksene sorteret efter position — så en tolinjers ingrediensliste i
    venstre spalte bliver flettet med opbevaringsteksten i højre:

        «Ingredienser:»            venstre
        «højst +5 °C.»             HØJRE, flettet ind
        «93 % grisekød, salt,»     venstre

    Efter fletningen kan appen hverken finde begyndelsen eller slutningen
    på ingredienslisten, og halvdelen af etiketten kommer med.

    Spalterne findes som huller i boksenes x-midtpunkter. Skævt
    fotograferede etiketter driver vandret ned ad billedet, så et fast
    lodret snit dur ikke — men midtpunkterne klumper stadig, og hullet
    mellem klumperne er stort i forhold til teksthøjden. Er der ikke et
    tydeligt hul, er det én spalte, og rækkefølgen står som den er.
    """
    # boxes er et numpy-array; `not boxes` ville sammenligne elementvis.
    if boxes is None or len(boxes) < 4 or len(boxes) != len(txts):
        return list(txts)

    linjer = []
    for boks, txt in zip(boxes, txts):
        pts = [(float(p[0]), float(p[1])) for p in boks]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        # Linjehøjden er venstre kants længde, IKKE boksens højde. En skævt
        # fotograferet etiket giver hældende bokse, hvis boksehøjde er
        # dobbelt så stor som teksten — målt 103 px for en linje på 89.
        (x0, y0), (_, _), (_, _), (x3, y3) = pts[0], pts[1], pts[2], pts[3]
        hoejde = ((x3 - x0) ** 2 + (y3 - y0) ** 2) ** 0.5
        linjer.append({
            "txt": txt,
            "midte": (min(xs) + max(xs)) / 2,
            "y": min(ys),
            "y2": max(ys),
            "hoejde": hoejde or (max(ys) - min(ys)),
        })

    median_hoejde = sorted(l["hoejde"] for l in linjer)[len(linjer) // 2] or 1
    bredde = max(l["midte"] for l in linjer) - min(l["midte"] for l in linjer)
    # Et spaltehul er både bredt i forhold til teksten OG i forhold til
    # etiketten. Begge krav skal med: kun det første splitter ernærings-
    # tabellers etiket/værdi-par, kun det andet misser smalle etiketter.
    graense = max(2.5 * median_hoejde, 0.12 * bredde)

    def side_om_side(a: list[dict], b: list[dict]) -> bool:
        """Rigtige spalter står ved siden af hinanden — altså overlapper
        de lodret. Gør de ikke det, er det ét afsnit over et andet, og et
        lodret snit ville stumpe teksten i stykker."""
        a0, a1 = min(l["y"] for l in a), max(l["y2"] for l in a)
        b0, b1 = min(l["y"] for l in b), max(l["y2"] for l in b)
        overlap = max(0.0, min(a1, b1) - max(a0, b0))
        mindste = min(a1 - a0, b1 - b0) or 1
        return overlap / mindste >= 0.4

    def del_op(gruppe: list[dict], dybde: int = 0) -> list[list[dict]]:
        if dybde >= 2 or len(gruppe) < 6:      # højst tre spalter
            return [gruppe]
        efter_x = sorted(gruppe, key=lambda l: l["midte"])
        bedst, bedst_hul = None, 0.0
        for i in range(3, len(efter_x) - 2):   # mindst 3 linjer i hver
            hul = efter_x[i]["midte"] - efter_x[i - 1]["midte"]
            if hul > bedst_hul:
                bedst, bedst_hul = i, hul
        if bedst is None or bedst_hul < graense:
            return [gruppe]
        venstre, hoejre = efter_x[:bedst], efter_x[bedst:]
        if not side_om_side(venstre, hoejre):
            return [gruppe]
        return del_op(venstre, dybde + 1) + del_op(hoejre, dybde + 1)

    spalter = del_op(linjer)
    spalter.sort(key=lambda s: min(l["midte"] for l in s))
    ud = []
    for spalte in spalter:
        ud += [l["txt"] for l in sorted(spalte, key=lambda l: l["y"])]
    return ud


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
        "text": "\n".join(i_spalter(res.boxes, res.txts)),
        "confidence": round(100 * sum(scores) / len(scores), 1) if scores else 0.0,
        "linjer": len(res.txts),
        "engine": "rapidocr",
        "sekunder": round(time.time() - t0, 2),
    }
