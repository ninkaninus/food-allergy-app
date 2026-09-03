"""
Karakteriseringstests for `app/static/index.html` — den ene brugerflade.

Der findes ingen JS-testkører i repoet (frontend er én fil uden byggetrin,
se CLAUDE.md), så testene herunder er statisk kontrol af den udgivne
kildetekst, af samme art som testene i test_offentlig_flade.py: de beviser
IKKE, at en browser rent faktisk opfører sig rigtigt, kun at KILDEN stadig
har den ønskede form.

Skrevet til 0.22.0: kameraet starter automatisk, kun ved allerede givet
tilladelse, og "motoren"/"OCR" er væk fra det, familien læser. Udvidet
efter kodegennemgangen af samme udgivelse: den forrige vares dom skal
skjules, mens der ledes efter en ny, kun ét kamera kan være i gang ad
gangen, og kameraet skal slukke, når man ikke kigger.
"""
import os
import pathlib
import re
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp())
os.environ.setdefault(
    "RULES_PATH",
    str(pathlib.Path(__file__).resolve().parents[1] / "data" / "allergens.yaml"),
)
os.environ.setdefault("COOKIE_SECURE", "0")
os.environ.setdefault("CHECK_PWNED_PASSWORDS", "0")

from fastapi.testclient import TestClient

from app.main import app


def _forsiden() -> str:
    return TestClient(app).get("/").text


def _funktionskrop(html: str, start_markoer: str, slut_markoer: str) -> str:
    """
    Udtrækker JS-kildetekst mellem to markører. Fejler med en læselig
    besked frem for en bar `ValueError` med et tegn-tal — så en kommentar,
    der bliver omformuleret, giver en fejl man kan handle på, ikke en
    gætteleg om hvilken markør der er brudt.
    """
    try:
        start = html.index(start_markoer) + len(start_markoer)
    except ValueError:
        raise AssertionError(
            f"startmarkør ikke fundet i den udgivne side: {start_markoer!r}"
        ) from None
    try:
        slut = html.index(slut_markoer, start)
    except ValueError:
        raise AssertionError(
            f"slutmarkør ikke fundet efter startmarkøren {start_markoer!r}: "
            f"{slut_markoer!r}"
        ) from None
    return html[start:slut]


# --- "motoren" og "OCR" ud af det, familien læser ------------------------

def test_brugervendt_tekst_siger_appen_og_laeste_ikke_motoren_og_ocr():
    """
    Familien synes "motoren" lyder mærkeligt, og "OCR" er ikke et ord de
    bruger. De rendrede strenge, en bruger rent faktisk ser, skal sige
    "appen"/"læste"/"læsning" i stedet. Kode-kommentarer er ikke omfattet
    — kun det, der ender i DOM'en.
    """
    html = _forsiden()

    forventede = [
        "Deklaration, som appen læste den",
        "ligner et allergen i den læste tekst — skal efterses",
        "Log ind under Indstillinger for at læse en deklaration.",
        "Billedet kunne ikke læses. Prøv igen.",
        "(appen læste «",
        "Appen fandt ingen af dine allergener — men læsningen kan have "
        "tabt dem. Læs teksten igennem.",
        "Appen har slet ikke tjekket det her billede. Læs teksten selv.",
        "oplyst af Open Food Facts",
        "spor oplyst af Open Food Facts",
    ]
    for streng in forventede:
        assert streng in html, f"mangler i den udgivne side: {streng!r}"

    gammel_tekst = [
        "Deklaration, som motoren læste den",
        "ligner et træf i den læste tekst — skal efterses",
        "omtrentligt match i OCR-tekst",
        "Log ind under Indstillinger for at bruge OCR.",
        "OCR fejlede (",
        "Sikkerhed ${d.confidence}%.",
        "Læsekvalitet ${d.confidence}%.",
        "Motoren fandt ingen af dine allergener — men OCR kan have tabt dem.",
        "Appen fandt ingen af dine allergener — men læsningen kan have "
        "tabt bogstaver. Læs teksten igennem.",
        "Motoren blev slet ikke kørt på det her billede.",
        "allergen-tag fra Open Food Facts",
        "sportag fra Open Food Facts",
        "Din browser bruger zxing-fallbacken",
        "varer i den lokale cache.",
    ]
    for streng in gammel_tekst:
        assert streng not in html, f"gammel udviklertekst står stadig: {streng!r}"


def test_ved_det_ikke_paastaar_stadig_ikke_at_vaere_sikker():
    """
    Invarianten oversat til ord: fravær af fund er ikke det samme som
    frit. Bundet til selve COPY.unverified-linjen, ikke til en fri
    substrengssøgning — ellers kunne linjen forsvinde fra COPY og overleve
    testen, hvis ordene stod tilbage i en kommentar et andet sted i filen.
    """
    html = _forsiden()
    m = re.search(r"unverified:\[(.*?)\],\n\s*safe:", html)
    assert m, "COPY.unverified findes ikke i den ventede form"
    linje = m.group(1).lower()
    assert "det er ikke det samme som frit" in linje


def test_konfidenstal_vises_kun_naar_det_advarer():
    """
    rapidocr scorer 96-98% på stort set alt, også på volapyk (se
    ocr-deklarationer-skillen) — et tal, der altid vises, ligner
    information uden at være det. Linjen skal kun optræde under 65%, og
    som en advarsel, ikke en statusoplysning.
    """
    html = _forsiden()
    krop = _funktionskrop(html, "const usikker = ", "\n  $('#ocrStatus').innerHTML")
    assert "d.confidence < 65" in krop
    assert "Læsningen er usikker (" in krop
    assert "Math.round(d.confidence)" in krop, (
        "konfidenstallet skal vises som et rundet heltal, ikke rå decimaler"
    )
    assert " %)" in krop, "mellemrum før procenttegnet — dansk talformat"


# --- serverens rå fejlstrenge må ikke ende på skærmen ---------------------

def test_ocr_fejl_skelner_statuskode_og_skjuler_serverens_egen_tekst():
    html = _forsiden()
    # "if(!r.ok){" og "if(!d.ok){" findes flere steder i filen (gemFoto,
    # bekræftelse, søgning …) — markøren for /api/ocr-kaldet skal derfor
    # bindes til den kommentar, der kun findes ved netop dette kald.
    krop = _funktionskrop(
        html,
        "// Statuskoden gives videre, ligesom i gemFoto()",
        "\n  const d = await r.json();",
    )
    assert "r.status === 401" in krop
    assert "r.status === 413" in krop
    krop2 = _funktionskrop(html, "if(!d.ok){", "\n  $('#declEdit').value")
    assert "textContent = d.error" not in krop2, (
        "serverens rå fejlstreng (fx 'Tesseract fejlede: …') må ikke vises "
        "direkte til familien"
    )


# --- kameraet må kun starte automatisk ved allerede given tilladelse -----

def test_autostart_tjekker_synlighed_foer_permissions():
    html = _forsiden()
    krop = _funktionskrop(
        html, "async function autostartCam(){", "\nautostartCam();",
    )
    assert "navigator.permissions?.query" in krop, (
        "autostartCam() tjekker ikke, om Permissions API findes overhovedet "
        "— Safari mangler den, og et ubetinget kald ville kaste"
    )
    synlig_pos = krop.find("visibilityState !== 'visible'")
    query_pos = krop.find("navigator.permissions.query")
    assert synlig_pos != -1, (
        "autostartCam() tjekker ikke længere, om fanen rent faktisk er "
        "synlig — kameraet kan tænde i en baggrundsfane"
    )
    assert synlig_pos < query_pos, (
        "synligheds-tjekket skal ske FØR Permissions API spørges"
    )
    assert "catch" in krop, (
        "intet catch om permissions.query() — Safari kaster her, og uden "
        "fangst ville autostarten vælte resten af opstarten"
    )


def test_autostart_starter_kun_kameraet_ved_et_direkte_granted_svar():
    """
    Bundet til FORMEN af betingelsen, ikke blot rækkefølgen af strenge i
    kildeteksten: `if(status.state === 'granted'){ /* noop */ }
    await startCam(true);` ville også bestå en position-baseret test
    (granted nævnes før startCam(true) et sted i teksten), men starter
    faktisk kameraet uanset tilladelse.
    """
    html = _forsiden()
    krop = _funktionskrop(
        html, "async function autostartCam(){", "\nautostartCam();",
    )
    assert re.search(
        r"status\.state\s*===\s*'granted'\s*\)\s*await\s+startCam\(true\)", krop
    ), (
        "startCam(true) er ikke den direkte konsekvens af "
        "'status.state === granted' — autostarten kan starte kameraet "
        "uanset svaret"
    )


def test_scan_knappen_bruger_samme_startcam_som_autostarten():
    html = _forsiden()
    knap = _funktionskrop(html, "$('#camBtn').onclick = () => {", "\n};")
    assert "stopCam()" in knap, "knappen kan ikke længere slå kameraet fra"
    assert "startCam(false)" in knap, (
        "knappen starter ikke længere kameraet via startCam() — den er "
        "også vejen tilbage, hvis autostarten er fejlet eller slået fra"
    )


def test_kamerafejl_ved_adgang_skelnes_paa_aarsag_og_er_stille_ved_autostart():
    """
    Med autostart bliver "kameraet er optaget" langt mere almindeligt end
    "intet svar endnu" — én fælles besked ville sende folk forkert hen.
    `silent` skal stadig gælde denne besked (en fejlet autostart må ikke
    se ud som en fejl, brugeren ikke bad om).
    """
    html = _forsiden()
    krop = _funktionskrop(html, "}catch(err){", "\n  }finally{")
    assert krop.count("if(!silent)") == 1
    assert "NotAllowedError" in krop
    assert "NotReadableError" in krop
    assert "AbortError" in krop


def test_zxing_fejlbesked_er_ikke_tavs_heller_ikke_ved_autostart():
    """
    Modsat kamera-adgangsfejlen handler dette ikke om tilladelse, og
    brugeren har allerede set videoen blinke op — beskeden skal vises
    uanset `silent`.
    """
    html = _forsiden()
    krop = _funktionskrop(html, "if(!native && !mod){", "\n  }")
    assert "if(!silent)" not in krop, (
        "zxing-fejlen er stadig betinget af silent — en fejlet autostart "
        "ville nu tie, selvom brugeren allerede har set kameraet forsøge"
    )
    assert "Kunne ikke starte scanneren. Tast koden ind." in krop


# --- kun ét kamera ad gangen, ingen dobbelte tick-løkker ------------------

def test_kun_eet_kamera_ad_gangen():
    html = _forsiden()
    krop = _funktionskrop(html, "async function startCam(silent){", "\n}\n\n$('#camBtn')")
    assert "if(stream || camStarter) return;" in krop, (
        "startCam() kan stadig starte et kamera nummer to, mens et første "
        "er undervejs — den førstes MediaStream mister sin reference og "
        "stoppes aldrig, og kameraindikatoren bliver ved med at lyse"
    )
    # Den sandsynlige regression er ikke, at vagten forsvinder — det er,
    # at `camStarter` ryddes for TIDLIGT. Ryddes den før `stream` er sat,
    # er der igen et vindue, hvor både `stream` er null og `camStarter`
    # false, mens en stream lever. Bind derfor til RÆKKEFØLGEN.
    assert "camStarter = true" in krop
    assert re.search(r"\}finally\{\s*camStarter = false;\s*\}", krop), (
        "camStarter ryddes ikke i en finally — kaster noget undervejs, "
        "kan kameraet aldrig startes igen"
    )
    mellem = krop[krop.index("camStarter = false"):krop.index("stream = s;")]
    assert "await" not in mellem, (
        "der er et await mellem camStarter ryddes og stream tildeles — "
        "dér kan et andet kald nå at starte et kamera nummer to"
    )


def test_kamerageneration_forhindrer_at_en_forsinket_start_overlever_stop():
    html = _forsiden()
    krop = _funktionskrop(html, "async function startCam(silent){", "\n}\n\n$('#camBtn')")
    # IKKE `count(...) == N`. Den form fejler på en RETTELSE, der
    # tilføjer et tjek mere — og det skete: fundet "stregkode fanget i
    # samme øjeblik som fanen skiftes" krævede et fjerde tjek, og testen
    # gjorde den korrekte rettelse rød. En test, der straffer et rigtigt
    # svar, er værre end ingen test.
    assert krop.count("gen !== camGen") >= 3, (
        "startCam() tjekker ikke generationstælleren nok steder — en "
        "getUserMedia eller zxing-indlæsning, der resolver EFTER "
        "stopCam(), kan stadig nå at tænde kameraet igen"
    )
    assert re.search(r"if\(gen !== camGen\)\{ s\.getTracks\(\)", krop), (
        "en forsinket getUserMedia tjekker ikke generationen, FØR den "
        "tildeler `stream` — så overlever den et stop"
    )
    assert re.search(r"catch\{ if\(gen === camGen\) stopCam\(\); return; \}", krop), (
        "en afvist cam.play() kalder stopCam() ubetinget — den ville "
        "tælle generationen op udefra og dræbe det NÆSTE kamera, "
        "brugeren allerede har bedt om"
    )
    assert "s.getTracks().forEach(t => t.stop())" in krop, (
        "en forsinket getUserMedia, der opdager sig selv forældet, lukker "
        "ikke det spor, den lige har åbnet — telefonens kameraindikator "
        "bliver ved med at lyse"
    )


def test_stopcam_oeger_generationen_og_stopper_sporet():
    html = _forsiden()
    krop = _funktionskrop(html, "function stopCam(){", "\n}")
    assert "camGen++" in krop, (
        "stopCam() øger ikke generationstælleren — en løbende tick-løkke "
        "eller en ventende opstart kan overleve et stop"
    )
    assert "getTracks().forEach(t => t.stop())" in krop


def test_tick_loekken_kan_ikke_fordobles():
    html = _forsiden()
    krop = _funktionskrop(html, "const tick = async () => {", "\n  tick();")
    assert "if(gen === camGen) setTimeout(" in krop, (
        "tick() planlægger sin næste runde uden at tjekke generationen — "
        "dér ville en fordobling faktisk komme fra"
    )
    assert re.search(r"if\(code\)\{\s*//[^\n]*\n(\s*//[^\n]*\n)*\s*if\(gen !== camGen\) return;", krop), (
        "en stregkode, der afkodes FÆRDIG efter et fanebytte, slås stadig "
        "op: telefonen vibrerer uden grund, og der lægges en dom om en "
        "tilfældig vare i en visning, brugeren har forladt"
    )


def test_camknap_skifter_tekst_mellem_scan_og_stop():
    """
    "Scan" betyder nu "stop", når kameraet allerede kører af sig selv —
    uden tekstskiftet slukker en dagplejer det, hun troede hun tændte.
    """
    html = _forsiden()
    start_krop = _funktionskrop(html, "async function startCam(silent){", "\n}\n\n$('#camBtn')")
    assert "$('#camBtn').textContent = 'Stop';" in start_krop
    stop_krop = _funktionskrop(html, "function stopCam(){", "\n}")
    assert "$('#camBtn').textContent = 'Scan';" in stop_krop


def test_scanknap_er_fyldt_og_slaa_op_er_ghost():
    """
    "Scan" er nu både den primære vej OG vejen tilbage, når autostarten
    fejler — den skal se sådan ud.
    """
    html = _forsiden()
    # Bind til class-attributten, ikke til hele taggen: etiketten på
    # #camBtn SKIFTER (Scan/Stop), og et tilføjet type="button" ville
    # ellers brække en test om noget helt andet.
    assert re.search(r'<button class="btn" id="camBtn"', html), "»Scan« er ikke den fyldte knap"
    assert re.search(r'<button class="btn ghost" id="go"', html), "»Slå op« er ikke ghost"


def test_kameraet_staar_under_indtastningsfeltet():
    """
    Tænder kameraet 200-800 ms efter indlæsning (autostart), må det ikke
    skubbe #ean/#camBtn/#go ned, mens en tommel er på vej mod en af dem.
    """
    html = _forsiden()
    assert html.index('id="scanHint"') < html.index('<video id="cam"')


# --- den forrige vares dom må ikke stå under et kørende kamera -----------

def test_kameraet_skjuler_forrige_doms_flade_naar_det_taender():
    """
    Scan vare A (grøn "SIKKER") → tryk "Scan" for vare B → uden dette står
    A's dom stadig synlig under søgeren, mens B fanges — præcis den
    forveksling, appen findes for at forhindre.
    """
    html = _forsiden()
    krop = _funktionskrop(html, "async function startCam(silent){", "\n}\n\n$('#camBtn')")
    assert "glemVistDom();" in krop, "kameraet rydder ikke den forrige vares dom væk"
    assert krop.index("glemVistDom();") < krop.index("stream = s;"), (
        "dommen skjules ikke, før kameraet rent faktisk vises — der kan "
        "nå at stå et billede med begge dele synlige"
    )


def test_den_forrige_doms_oprydning_er_ET_sted():
    """
    De tre linjer hører sammen og skal blive ved med at gøre det.
    Kameraet var før det eneste sted, de stod; nu kalder også
    malVaelgPanel() og chip-klikket dem, fordi grundlaget for en vist dom
    kan holde op med at gælde uden at nogen scanner noget.

    - opslagNr++ : et opslag, der stadig er undervejs, sætter ellers
      fladen synlig igen fra sin egen fetch-fortsættelse (visSlab og
      render), som intet ved om, at spørgsmålet er blevet stillet. På
      mobildata i en butik er det normalen, ikke kanten.
    - #confirmPanel er SØSKENDE til #verdict, ikke barn, og følger ikke
      med, når kortet skjules.
    """
    krop = _funktionskrop(_forsiden(), "function glemVistDom(){", "\n}")
    assert "opslagNr++;" in krop, (
        "et opslag undervejs kan stadig folde sin dom ud bagefter"
    )
    assert "$('#confirmPanel').hidden = true;" in krop, (
        "bekræftelsesformularen for den forrige vare bliver stående"
    )
    assert "$('#verdict').hidden = true;" in krop, "selve fladen bliver stående"

    # …og de tre kaldes fra hvert af de steder, hvor grundlaget kan falde bort.
    html = _forsiden()
    for start, slut, hvor in [
        ("function malVaelgPanel(){", "\n}", "spørgsmålet stilles"),
        ("$('#prefChips').querySelectorAll('.chip').forEach", "\n    });",
         "et allergen slås til eller fra"),
    ]:
        assert "glemVistDom();" in _funktionskrop(html, start, slut), (
            f"dommen bliver stående, når {hvor} — se "
            "tests/test_frontend_adfaerd.py for adfærden"
        )


# --- kameraet skal slukke, når man ikke kigger ----------------------------

def test_fanebytte_vaek_fra_scan_slukker_kameraet():
    html = _forsiden()
    krop = _funktionskrop(
        html,
        "document.querySelectorAll('nav.tabs button').forEach(b => b.onclick = () => {",
        "\n});",
    )
    assert "stopCam()" in krop
    assert "b.dataset.view !== 'scan'" in krop, (
        "kameraet slukkes ikke specifikt ved at FORLADE scan-fanen — enten "
        "slukker det slet ikke, eller det slukker for tidligt"
    )


def test_baggrund_slukker_kameraet():
    html = _forsiden()
    assert "document.addEventListener('visibilitychange'" in html, (
        "intet lytter efter, at appen går i baggrunden — kameraet kan "
        "blive ved med at filme, mens telefonen ligger i lommen"
    )
    krop = _funktionskrop(
        html, "document.addEventListener('visibilitychange', () => {", "\n});",
    )
    assert "stopCam()" in krop
    assert "visibilityState !== 'visible'" in krop


# --- teksten om at søge i det lokale korpus, ikke motoren -----------------

def test_attribution_tekst_siger_gemt_i_appen():
    html = _forsiden()
    assert "${n} varer er gemt i appen." in html


def test_reservelaeseren_siges_hoejt():
    """
    Svarer OCR-tjenesten ikke, falder appen tilbage til Tesseract
    (`app/ocr_klient.py`). Målt på familiens egne butiksfotos finder den
    2,8 gange FÆRRE rigtige danske ord — altså er netop DEN læsning
    svagere end normalt, og forhåndstjekket under den er tilsvarende
    mindre værd.

    Serveren sagde det selv i `hint`: "(OCR-tjenesten svarede ikke —
    brugte den indbyggede læsning, som er svagere.)". Da 0.22.0 holdt op
    med at vise `hint`, forsvandt oplysningen — uden at nogen valgte
    det. Under-advarsel er den farlige retning, så den bor nu i frontend.
    """
    html = _forsiden()
    assert "d.engine !== 'rapidocr'" in html, (
        "der er ingen kontrol af, om reservelæseren blev brugt"
    )
    assert "svagere reservelæsning" in html, (
        "familien får ikke at vide, at læsningen er svagere end normalt"
    )


# --- appen spørger, den gætter ikke (0.23.1) ------------------------------
#
# En frisk telefon uden login blev TAVST sat til alle 17 allergener:
#
#     if(!prefs.allergens.length) prefs.allergens = ALLERGENS.map(a => a.slug);
#
# Og fordi en samlet dom kræver, at ALLE vurderede allergener er manuelt
# bekræftet frie, blev et rugbrød, familien selv havde godkendt, ikke
# bare gråt for dagplejeren — det blev RØDT, fordi motoren finder gluten
# i rugmelet. Backend-siden af den historie står i
# tests/test_udlogget_allergensaet.py; her holdes den vagt, der gør, at
# spørgsmålet overhovedet bliver stillet.
#
# Den anden vej er farligere: et tomt sæt må aldrig blive til "tjek
# ingenting". Serveren afviser det med 400, og frontend skal lade være
# med at kalde.

def test_frisk_telefon_saettes_ikke_tavst_til_alle_17():
    html = _forsiden()
    assert "if(!prefs.allergens.length) prefs.allergens =" not in html, (
        "opstarten gætter igen på et allergensæt, ingen har valgt"
    )
    krop = _funktionskrop(html, "function effektivAllergener(){", "\nconst harValgtAllergener")
    assert "ALLERGENS.map" not in krop, (
        "effektivAllergener() falder tilbage til alle 17 igen — så er "
        "spørgsmålet aldrig noget, brugeren kommer til at se"
    )
    assert "return sæt || []" in krop


def test_scan_indgangen_spoerger_foer_den_kalder_serveren():
    """Rækkefølgen ER vagten: prøven skal stå før fetch, ikke efter."""
    krop = _funktionskrop(_forsiden(), "async function lookup(code){", "function highlight(text")
    assert "harValgtAllergener()" in krop, "scan-indgangen har ingen vagt"
    assert krop.index("harValgtAllergener()") < krop.index("fetch(`/api/scan/"), (
        "vagten står EFTER kaldet — så er den ikke en vagt"
    )


def test_soege_indgangen_har_den_samme_vagt():
    """
    Listen er den anden indgang til nøjagtig samme domslogik
    (`_verdict_rows` på serveren). Rettes kun scan-skærmen, svarer listen
    videre på et gæt.
    """
    krop = _funktionskrop(_forsiden(), "async function soeg(){", "// status-knapper med antal")
    assert "harValgtAllergener()" in krop, "søgningen har ingen vagt"
    assert krop.index("harValgtAllergener()") < krop.index("fetch('/api/soeg?"), (
        "vagten står EFTER kaldet — så er den ikke en vagt"
    )


def test_spoergsmaalet_findes_og_ligner_ikke_en_dom():
    """
    Panelet må ikke bære en af dommens fire farver: et ubesvaret
    spørgsmål, der ser ud som et svar, er værre end ingen advarsel.
    Farverne sættes på `#slab` via `data-r` — spørgsmålet er en almindelig
    `.sec`.
    """
    html = _forsiden()
    panel = _funktionskrop(html, '<section class="sec" id="vaelgPanel"', "</section>")
    assert "Hvad skal appen tjekke for?" in panel
    assert 'id="vaelgGo"' in panel
    assert "data-r" not in panel and "slab" not in panel, (
        "spørgsmålet har fået en domsfarve"
    )
    # Markup alene beviser ingenting: en domsfarve ville komme fra CSS'en.
    # `#vaelgPanel{background:var(--unsafe)}` består en markup-test og
    # maler et ubesvaret spørgsmål rødt.
    css = _funktionskrop(html, "<style>", "</style>")
    for selektor, regel in re.findall(r"([^{}]*)\{([^{}]*)\}", css):
        if "#vaelgPanel" not in selektor:
            continue
        for token in ("--unsafe", "--caution", "--safe", "--unverified"):
            assert token not in regel, (
                f"spørgsmålet males med domsfarven {token} i CSS-reglen "
                f"«{selektor.strip()}» — et ubesvaret spørgsmål må ikke "
                "ligne et svar"
            )


def test_headeren_kan_ikke_laese_et_tomt_saet_som_alle_allergener():
    """
    Før stod der "Tjekker for: alle allergener" på en telefon, hvor
    ingen havde valgt noget. Det var ikke bare upræcist — det var det
    svar, der gjorde familiens egen godkendte vare rød.

    Testen påstår om BETINGELSEN, ikke om rækkefølgen af to strenge i en
    ternær: "alle allergener" kræver, at der overhovedet ER en liste at
    være alle af. Uden `ALLERGENS.length &&` giver et tomt sæt og en tom
    liste tilsammen 0 >= 0 — altså "alle allergener" om ingenting, netop
    når /api/allergens er den, der har svigtet.

    Hvad headeren så rent faktisk skriver, er efterprøvet ved at KØRE
    modulet: tests/test_frontend_adfaerd.py, scenen "headeren".
    """
    html = _forsiden()
    krop = _funktionskrop(html, "const paintWho = () => {", "\n};")
    i = krop.find("'alle allergener'")
    assert i != -1, "headeren har ikke længere en gren for det fulde sæt"
    betingelse = krop[max(0, i - 160):i]
    assert "ALLERGENS.length &&" in betingelse, (
        "'alle allergener' er ikke betinget af, at der ER en liste — et "
        "tomt sæt og en tom liste ville læses som 'alle'"
    )
    assert ">= ALLERGENS.length" in betingelse, (
        "'alle allergener' måles ikke længere mod hele regelsættet"
    )
    # Slugs er databasens ord: der må aldrig stå "Tjekker for maelkeprotein".
    assert "|| s" not in krop, (
        "headeren falder tilbage til slug'en, når et navn ikke kan slås op"
    )
