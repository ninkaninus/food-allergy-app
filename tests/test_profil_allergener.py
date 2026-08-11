"""
Regelsættet vokser over tid. Når det sker, skal de nye allergener op på de
profiler, der allerede findes — ellers er de usynlige, fordi `list_profiles`
bygger listen fra ProfileAllergen og ikke fra Allergen. Det er en stille fejl:
appen ser sund ud, healthchecket er grønt, og allergenet findes bare ikke.

Men de må ikke slås til af sig selv. Et deploy skal aldrig kunne ændre, hvad
appen advarer om for et barn — hverken opad eller nedad.
"""
import os, pathlib, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

TMP = tempfile.mkdtemp()
os.environ.update(
    DATA_DIR=TMP,
    RULES_PATH=str(pathlib.Path(__file__).resolve().parents[1] / "data" / "allergens.yaml"),
    COOKIE_SECURE="0",
    CHECK_PWNED_PASSWORDS="0",
)

from fastapi.testclient import TestClient
from sqlalchemy import select

from app import db as dbmod
from app.db import SessionLocal, init_db
from app.main import app
from app.models import Allergen, ProfileAllergen

# Slugs fra den rigtige YAML, sat fast før nogen test lægger noget oveni.
BASE_SLUGS = set(dbmod.RULES.allergens)


def _udvid_regelsaettet(monkeypatch, slug: str) -> None:
    """Lad som om regelsættet fik et allergen mere, uden at røre YAML-filen."""
    monkeypatch.setitem(
        dbmod.RULES.allergens,
        slug,
        {"meta": {"name_da": slug.capitalize(), "eu14": False}, "contains": [],
         "maybe": [], "exclude": []},
    )


def _profil_raekke(db, slug: str):
    return db.scalar(
        select(ProfileAllergen)
        .join(Allergen, Allergen.id == ProfileAllergen.allergen_id)
        .where(Allergen.slug == slug)
    )


def test_frisk_database_slaar_alt_til():
    """Førstegangsopsætning: profilen får alle kendte allergener aktive."""
    init_db()
    with SessionLocal() as db:
        for slug in BASE_SLUGS:
            pa = _profil_raekke(db, slug)
            assert pa is not None, f"{slug} mangler helt på profilen"
            assert pa.active is True, f"{slug} burde være slået til på en frisk profil"


def test_nyt_allergen_faar_raekke_paa_eksisterende_profil(monkeypatch):
    """Det, deployet på serveren ikke gjorde: rækken skal oprettes bagudrettet."""
    init_db()  # husstand og profil findes nu — som på serveren
    _udvid_regelsaettet(monkeypatch, "proeveallergen")
    init_db()

    with SessionLocal() as db:
        pa = _profil_raekke(db, "proeveallergen")
        assert pa is not None, "nyt allergen kom aldrig op på den eksisterende profil"
        assert pa.active is False, "et nyt allergen må ikke slå sig selv til"


def test_nyt_allergen_er_synligt_i_profil_api(monkeypatch):
    """Selve symptomet: uden en række er der ingen boks at sætte kryds i."""
    init_db()
    _udvid_regelsaettet(monkeypatch, "synlighedstest")
    init_db()

    r = TestClient(app).get("/api/profiles")
    assert r.status_code == 200
    slugs = {a["slug"]: a for p in r.json() for a in p["allergens"]}
    assert "synlighedstest" in slugs, "allergenet kan ikke ses i UI'et"
    assert slugs["synlighedstest"]["active"] is False


def test_udvidelse_roerer_ikke_eksisterende_kryds(monkeypatch):
    """En regeludvidelse må ikke skrive forældrenes valg over."""
    init_db()
    slaaet_fra = sorted(BASE_SLUGS)[0]
    stadig_til = sorted(BASE_SLUGS)[1:3]

    with SessionLocal() as db:
        _profil_raekke(db, slaaet_fra).active = False
        for s in stadig_til:
            _profil_raekke(db, s).active = True
        db.commit()

    _udvid_regelsaettet(monkeypatch, "endnu_et_allergen")
    init_db()

    with SessionLocal() as db:
        assert _profil_raekke(db, slaaet_fra).active is False, (
            "et allergen forældrene havde slået fra, blev tændt igen af et deploy"
        )
        for s in stadig_til:
            assert _profil_raekke(db, s).active is True, f"{s} blev slukket af et deploy"
        assert _profil_raekke(db, "endnu_et_allergen").active is False
