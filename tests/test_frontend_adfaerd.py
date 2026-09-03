"""
Frontendens vagter, efterprøvet ved at KØRE dem — ikke ved at læse dem.

`tests/test_frontend.py` er statisk kontrol af kildeteksten, og den siger
det selv: den beviser, at kilden har den ønskede FORM, ikke at browseren
gør det rigtige. Vagterne omkring »hvad skal appen tjekke for« afgør,
hvilket allergensæt en dom bliver regnet ud fra, og en vagt, der står ét
trin for sent i en betinget kæde, består en substring-test og fejler i
Netto.

Derfor kører testene her `app/static/index.html`s modul i node med en
DOM-stub (`tests/frontend_stub.mjs`) og påstår om ADFÆRD: hvilke URL'er
blev kaldt, med hvilket sæt, og hvad står der på skærmen bagefter.

Alle ni scener er efterprøvet mod 0.23.1's index.html: hver eneste
FEJLER dér og består her. De beskriver altså en rettelse, ikke bare en
tilstand.

Node medfølger ikke repoet. Er den her ikke, springes testene over — og
en oversprunget test er ikke en grøn test. GitHubs ubuntu-kørere har node
forinstalleret, så CI kører dem.
"""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

ROD = pathlib.Path(__file__).resolve().parents[1]
SIDE = ROD / "app" / "static" / "index.html"
STUB = pathlib.Path(__file__).resolve().parent / "frontend_stub.mjs"

node = shutil.which("node")
kraever_node = pytest.mark.skipif(node is None, reason="node er ikke installeret")

# Modulets funktioner er modul-scopede og ellers utilgængelige udefra.
# Linjen her er testens eneste indgreb i kildeteksten — getters, fordi
# let-bindingerne ændrer sig undervejs.
UDSTIL = """

globalThis.__t = {
  lookup, soeg, paintWho, paintPrefChips, refreshAuth, malVaelgPanel,
  effektivAllergener, harValgtAllergener, prefs,
  VAELG_FOERST, KLAR_TIL_OPSLAG, HENTER_SAET, SPOERGSMAALET,
  get USER(){ return USER; },
  get ALLERGENS(){ return ALLERGENS; },
  get SERVER_ALLERGENS(){ return SERVER_ALLERGENS; },
  get AUTH_AFKLARET(){ return AUTH_AFKLARET; },
};
"""

# Scenerne bor i frontend_stub.mjs. Teksten her er den, en fejlbesked
# skal kunne læses med — hvad der går galt for et menneske, hvis scenen
# falder.
SCENER = {
    "b1_logud": "en grøn SIKKER bliver stående, efter hun logger ud og sættet bliver tomt",
    "b1_chip": "en dom fra det gamle sæt bliver stående, når et allergen slås til",
    "b2_gammel_noegle": "det gamle localStorage-sæt (alle 17) gælder stadig, så appen aldrig spørger",
    "b3_besked_tages_ned": "»Vælg først …« bliver stående, efter hun har valgt",
    "b4_porten": "en scanning i AUTH-vinduet kasseres lydløst",
    "liste_naar_sessionen_udloeber": "listen bliver stående med domme fra det gamle sæt",
    "soeg_bidragyder": "listen lover en bidragyder et valg, hun ikke må træffe",
    "ingen_allergenliste": "et fejlet /api/allergens låser appen uden at sige noget",
    "profiler_401": "en 401 fra /api/profiles ligner »ingen allergener slået til«",
    "headeren": "headeren skriver ikke-dansk eller en rå slug",
}


@pytest.fixture(scope="module")
def modul(tmp_path_factory) -> str:
    """Modulet, som det udgives — trukket ud af den ene HTML-fil."""
    html = SIDE.read_text(encoding="utf-8")
    m = re.search(r'<script type="module">\n(.*?)\n</script>', html, re.S)
    assert m, "kunne ikke finde <script type=\"module\"> i index.html"
    sti = tmp_path_factory.mktemp("frontend") / "modul.mjs"
    sti.write_text(m.group(1) + UDSTIL, encoding="utf-8")
    return sti.as_uri()


@kraever_node
def test_modulet_er_syntaktisk_gyldigt(modul):
    """
    Det eneste syntakstjek, frontend har. Uden det opdages en manglende
    parentes i index.html først, når appen er tom i en browser.
    """
    r = subprocess.run([node, "--check", pathlib.Path(modul[len("file://"):])],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


@kraever_node
@pytest.mark.parametrize("scene", list(SCENER), ids=list(SCENER))
def test_vagt(modul, scene):
    r = subprocess.run([node, str(STUB), modul, scene],
                       capture_output=True, text=True, timeout=60)
    assert r.stdout.strip(), f"stubben skrev intet.\n{r.stderr}"
    ud = json.loads(r.stdout.strip().splitlines()[-1])
    assert "fejl" not in ud, f"{SCENER[scene]}:\n{ud['fejl']}"
    faldne = [p for p in ud["paastande"] if not p["ok"]]
    assert not faldne, "{}:\n{}".format(
        SCENER[scene],
        "\n".join(f"  - {p['navn']} (fik: {p['detalje'] or '—'})" for p in faldne),
    )
    assert ud["paastande"], "scenen påstod ingenting"
