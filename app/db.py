from __future__ import annotations

import os
import secrets
from pathlib import Path

from sqlalchemy import create_engine, select
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


def init_db() -> None:
    Base.metadata.create_all(engine)
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

        # Første husstand + profil, så appen er brugbar med det samme.
        if db.scalar(select(Household)) is None:
            hh = Household(
                name=os.getenv("HOUSEHOLD_NAME", "Vores husstand"),
                token=os.getenv("HOUSEHOLD_TOKEN") or secrets.token_urlsafe(24),
            )
            db.add(hh)
            db.flush()
            prof = Profile(household_id=hh.id, name=os.getenv("PROFILE_NAME", "Barn"))
            db.add(prof)
            db.flush()
            db.commit()
            # Slå alle kendte allergener til som strict fra start.
            for a in db.scalars(select(Allergen)).all():
                db.add(
                    ProfileAllergen(
                        profile_id=prof.id, allergen_id=a.id, severity="strict"
                    )
                )
        db.commit()


def default_household(db: Session) -> Household:
    """Prototype: én husstand. Se README om rigtig auth før I deler appen."""
    return db.scalar(select(Household).order_by(Household.id))
