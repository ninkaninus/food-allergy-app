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

import pytest

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


# --- udklippet må aldrig tage ingredienslisten med sig -------------------
# Fundet ved gennemgang 2026-08-21. `_slut()` tager den TIDLIGSTE
# slutmarkør, og med spaltelæsning står opbevaringen tit før
# deklarationen. Alle fire sager gav found_section=True, så
# fald-tilbage-til-råteksten reddede dem ikke.

def _sektion_beholder(raa: str, *ord: str) -> None:
    ud = s(raa)
    for o in ord:
        assert o.lower() in ud.lower(), f"{o!r} blev klippet væk: {ud!r}"


def test_slutmarkoer_foer_listen_klipper_ikke_listen_vaek():
    _sektion_beholder(
        "Fuldkornsknækbrød. Opbevares tørt og køligt.\n"
        "Rugmel, hvedemel, sesamfrø, skummetmælkspulver, salt.",
        "skummetmælkspulver", "sesamfrø", "rugmel",
    )


def test_ocr_taber_bogstav_i_startmarkoeren():
    """INGRED1ENSER: ét ciffer for et I — den almindeligste OCR-fejl."""
    _sektion_beholder(
        "INGRED1ENSER: Opbevares ved højst +5 °C. Hvedemel, sukker, æg, mælk.",
        "hvedemel", "æg", "mælk",
    )


def test_forkert_startmarkoer_med_slutmarkoer_lige_efter():
    _sektion_beholder(
        "Indhold: 500 g. Nettovægt 500 g. Ingredienser: Hvedemel, mælkepulver, æg.",
        "mælkepulver", "hvedemel",
    )


def test_spor_foer_ingredienslisten_bevares():
    """Sporadvarslen står i HOVEDET, ikke i halen — den skal stadig med."""
    _sektion_beholder(
        "Kan indeholde spor af mælk og nødder. Ingredienser: Hvedemel, sukker, rapsolie.",
        "spor af mælk", "hvedemel",
    )


def test_normal_etiket_bliver_stadig_klippet():
    """
    Modprøven til de fire ovenfor: vagten må kun redde et udklip, der
    slet ikke ligner en ingrediensliste. Danske næringstabeller bruger
    komma som decimaltegn, så en helt normal etiket har flere kommaer
    UDEN FOR listen end i den — uden loftet blev hele pakketeksten sendt
    til motoren, og »2,5 dl sødmælk« i en tilberedningsanvisning gjorde
    varen rød.
    """
    t = ("Ingredienser: Hvedemel, sukker, rapsolie, æg, salt. "
         "Tilberedning: Rør pulveret op i 2,5 dl sødmælk og pisk i 3 minutter. "
         "Næringsindhold pr. 100 g: Energi 1580 kJ, fedt 12,4 g, "
         "heraf mættede 2,1 g, kulhydrat 62,3 g, protein 8,7 g.")
    ud = s(t)
    assert "sødmælk" not in ud, "tilberedningsanvisningen slap med i sektionen"
    assert "Næringsindhold" not in ud and "1580" not in ud
    assert "rapsolie" in ud and "æg" in ud


def test_staerk_markoer_bliver_troet():
    """
    Vagten må ikke efterprøve et udklip efter »Ingredienser:«. En kort
    liste (»Ris 100%.«) har færre kommaer end resten af pakken, så vagten
    ville kaste det rigtige udklip væk — og »en klat smør« i en
    tilberedningsanvisning ville gøre varen rød.
    """
    ud = s("Ingredienser: Ris 100%.\n"
           "Tilberedning: Kog risene og vend dem med en klat smør.")
    assert "smør" not in ud and "Ris" in ud


def test_kasseret_udklip_lægger_spor_bagest():
    """
    Når vagten fyrer, må råteksten IKKE bruges i original rækkefølge.
    Står sporfrasen før listen og OCR har tabt punktummet, æder
    _spor_spans()' 200-tegns vindue ellers ingredienslisten, og en RØD
    vare bliver GUL — under-advarsel, den farlige retning.
    """
    from app.matcher import Ruleset
    import pathlib as _p
    R = Ruleset(_p.Path(__file__).resolve().parents[1] / "data" / "allergens.yaml")
    ud = s("KAN INDEHOLDE SPOR AF NØDDER\n"
           "Indhold: Hvedemel, skummetmælkspulver\n"
           "Næringsindhold pr. 100 g: Energi 1800 kJ, fedt 15,0 g, heraf mættede 7,0 g.")
    assert R.evaluate("maelkeprotein", ud).state.value == "contains", \
        f"mælk blev nedgraderet til spor: {ud!r}"
    assert "nødder" in ud.lower(), "sporadvarslen forsvandt"


@pytest.mark.parametrize("raa", [
    "KAN INDEHOLDE SPOR AF NØDDER Indhold: hvedemel, skummetmælkspulver",
    "Kan indeholde spor af nødder Indhold: mælk Nettovægt 500 g "
    "Energi 1800 kJ, fedt 2,0 g, kulhydrat 5,0 g",
    "KAN INDEHOLDE SPOR AF NØDDER Indhold: skummetmælkspulver Opbevares tørt "
    "Energi 1800 kJ, fedt 15,0 g, protein 9,1 g",
])
def test_sporfrase_paa_samme_linje_sluger_ikke_listen(raa):
    """
    Fundet ved gennemgang før 0.19.0. Står sporfrasen på SAMME linje som
    ingredienslisten, og har OCR tabt punktummet, løb spor-området fra
    frasen og hen over deklarationen — og en RØD vare blev GUL.

    Et spor-område må aldrig løbe hen over starten på en ingrediensliste.
    """
    from app.matcher import Ruleset
    import pathlib as _p
    R = Ruleset(_p.Path(__file__).resolve().parents[1] / "data" / "allergens.yaml")
    ud = s(raa)
    assert R.evaluate("maelkeprotein", ud).state.value == "contains", \
        f"mælk blev nedgraderet til spor: {ud!r}"
    assert R.evaluate("noedder", ud).state.value == "trace_risk", \
        "sporadvarslen om nødder forsvandt"
