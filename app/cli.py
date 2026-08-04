"""
Kommandolinje. Kør inde i containeren:

    docker compose exec allergiscan python -m app.cli adduser dig@example.dk "William"
    docker compose exec allergiscan python -m app.cli reindex
"""

from __future__ import annotations

import asyncio
import getpass
import sys

from sqlalchemy import select

from . import ingredients as ix
from .auth import hash_password, validate_new_password
from .db import SessionLocal, default_household, init_db
from .models import Product, User


def adduser(email: str, name: str, role: str = "admin") -> None:
    pw = getpass.getpass("Adgangskode (mindst 14 tegn): ")
    if pw != getpass.getpass("Gentag: "):
        sys.exit("De to kodeord er ikke ens.")
    try:
        asyncio.run(validate_new_password(pw))
    except Exception as e:
        sys.exit(getattr(e, "detail", str(e)))

    init_db()
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email.lower())):
            sys.exit("Den mail findes allerede.")
        db.add(
            User(
                household_id=default_household(db).id,
                email=email.lower(),
                name=name,
                password_hash=hash_password(pw),
                role=role,
                source="local",
            )
        )
        db.commit()
    print(f"Oprettet {email} som {role}.")


def reindex() -> None:
    """Genopbygger ingrediensindekset fra de rå tekster, vi allerede har."""
    init_db()
    with SessionLocal() as db:
        n = 0
        for p in db.scalars(select(Product)):
            n += bool(ix.index_product(db, p.ean, None, p.off_allergen_tags,
                                       p.ingredients_text))
        db.commit()
    print(f"Genindekserede {n} varer.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "adduser":
        adduser(*sys.argv[2:])
    elif cmd == "reindex":
        reindex()
    else:
        sys.exit("Brug: python -m app.cli [adduser EMAIL NAVN [ROLLE] | reindex]")
