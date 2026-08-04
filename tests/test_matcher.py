"""Regressionstest for matcheren. Kør: python -m pytest tests/ -q"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pytest
from app.matcher import Ruleset, State

R = Ruleset(pathlib.Path(__file__).resolve().parents[1] / "data" / "allergens.yaml")

CASES = [
    # de falske positiver, som naiv substring-matchning ville ramme
    ("maelkeprotein", "Vand, kakaosmør, sukker, sojalecithin", State.UNKNOWN),
    ("maelkeprotein", "Kokosmælk 60%, vand, guargummi", State.UNKNOWN),
    ("maelkeprotein", "Jordnøddesmør 90%, salt", State.UNKNOWN),
    ("maelkeprotein", "Havregryn, mælkebøtterod", State.UNKNOWN),
    ("maelkeprotein", "Vand, mælkesyre (E270)", State.UNKNOWN),
    ("maelkeprotein", "Mælkefri margarine, rapsolie", State.UNKNOWN),
    ("aeg", "Sukker, ægte vanilje, hvedemel", State.UNKNOWN),
    ("aeg", "Tomat, æggeplante, olivenolie", State.UNKNOWN),
    # de rigtige positiver, som en for aggressiv undtagelsesliste ville tabe
    ("maelkeprotein", "Skummetmælkspulver, sukker", State.CONTAINS),
    ("maelkeprotein", "Laktosefri mælk, salt", State.CONTAINS),
    ("maelkeprotein", "Rapsolie, valle, salt", State.CONTAINS),
    ("maelkeprotein", "Mel, natriumkaseinat", State.CONTAINS),
    ("aeg", "Hvedemel, æggeblomme, smør", State.CONTAINS),
    ("jordbaer", "Sukker, jordbærpuré 30%", State.CONTAINS),
    ("banan", "Bananmel, vand", State.CONTAINS),
    # gråzonen
    ("aeg", "Rapsolie, lecithin, eddike", State.TRACE_RISK),
    ("jordbaer", "Æblejuice, bærblanding, sukker", State.TRACE_RISK),
    ("banan", "Havre, tropisk frugtblanding", State.TRACE_RISK),
    # tom tekst er ALDRIG frit
    ("maelkeprotein", None, State.UNKNOWN),
    ("maelkeprotein", "", State.UNKNOWN),
]

@pytest.mark.parametrize("slug,text,expected", CASES)
def test_state(slug, text, expected):
    assert R.evaluate(slug, text).state is expected

def test_off_tag_wins_over_text():
    v = R.evaluate("maelkeprotein", "ingen mejeriord her", off_allergen_tags=["en:milk"])
    assert v.state is State.CONTAINS

def test_engine_never_returns_free():
    """Kun et menneske kan sætte FREE. Motoren må aldrig gøre det selv."""
    for slug in R.allergens:
        for text in ["vand, salt", "", None, "mælk", "kan indeholde spor af mælk"]:
            assert R.evaluate(slug, text).state is not State.FREE


AROMA = [
    # aroma-varianter må ikke blive røde på præfikset — de er gule
    ("jordbaer", "Sukker, jordbæraroma, citronsyre", State.TRACE_RISK),
    ("maelkeprotein", "Rapsolie, smøraroma, salt", State.TRACE_RISK),
    ("maelkeprotein", "Vand, mælkesyrekultur", State.TRACE_RISK),
]

@pytest.mark.parametrize("slug,text,expected", AROMA)
def test_aroma_is_amber_not_red(slug, text, expected):
    assert R.evaluate(slug, text).state is expected

def test_trace_marker_is_amber():
    v = R.evaluate("maelkeprotein", "Hvedemel, sukker. Kan indeholde spor af nødder.")
    assert v.state is State.TRACE_RISK


# --- OCR-tolerance ---------------------------------------------------------
# Tesseract læser dansk 6-punkts tryk med ~90% konfidens, og de 10% rammer
# systematisk æ/ø/å. Uden tolerance misser motoren netop de allergener,
# der faktisk stod på pakken.

OCR_GARBLED = [
    ("maelkeprotein", "Havregryn, skummetmaalkspulver, sukker", State.CONTAINS),
    ("jordbaer", "Havregryn, tørrede jordbzer 4%, salt", State.CONTAINS),
    ("maelkeprotein", "Hvedemel, fl0de, sukker", State.CONTAINS),
    ("aeg", "Mel, aeggeblomme, smoer", State.CONTAINS),
]

@pytest.mark.parametrize("slug,text,expected", OCR_GARBLED)
def test_ocr_tolerance_catches_garbled(slug, text, expected):
    assert R.evaluate(slug, text, ocr=True).state is expected

CLEAN = [
    "Rismel, solsikkeolie, salt, gærekstrakt",
    "Vand, sukker, citronsyre, farve E160a",
    "Kikærter, tahin, hvidløg, spidskommen, olivenolie",
    "Tomat, basilikum, oregano, havsalt, peber",
]

@pytest.mark.parametrize("text", CLEAN)
def test_ocr_tolerance_no_false_positives(text):
    """Fuzzy-matchning må ikke gøre rene deklarationer røde."""
    for slug in R.allergens:
        assert R.evaluate(slug, text, ocr=True).state is not State.CONTAINS

def test_ocr_mode_still_never_returns_free():
    for slug in R.allergens:
        for text in ["vand, salt", "", None, "skummetmaalkspulver"]:
            assert R.evaluate(slug, text, ocr=True).state is not State.FREE

def test_exclusions_survive_ocr_mode():
    """'ægte vanilje' må heller ikke give æg når tolerancen er slået til."""
    assert R.evaluate("aeg", "Sukker, ægte vanilje", ocr=True).state is not State.CONTAINS
