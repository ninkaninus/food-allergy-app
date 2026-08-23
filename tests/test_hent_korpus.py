"""
scripts/hent-korpus.py — de rene funktioner testes her uden en kørende
server: destinationsvagten (`_sikker_destination`), tælleren for brugbare
par (`brugbare_par`), og de små sikkerhedshjælpere (URL-skema, atomisk
billedskrivning, felt-validering).

Selve netværksdelen (login + download) kræver en kørende server og
familiens rigtige billeder og testes ikke her — se ROADMAP.md. Det, der
SKAL være dækket af en test, er det oplagte fejltilfælde: at scriptet ved
et uheld peger ind i repoet, hvor git aldrig glemmer igen.
"""
import importlib.util
import os
import pathlib
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "hent-korpus.py"


def _modul():
    spec = importlib.util.spec_from_file_location("hent_korpus", SCRIPT)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture(scope="module")
def hk():
    return _modul()


def _har_git() -> bool:
    return subprocess.run(["git", "-C", str(REPO), "rev-parse"],
                           capture_output=True).returncode == 0


# --- _sikker_destination --------------------------------------------------

def test_mappe_uden_for_repoet_er_altid_ok(hk, tmp_path):
    hk._sikker_destination(tmp_path / "allergiscan-korpus")


def test_mappe_inde_i_repoet_bliver_afvist(hk):
    with pytest.raises(SystemExit) as e:
        hk._sikker_destination(REPO / "app" / "static")
    assert "ligger inde i repoet" in str(e.value)
    assert "uden for repoet" in str(e.value)


@pytest.mark.parametrize("relativ", ["app/static/korpus", "data/korpus", "app/korpus"])
def test_kendte_offentlige_mapper_afvises_selvom_de_ikke_findes(hk, relativ):
    """De tre kanaler, den forrige (git check-ignore-baserede) udgave
    lukkede ind: `app/static/korpus` havner i StaticFiles-mountet,
    `data/korpus` og `app/korpus` havner i det offentlige GHCR-image via
    `COPY data`/`COPY app` i Dockerfile. Ingen af dem findes på disken —
    den gamle fejl var netop, at check-ignore matcher forskelligt alt
    efter om stien findes."""
    sti = REPO / relativ
    assert not sti.exists()
    with pytest.raises(SystemExit):
        hk._sikker_destination(sti)


@pytest.mark.parametrize("relativ", ["app/static/korpus", "data/korpus", "app/korpus"])
def test_kendte_offentlige_mapper_afvises_naar_de_findes(hk, relativ):
    """Samme mapper, men nu rent faktisk oprettet — skal afvises præcis
    lige så hårdt som når de ikke findes."""
    sti = REPO / relativ
    sti.mkdir(parents=True, exist_ok=False)
    try:
        with pytest.raises(SystemExit):
            hk._sikker_destination(sti)
    finally:
        sti.rmdir()


def test_gitignoreret_mappe_inde_i_repoet_afvises_alligevel(hk):
    """`data-runtime/` er gitignoreret, men det er IKKE nok længere:
    vagten afviser nu ubetinget enhver sti inde i repoet, uanset hvad
    .gitignore siger. .gitignore beskriver, hvad git viser — ikke hvad
    der er sikkert at skrive familiens fotos til."""
    if not _har_git():
        pytest.skip("intet .git i denne kørsel")
    with pytest.raises(SystemExit):
        hk._sikker_destination(REPO / "data-runtime" / "korpus")


def test_ingen_git_faejler_lukket(hk, monkeypatch, tmp_path):
    """Kan repo-roden ikke bekræftes (ingen .git — fx en ZIP-kopi af
    filerne), skal vagten afvise, ikke antage at destinationen er sikker
    — også når destinationen ligger et sted, der reelt ER uden for enhver
    repo."""
    monkeypatch.setattr(hk, "_repo_rod", lambda: None)
    with pytest.raises(SystemExit) as e:
        hk._sikker_destination(tmp_path / "allergiscan-korpus")
    assert "intet .git" in str(e.value) or ".git" in str(e.value)


def test_miljoevariabel_mangler_stopper_med_forklaring(hk, monkeypatch):
    monkeypatch.delenv("KORPUS_URL", raising=False)
    with pytest.raises(SystemExit) as e:
        hk._miljoevariabel("KORPUS_URL")
    assert "KORPUS_URL" in str(e.value)


def test_miljoevariabel_hemmelig_falder_tilbage_paa_getpass(hk, monkeypatch):
    monkeypatch.delenv("KORPUS_KODEORD", raising=False)
    monkeypatch.setattr(hk.getpass, "getpass", lambda prompt: "tastet-interaktivt")
    assert hk._miljoevariabel("KORPUS_KODEORD", hemmelig=True) == "tastet-interaktivt"


def test_miljoevariabel_hemmelig_uden_input_stopper(hk, monkeypatch):
    monkeypatch.delenv("KORPUS_KODEORD", raising=False)
    monkeypatch.setattr(hk.getpass, "getpass", lambda prompt: "")
    with pytest.raises(SystemExit):
        hk._miljoevariabel("KORPUS_KODEORD", hemmelig=True)


# --- _kraev_sikker_url -----------------------------------------------------

def test_https_url_er_ok(hk):
    hk._kraev_sikker_url("https://allergiscan.eksempel.dk")


@pytest.mark.parametrize("url", ["http://localhost:8000", "http://127.0.0.1:8000"])
def test_http_localhost_er_ok(hk, url):
    hk._kraev_sikker_url(url)


def test_http_paa_rigtig_vaert_afvises(hk):
    with pytest.raises(SystemExit) as e:
        hk._kraev_sikker_url("http://allergiscan.eksempel.dk")
    assert "klartekst" in str(e.value)


# --- _valider_foto_felter ---------------------------------------------------

def test_gyldige_foto_felter_ok(hk):
    hk._valider_foto_felter("5701234567890", "deklaration")
    hk._valider_foto_felter("5701234567890", "front")


def test_ean_med_bogstaver_afvises(hk):
    with pytest.raises(SystemExit):
        hk._valider_foto_felter("../../etc/passwd", "front")


def test_ukendt_slags_afvises(hk):
    with pytest.raises(SystemExit):
        hk._valider_foto_felter("5701234567890", "bagside")


# --- _gem_billede: atomisk, kun rigtige JPEG'er -----------------------------

def test_gem_billede_skriver_atomisk_og_saetter_rettigheder(hk, tmp_path):
    sti = tmp_path / "5701234567890_deklaration_1.jpg"
    hk._gem_billede(b"\xff\xd8\xff\xe0resten er ligegyldigt", sti)
    assert sti.exists()
    assert sti.read_bytes().startswith(b"\xff\xd8")
    assert not sti.with_name(sti.name + ".part").exists(), "midlertidig fil skal være væk efter succes"
    assert (os.stat(sti).st_mode & 0o777) == 0o600


def test_gem_billede_afviser_ikke_jpeg_og_efterlader_intet(hk, tmp_path):
    """En udløbet session, der giver en HTML-loginside i stedet for et
    billede, må ikke ende som en troværdig .jpg på disken."""
    sti = tmp_path / "5701234567890_deklaration_2.jpg"
    with pytest.raises(ValueError):
        hk._gem_billede(b"<html>log ind igen</html>", sti)
    assert not sti.exists()
    assert not sti.with_name(sti.name + ".part").exists()


# --- brugbare_par ------------------------------------------------------------

def test_brugbare_par_kun_forsidefoto_taeller_ikke(hk):
    manifest = [{
        "deklaration": "Mælk, sukker.",
        "deklaration_gik_gennem_bekraeftelse": True,
        "fotos": [{"slags": "front"}],
    }]
    assert hk.brugbare_par(manifest) == 0


def test_brugbare_par_taeller_par_ikke_varer(hk):
    manifest = [{
        "deklaration": "Mælk, sukker.",
        "deklaration_gik_gennem_bekraeftelse": True,
        "fotos": [{"slags": "deklaration"}, {"slags": "deklaration"}, {"slags": "front"}],
    }]
    assert hk.brugbare_par(manifest) == 2


def test_brugbare_par_blank_tekst_taeller_ikke(hk):
    manifest = [{
        "deklaration": "   ",
        "deklaration_gik_gennem_bekraeftelse": True,
        "fotos": [{"slags": "deklaration"}],
    }]
    assert hk.brugbare_par(manifest) == 0


def test_brugbare_par_ikke_bekraeftet_taeller_ikke(hk):
    manifest = [{
        "deklaration": "Mælk, sukker.",
        "deklaration_gik_gennem_bekraeftelse": False,
        "fotos": [{"slags": "deklaration"}],
    }]
    assert hk.brugbare_par(manifest) == 0
