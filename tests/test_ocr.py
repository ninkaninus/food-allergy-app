"""
Regressionstest for OCR-forbehandlingen.

Baggrund: den oprindelige pipeline binariserede med en GLOBAL Otsu-tærskel.
På jævnt belyste billeder fungerede den, men på et telefonfoto med skygge i
den ene side og glans i den anden findes der ingen enkelt tærskel, der
passer hele billedet — resultatet var 26-42 % konfidens og ren volapyk.
Den adaptive lokale tærskel giver 86-93 % på de samme billeder.

Integrationstestene genererer netop sådan et billede og kræver Tesseract
med dansk sprogmodel plus en TrueType-font. Mangler noget af det (typisk
lokalt), springes de over — CI installerer det og kører dem altid.
"""
import pathlib
import shutil
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.ocr import extract_section, preprocess, read_declaration

# --- extract_section: ren tekstlogik, kører altid --------------------------

def test_section_marker_efterlader_ikke_er():
    """'Ingredienser' og 'ingrediens' matcher samme sted — længste vinder,
    ellers blev 'er:' hængende forrest i den udklippede tekst."""
    t = "Ingredienser: Hvedemel, sukker. Næringsindhold pr. 100 g: energi."
    s = extract_section(t)
    assert s.startswith("Hvedemel")
    assert "energi" not in s

def test_section_uden_markoer_er_hele_teksten():
    assert extract_section("Hvedemel, sukker") == "Hvedemel, sukker"

def test_indhold_matcher_ikke_inde_i_naeringsindhold():
    """Målt på et rigtigt foto: 'indhold' matchede inde i 'Næringsindhold',
    og sektionen blev ernæringstabel i stedet for ingrediensliste."""
    t = "Næringsindhold pr. 100 g: Energi 1888 kJ, Fedt 18 g"
    assert extract_section(t) == t          # ingen markør — hele teksten
    assert extract_section("Indhold: hvedemel, vand").startswith("hvedemel")


# --- integration: kræver tesseract + dan + font ----------------------------

def _font():
    for p in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    ]:
        if pathlib.Path(p).exists():
            return p
    return None

def _har_dansk_tesseract():
    if not shutil.which("tesseract"):
        return False
    import pytesseract
    try:
        return "dan" in pytesseract.get_languages(config="")
    except Exception:
        return False

kraever_tesseract = pytest.mark.skipif(
    not (_har_dansk_tesseract() and _font()),
    reason="kræver tesseract-ocr-dan og DejaVu-font (installeres i CI)",
)

TEKST = (
    "Ingredienser: Hvedemel, sukker, skummetmælkspulver,\n"
    "palmeolie, kakaosmør, jordbær 4%, æggeblomme, salt.\n"
    "Næringsindhold pr. 100 g: Energi 2100 kJ."
)

def _deklarationsfoto(gradient=True, glans=True, exif_rotation=False):
    """Syntetisk emballagefoto: tekst + lysgradient + glansplet, som JPEG."""
    import io
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

    img = Image.new("L", (1400, 460), 235)
    d = ImageDraw.Draw(img)
    d.multiline_text((60, 50), TEKST, font=ImageFont.truetype(_font(), 26), spacing=14, fill=25)

    if gradient:  # venstre side i skygge
        g = Image.new("L", (256, 1))
        g.putdata([round(110 * (1 - i / 255) ** 1.5) for i in range(256)])
        img = ImageChops.subtract(img, g.resize(img.size))
    if glans:     # blank plet i højre side
        o = Image.new("L", img.size, 0)
        ImageDraw.Draw(o).ellipse([900, 40, 1300, 300], fill=170)
        img = ImageChops.add(img, o.filter(ImageFilter.GaussianBlur(60)))
    img = img.rotate(1.6, expand=True, fillcolor=180, resample=Image.BICUBIC)

    buf = io.BytesIO()
    if exif_rotation:  # gemt liggende med orientation=6, som telefoner gør
        ex = Image.Exif()
        ex[274] = 6
        img.rotate(90, expand=True).convert("RGB").save(buf, "JPEG", quality=78, exif=ex)
    else:
        img.convert("RGB").save(buf, "JPEG", quality=78)
    return buf.getvalue()


@kraever_tesseract
def test_ujaevnt_lys_laeses_stadig():
    """Det billede, der knækkede den globale tærskel. 70 er porten —
    den gamle pipeline lå på 26."""
    r = read_declaration(_deklarationsfoto())
    assert r["ok"]
    assert r["confidence"] >= 70
    assert "hvedemel" in r["text"].lower()
    assert r["found_section"]

@kraever_tesseract
def test_exif_rotation_respekteres():
    r = read_declaration(_deklarationsfoto(exif_rotation=True))
    assert r["ok"]
    assert r["confidence"] >= 70
    assert "hvedemel" in r["text"].lower()


def _helposefoto():
    """
    Foto af HELE posen, som folk faktisk tager dem: lys tekst på mørk
    bund, deklarationen er en lille blok, og der er grafik omkring.
    Det er casen, hvor ét-pas-OCR gav 28 % konfidens og ren volapyk på
    et rigtigt foto — to-pas-redningen skal finde blokken og læse den.
    """
    import io
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    img = Image.new("L", (1500, 1900), 70)          # mørk pose
    d = ImageDraw.Draw(img)
    stor = ImageFont.truetype(_font(), 40)
    lille = ImageFont.truetype(_font(), 26)
    d.text((120, 150), "Økologisk müsli med banan", font=stor, fill=210)
    for x, y, r_ in [(200, 420, 90), (900, 300, 70), (1200, 800, 110), (400, 1500, 80)]:
        d.ellipse([x, y, x + r_, y + r_ // 2], outline=110, width=4)   # "grafik"
    d.multiline_text(
        (120, 700),
        "Ingredienser: 43% glutenfri havregryn,\n"
        "rørsukker, 13% bananchips (banan,\n"
        "kokosolie, sukker), puffede ris,\n"
        "7% ristede kokosflager.",
        font=lille, fill=215, spacing=12,
    )
    d.text((120, 1100), "Opbevaring: Tørt og ved stuetemperatur.", font=lille, fill=215)
    img = img.filter(ImageFilter.GaussianBlur(0.5))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=80)
    return buf.getvalue()


@kraever_tesseract
def test_helposefoto_reddes_af_topas():
    r = read_declaration(_helposefoto())
    assert r["ok"]
    t = r["text"].lower()
    # Det afgørende: allergenordene overlever, så matcheren kan se dem.
    assert "banan" in t
    assert "havregryn" in t
    assert r["confidence"] >= 50


def _naerbillede_lys_paa_moerk():
    """
    Nærbillede af deklarationen på en mørk pose, hvor 'Ingredienser' er
    skåret ud af rammen. Her kan to-pas-redningen ikke finde sin markør —
    lys-polariteten SKAL være en fuldgyldig kandidat for hele billedet.
    """
    import io
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    img = Image.new("L", (1400, 520), 70)
    d = ImageDraw.Draw(img)
    d.multiline_text(
        (60, 60),
        "rørsukker, 13% bananchips (banan,\n"
        "kokosolie, sukker, honning), puffede ris,\n"
        "7% ristede kokosflager, solsikkeolie.",
        font=ImageFont.truetype(_font(), 30), fill=220, spacing=16,
    )
    img = img.filter(ImageFilter.GaussianBlur(0.5))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=80)
    return buf.getvalue()


@kraever_tesseract
def test_etiket_paa_tvaers_rettes_af_osd():
    """Etiketten sidder tit 90° på pakken — kameraet vendte rigtigt, det
    gjorde pakken ikke, så EXIF ved ingenting. Tesseracts OSD skal opdage
    det. (OSD kræver en rimelig mængde tekst; på meget sparsomme billeder
    melder den pas, og så gælder hintet om at tage et nyt billede.)"""
    import io
    from PIL import Image

    img = Image.open(io.BytesIO(_deklarationsfoto(gradient=False, glans=False)))
    buf = io.BytesIO()
    img.rotate(90, expand=True).save(buf, "JPEG", quality=85)  # ingen EXIF
    r = read_declaration(buf.getvalue())
    assert r["ok"]
    assert "hvedemel" in r["text"].lower()
    assert r["confidence"] >= 70


@kraever_tesseract
def test_lys_tekst_uden_markoer_laeses():
    r = read_declaration(_naerbillede_lys_paa_moerk())
    assert r["ok"]
    t = r["text"].lower()
    assert "banan" in t
    assert "kokosolie" in t
    assert r["confidence"] >= 60
