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
from PIL import Image, ImageChops, ImageFilter, ImageOps

from .matcher import _edit_distance, fold

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
    Tesseract vil have stor, ren, høj-kontrast tekst. Emballagefotos har
    ujævnt lys, skygge og glans — og dér bryder en GLOBAL tærskel (Otsu)
    sammen: der findes ingen enkelt værdi, der er rigtig for både den
    mørke og den blanke ende af billedet, og halvdelen af teksten drukner.

    Målt på syntetiske deklarationsfotos med lysgradient og glansplet:
    global Otsu gav 26-42 % konfidens og ren volapyk; den adaptive lokale
    tærskel nedenfor gav 86-93 % og næsten fejlfri tekst. På jævnt belyste
    billeder er de to ens (~94 %).
    """
    return _binarize(_grayscale(img, max_side))


def _grayscale(img: Image.Image, max_side: int = 2200) -> Image.Image:
    img = ImageOps.exif_transpose(img)
    img = img.convert("L")

    # Normalisér størrelsen: op mod ~300 dpi hvis billedet er lille, ned
    # hvis telefonen leverer 12 MP — tekststørrelsen er rigelig alligevel,
    # og både sløringsradius og køretid opfører sig bedst i det interval.
    w, h = img.size
    if max(w, h) < max_side:
        scale = max_side / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    elif max(w, h) > 3200:
        scale = 3200 / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    return ImageOps.autocontrast(img, cutoff=2)


def _binarize(img: Image.Image) -> Image.Image:
    # Adaptiv lokal tærskel i ren PIL: hver pixel sammenlignes med sit
    # lokale gennemsnit (boksslør). Bogstaver er mørkere end deres nære
    # omgivelser, uanset om omgivelserne ligger i skygge eller glans —
    # det er hele forskellen fra den globale tærskel.
    radius = max(15, round(max(img.size) / 90))
    local_mean = img.filter(ImageFilter.BoxBlur(radius))
    # subtract med offset 128: resultatet er 128 + (pixel - gennemsnit)
    diff = ImageChops.subtract(img, local_mean, scale=1.0, offset=128)
    # 12 gråtoner under lokalgennemsnittet = tekst. Mindre fanger støj.
    return diff.point(lambda p: 255 if p > 116 else 0)


def _tsv(proc: Image.Image, lang: str, psm: int) -> dict:
    return pytesseract.image_to_data(
        proc, lang=lang, config=f"--oem 1 --psm {psm}",
        output_type=pytesseract.Output.DICT,
    )


def _ligner(word: str, target: str, tol: int) -> bool:
    w = "".join(ch for ch in fold(word.lower()) if ch.isalpha())
    return bool(w) and (_edit_distance(w, target, tol) <= tol or target[:7] in w)


def _reconstruct(tsv: dict, threshold: int) -> tuple[str, float]:
    """
    Sætter teksten sammen af ord med konfidens over tærsklen, i læseorden.
    Grafik og folder bliver til lav-konfidens vrøvleord — det er dem, der
    gjorde hele-pose-fotos til suppe, og de filtreres væk her.
    """
    parts: list[str] = []
    last = None
    kept: list[int] = []
    for i in range(len(tsv["text"])):
        t = tsv["text"][i].strip()
        c = tsv["conf"][i]
        c = int(c) if str(c).lstrip("-").isdigit() else -1
        if not t or c < threshold:
            continue
        key = (tsv["block_num"][i], tsv["par_num"][i], tsv["line_num"][i])
        if last is not None and key != last:
            parts.append("\n")
        parts.append(t + " ")
        last = key
        kept.append(c)
    mean = round(sum(kept) / len(kept), 1) if kept else 0.0
    return "".join(parts), mean


def _find_declaration_crop(gray: Image.Image, lang: str) -> Image.Image | None:
    """
    Leder efter 'Ingredienser'-markøren og beskærer til deklarationsblokken.

    Prøver begge polariteter: mange danske poser har LYS tekst på mørk
    bund, og dér er den almindelige binarisering (mørk tekst = tekst)
    blind. Markøren og slutmarkøren ('Opbevaring', 'Næringsindhold')
    matches fuzzy, for de er selv OCR-læste.
    """
    for invert in (False, True):
        proc = _binarize(ImageOps.invert(gray) if invert else gray)
        try:
            tsv = _tsv(proc, lang, 3)
        except pytesseract.TesseractError:
            continue
        marker = None
        for i in range(len(tsv["text"])):
            t = tsv["text"][i].strip()
            if len(t) >= 8 and _ligner(t, "ingredienser", 3):
                marker = (tsv["top"][i], tsv["height"][i])
                break
        if marker is None:
            continue
        top, h = marker
        end = None
        for target in ("opbevaring", "naeringsindhold", "naeringsdeklaration", "nutrition"):
            for i in range(len(tsv["text"])):
                t = tsv["text"][i].strip()
                if len(t) >= 7 and tsv["top"][i] > top + h and _ligner(t, target, 2):
                    if end is None or tsv["top"][i] < end:
                        end = tsv["top"][i]
        y0 = max(0, top - 2 * h)
        y1 = end - h // 2 if end else min(proc.height, top + 16 * h)
        if y1 - y0 >= 2 * h:
            return proc.crop((0, y0, proc.width, y1))
    return None


def extract_section(text: str) -> str:
    """Klipper deklarationen ud af al den anden tekst på pakken."""
    low = text.lower()
    # Tidligste markør vinder; står to på samme position ("ingredienser"
    # og "ingrediens"), vinder den længste — ellers blev "er:" hængende
    # forrest i den udklippede tekst.
    best: tuple[int, int] | None = None  # (position, markørlængde)
    for m in SECTION_MARKERS:
        i = low.find(m)
        if i == -1:
            continue
        if best is None or i < best[0] or (i == best[0] and len(m) > best[1]):
            best = (i, len(m))
    if best is None:
        return text.strip()

    tail = text[best[0] + best[1]:]
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

    gray = _grayscale(img)
    proc = _binarize(gray)

    # psm 6 = én sammenhængende tekstblok. Passer til et nærbillede af
    # en deklaration — den almindelige og bedste måde at bruge OCR på.
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

    # To-pas-redning for fotos af HELE posen. Målt på et rigtigt foto
    # (lys tekst på mørkerød pose, præget grafik): helbilledet gav 28 %
    # og suppe; find-blokken-og-genlæs gav 72 % og næsten hele
    # deklarationen — inklusive 'bananchips* (banan*', som er dét,
    # matcheren skal se. psm 4 (én spalte) slog psm 6 på croppen.
    if mean_conf < 65:
        crop = _find_declaration_crop(gray, lang)
        if crop is not None:
            # Tærskel 10: konfidens 0 er dér, grafik-suppen bor, men alt
            # med bare minimal konfidens beholdes — et tabt allergenord
            # er dyrere end et vrøvleord, som mennesket alligevel ser.
            try:
                rescue, rescue_conf = _reconstruct(_tsv(crop, lang, 4), threshold=10)
            except pytesseract.TesseractError:
                rescue, rescue_conf = "", 0.0
            if rescue.strip() and rescue_conf > mean_conf:
                raw = rescue
                mean_conf = rescue_conf

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
