"""Regressionstest for matcheren. Kør: python -m pytest tests/ -q"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pytest
from app.matcher import Basis, Ruleset, State

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

# --- spor er ikke det samme som indhold ------------------------------------
# Forskellen betyder noget for dem, der bruger appen: nogle tåler spor,
# andre gør ikke. Tidligere gjorde en sporangivelse det nævnte allergen
# RØDT (som stod det i ingredienslisten) og alle andre allergener gule —
# også dem, etiketten slet ikke nævnte. Begge dele er rettet her.

def test_spor_af_allergenet_er_gult_ikke_roedt():
    v = R.evaluate("maelkeprotein", "Hvedemel, sukker. Kan indeholde spor af mælk.")
    assert v.state is State.TRACE_RISK
    assert v.basis is Basis.TRACE_STATEMENT


def test_spor_af_noget_ANDET_rammer_ikke_dette_allergen():
    """Etiketten siger hvilke spor der er risiko for. Nævner den kun
    nødder, er mælk ikke en sporrisiko — og en app, der råber ulv ved
    hver eneste vare, bliver holdt op med at blive læst."""
    v = R.evaluate("maelkeprotein", "Hvedemel, sukker. Kan indeholde spor af nødder.")
    assert v.state is State.UNKNOWN
    assert R.evaluate("noedder", "Hvedemel, sukker. Kan indeholde spor af nødder.").state \
        is State.TRACE_RISK


def test_ingredienslisten_vinder_over_sporangivelsen():
    """Står allergenet BÅDE i listen og i sporangivelsen, er det rødt."""
    for t in [
        "Hvedemel, mælk, sukker. Kan indeholde spor af nødder.",
        "Hvedemel, mælk. Kan indeholde spor af mælk og nødder.",
    ]:
        assert R.evaluate("maelkeprotein", t).state is State.CONTAINS


def test_vag_sporangivelse_advarer_stadig_bredt():
    """Kan vi ikke se HVAD der er spor af, må alle få den gule."""
    v = R.evaluate("maelkeprotein", "Hvedemel, sukker. Kan indeholde spor af andre kornsorter.")
    assert v.state is State.TRACE_RISK
    assert v.basis is Basis.TRACE_UNSPECIFIED


def test_anlaegsformulering_taeller_som_spor():
    v = R.evaluate("noedder", "Mel, salt. Fremstillet på et anlæg, hvor der også anvendes nødder.")
    assert v.state is State.TRACE_RISK
    assert v.basis is Basis.TRACE_STATEMENT


def test_spor_uden_punktum_sluger_ikke_resten():
    """OCR taber punktummer. Uden loft på spanet kunne én markør sluge
    resten af teksten og gøre et rigtigt allergen til "kun spor" —
    under-advarsel er den farlige retning."""
    lang = ("Kan indeholde spor af nødder " + "fyld " * 60 + "mælk sukker")
    assert R.evaluate("maelkeprotein", lang).state is State.CONTAINS


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
    # skal være rene for ALLE allergener — tahin (sesam) og tomat røg ud,
    # da regelsættet voksede til EU-14 + tomat
    "Rismel, solsikkeolie, salt, gærekstrakt",
    "Vand, sukker, citronsyre, farve E160a",
    "Kikærter, hvidløg, spidskommen, olivenolie, citronsaft",
    "Agurk, basilikum, oregano, havsalt, peber",
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


# --- EU-14 + tomat ---------------------------------------------------------
# Én positiv og én orddannelses-negativ pr. regel. Negativerne er ord, hvor
# allergenet står bagest eller slet ikke er der — naiv substring ville
# ramme dem alle.

EU14 = [
    # gluten
    ("gluten", "Hvedemel, vand, gær, salt", State.CONTAINS),
    ("gluten", "Bygmalt, humle, vand", State.CONTAINS),
    ("gluten", "Havregryn, rosiner", State.CONTAINS),
    ("gluten", "Boghvedemel, bagepulver, salt", State.UNKNOWN),
    ("gluten", "Glukosesirup, maltodextrin, aroma", State.UNKNOWN),
    # krebsdyr
    ("krebsdyr", "Rejer 40%, vand, salt", State.CONTAINS),
    ("krebsdyr", "Jomfruhummer, citron", State.CONTAINS),
    ("krebsdyr", "Skaldyrsfond, vand", State.TRACE_RISK),
    # fisk
    ("fisk", "Torskefilet, rasp, rapsolie", State.CONTAINS),
    ("fisk", "Ansjoser, olivenolie, salt", State.CONTAINS),
    ("fisk", "Tunge, persillesovs", State.TRACE_RISK),   # søtunge eller oksetunge?
    ("fisk", "Oksetunge, lage, salt", State.UNKNOWN),    # okse — ikke fisk
    # jordnødder er en bælgfrugt med egen post — og IKKE en nød
    ("jordnoed", "Jordnøddeolie, salt", State.CONTAINS),
    ("noedder", "Jordnøddeolie, salt", State.UNKNOWN),
    # soja — og pointen med per-allergen-regler: sojamælk er soja, ikke mælk
    ("soja", "Sojalecithin, kakaomasse", State.CONTAINS),
    ("soja", "Sojamælk, havregryn", State.CONTAINS),
    ("maelkeprotein", "Sojamælk, vand", State.UNKNOWN),
    # nødder
    ("noedder", "Hakkede hasselnødder 13%", State.CONTAINS),
    ("noedder", "Marcipan, sukker", State.CONTAINS),
    ("noedder", "Mandelmælk, vand", State.CONTAINS),
    ("maelkeprotein", "Mandelmælk, vand", State.UNKNOWN),
    ("noedder", "Revet muskatnød, kanel", State.UNKNOWN),
    ("noedder", "Kokosmel, kokosnødder, sukker", State.UNKNOWN),
    ("noedder", "Sukker, mandelaroma", State.TRACE_RISK),
    # selleri, sennep, sesam
    ("selleri", "Knoldselleri, løg, gulerod", State.CONTAINS),
    ("sennep", "Dijonsennep, honning", State.CONTAINS),
    ("sesam", "Tahin (sesampasta), kikærter", State.CONTAINS),
    ("sesam", "Hummus med paprika", State.TRACE_RISK),
    # sulfit — men sulfat er noget andet
    ("sulfit", "Tørrede abrikoser, konserveringsmiddel e220", State.CONTAINS),
    ("sulfit", "Hvidvin, natriummetabisulfit", State.CONTAINS),
    ("sulfit", "Mineralsalte (magnesiumsulfat)", State.UNKNOWN),
    # lupin
    ("lupin", "Lupinmel, vand", State.CONTAINS),
    # bløddyr
    ("bloeddyr", "Blåmuslinger, hvidvin, persille", State.CONTAINS),
    ("bloeddyr", "Østerssauce, sukker", State.CONTAINS),
    # tomat
    ("tomat", "Tomatpuré 20%, løg", State.CONTAINS),
    ("tomat", "Ketchup, sennepsfrø", State.CONTAINS),
    ("tomat", "Aromatiseret sort te", State.UNKNOWN),
]

@pytest.mark.parametrize("slug,text,expected", EU14)
def test_eu14_state(slug, text, expected):
    assert R.evaluate(slug, text).state is expected


def test_all_eu14_covered():
    """Alle 14 EU-allergener skal findes i regelsættet med korrekt OFF-tag."""
    expected = {
        "en:gluten", "en:crustaceans", "en:eggs", "en:fish", "en:peanuts",
        "en:soybeans", "en:milk", "en:nuts", "en:celery", "en:mustard",
        "en:sesame-seeds", "en:sulphur-dioxide-and-sulphites", "en:lupin",
        "en:molluscs",
    }
    actual = {
        r["meta"]["off_tag"]
        for r in R.allergens.values()
        if r["meta"].get("eu14")
    }
    assert actual == expected


# OCR-fuzzy leder i vinduer INDE i sammensatte ord, så et uskyldigt ord ét
# redigeringstrin fra et allergen bliver rødt, hvis det ikke står i exclude.
# Hvert af de her ord har fundet vej til exclude af netop den grund.

OCR_WINDOW_TRAPS = [
    ("gluten", "Hvide bønner, vand, salt"),          # hvide ≈ hvede
    ("gluten", "Smeltet smør, sukker"),              # smelt ≈ spelt
    ("gluten", "Boghvedemel, vand"),                 # vinduet "hvede" i boghvede
    ("krebsdyr", "Varenummer 1234, sukker"),         # nummer ≈ hummer
    ("krebsdyr", "Grillet kylling, salt"),           # grill ≈ krill
    ("fisk", "Norsk rapsolie, salt"),                # norsk ≈ torsk
    ("noedder", "Rystes om nødvendigt før brug"),    # nødvendig ≈ nødde
    ("noedder", "Revet muskatnød, kanel"),           # vinduet "nødde" i muskatnød
    ("sesam", "Tahiti-vanilje, fløde"),              # tahiti ≈ tahin
    ("sulfit", "Magnesiumsulfat, kalk"),             # sulfat ≈ sulfit
    ("bloeddyr", "Kanelsnegle med remonce"),         # vinduet "snegl" i kanelsnegle
    ("bloeddyr", "Sild fanget i Østersøen"),         # vinduet "østers" i østersøen
    ("tomat", "Aromatiseret te, sukker"),            # vinduet "romat" i aromatiseret
]

@pytest.mark.parametrize("slug,text", OCR_WINDOW_TRAPS)
def test_ocr_window_traps_stay_silent(slug, text):
    assert R.evaluate(slug, text, ocr=True).state is not State.CONTAINS


OCR_GARBLED_EU14 = [
    ("bloeddyr", "Blaamuslinger, vand, salt", State.CONTAINS),
    ("jordnoed", "Ristede jordn0dder, salt", State.CONTAINS),
    ("noedder", "Hasseln0dder, sukker", State.CONTAINS),
]

@pytest.mark.parametrize("slug,text,expected", OCR_GARBLED_EU14)
def test_ocr_tolerance_eu14(slug, text, expected):
    assert R.evaluate(slug, text, ocr=True).state is expected


# --- sammensætninger med allergenet BAGEST ------------------------------
# Lookbehind'en (?<![a-zæøå]) rammer præfikser, ikke suffikser, så hvert
# af disse ord SKAL stå eksplicit i contains. Gennemgangen 2026-08-21
# fandt 30+ tavse ord — den her tabel er vagten, der opdager det næste.

ETIKETORD = [
    # (slug, tekst som den står på en dansk etiket)
    ("maelkeprotein", "Feta 20%, oliven, oregano"),
    ("maelkeprotein", "Halloumi, olivenolie"),
    ("maelkeprotein", "Hytteost 5%, purløg"),
    ("maelkeprotein", "Brie, karse"),
    ("maelkeprotein", "Gouda 45+, salt"),
    ("maelkeprotein", "Havarti 45+"),
    ("maelkeprotein", "Danbo 30+"),
    ("maelkeprotein", "Gedemælk, salt"),
    ("maelkeprotein", "Salatost i olie"),
    ("jordbaer", "Skovjordbær 40%, sukker"),
    ("jordbaer", "Markjordbær, sukker"),
    ("aeg", "Helæg (pasteuriseret), sukker"),
    ("noedder", "Råmarcipan 25%, sukker"),
    ("tomat", "Cherrytomater 40%, olivenolie"),
    ("tomat", "Blommetomat, basilikum"),
    ("selleri", "Stangselleri, gulerod"),
    ("sulfit", "Vin, kaliummetabisulfit"),
    ("fisk", "Alaskasej 60%, rasp"),
    ("krebsdyr", "Langust, hvidvin"),
    ("krebsdyr", "Kongekrabbe, mayonnaise"),
    ("bloeddyr", "Sandmusling i lage"),
]


@pytest.mark.parametrize("slug,tekst", ETIKETORD)
def test_allergen_bagest_i_ordet_findes(slug, tekst):
    v = R.evaluate(slug, tekst)
    assert v.state == State.CONTAINS, f"{tekst!r} gav {v.state.value} for {slug}"


# De undtagelser, ordene ovenfor IKKE må ødelægge.
@pytest.mark.parametrize("slug,tekst", [
    ("maelkeprotein", "Kokosmælk, vand"),
    ("maelkeprotein", "Kakaosmør, sukker"),
    ("maelkeprotein", "Mælkebøtterod, cikorie"),
    ("maelkeprotein", "Mælkesyre (E270)"),
    ("aeg", "Ægte vanilje, sukker"),
    ("fisk", "Sejt rugbrød, hvedemel"),
])
def test_undtagelserne_holder_stadig(slug, tekst):
    assert R.evaluate(slug, tekst).state != State.CONTAINS, f"falsk positiv: {tekst!r}"


def test_sporangivelse_taber_ikke_et_allergen_etiketten_naevner():
    """"Spor af gedemælk" skal give gul for mælkeprotein, ikke tavshed."""
    for tekst, slug in [
        ("Mel, salt. Kan indeholde spor af nødder og gedemælk.", "maelkeprotein"),
        ("Mel, salt. Kan indeholde spor af mælk og stangselleri.", "selleri"),
    ]:
        v = R.evaluate(slug, tekst)
        assert v.state == State.TRACE_RISK, f"{tekst!r} gav {v.state.value} for {slug}"


def test_spor_passet_ser_ikke_exclude():
    """
    Spor-passet kører `contains` på RÅ tekst (`_find(udsnit, udsnit, ...)`),
    ikke på den maskerede — det ser altså ikke `exclude`. Derfor giver
    "spor af mælkesyre" GULT, selvom "mælkesyre" i ingredienslisten er
    maskeret væk og giver gråt.

    De to pas svarer altså forskelligt på det samme ord. Retningen er den
    sikre (over-advarsel), og det er derfor ikke rettet — men det er en
    reel uoverensstemmelse, og testen står som en vagt: ændrer nogen
    spor-passet til at maskere, skal det være en bevidst beslutning.
    """
    i_listen = R.evaluate("maelkeprotein", "Mel, mælkesyre (E270), salt.")
    i_sporet = R.evaluate("maelkeprotein", "Mel. Kan indeholde spor af mælkesyre.")
    assert i_listen.state == State.UNKNOWN, "exclude holdt ikke i contains-passet"
    assert i_sporet.state == State.TRACE_RISK, (
        f"spor-passet gav {i_sporet.state.value} — hvis det er blevet "
        "maskeret, så opdatér allergen-regler-skillen i samme commit"
    )
