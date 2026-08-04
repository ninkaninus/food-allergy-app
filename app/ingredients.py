"""
Fuldt ingrediensindeks.

Svaret på "kan vi bare indeksere alle ingredienser og filtrere på alt?" er:
ja, og du bør — men det må aldrig blive det, der afgør om noget er sikkert.

Grunden er dækningsasymmetri. Open Food Facts' parser opløser en pæn del
af danske ingredienstekster til taksonomi-id'er (`en:whole-milk`), men
resten kommer tilbage som `da:<rå tekst>` eller slet ikke. Filtrerer du
kun på tags, er en uopløst ingrediens usynlig — og usynlig ligner fraværende.
Det er præcis den fejl, hele appen er bygget for at undgå.

Derfor to lag med hver sin opgave:

    INDEKS (dette modul)     bredt, upræcist. Til at finde og filtrere.
                             "vis alt uden jordbær", "hvad går igen i det,
                             hun tåler?". Producerer aldrig en dom.

    REGELSÆT (matcher.py)    smalt, høj recall. Til sikkerhed. Optimeret
                             for aldrig at overse noget, på bekostning af
                             falske positiver.

Broen mellem dem er `suggest()`: når I tilføjer noget nyt, hun ikke tåler,
graver den i jeres eget korpus efter de stavemåder, der faktisk optræder i
danske deklarationer — så synonymlisten skrives ud fra virkeligheden i
stedet for fantasien.
"""

from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .matcher import normalize
from .models import Ingredient, Product, ProductIngredient

# Ord der optræder i enhver deklaration og intet fortæller
STOPWORDS = {
    "og", "eller", "af", "med", "uden", "til", "fra", "the", "and", "or", "of",
    "ca", "min", "max", "heraf", "indeholder", "ingredienser", "ingrediens",
    "næringsindhold", "kan", "spor", "produkt", "vægt", "total", "andel",
    "e", "nr", "pr", "g", "kg", "ml", "l", "mg",
}


def _key(tag: str | None, label: str) -> str:
    if tag:
        return tag.lower()
    return "text:" + re.sub(r"\s+", " ", normalize(label))[:180]


def _upsert(db: Session, tag: str | None, label: str) -> Ingredient | None:
    label = (label or "").strip()
    if not label and not tag:
        return None
    key = _key(tag, label)
    row = db.scalar(select(Ingredient).where(Ingredient.key == key))
    if row is None:
        lang = tag.split(":", 1)[0] if tag and ":" in tag else None
        row = Ingredient(
            key=key,
            tag=tag,
            label=label or (tag or "").split(":", 1)[-1].replace("-", " "),
            lang=lang,
            # en:… er opløst i OFF's taksonomi. da:… er blot rå tekst.
            resolved=bool(tag and tag.startswith("en:")),
            seen_count=0,
        )
        db.add(row)
        db.flush()
    row.seen_count += 1
    return row


def _flatten(nodes: list | None, out: list, depth: int = 0) -> None:
    """OFF's `ingredients` er et træ — sammensatte ingredienser har underdele."""
    for n in nodes or []:
        if not isinstance(n, dict):
            continue
        out.append(n)
        _flatten(n.get("ingredients"), out, depth + 1)


def index_product(
    db: Session,
    ean: str,
    off_ingredients: list | None,
    off_tags: list[str] | None,
    ingredients_text: str | None,
) -> int:
    """Genopbygger indekset for én vare. Idempotent."""
    db.query(ProductIngredient).filter(ProductIngredient.product_ean == ean).delete()

    rows: list[dict] = []
    _flatten(off_ingredients, rows)

    seen: set[int] = set()
    pos = 0

    for n in rows:
        ing = _upsert(db, n.get("id"), n.get("text") or "")
        if ing is None or ing.id in seen:
            continue
        seen.add(ing.id)
        pct = n.get("percent") or n.get("percent_estimate")
        db.add(
            ProductIngredient(
                product_ean=ean,
                ingredient_id=ing.id,
                position=pos,
                percent=float(pct) if isinstance(pct, (int, float)) else None,
            )
        )
        pos += 1

    # Faldt OFF's parser helt igennem, indekserer vi den rå tekst i stumper,
    # så varen stadig kan findes ved fritekstfiltrering.
    if not rows and ingredients_text:
        for part in re.split(r"[,;.()\[\]]+", normalize(ingredients_text)):
            part = part.strip(" -–—*")
            if len(part) < 3 or part in STOPWORDS or part.isdigit():
                continue
            ing = _upsert(db, None, part)
            if ing is None or ing.id in seen:
                continue
            seen.add(ing.id)
            db.add(
                ProductIngredient(product_ean=ean, ingredient_id=ing.id, position=pos)
            )
            pos += 1

    return len(seen)


def suggest(db: Session, q: str, limit: int = 25) -> list[dict]:
    """
    Synonymforslag til allergens.yaml, gravet ud af jeres eget korpus.

    Søger man "jordbær", kommer alle de stavemåder tilbage, der faktisk
    står i de deklarationer, I har scannet — jordbærpuré, jordbærkoncentrat,
    frysetørrede jordbær — sorteret efter hvor ofte de er set.
    """
    needle = f"%{normalize(q)}%"
    rows = db.execute(
        select(Ingredient)
        .where(
            func.lower(Ingredient.label).like(needle)
            | func.lower(func.coalesce(Ingredient.tag, "")).like(needle)
        )
        .order_by(Ingredient.seen_count.desc())
        .limit(limit)
    ).scalars()
    return [
        {
            "label": r.label,
            "tag": r.tag,
            "resolved": r.resolved,
            "seen": r.seen_count,
            "lang": r.lang,
        }
        for r in rows
    ]


def filter_products(
    db: Session,
    exclude: list[str] | None = None,
    include: list[str] | None = None,
    limit: int = 100,
) -> list[dict]:
    """
    Fritekstfiltrering på tværs af hele indekset — det, der gør at I kan
    lede efter varer på andet end de fire faste allergener.
    """
    stmt = select(Product)

    for term in include or []:
        sub = (
            select(ProductIngredient.product_ean)
            .join(Ingredient, Ingredient.id == ProductIngredient.ingredient_id)
            .where(func.lower(Ingredient.label).like(f"%{normalize(term)}%"))
        )
        stmt = stmt.where(Product.ean.in_(sub))

    for term in exclude or []:
        sub = (
            select(ProductIngredient.product_ean)
            .join(Ingredient, Ingredient.id == ProductIngredient.ingredient_id)
            .where(func.lower(Ingredient.label).like(f"%{normalize(term)}%"))
        )
        stmt = stmt.where(~Product.ean.in_(sub))

    out = []
    for p in db.scalars(stmt.limit(limit)):
        n_indexed = db.scalar(
            select(func.count())
            .select_from(ProductIngredient)
            .where(ProductIngredient.product_ean == p.ean)
        )
        out.append(
            {
                "ean": p.ean,
                "name": p.name,
                "brand": p.brand,
                "image_url": p.image_url,
                "n_ingredients": n_indexed,
                # Vigtig advarsel til frontend: en vare uden indekserede
                # ingredienser slipper gennem ethvert exclude-filter.
                "indexed": bool(n_indexed),
            }
        )
    return out
