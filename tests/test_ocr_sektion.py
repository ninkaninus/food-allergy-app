"""
Sektionsudklippet: hvor meget af etiketten kommer med?

Med den nye OCR-motor læses HELE etiketten — også opbevaring,
ernæringstabel og producentadresse. Kommer det med i ingredienslisten,
sker der to ting: teksten bliver svær at læse igennem, og matcheren
fuzzy-matcher på støjen og giver falske røde kryds.

Den farlige retning er dog den modsatte: klipper vi for hårdt, kan en
sporadvarsel forsvinde. Derfor hentes de altid tilbage.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.ocr import clean, extract_section


def s(t: str) -> str:
    return clean(extract_section(t))


# --- slutmarkører gælder også uden en startmarkør -------------------------
# Målt på en rigtig saftetiket: teksten begyndte direkte med "Vand, sukker,
# …" uden ordet "Ingredienser", og så kom HELE etiketten med.

def test_uden_startmarkoer_klippes_der_stadig():
    t = ("Vand, sukker, rabarberjuice (6%), naturlig aroma. "
         "NAERINGSINDHOLD PR. 100 ML: Energi 117 kJ Fedt 0 g")
    ud = s(t)
    assert ud.startswith("Vand, sukker")
    assert "NAERINGSINDHOLD" not in ud and "117" not in ud


def test_ocr_mangler_danske_tegn_i_markoeren():
    """OCR skriver NÆRINGSINDHOLD som NAERINGSINDHOLD — markøren skal ramme."""
    for variant in ["NÆRINGSINDHOLD", "NAERINGSINDHOLD", "NARINGSINDHOLD"]:
        assert "Energi" not in s(f"Hvedemel, salt. {variant} PR 100 G: Energi 900 kJ")


def test_indhold_matcher_ikke_inde_i_naeringsindhold():
    t = "Næringsindhold pr. 100 g: Energi 1888 kJ"
    assert s(t) == ""      # intet er ingrediensliste her


# --- sporadvarsler må ALDRIG klippes væk ----------------------------------

def test_spor_bevares_selvom_de_staar_efter_en_slutmarkoer():
    t = ("Ingredienser: 93 % grisekød, salt, sennepsfrø. "
         "Næringsindhold pr. 100 g: Energi 1090 kJ. "
         "Kan indeholde spor af pistacienødder og selleri.")
    ud = s(t)
    assert "pistacienødder" in ud and "selleri" in ud
    assert "1090" not in ud


def test_spor_bevares_efter_producentlinje():
    t = ("Ingredienser: Hvedemel, sukker. Produceret af Bageriet A/S, Aarhus. "
         "Kan indeholde spor af nødder.")
    ud = s(t)
    assert "nødder" in ud
    assert "Bageriet" not in ud


def test_spor_kommer_kun_med_en_gang():
    t = ("Ingredienser: Mel. Opbevaring: Tørt. Kan indeholde spor af nødder. "
         "Kan indeholde spor af nødder.")
    assert s(t).lower().count("spor af nødder") == 2   # to sætninger, ikke fire


# --- almindelige etiketter må ikke blive stumpede -------------------------

def test_hele_ingredienslisten_beholdes():
    t = ("Ingredienser: Hvedemel, vand, gær, salt, rapsolie, sukker, "
         "surhedsregulerende middel (E 262), hvedegluten. "
         "Opbevaring: Tørt og ved stuetemperatur.")
    ud = s(t)
    assert "hvedegluten" in ud
    assert "stuetemperatur" not in ud
