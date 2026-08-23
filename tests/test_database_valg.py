"""
Appen skal vide, hvilken database den kigger i.

Baggrund (0.21.1): `app/db.py` faldt tavst tilbage på en SQLite-fil, hvis
`DATABASE_URL` manglede. Forsvandt variablen — en tastefejl i `.env`, en
ændring i compose, `${DATABASE_URL:-}` der resolver tomt — fejlede appen
ikke. Den lavede en splinterny, TOM database og startede grønt op. Alle
varer, domme, brugere og billeder var væk fra appens synsfelt, mens de
rigtige data lå uberørt i Postgres. Healthchecket bestod, og autodeploy
meldte fuldført.

Vagten køres ved import af `app.db`, så hvert tilfælde skal have sin egen
proces — derfor subprocess og ikke monkeypatch.
"""
import os
import pathlib
import subprocess
import sys

ROD = pathlib.Path(__file__).resolve().parents[1]


def _start(env_ekstra, tmp):
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(ROD),
        "DATA_DIR": str(tmp),
        "RULES_PATH": str(ROD / "data" / "allergens.yaml"),
        "COOKIE_SECURE": "0",
        "CHECK_PWNED_PASSWORDS": "0",
        "OFF_BASE_URL": "http://127.0.0.1:9",
    }
    env.update(env_ekstra)
    return subprocess.run(
        [sys.executable, "-c", "import app.db; print('STARTEDE')"],
        env=env, capture_output=True, text=True, timeout=90, cwd=ROD,
    )


def test_manglende_database_url_stopper_opstarten(tmp_path):
    r = _start({}, tmp_path)
    assert r.returncode != 0, "appen startede på en tom database uden at sige det"
    assert "TILLAD_SQLITE" in r.stderr, "fejlen siger ikke, hvad man skal gøre"
    assert not (tmp_path / "allergiscan.db").exists(), (
        "der blev oprettet en tom database, selvom opstarten fejlede"
    )


def test_tom_database_url_taeller_som_manglende(tmp_path):
    """`DATABASE_URL: "${DATABASE_URL:-}"` i docker-compose.yml giver en
    TOM streng, ikke en manglende variabel, når .env ikke sætter den.
    Det er netop den vej, fejlen ville komme ad i drift."""
    r = _start({"DATABASE_URL": "   "}, tmp_path)
    assert r.returncode != 0, "en tom DATABASE_URL blev accepteret som 'ikke sat'"


def test_sqlite_kan_vaelges_udtrykkeligt(tmp_path):
    """Lokal udvikling skal stadig kunne køre uden en Postgres-container."""
    r = _start({"TILLAD_SQLITE": "1"}, tmp_path)
    assert r.returncode == 0, r.stderr
    assert "STARTEDE" in r.stdout
    assert "database = sqlite" in r.stdout, (
        "opstarten siger ikke hvilken database det blev — så kan man ikke "
        "se forskel på Postgres og en tom fil uden at logge ind"
    )
