from __future__ import annotations

import os
import secrets
from pathlib import Path

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from .matcher import Ruleset
from .models import Allergen, Base, Household, Profile, ProfileAllergen

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
RULES_PATH = Path(os.getenv("RULES_PATH", "/app/data/allergens.yaml"))

DATA_DIR.mkdir(parents=True, exist_ok=True)

# SQLite er rigeligt til én husstand. Skal appen deles med flere familier med
# samtidige skrivninger, sæt DATABASE_URL til Postgres-containeren:
#   postgresql+psycopg://allergiscan:hemmeligt@postgres:5432/allergiscan
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{DATA_DIR / 'allergiscan.db'}"

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=5)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
RULES = Ruleset(RULES_PATH)


def get_session() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def tilfoej_manglende_kolonner() -> None:
    """
    Additiv mini-migrering, kørt ved hver opstart.

    `create_all` opretter kun tabeller, der mangler helt — en NY kolonne på
    en tabel, der allerede findes, laver den aldrig. Uden det her giver et
    deploy, der tilføjer en kolonne, "no such column" på jeres eksisterende
    database, og appen ser ud til at være i stykker uden grund. (Det skete
    med `imported_product.valideret_mod` mellem 0.9.0 og 0.10.0.)

    Kun tilføjelser: aldrig sletning, aldrig typeændring. Nye kolonner
    laves nullable uanset modellen, for de eksisterende rækker har ingen
    værdi — har kolonnen en skalar default, fyldes den bagefter ind.
    """
    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        findes = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in findes:
                continue
            ddl = col.type.compile(engine.dialect)
            with engine.begin() as con:
                con.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl}'))
                d = getattr(col.default, "arg", None)
                if d is not None and not callable(d):
                    con.execute(
                        text(f'UPDATE "{table.name}" SET "{col.name}" = :v'), {"v": d}
                    )


def _drop_scan_tabellen() -> None:
    """
    Bevidst, destruktiv engangshandling — ikke en fejl, hvis du støder på
    den her. `scan` var fødevaredagbogen (hvad blev slået op, hvornår,
    for hvilken profil), fjernet i 0.20.0.

    Den kunne aldrig blive en RIGTIG fødevaredagbog, fordi familien ikke
    scanner alt, barnet spiser. En delvis log over OPSLAG ville ikke bare
    være svag som efterforskningsværktøj — den ville VILDLEDE: man kigger
    i den efter en reaktion, ser ingenting, og konkluderer forkert, at
    synderen ikke var der. En log, man ikke kan stole på, er dårligere
    end ingen log. Og den var den mest følsomme rest af persondata i
    basen.

    `Scan` findes ikke i `Base.metadata` længere (se app/models.py), så
    `create_all()` opretter den ikke og rører den heller ikke — tabellen
    skal droppes eksplicit, ellers bliver dataene liggende for evigt,
    fordi ingen husker at køre en kommando. `DROP TABLE IF EXISTS` er
    idempotent: efter første oprydning er den en billig no-op ved hver
    opstart.
    """
    with engine.begin() as con:
        con.execute(text("DROP TABLE IF EXISTS scan"))


def init_db() -> None:
    Base.metadata.create_all(engine)
    tilfoej_manglende_kolonner()
    _drop_scan_tabellen()
    with SessionLocal() as db:
        # Allergener synkroniseres fra YAML ved hver opstart.
        for slug, rule in RULES.allergens.items():
            meta = rule["meta"]
            row = db.scalar(select(Allergen).where(Allergen.slug == slug))
            if row is None:
                row = Allergen(slug=slug)
                db.add(row)
            row.name_da = meta["name_da"]
            row.off_tag = meta.get("off_tag")
            row.eu14 = bool(meta.get("eu14"))
            row.note = (meta.get("note") or "").strip() or None

        # Allergen-rækkerne skal have id'er, før profilerne kan pege på dem.
        db.flush()

        # `Profile.name` lå unødigt på serveren: headerens "Tjekker for …"
        # kommer udelukkende fra telefonens egen localStorage og har
        # ALDRIG læst denne kolonne. Ryd en værdi, der allerede ligger i
        # produktionsdatabasen fra før dette — kolonnen er NOT NULL, så
        # den bliver ved med at eksistere, tom. Billigt at tjekke hver
        # opstart; kører kun UPDATE, når der rent faktisk er noget at rydde.
        for p in db.scalars(select(Profile).where(Profile.name != "")):
            p.name = ""

        # Første husstand + profil, så appen er brugbar med det samme.
        fresh: set[int] = set()
        if db.scalar(select(Household)) is None:
            hh = Household(
                name=os.getenv("HOUSEHOLD_NAME", "Vores husstand"),
                token=os.getenv("HOUSEHOLD_TOKEN") or secrets.token_urlsafe(24),
            )
            db.add(hh)
            db.flush()
            # Tomt med vilje — se oprydningen ovenfor. Ingen PROFILE_NAME
            # mere: et barnets navn skal ikke kunne sættes via serverens
            # miljøvariabler, når det slet ikke må ligge på serveren.
            prof = Profile(household_id=hh.id, name="")
            db.add(prof)
            db.flush()
            fresh.add(prof.id)

        # Et allergen uden ProfileAllergen-række er usynligt: list_profiles bygger
        # listen derfra, så det kan hverken ses eller slås til. Udvides regelsættet,
        # skal de nye altså op på de profiler, der allerede findes.
        #
        # Op, men ikke til. På en frisk profil slås alt til som hidtil; på en
        # eksisterende er default `active=False`. Hvad barnet reagerer på, er
        # forældrenes beslutning, ikke en bivirkning af et deploy — og en stribe
        # nye advarsler, ingen har bedt om, koster den tillid appen lever af.
        allergens = db.scalars(select(Allergen)).all()
        for p in db.scalars(select(Profile)).all():
            known = set(
                db.scalars(
                    select(ProfileAllergen.allergen_id).where(
                        ProfileAllergen.profile_id == p.id
                    )
                )
            )
            for a in allergens:
                if a.id not in known:
                    db.add(
                        ProfileAllergen(
                            profile_id=p.id,
                            allergen_id=a.id,
                            severity="strict",
                            active=p.id in fresh,
                        )
                    )
        db.commit()


def default_household(db: Session) -> Household:
    """Prototype: én husstand. Se README om rigtig auth før I deler appen."""
    return db.scalar(select(Household).order_by(Household.id))
