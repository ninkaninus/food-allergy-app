"""
OCR af varedeklarationer.

Bruges når en vare ikke findes i Open Food Facts, eller når OFF mangler
ingredienslisten — hvilket ifølge OFF's egne completeness-tal gælder
omkring to tredjedele af de danske varer.

OCR-resultatet bliver ALDRIG til en dom af sig selv. Det lander i
bekræftelsesskærmen som redigerbar tekst, et menneske retter fejlene,
og først derefter gemmes den. Tesseract læser 6-punkts tryk på krøllet
folie med omtrent den præcision, man kunne forvente, så det manuelle
gennemsyn er ikke en formalitet.

Kører lokalt i containeren. Ingen billeder forlader din server.
"""

from __future__ import annotations

import io
import re

import pytesseract
from PIL import Image, ImageFilter, ImageOps

# Deklarationen står næsten altid efter et af disse ord
SECTION_MARKERS = [
    "ingredienser", "ingrediens", "indhold", "sammensætning",
    "ingredients", "zutaten", "ingrediënten", "ainesosat",
]
END_MARKERS = [
    "næringsindhold", "næringsdeklaration", "nutrition", "energi ",
    "opbevares", "bedst før", "mindst holdbar", "nettovægt",
]


def preprocess(img: Image.Image, max_side: int = 2200) -> Image.Image:
    """
    Tesseract vil have stor, ren, høj-kontrast gråtone. Emballagefotos er
    små, skæve og har glans. Det her lukker en del af afstanden.
    """
    img = ImageOps.exif_transpose(img)
    img = img.convert("L")

    # Op i opløsning — Tesseract er trænet på ~300 dpi tryk
    w, h = img.size
    if max(w, h) < max_side:
        scale = max_side / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    img = ImageOps.autocontrast(img, cutoff=2)
    img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))

    # Otsu-tærskel fra histogrammet
    hist = img.histogram()
    total = sum(hist)
    sum_all = sum(i * hist[i] for i in range(256))
    sum_b = w_b = 0
    best_var, best_t = -1.0, 128
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / w_f
        var = w_b * w_f * (m_b - m_f) ** 2
        if var > best_var:
            best_var, best_t = var, t

    return img.point(lambda p: 255 if p > best_t else 0, mode="1")


def extract_section(text: str) -> str:
    """Klipper deklarationen ud af al den anden tekst på pakken."""
    low = text.lower()
    start = -1
    for m in SECTION_MARKERS:
        i = low.find(m)
        if i != -1 and (start == -1 or i < start):
            start = i + len(m)
    if start == -1:
        return text.strip()

    tail = text[start:]
    low_tail = tail.lower()
    end = len(tail)
    for m in END_MARKERS:
        i = low_tail.find(m)
        if i != -1:
            end = min(end, i)
    return tail[:end].lstrip(" :.-\n").strip()


def clean(text: str) -> str:
    """Retter de fejl, Tesseract laver systematisk på danske deklarationer."""
    t = text.replace("|", "l").replace("\u00ad", "")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\s*\n\s*", " ", t)          # linjeskift midt i en liste
    t = re.sub(r"(?<=[a-zæøå])- (?=[a-zæøå])", "", t)   # orddeling
    t = re.sub(r"\s+([,.;:%])", r"\1", t)
    t = re.sub(r",{2,}", ",", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()


def read_declaration(data: bytes, lang: str = "dan+eng") -> dict:
    """
    Returnerer rå tekst, udklippet deklaration og Tesseracts egen
    konfidens, så frontend kan sige "det her så ikke godt ud, tag et nyt".
    """
    try:
        img = Image.open(io.BytesIO(data))
    except Exception as e:
        return {"ok": False, "error": f"Kunne ikke læse billedet: {e}"}

    proc = preprocess(img)

    # psm 6 = én sammenhængende tekstblok. Passer til en deklaration.
    config = "--oem 1 --psm 6"
    try:
        raw = pytesseract.image_to_string(proc, lang=lang, config=config)
        data_tsv = pytesseract.image_to_data(
            proc, lang=lang, config=config, output_type=pytesseract.Output.DICT
        )
    except pytesseract.TesseractError as e:
        return {"ok": False, "error": f"Tesseract fejlede: {e}"}
    except pytesseract.TesseractNotFoundError:
        return {"ok": False, "error": "Tesseract er ikke installeret i containeren."}

    confs = [int(c) for c in data_tsv.get("conf", []) if str(c).lstrip("-").isdigit()]
    confs = [c for c in confs if c >= 0]
    mean_conf = round(sum(confs) / len(confs), 1) if confs else 0.0

    section = clean(extract_section(raw))
    return {
        "ok": True,
        "confidence": mean_conf,
        "found_section": bool(section and section != clean(raw)),
        "text": section or clean(raw),
        "raw": clean(raw),
        "hint": (
            "Læsningen er usikker — tag et nyt billede tættere på, uden glans."
            if mean_conf < 65
            else "Læs teksten igennem og ret fejl, før du gemmer."
        ),
    }
