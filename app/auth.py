"""
Autentificering.

Modellen er bevidst asymmetrisk:

    LÆSNING  — helt åben. Ingen konto, ingen cookie-banner, intet.
               Valg af allergener ligger i browserens localStorage.
    SKRIVNING — kræver en bruger. Det er kun her, en vare kan blive grøn,
               og en grøn vare er en påstand, nogen skal stå på mål for.

To veje ind, som kan køre samtidig:

  1. Lokal bruger med adgangskode (argon2id). Nok hvis appen kun er
     tilgængelig på dit LAN eller gennem WireGuard.
  2. Betroet reverse proxy. Authelia/authentik sætter Remote-User og
     Remote-Groups efter en forward-auth. Appen opretter brugeren
     ved første besøg. Sæt TRUST_PROXY_AUTH=1 og TRUSTED_PROXY_HOSTS.

Slå ALDRIG TRUST_PROXY_AUTH til uden at proxyen faktisk strimler
Remote-User fra indgående requests. Ellers er headeren en gratis login.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import secrets

import httpx
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import cfaccess
from .db import default_household, get_session
from .models import SessionToken, User, now

COOKIE = "as_session"
SESSION_DAYS = int(os.getenv("SESSION_DAYS", "30"))
TRUST_PROXY_AUTH = os.getenv("TRUST_PROXY_AUTH", "0") == "1"
TRUSTED_PROXY_HOSTS = {
    h.strip() for h in os.getenv("TRUSTED_PROXY_HOSTS", "").split(",") if h.strip()
}
CHECK_PWNED = os.getenv("CHECK_PWNED_PASSWORDS", "1") == "1"
MIN_PASSWORD_LEN = int(os.getenv("MIN_PASSWORD_LEN", "14"))

ph = PasswordHasher()


def hash_password(pw: str) -> str:
    return ph.hash(pw)


def verify_password(stored: str, pw: str) -> bool:
    try:
        ph.verify(stored, pw)
        return True
    except VerifyMismatchError:
        return False


async def password_is_reused(pw: str) -> bool:
    """
    Slår adgangskoden op hos Have I Been Pwned med k-anonymitet:
    kun de første fem tegn af SHA-1-hashen forlader maskinen, og HIBP
    sender ~800 hash-suffikser retur, som vi matcher lokalt. Selve
    adgangskoden bliver aldrig sendt nogen steder.

    Fejler opslaget (ingen netværk), returnerer vi False — vi vil hellere
    lade en oprettelse gå igennem end at blokere den på en netværksfejl.
    """
    if not CHECK_PWNED:
        return False
    digest = hashlib.sha1(pw.encode("utf-8")).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(
                f"https://api.pwnedpasswords.com/range/{prefix}",
                headers={"Add-Padding": "true", "User-Agent": "AllergiScan"},
            )
        if r.status_code != 200:
            return False
        return any(line.split(":")[0] == suffix for line in r.text.splitlines())
    except httpx.HTTPError:
        return False


async def validate_new_password(pw: str) -> None:
    if len(pw) < MIN_PASSWORD_LEN:
        raise HTTPException(400, f"Adgangskoden skal være mindst {MIN_PASSWORD_LEN} tegn.")
    if await password_is_reused(pw):
        raise HTTPException(
            400,
            "Den adgangskode er set i kendte datalæk. Vælg en, du ikke bruger andre steder.",
        )


# --- sessioner -------------------------------------------------------------


def _hash_token(tok: str) -> str:
    return hashlib.sha256(tok.encode("utf-8")).hexdigest()


def issue_session(db: Session, user: User, user_agent: str | None) -> str:
    raw = secrets.token_urlsafe(40)
    db.add(
        SessionToken(
            token_hash=_hash_token(raw),
            user_id=user.id,
            expires_at=now().replace(tzinfo=None) + dt.timedelta(days=SESSION_DAYS),
            user_agent=(user_agent or "")[:300] or None,
        )
    )
    user.last_login = now().replace(tzinfo=None)
    db.commit()
    return raw


def revoke_session(db: Session, raw: str | None) -> None:
    if not raw:
        return
    row = db.scalar(
        select(SessionToken).where(SessionToken.token_hash == _hash_token(raw))
    )
    if row:
        db.delete(row)
        db.commit()


# --- afhængigheder ---------------------------------------------------------


def _provision(db: Session, email: str, name: str, source: str, admin: bool) -> User | None:
    """Opretter brugeren ved første besøg. Identiteten er allerede bevist."""
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        hh = default_household(db)
        user = User(
            household_id=hh.id,
            email=email,
            name=name,
            password_hash=None,
            role="admin" if admin else "curator",
            source=source,
        )
        db.add(user)
        db.commit()
    return user if user.active else None


def _cf_access_user(db: Session, request: Request) -> User | None:
    """
    Cloudflare Access. Kræver et gyldigt, signeret JWT — ikke bare en header.
    Se app/cfaccess.py for hvorfor den skelnen er hele pointen med Tunnel.
    """
    if not cfaccess.enabled():
        return None
    ident = cfaccess.identity(request.headers)
    if ident is None:
        return None
    email, name = ident
    admins = {a.strip().lower() for a in os.getenv("CF_ACCESS_ADMINS", "").split(",") if a.strip()}
    return _provision(db, email, name, "cf_access", admin=email in admins)


def _proxy_user(db: Session, request: Request) -> User | None:
    if not TRUST_PROXY_AUTH:
        return None
    peer = request.client.host if request.client else None
    if TRUSTED_PROXY_HOSTS and peer not in TRUSTED_PROXY_HOSTS:
        return None
    email = request.headers.get("remote-email") or request.headers.get("remote-user")
    if not email:
        return None
    groups = (request.headers.get("remote-groups") or "").lower()
    return _provision(
        db,
        email.lower(),
        request.headers.get("remote-name") or email.split("@")[0],
        "proxy",
        admin="admin" in groups,
    )


def current_user(
    request: Request, db: Session = Depends(get_session)
) -> User | None:
    """Returnerer brugeren hvis der er en. Rejser ikke fejl — læsning er åben."""
    # Rækkefølge efter styrke af bevis: kryptografisk signeret token først,
    # derefter betroet-proxy-header, derefter vores egen session-cookie.
    for candidate in (_cf_access_user(db, request), _proxy_user(db, request)):
        if candidate:
            return candidate

    raw = request.cookies.get(COOKIE)
    if not raw:
        return None
    row = db.scalar(
        select(SessionToken).where(SessionToken.token_hash == _hash_token(raw))
    )
    if row is None or row.expires_at < now().replace(tzinfo=None):
        return None
    user = db.get(User, row.user_id)
    return user if user and user.active else None


def require_curator(user: User | None = Depends(current_user)) -> User:
    """Bruges på alt, der skriver domme."""
    if user is None:
        raise HTTPException(401, "Log ind for at bekræfte varer.")
    if user.role not in ("curator", "admin"):
        raise HTTPException(403, "Din konto må kun læse.")
    return user


def require_admin(user: User | None = Depends(current_user)) -> User:
    if user is None:
        raise HTTPException(401, "Log ind.")
    if user.role != "admin":
        raise HTTPException(403, "Kræver administrator.")
    return user
