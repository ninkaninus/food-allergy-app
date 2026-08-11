"""
Open Food Facts-klient.

OFF beder udtrykkeligt om en beskrivende User-Agent. Uden den bliver du
rate-limited. Sæt OFF_USER_AGENT i .env med din egen kontaktadresse.
"""

from __future__ import annotations

import os

import httpx

from .version import VERSION

BASE = os.getenv("OFF_BASE_URL", "https://world.openfoodfacts.org")
UA = os.getenv("OFF_USER_AGENT", f"AllergiScan/{VERSION} (selfhosted; kontakt@example.dk)")

FIELDS = ",".join(
    [
        "code",
        "product_name",
        "product_name_da",
        "brands",
        "quantity",
        "image_front_small_url",
        "ingredients_text",
        "ingredients_text_da",
        "ingredients_text_en",
        "ingredients",
        "ingredients_n",
        "unknown_ingredients_n",
        "allergens_tags",
        "traces_tags",
        "countries_tags",
        "last_modified_t",
    ]
)


class Lookup(dict):
    """Fladt resultat. found=False betyder 'ikke i OFF' — ikke 'sikker'."""


async def fetch_product(ean: str, timeout: float = 8.0) -> Lookup:
    url = f"{BASE}/api/v2/product/{ean}"
    async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": UA}) as c:
        try:
            r = await c.get(url, params={"fields": FIELDS})
        except httpx.HTTPError as e:
            return Lookup(found=False, error=f"netværksfejl: {e}")

    if r.status_code == 404:
        return Lookup(found=False, error=None)
    if r.status_code != 200:
        return Lookup(found=False, error=f"OFF svarede {r.status_code}")

    body = r.json()
    if body.get("status") != 1:
        return Lookup(found=False, error=None)

    p = body.get("product", {}) or {}

    # Foretræk dansk ingrediensliste. Falder tilbage til generisk, så engelsk.
    text, lang = None, None
    for key, code in (
        ("ingredients_text_da", "da"),
        ("ingredients_text", None),
        ("ingredients_text_en", "en"),
    ):
        val = (p.get(key) or "").strip()
        if val:
            text, lang = val, code or "?"
            break

    return Lookup(
        found=True,
        error=None,
        ean=p.get("code") or ean,
        name=p.get("product_name_da") or p.get("product_name") or None,
        brand=p.get("brands") or None,
        quantity=p.get("quantity") or None,
        image_url=p.get("image_front_small_url") or None,
        ingredients_text=text,
        ingredients_lang=lang,
        ingredients=p.get("ingredients") or [],
        ingredients_n=p.get("ingredients_n"),
        unknown_ingredients_n=p.get("unknown_ingredients_n"),
        off_allergen_tags=p.get("allergens_tags") or [],
        off_trace_tags=p.get("traces_tags") or [],
        countries=p.get("countries_tags") or [],
        last_modified=p.get("last_modified_t"),
    )
