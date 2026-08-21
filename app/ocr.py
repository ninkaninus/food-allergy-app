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
# Markører, der utvetydigt indleder en deklaration. "indhold" og
# "sammensætning" er svage — de står også på pakker om noget helt andet
# ("Indhold: 500 g") — og et udklip efter dem er værd at efterprøve.
STRONG_SECTION_MARKERS = {
    "ingredienser", "ingrediens", "ingredients", "zutaten",
    "ingrediënten", "ainesosat",
}

END_MARKERS = [
    "næringsindhold", "næringsdeklaration", "nutrition", "energi ",
    "opbevares", "opbevaring", "bedst før", "mindst holdbar", "nettovægt",
    # alt herunder står efter ingredienslisten på danske etiketter
    "opblanding", "tilberedning", "brugsanvisning", "serveringsforslag",
    "produceret af", "produceret i", "importeret af", "distribueret af",
    "emballagen", "sorteres som", "efter åbning",
]

# Sporadvarsler skal ALDRIG klippes væk, uanset hvor på etiketten de står.
# De står tit efter en slutmarkør ("… (E 250). Kan indeholde spor af
# pistacienødder og selleri." efter "Produceret af"), og under-advarsel er
# den farlige retning. Derfor hentes de tilbage til sektionen.
TRACE_PHRASES = [
    "kan indeholde", "kan indeholde spor", "fremstillet på et anlæg",
    "fremstillet på fabrik", "produceret på et anlæg", "hvor der også",
    "may contain", "spor af",
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


def _crop_ved_markoer(proc: Image.Image, tsv: dict) -> Image.Image | None:
    """Finder 'Ingredienser'-markøren i en ordliste og beskærer til blokken.
    Markør og slutmarkør matches fuzzy, for de er selv OCR-læste."""
    marker = None
    for i in range(len(tsv["text"])):
        t = tsv["text"][i].strip()
        if len(t) >= 8 and _ligner(t, "ingredienser", 3):
            marker = (tsv["top"][i], tsv["height"][i])
            break
    if marker is None:
        return None
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
    if y1 - y0 < 2 * h:
        return None
    return proc.crop((0, y0, proc.width, y1))


def _find_declaration_crop(
    gray: Image.Image,
    lang: str,
    tsvs: dict[bool, dict] | None = None,
    first_invert: bool = False,
) -> Image.Image | None:
    """
    Leder efter 'Ingredienser'-markøren og beskærer til deklarationsblokken.

    Prøver begge polariteter: mange danske poser har LYS tekst på mørk
    bund, og dér er den almindelige binarisering (mørk tekst = tekst)
    blind. Ordlisterne fra fuldbillede-læsningen genbruges først — det
    sparer de langsomme psm 3-kørsler i de fleste tilfælde.
    """
    order = [first_invert, not first_invert]
    for invert in order:
        tsv = (tsvs or {}).get(invert)
        if tsv is None:
            continue
        crop = _crop_ved_markoer(_binarize(ImageOps.invert(gray) if invert else gray), tsv)
        if crop is not None:
            return crop
    # psm 3 segmenterer nogle gange blokke, som psm 6 kører sammen — sidste forsøg
    for invert in order:
        proc = _binarize(ImageOps.invert(gray) if invert else gray)
        try:
            tsv = _tsv(proc, lang, 3)
        except pytesseract.TesseractError:
            continue
        crop = _crop_ved_markoer(proc, tsv)
        if crop is not None:
            return crop
    return None


def _candidates(gray: Image.Image, lang: str) -> tuple[tuple[str, float, bool], dict[bool, dict]]:
    """
    Læser hele billedet i begge polariteter; bedste filtrerede konfidens
    vinder. Mange danske poser har LYS tekst på mørk bund, og dér er
    mørk-tekst-binariseringen blind. Er den mørke læsning god (>= 80,
    normaltilfældet), springes den lyse over.
    """
    best = ("", -1.0, False)
    tsvs: dict[bool, dict] = {}
    for invert in (False, True):
        proc = _binarize(ImageOps.invert(gray) if invert else gray)
        tsv = _tsv(proc, lang, 6)
        tsvs[invert] = tsv
        text, conf = _reconstruct(tsv, threshold=10)
        if conf > best[1]:
            best = (text, conf, invert)
        if best[1] >= 80:
            break
    return best, tsvs


def _osd_rotation(proc: Image.Image) -> int:
    """
    Tesseracts orienterings-detektion: hvor mange grader skal billedet
    drejes for at teksten vender rigtigt? Etiketter sidder tit 90° på
    pakken, og EXIF ved det ikke — kameraet vendte rigtigt, det gjorde
    pakken ikke. Under konfidens 2 er svaret gætværk og ignoreres.
    """
    try:
        osd = pytesseract.image_to_osd(proc)
    except Exception:
        return 0
    m = re.search(r"Rotate:\s*(\d+)", osd)
    c = re.search(r"Orientation confidence:\s*([\d.]+)", osd)
    rot = int(m.group(1)) % 360 if m else 0
    return rot if rot and c and float(c.group(1)) >= 2.0 else 0


def _markoer(m: str) -> re.Pattern:
    """
    Markør-regex, der tåler det OCR gør ved danske etiketter.

    Tre tilgivelser, hver med et målt tilfælde bag sig:
      æ ø å   læses tit som ae/a, oe/o, aa/a — en rigtig saftetiket kom
              ud som "NAERINGSINDHOLD", så "næringsindhold" ramte ikke.
      mellemrum forsvinder ("Udenlarvestoffer"), så de er valgfrie.
      ordgrænse foran kræves stadig: "indhold" må ikke matche inde i
              "Næringsindhold" og gøre ernæringstabellen til sektionen.
    """
    dele = []
    for ch in m:
        if ch == "æ":
            dele.append("(?:æ|ae|a)")
        elif ch == "ø":
            dele.append("(?:ø|oe|o)")
        elif ch == "å":
            dele.append("(?:å|aa|a)")
        elif ch == " ":
            dele.append(r"\s*")
        else:
            dele.append(re.escape(ch))
    return re.compile(r"(?<![a-zæøå])" + "".join(dele))


def _slut(tekst: str, fra: int = 0) -> int:
    """Hvor holder ingredienslisten op? Tidligste slutmarkør efter `fra`."""
    low = tekst.lower()
    end = len(tekst)
    for m in END_MARKERS:
        hit = _markoer(m).search(low, fra)
        if hit is not None:
            end = min(end, hit.start())
    return end


def _kommaer(t: str) -> int:
    return t.count(",")


def _klippet_forkert(beholdt: str, kasseret: str) -> bool:
    """
    Ligner det, vi smed væk, en ingrediensliste mere end det, vi beholdt?

    Kommaet er ingredienslistens signatur — ingredienser står adskilt.
    Er der mindst to flere i det kasserede, har vi klippet det forkerte
    sted, og så er udklippet værre end ingen udklipning.

    Det sker, fordi `_slut()` tager den TIDLIGSTE slutmarkør. Står
    "Opbevares ved højst +5 °C" i venstre spalte og deklarationen i
    højre, læser spaltelæseren opbevaringen først, og hele
    ingredienslisten ryger. Det samme, når OCR taber ét bogstav i
    "Ingredienser" (INGRED1ENSER), så startmarkøren ikke rammer.

    Retningen er hele pointen: at tage for meget med giver støj og
    måske en falsk advarsel. At tage for lidt med gør en vare med mælk
    i tavs.

    Men vagten må KUN redde et udklip, der slet ikke ligner en
    ingrediensliste — ikke et, der bare er kortere end resten af pakken.
    Danske næringstabeller bruger komma som decimaltegn ("fedt 12,4 g,
    heraf mættede 2,1 g"), så en helt normal etiket har flere kommaer
    uden for listen end i den. Uden `< 3` blev hele pakketeksten sendt
    til motoren, og "2,5 dl sødmælk" i en tilberedningsanvisning gjorde
    varen rød. Det ville rulle 0.17.0 tilbage i det stille.
    """
    return _kommaer(beholdt) < 3 and _kommaer(kasseret) >= _kommaer(beholdt) + 2


def extract_section(text: str) -> str:
    """
    Klipper deklarationen ud af al den anden tekst på pakken.

    Slutmarkørerne gælder OGSÅ, når der ikke er nogen startmarkør. Mange
    danske etiketter skriver bare ingredienserne uden at sætte
    "Ingredienser:" foran, og OCR taber det tit alligevel — før tog vi
    så hele teksten med, ernæringstabel, opblandingsvejledning og det
    hele. Slutningen kan vi kende uafhængigt af begyndelsen.

    Ser udklippet forkert ud (se `_klippet_forkert`), kasseres det, og
    hele teksten bruges. Et sikkerhedsnet, der kun virker, når
    udklipningen fejler fuldstændigt, er ikke et sikkerhedsnet.
    """
    low = text.lower()
    # Tidligste markør vinder; står to på samme position ("ingredienser"
    # og "ingrediens"), vinder den længste — ellers blev "er:" hængende
    # forrest i den udklippede tekst.
    best: tuple[int, int] | None = None  # (position, markørlængde)
    staerk = False
    for m in SECTION_MARKERS:
        hit = _markoer(m).search(low)
        if hit is None:
            continue
        i = hit.start()
        if best is None or i < best[0] or (i == best[0] and len(m) > best[1]):
            best = (i, len(m))
            staerk = m in STRONG_SECTION_MARKERS

    if best is None:
        start, slut = 0, _slut(text)
        sektion = text[:slut].strip()
    else:
        start = best[0] + best[1]
        slut = _slut(text, start)
        sektion = text[start:slut].lstrip(" :.-\n").strip()

    # Stod der "Ingredienser:", tror vi på udklippet. Vagten er til for de
    # etiketter, hvor markøren manglede eller var svag — dét er dér, der
    # bliver klippet forkert. Efterprøver vi også et udklip efter en stærk
    # markør, kaster vi rigtige udklip væk på korte lister ("Ingredienser:
    # Ris 100%." + en tilberedningsanvisning med smør i).
    if not staerk and _klippet_forkert(sektion, text[:start] + text[slut:]):
        # Rå tekst i ORIGINAL rækkefølge er farlig: står sporfrasen før
        # listen og OCR har tabt punktummet, æder _spor_spans()' 200-tegns
        # vindue ingredienslisten, og en rød vare bliver gul. Læg derfor
        # sporsætningerne bagest, som den normale vej gør.
        omraader = _spor_omraader(text, stop_ved_linjeskift=True)
        krop = text
        for a, b in sorted(omraader, reverse=True):
            krop = krop[:a] + " " + krop[b:]
        spor = "".join(" " + text[a:b].strip() for a, b in omraader)
        return (krop.strip() + spor).strip()

    # Sporadvarsler hentes tilbage fra BEGGE sider af udklippet. Står
    # "Kan indeholde spor af mælk" før "Ingredienser:", ligger den i
    # hovedet, ikke i halen — og en tabt sporadvarsel er under-advarsel.
    spor = _spor_uddrag(text[:start]) + _spor_uddrag(text[slut:])
    return (sektion + spor).strip()


def _spor_fra_resten(text: str, fra: int) -> str:
    """Bevaret navn: sporadvarsler i alt fra `fra` og frem."""
    return _spor_uddrag(text[fra:])


def _spor_omraader(rest: str, stop_ved_linjeskift: bool = False) -> list[tuple[int, int]]:
    """
    Hvor står sporsætningerne i `rest` — sammenflettede spans.

    `stop_ved_linjeskift` bruges KUN, når et kasseret udklip skal skilles
    ad. Uden det løber spanet til første punktum, og taber OCR punktummet
    (»Næringsindhold pr.« er det næste, der har et), sluger spanet hele
    ingredienslisten. I den normale vej er den lange udgave rigtig: en
    sporsætning kan sagtens brydes over to linjer, og at klippe den midt
    over ville tabe allergennavnene — under-advarsel.
    """
    low = rest.lower()
    fundet: list[tuple[int, int]] = []
    for frase in TRACE_PHRASES:
        for hit in _markoer(frase).finditer(low):
            s = hit.start()
            grænser = [i for i in (rest.find(".", s),) if i != -1]
            if stop_ved_linjeskift:
                grænser += [i for i in (rest.find("\n", s),) if i != -1]
            # En sporsætning indeholder ALDRIG starten på en
            # ingrediensliste. Uden det her kunne området løbe fra
            # sporfrasen og hen over deklarationen, når OCR har tabt både
            # punktum og linjeskift — og så blev en RØD vare gul.
            for markoer in SECTION_MARKERS:
                h = _markoer(markoer).search(low, s + 1)
                if h is not None:
                    grænser.append(h.start())
            e = min([g + 1 for g in grænser] + [len(rest), s + 200])
            fundet.append((s, e))
    if not fundet:
        return []
    fundet.sort()
    flettet: list[tuple[int, int]] = []
    for s, e in fundet:
        if flettet and s <= flettet[-1][1]:
            flettet[-1] = (flettet[-1][0], max(flettet[-1][1], e))
        else:
            flettet.append((s, e))
    return flettet


def _spor_uddrag(rest: str) -> str:
    """
    Henter sporadvarsler ud af den del, der blev klippet væk.

    Uden det ville en hårdere beskæring kunne tabe "Kan indeholde spor af
    pistacienødder og selleri" — netop den sætning, der afgør, om varen
    kan spises. Sætningen tages fra frasen til punktum (eller 200 tegn,
    for OCR taber punktummer).
    """
    if not rest.strip():
        return ""
    low = rest.lower()
    fundet: list[tuple[int, int]] = []
    for frase in TRACE_PHRASES:
        for hit in _markoer(frase).finditer(low):
            s = hit.start()
            punktum = rest.find(".", s)
            e = min(punktum + 1 if punktum != -1 else len(rest), s + 200)
            fundet.append((s, e))
    if not fundet:
        return ""
    # flet overlappende spans, så samme sætning ikke kommer med to gange
    fundet.sort()
    flettet: list[tuple[int, int]] = []
    for s, e in fundet:
        if flettet and s <= flettet[-1][1]:
            flettet[-1] = (flettet[-1][0], max(flettet[-1][1], e))
        else:
            flettet.append((s, e))
    return "".join(" " + rest[s:e].strip() for s, e in flettet)


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

    try:
        (raw, mean_conf, vinder), tsvs = _candidates(gray, lang)
    except pytesseract.TesseractError as e:
        return {"ok": False, "error": f"Tesseract fejlede: {e}"}
    except pytesseract.TesseractNotFoundError:
        return {"ok": False, "error": "Tesseract er ikke installeret i containeren."}

    # Vender etiketten 90° på pakken? Målt på et rigtigt foto af pølser i
    # mørk pose med etiketten på langs: uden rotation suppe (38 %), med
    # OSD-rotation fandt redningen 'Ingredienser' og læste blokken (73 %).
    if mean_conf < 65:
        # OSD skal se bogstaverne, og vi ved ikke hvilken polaritet de
        # bor i — prøv vinderen først, så den anden.
        rot = 0
        for invert in (vinder, not vinder):
            rot = _osd_rotation(_binarize(ImageOps.invert(gray) if invert else gray))
            if rot:
                break
        if rot:
            roteret = gray.rotate(-rot, expand=True)
            try:
                (raw2, conf2, vinder2), tsvs2 = _candidates(roteret, lang)
            except pytesseract.TesseractError:
                raw2, conf2 = "", -1.0
            if conf2 > mean_conf:
                gray, raw, mean_conf, vinder, tsvs = roteret, raw2, conf2, vinder2, tsvs2
    mean_conf = max(mean_conf, 0.0)

    # To-pas-redning for fotos af HELE posen. Målt på et rigtigt foto
    # (lys tekst på mørkerød pose, præget grafik): helbilledet gav 28 %
    # og suppe; find-blokken-og-genlæs gav 72 % og næsten hele
    # deklarationen — inklusive 'bananchips* (banan*', som er dét,
    # matcheren skal se. psm 4 (én spalte) slog psm 6 på croppen.
    if mean_conf < 65:
        crop = _find_declaration_crop(gray, lang, tsvs, vinder)
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

    return efterbehandl(raw, mean_conf)


def efterbehandl(raw: str, mean_conf: float) -> dict:
    """
    Rå OCR-tekst -> det, bekræftelsesskærmen skal bruge.

    Deles af begge veje: Tesseract herover og OCR-containeren (se
    ocr_klient.py). Al dansk-specifik logik — sektionsudklip og
    oprydning — bor HER, ikke i OCR-tjenesten. Tjenesten leverer tegn;
    betydning lægges på i appen, hvor matcheren også bor.
    """
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
