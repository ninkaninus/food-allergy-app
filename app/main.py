from __future__ import annotations

import datetime as dt
import os
from dataclasses import asdict
from pathlib import Path

import httpx

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import ingredients as ix
from . import off
from .auth import (
    COOKIE,
    SESSION_DAYS,
    current_user,
    issue_session,
    require_admin,
    require_curator,
    revoke_session,
    validate_new_password,
    verify_password,
)
from .db import RULES, default_household, get_session, init_db
from .matcher import Basis, State, aggregate, ingredients_hash, normalize
from .version import VERSION
from .models import (
    Allergen,
    User,
    Product,
    Profile,
    ProfileAllergen,
    ReviewItem,
    Scan,
    Verdict,
    now,
)

app = FastAPI(title="AllergiScan", version=VERSION)
STATIC = Path(__file__).parent / "static"


@app.on_event("startup")
def _startup() -> None:
    init_db()


# --------------------------------------------------------------------------
# hjælpere
# --------------------------------------------------------------------------


def _active_slugs(db: Session, profile_id: int) -> list[str]:
    rows = db.execute(
        select(Allergen.slug)
        .join(ProfileAllergen, ProfileAllergen.allergen_id == Allergen.id)
        .where(ProfileAllergen.profile_id == profile_id, ProfileAllergen.active.is_(True))
    ).scalars()
    return list(rows)


def _queue(db: Session, hh_id: int, ean: str, reason: str) -> None:
    existing = db.scalar(
        select(ReviewItem).where(
            ReviewItem.household_id == hh_id,
            ReviewItem.product_ean == ean,
            ReviewItem.status == "pending",
        )
    )
    if existing is None:
        db.add(ReviewItem(household_id=hh_id, product_ean=ean, reason=reason))


async def _ensure_product(db: Session, ean: str, refresh: bool = False) -> tuple[Product | None, str]:
    """Returnerer (produkt, kilde). Henter fra OFF hvis ukendt eller forældet."""
    p = db.get(Product, ean)
    fresh_enough = (
        p is not None
        and p.fetched_at is not None
        and (now().replace(tzinfo=None) - p.fetched_at) < dt.timedelta(days=14)
    )
    if p is not None and fresh_enough and not refresh:
        return p, "cache"

    res = await off.fetch_product(ean)
    if not res.get("found"):
        # Skeln mellem "OFF kender den ikke" og "OFF kunne ikke nås".
        # Fejlen må ikke ligne et ærligt ikke-fundet — så tror brugeren,
        # at varen er tjekket, når intet opslag overhovedet er sket.
        return p, ("off_error" if res.get("error") else "off_miss")

    if p is None:
        p = Product(ean=ean)
        db.add(p)

    p.name = res["name"]
    p.brand = res["brand"]
    p.quantity = res["quantity"]
    p.image_url = res["image_url"]
    p.ingredients_text = res["ingredients_text"]
    p.ingredients_lang = res["ingredients_lang"]
    p.ingredients_hash = ingredients_hash(res["ingredients_text"])
    p.off_allergen_tags = res["off_allergen_tags"]
    p.off_trace_tags = res["off_trace_tags"]
    p.source = "off"
    p.fetched_at = now().replace(tzinfo=None)
    db.flush()

    # Fuldt ingrediensindeks — til filtrering, ikke til domme. Se ingredients.py.
    ix.index_product(db, ean, res.get("ingredients"), res["off_allergen_tags"],
                     res["ingredients_text"])
    db.flush()
    return p, "off"


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------


@app.get("/api/profiles")
def list_profiles(db: Session = Depends(get_session)):
    hh = default_household(db)
    out = []
    for prof in db.scalars(select(Profile).where(Profile.household_id == hh.id)):
        out.append(
            {
                "id": prof.id,
                "name": prof.name,
                "allergens": [
                    {
                        "slug": pa.allergen.slug,
                        "name": pa.allergen.name_da,
                        "severity": pa.severity,
                        "active": pa.active,
                        "eu14": pa.allergen.eu14,
                    }
                    for pa in prof.allergens
                ],
            }
        )
    return out


class ToggleIn(BaseModel):
    slug: str
    active: bool
    severity: str = "strict"


@app.post("/api/profiles/{profile_id}/allergens")
def toggle_allergen(profile_id: int, body: ToggleIn, db: Session = Depends(get_session)):
    """Slå et allergen til/fra uden at røre ved produktdata eller domme."""
    a = db.scalar(select(Allergen).where(Allergen.slug == body.slug))
    if a is None:
        raise HTTPException(404, "ukendt allergen")
    pa = db.scalar(
        select(ProfileAllergen).where(
            ProfileAllergen.profile_id == profile_id,
            ProfileAllergen.allergen_id == a.id,
        )
    )
    if pa is None:
        pa = ProfileAllergen(profile_id=profile_id, allergen_id=a.id)
        db.add(pa)
    pa.active = body.active
    pa.severity = body.severity
    db.commit()
    return {"ok": True}


@app.get("/api/scan/{ean}")
async def scan(
    ean: str,
    profile_id: int | None = None,
    allergens: str | None = None,
    refresh: bool = False,
    db: Session = Depends(get_session),
):
    """
    Åbent endpoint — ingen login.

    `allergens` er en kommasepareret liste af slugs. Frontend sender den
    fra localStorage, så man kan scanne og filtrere uden konto overhovedet.
    Er den ikke sat, falder vi tilbage til den gemte profil.
    """
    ean = "".join(ch for ch in ean if ch.isdigit())
    if len(ean) < 8:
        raise HTTPException(400, "stregkoden ser ikke rigtig ud")

    hh = default_household(db)
    prof = (
        db.get(Profile, profile_id)
        if profile_id
        else db.scalar(select(Profile).where(Profile.household_id == hh.id))
    )
    if allergens is not None:
        slugs = [s for s in (t.strip() for t in allergens.split(",")) if s in RULES.allergens]
        if not slugs:
            raise HTTPException(400, "ingen gyldige allergener angivet")
    else:
        slugs = _active_slugs(db, prof.id) if prof else list(RULES.allergens)

    product, source = await _ensure_product(db, ean, refresh=refresh)

    if product is None and source == "off_error":
        # Ingen kø og ingen "findes ikke" — opslaget er ikke sket.
        return {
            "ean": ean,
            "found": False,
            "result": "error",
            "message": "Open Food Facts kunne ikke nås fra serveren. Varen er "
                       "IKKE slået op — tjek serverens internetforbindelse og "
                       "prøv igen.",
            "allergens": [],
        }

    if product is None:
        _queue(db, hh.id, ean, "not_found")
        db.add(Scan(household_id=hh.id, profile_id=prof.id if prof else None,
                    product_ean=ean, result="unknown"))
        db.commit()
        return {
            "ean": ean,
            "found": False,
            "result": "unknown",
            "message": "Ikke i Open Food Facts. Lagt i bekræftelseskøen — "
                       "tag et billede af varedeklarationen og tast den ind.",
            "allergens": [],
        }

    # Gemte manuelle domme, men kun hvis opskriften ikke er ændret.
    stored = {
        v.allergen.slug: v
        for v in db.scalars(
            select(Verdict).where(
                Verdict.household_id == hh.id, Verdict.product_ean == ean
            )
        )
    }
    stale = [
        slug
        for slug, v in stored.items()
        if v.basis == Basis.MANUAL.value and v.ingredients_hash != product.ingredients_hash
    ]
    if stale:
        _queue(db, hh.id, ean, "recipe_changed")

    rows = []
    verdicts = []
    for slug in slugs:
        v = stored.get(slug)
        if v is not None and v.basis == Basis.MANUAL.value and slug not in stale:
            computed = None
            state, basis, evidence = v.state, v.basis, v.evidence
        else:
            computed = RULES.evaluate(
                slug,
                product.ingredients_text,
                product.off_allergen_tags,
                product.off_trace_tags,
            )
            state, basis = computed.state.value, computed.basis.value
            evidence = [asdict(h) for h in computed.hits]

        meta = RULES.allergens[slug]["meta"]
        rows.append(
            {
                "slug": slug,
                "name": meta["name_da"],
                "eu14": bool(meta.get("eu14")),
                "state": state,
                "basis": basis,
                "evidence": evidence,
                "stale": slug in stale,
            }
        )
        if computed is not None:
            verdicts.append(computed)
        else:
            from .matcher import AllergenVerdict

            verdicts.append(AllergenVerdict(slug, State(state), Basis(basis)))

    result = aggregate(verdicts)

    if result in ("unverified", "caution") or not product.ingredients_text:
        _queue(
            db,
            hh.id,
            ean,
            "no_ingredients" if not product.ingredients_text else "maybe_hit",
        )

    db.add(Scan(household_id=hh.id, profile_id=prof.id if prof else None,
                product_ean=ean, result=result))
    db.commit()

    return {
        "ean": ean,
        "found": True,
        "source": source,
        "result": result,
        "product": {
            "name": product.name,
            "brand": product.brand,
            "quantity": product.quantity,
            "image_url": product.image_url,
            "ingredients_text": product.ingredients_text,
            "ingredients_parsed": normalize(product.ingredients_text),
            "ingredients_lang": product.ingredients_lang,
        },
        "allergens": rows,
        "profile": {"id": prof.id, "name": prof.name} if prof else None,
    }


class ConfirmIn(BaseModel):
    verdicts: dict[str, str]   # {"maelkeprotein": "free", "aeg": "contains"}
    note: str | None = None
    ingredients_text: str | None = None   # hvis I taster deklarationen ind selv


@app.post("/api/products/{ean}/confirm")
def confirm(
    ean: str,
    body: ConfirmIn,
    user: User = Depends(require_curator),
    db: Session = Depends(get_session),
):
    """
    Manuel bekræftelse. Det ENESTE sted en vare kan blive grøn — og derfor
    det eneste sted, der kræver login. Navnet i decided_by kommer fra
    sessionen, ikke fra klienten.
    """
    hh = default_household(db)
    product = db.get(Product, ean)
    if product is None:
        product = Product(ean=ean, source="manual")
        db.add(product)

    if body.ingredients_text:
        product.ingredients_text = body.ingredients_text
        product.ingredients_lang = "da"
        product.source = "manual"
    product.ingredients_hash = ingredients_hash(product.ingredients_text)

    for slug, state in body.verdicts.items():
        if slug not in RULES.allergens:
            raise HTTPException(400, f"ukendt allergen: {slug}")
        if state not in {s.value for s in State}:
            raise HTTPException(400, f"ugyldig tilstand: {state}")
        a = db.scalar(select(Allergen).where(Allergen.slug == slug))
        v = db.scalar(
            select(Verdict).where(
                Verdict.household_id == hh.id,
                Verdict.product_ean == ean,
                Verdict.allergen_id == a.id,
            )
        )
        if v is None:
            v = Verdict(household_id=hh.id, product_ean=ean, allergen_id=a.id)
            db.add(v)
        v.state = state
        v.basis = Basis.MANUAL.value
        v.evidence = []
        v.note = body.note
        v.ingredients_hash = product.ingredients_hash
        v.decided_by = user.name
        v.decided_at = now().replace(tzinfo=None)

    if body.ingredients_text:
        ix.index_product(db, ean, None, [], product.ingredients_text)

    for item in db.scalars(
        select(ReviewItem).where(
            ReviewItem.household_id == hh.id,
            ReviewItem.product_ean == ean,
            ReviewItem.status == "pending",
        )
    ):
        item.status = "done"
        item.resolved_at = now().replace(tzinfo=None)

    db.commit()
    return {"ok": True}


@app.get("/api/queue")
def queue(db: Session = Depends(get_session)):
    hh = default_household(db)
    out = []
    for item in db.scalars(
        select(ReviewItem)
        .where(ReviewItem.household_id == hh.id, ReviewItem.status == "pending")
        .order_by(ReviewItem.created_at.desc())
    ):
        p = db.get(Product, item.product_ean)
        out.append(
            {
                "ean": item.product_ean,
                "reason": item.reason,
                "created_at": item.created_at.isoformat(),
                "name": p.name if p else None,
                "brand": p.brand if p else None,
                "has_ingredients": bool(p and p.ingredients_text),
            }
        )
    return out


@app.get("/api/allergens")
def allergens():
    return [
        {
            "slug": s,
            "name": r["meta"]["name_da"],
            "eu14": bool(r["meta"].get("eu14")),
            "note": (r["meta"].get("note") or "").strip(),
            "n_contains": len(r["contains"]),
            "n_maybe": len(r["maybe"]),
            "n_exclude": len(r["exclude"]),
        }
        for s, r in RULES.allergens.items()
    ]


# --------------------------------------------------------------------------
# Auth. Læsning kræver intet — kun bekræftelser gør.
# --------------------------------------------------------------------------


class LoginIn(BaseModel):
    email: str
    password: str


@app.post("/api/auth/login")
def login(
    body: LoginIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_session),
):
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    # Samme svar uanset om mailen findes — ellers kan man opremse brugere.
    if user is None or not user.active or not user.password_hash:
        raise HTTPException(401, "Forkert mail eller adgangskode.")
    if not verify_password(user.password_hash, body.password):
        raise HTTPException(401, "Forkert mail eller adgangskode.")

    token = issue_session(db, user, request.headers.get("user-agent"))
    response.set_cookie(
        COOKIE,
        token,
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
        # Kun over HTTPS når appen står bag en proxy. Sæt COOKIE_SECURE=0 for rent LAN.
        secure=os.getenv("COOKIE_SECURE", "1") == "1",
        path="/",
    )
    return {"name": user.name, "email": user.email, "role": user.role}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_session)):
    revoke_session(db, request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: User | None = Depends(current_user)):
    if user is None:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "source": user.source,
    }


class NewUserIn(BaseModel):
    email: str
    name: str
    password: str
    role: str = "curator"


@app.post("/api/auth/users")
async def create_user(
    body: NewUserIn,
    _: User = Depends(require_admin),
    db: Session = Depends(get_session),
):
    """
    Opretter en bruger. Adgangskoden tjekkes mod Have I Been Pwned med
    k-anonymitet, så genbrugte kodeord bliver afvist uden at kodeordet
    nogensinde forlader maskinen. Se auth.py.
    """
    from .auth import hash_password

    await validate_new_password(body.password)
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(409, "Den mail findes allerede.")
    hh = default_household(db)
    db.add(
        User(
            household_id=hh.id,
            email=body.email.strip().lower(),
            name=body.name.strip(),
            password_hash=hash_password(body.password),
            role=body.role,
            source="local",
        )
    )
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------
# Fuldt ingrediensindeks — filtrering og synonymforslag
# --------------------------------------------------------------------------


@app.get("/api/ingredients/suggest")
def ingredient_suggest(q: str, db: Session = Depends(get_session)):
    """
    Graver stavemåder ud af jeres eget korpus, når I skal skrive en ny
    synonymliste. Søg "jordbær" og se hvad danske deklarationer faktisk
    kalder det.
    """
    return ix.suggest(db, q)


@app.get("/api/products")
def product_filter(
    exclude: str | None = None,
    include: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_session),
):
    """Fritekstfiltrering på hele indekset. Kommasepareret."""
    split = lambda v: [t.strip() for t in (v or "").split(",") if t.strip()]  # noqa: E731
    rows = ix.filter_products(db, exclude=split(exclude), include=split(include), limit=limit)
    unindexed = sum(1 for r in rows if not r["indexed"])
    return {
        "count": len(rows),
        "unindexed": unindexed,
        "warning": (
            f"{unindexed} varer har ingen indekserede ingredienser og slipper "
            "derfor gennem ethvert fravalg. Filtrering er til at finde varer, "
            "ikke til at afgøre om de er sikre."
        )
        if unindexed
        else None,
        "products": rows,
    }


# --------------------------------------------------------------------------
# OCR
# --------------------------------------------------------------------------


@app.post("/api/ocr")
async def ocr_declaration(
    image: UploadFile = File(...),
    _: User = Depends(require_curator),
):
    """
    Foto af varedeklarationen -> tekst. Kører lokalt i containeren; billedet
    forlader ikke serveren og bliver ikke gemt. Resultatet er et forslag,
    som skal rettes igennem i bekræftelsesskærmen.
    """
    from .ocr import read_declaration

    data = await image.read()
    if len(data) > 12 * 1024 * 1024:
        raise HTTPException(413, "Billedet er for stort (max 12 MB).")
    res = read_declaration(data)
    if not res.get("ok"):
        return res

    # Kør teksten gennem matcheren med OCR-tolerance slået til, så
    # bekræftelsesskærmen kan pege på hvad der skal efterses. Tesseract
    # laver "skummetmaalkspulver" ud af "skummetmælkspulver", og eksakt
    # matchning ville tabe det.
    res["allergens"] = []
    for slug, rule in RULES.allergens.items():
        v = RULES.evaluate(slug, res["text"], ocr=True)
        res["allergens"].append(
            {
                "slug": slug,
                "name": rule["meta"]["name_da"],
                "state": v.state.value,
                "basis": v.basis.value,
                "evidence": [asdict(h) for h in v.hits],
                # Fuzzy-træf er gæt. Frontend skal sige "ligner", ikke "er".
                "approximate": v.basis.value == "ocr_fuzzy",
            }
        )
    return res


# --------------------------------------------------------------------------
# Licens og kreditering (ODbL kræver det — se NOTICE.md)
# --------------------------------------------------------------------------


@app.get("/api/attribution")
def attribution(db: Session = Depends(get_session)):
    n_off = db.scalar(
        select(func.count()).select_from(Product).where(Product.source == "off")
    )
    n_own = db.scalar(select(func.count()).select_from(Verdict))
    return {
        "data_sources": [
            {
                "name": "Open Food Facts",
                "url": "https://openfoodfacts.org",
                "licence": "ODbL 1.0",
                "licence_url": "https://opendatacommons.org/licenses/odbl/1-0/",
                "covers": "Produktnavne, mærker, ingredienslister, allergen-tags",
                "records": n_off,
            },
            {
                "name": "Produktbilleder fra Open Food Facts",
                "licence": "CC BY-SA 3.0",
                "licence_url": "https://creativecommons.org/licenses/by-sa/3.0/",
                "covers": "Billeder vist ved siden af varer",
            },
        ],
        "own_work": {
            "covers": "Jeres manuelle domme og noter. Ikke afledt af Open Food Facts.",
            "records": n_own,
            "note": "Ligger i en separat tabel, så de to datasæt kan skilles ad "
                    "hvis produktcachen nogensinde skal deles under ODbL.",
        },
        "software": "Se NOTICE.md i kildekoden.",
    }


@app.get("/api/version")
def version():
    return {"version": VERSION}


@app.get("/api/diagnostik")
async def diagnostik(db: Session = Depends(get_session)):
    """
    Til fejlsøgning når "der sker ikke noget": hvilken database kigger
    appen i, er der data i den, og kan Open Food Facts nås fra
    containeren? Se fejlsøgningsafsnittet i deploy/UNRAID.md.
    """
    from .db import DATA_DIR, DATABASE_URL

    motor = "postgres" if DATABASE_URL.startswith("postgresql") else "sqlite"
    info = {
        "version": VERSION,
        "database": {
            "motor": motor,
            "sti": str(DATA_DIR / "allergiscan.db") if motor == "sqlite" else "postgres-containeren",
            "skrivbar": os.access(DATA_DIR, os.W_OK) if motor == "sqlite" else True,
            "produkter": db.scalar(select(func.count()).select_from(Product)),
            "domme": db.scalar(select(func.count()).select_from(Verdict)),
            "brugere": db.scalar(select(func.count()).select_from(User)),
        },
    }
    try:
        async with httpx.AsyncClient(timeout=4.0, headers={"User-Agent": off.UA}) as c:
            r = await c.head(off.BASE)
        info["off"] = {"kan_naas": True, "status": r.status_code}
    except Exception as e:
        info["off"] = {"kan_naas": False, "fejl": str(e)}
    return info


@app.get("/api/changelog")
def changelog():
    """Release notes som ren tekst — frontend viser dem under »Nyheder«."""
    path = Path(__file__).resolve().parents[1] / "CHANGELOG.md"
    if not path.exists():
        return PlainTextResponse("Ingen release notes fundet.", status_code=404)
    return PlainTextResponse(path.read_text(encoding="utf-8"))


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
