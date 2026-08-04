"""
Cloudflare Access som identitetskilde.

Hvorfor det her modul findes:

Med Cloudflare Tunnel er der ingen reverse proxy på din egen maskine til at
strimle headere. Tunnellen sender trafikken direkte til containeren. Havde vi
bare stolet på `Cf-Access-Authenticated-User-Email`, som Access sætter, ville
enhver, der kan nå containeren ad anden vej — et andet Docker-netværk, en
fejlkonfigureret port, dig selv fra LAN — kunne sætte den header selv og få
skriveadgang.

Access signerer derfor et JWT i `Cf-Access-Jwt-Assertion`. Vi validerer
signaturen mod dit teams offentlige nøgler og tjekker at `aud` matcher netop
denne applikation. Et token udstedt til en anden af dine Access-apps duer
ikke her. Det er forskellen på "headeren siger, at brugeren er logget ind"
og "Cloudflare kan bevise det".

Slås til med:
    CF_ACCESS_TEAM_DOMAIN=ditteam.cloudflareaccess.com
    CF_ACCESS_AUD=<Application Audience Tag fra Access-appen>

Er de ikke sat, er modulet inaktivt, og appen bruger lokale brugere.
"""

from __future__ import annotations

import os
import time

import jwt
from jwt import PyJWKClient

TEAM_DOMAIN = os.getenv("CF_ACCESS_TEAM_DOMAIN", "").strip().rstrip("/")
AUD = os.getenv("CF_ACCESS_AUD", "").strip()
HEADER = "cf-access-jwt-assertion"

_jwks: PyJWKClient | None = None
_jwks_at: float = 0.0
# Cloudflare roterer nøgler jævnligt; PyJWKClient cacher selv, men vi
# genskaber klienten en gang i timen så en rotation ikke låser os ude.
_JWKS_TTL = 3600


def enabled() -> bool:
    return bool(TEAM_DOMAIN and AUD)


def _client() -> PyJWKClient:
    global _jwks, _jwks_at
    now = time.time()
    if _jwks is None or now - _jwks_at > _JWKS_TTL:
        _jwks = PyJWKClient(f"https://{TEAM_DOMAIN}/cdn-cgi/access/certs")
        _jwks_at = now
    return _jwks


def verify(token: str) -> dict | None:
    """
    Returnerer claims hvis tokenet er gyldigt for netop denne applikation.
    Returnerer None ved enhver tvivl — vi fejler lukket.
    """
    if not enabled() or not token:
        return None
    try:
        key = _client().get_signing_key_from_jwt(token).key
        return jwt.decode(
            token,
            key,
            algorithms=["RS256", "ES256"],
            audience=AUD,
            issuer=f"https://{TEAM_DOMAIN}",
            options={"require": ["exp", "iat", "aud", "iss"]},
        )
    except Exception:
        # Ugyldig signatur, forkert aud, udløbet, nøgler kunne ikke hentes.
        # Alle tilfælde betyder det samme: ingen adgang.
        return None


def identity(headers) -> tuple[str, str] | None:
    """(email, navn) hvis Access har bevist brugerens identitet, ellers None."""
    claims = verify(headers.get(HEADER, ""))
    if not claims:
        return None
    email = (claims.get("email") or "").lower().strip()
    if not email:
        return None
    return email, claims.get("name") or email.split("@")[0]
