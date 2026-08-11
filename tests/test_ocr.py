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
