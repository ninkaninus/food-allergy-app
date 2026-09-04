from __future__ import annotations

import datetime as dt
import io
import os
import secrets
from dataclasses import asdict
from pathlib import Path

import httpx

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import ingredients as ix
from . import off
from .auth import (
    COOKIE,
    SESSION_DAYS,
    current_user,
    afsender,
    forsoeg_fejlede,
    forsoeg_lykkedes,
    require_user,
    spaerret,
    issue_session,
    require_admin,
    require_curator,
    revoke_session,
    validate_new_password,
    verify_password,
)
from .db import RULES, default_household, get_session, init_db
from .matcher import Basis, State, aggregate, fold, ingredients_hash, normalize
from .version import VERSION
from .models import (
    Allergen,
    GYLDIGE_ROLLER,
    ProductPhoto,
    User,
    Product,
    Profile,
    ProfileAllergen,
    ReviewItem,
    Verdict,
    now,
)

# docs_url/redoc_url/openapi_url slået fra: appen ligger åbent på
# internettet, og /docs er et komplet kort over alle ruter — også de
# skrivende. Det offentlige er dommen og listen, ikke API-fladen.
app = FastAPI(title="AllergiScan", version=VERSION,
              docs_url=None, redoc_url=None, openapi_url=None)
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
    """
    Læg varen i bekræftelseskøen, eller genåbn den post der allerede er der.

    Unique-constrainten på ReviewItem er (husstand, EAN) UANSET status.
    Ledte vi kun efter en "pending" post, ville en vare, køen én gang har
    lukket, give en dublet — og dermed 500 på hver eneste scanning af
    netop de varer, familien har gjort arbejdet på. Køen er ét sæt af
    åbne poster pr. vare, ikke en historik.
    """
    item = db.scalar(
        select(ReviewItem).where(
            ReviewItem.household_id == hh_id,
            ReviewItem.product_ean == ean,
        )
    )
    if item is None:
        db.add(ReviewItem(household_id=hh_id, product_ean=ean, reason=reason))
    elif item.status != "pending":
        item.status = "pending"
        item.reason = reason
        item.resolved_at = None
        # created_at bevares med vilje: /api/queue sorterer på den, og en
        # vare, der køes igen ved hver scanning, ville ellers hoppe til
        # toppen hver gang og skubbe det ægte nye ned.


def _visningsnavn(p: Product) -> str | None:
    """
    Navnet, et menneske skal se — familiens eget (`navn_manuelt`), hvis de
    har skrevet ét, ellers Open Food Facts' (`name`). Bruges alle steder,
    en vares navn vises: `navn_manuelt` skal vinde for evigt, også efter
    at OFF senere lærer varen at kende og udfylder `name` (se
    _ensure_product(), som aldrig rører `navn_manuelt`).

    Selve reglen ligger på modellen (`Product.visningsnavn`), så den ikke
    kan glemmes igen ét sted, mens den huskes et andet — se
    `app/ingredients.py:filter_products()`, som brugte `p.name` rå.
    """
    return p.visningsnavn


def _soegenoegle(s: str | None) -> str:
    """
    Søgenøgle, hvor de danske stavemåder falder sammen: 'pålæg', 'paalaeg'
    og 'palaeg' bliver alle til 'palag'. `fold` alene er ikke nok — den
    laver å til aa, og den, der taster på en telefon i en butik, skriver
    lige så tit ét a. Overinklusion er fint her; det er filterlaget, ikke
    en dom.
    """
    t = fold((s or "").lower())
    for dobbelt, enkelt in (("aa", "a"), ("ae", "a"), ("oe", "o")):
        t = t.replace(dobbelt, enkelt)
    return t


def _verdict_rows(
    db: Session,
    hh_id: int,
    product: Product,
    slugs: list[str],
    stored: dict | None = None,
):
    """
    Domslogikken, som både scan-skærmen og gennemse-listen bruger — én
    kilde, så listen aldrig kan sige noget andet end scanningen ville.
    Gemte manuelle domme gælder kun, hvis opskriften er uændret
    (ingredients_hash); alt andet beregnes af motoren. Ingen sideeffekter:
    kø og scanlog hører til i scan-endpointet.
    """
    from .matcher import AllergenVerdict

    if stored is None:
        stored = {
            v.allergen.slug: v
            for v in db.scalars(
                select(Verdict).where(
                    Verdict.household_id == hh_id, Verdict.product_ean == product.ean
                )
            )
        }
    stale = [
        slug
        for slug, v in stored.items()
        if v.basis == Basis.MANUAL.value and v.ingredients_hash != product.ingredients_hash
    ]

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
            verdicts.append(AllergenVerdict(slug, State(state), Basis(basis)))

    return rows, verdicts, stale


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

    # En TOM værdi fra OFF må aldrig overskrive noget, vi allerede har.
    # OFF kender kun ~10 % af familiens varer med ingrediensliste, så
    # "fundet, men uden tekst" er normaltilfældet — og den tekst, et
    # menneske har tastet af den fysiske pakke, er det dyreste arbejde i
    # appen. Har OFF derimod en tekst, vinder den: det er dét, der får
    # ingredients_hash til at skifte, når producenten ændrer opskriften.
    p.name = res["name"] or p.name
    p.brand = res["brand"] or p.brand
    p.quantity = res["quantity"] or p.quantity
    p.image_url = res["image_url"] or p.image_url
    if res["ingredients_text"]:
        p.ingredients_text = res["ingredients_text"]
        p.ingredients_lang = res["ingredients_lang"]
        p.ingredients_hash = ingredients_hash(res["ingredients_text"])
    # source hører til HELE rækken, ikke kun teksten: navn, mærke, mængde
    # og billede kom fra OFF uanset. attribution() tæller på det felt for
    # at opfylde ODbL — se NOTICE.md.
    p.source = "off"
    p.off_allergen_tags = res["off_allergen_tags"]
    p.off_trace_tags = res["off_trace_tags"]
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
def list_profiles(
    # require_user, ikke require_curator: allergensættet er familiens
    # DELTE indstilling, og en inviteret bidragyder skal hente det samme
    # sæt som familien selv — ellers kunne hun ende med at tjekke for de
    # forkerte allergener. Der er ikke noget navn at skjule for hende
    # længere (se Profile.name), kun allergenerne, og dem må hun kende
    # for at kunne hjælpe med rigtige billeder.
    _: User = Depends(require_user),
    db: Session = Depends(get_session),
):
    hh = default_household(db)
    out = []
    for prof in db.scalars(select(Profile).where(Profile.household_id == hh.id)):
        out.append(
            {
                "id": prof.id,
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
def toggle_allergen(
    profile_id: int,
    body: ToggleIn,
    _: User = Depends(require_curator),
    db: Session = Depends(get_session),
):
    """
    Slå et allergen til/fra for HELE familien — uden at røre produktdata
    eller domme.

    Siden 0.20.0 er dette PWA'ens egen skrivevej for curator/admin:
    chipsene under Indstillinger kalder ruten direkte, og ændringen
    gælder med det samme på alle telefoner, der er logget ind (se
    `effektivAllergener()` i app/static/index.html). Den anonyme vej er
    stadig `allergens=` på `/api/scan` — men den vælger kun, hvad ÉN
    scanning skal vurderes imod, den skriver ingenting.
    """
    hh = default_household(db)
    prof = db.get(Profile, profile_id)
    if prof is None or prof.household_id != hh.id:
        raise HTTPException(404, "ukendt profil")
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
    allergens: str | None = None,
    refresh: bool = False,
    bruger: User | None = Depends(current_user),
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
    # Profilen vælges IKKE af kalderen længere. Før kom `profile_id` fra
    # query-strengen og blev slået op uden at tjekke husstanden, så en
    # fremmed kunne vælge et andet barns profil og få DENS allergensæt
    # personaliseret ud. Appen sendte den aldrig selv — frontend bruger
    # `allergens=`.
    prof = db.scalar(select(Profile).where(Profile.household_id == hh.id))
    # ?refresh=true springer 14-dages-cachen over. Den må en ulogindet
    # kalder ikke styre.
    #
    # BEMÆRK at hegnet kun dækker den TVUNGNE genhentning. En ukendt
    # stregkode giver stadig ét udgående Open Food Facts-kald og én
    # Product-række, uanset hvem der spørger — det er prisen for, at
    # opslaget er åbent. Negative svar caches ikke, så samme ukendte
    # stregkode koster et friskt kald hver gang. Skal det lukkes, er det
    # en ændring af den offentlige flade, ikke en kommentar.
    if refresh and bruger is None:
        refresh = False
    if allergens is not None:
        slugs = [s for s in (t.strip() for t in allergens.split(",")) if s in RULES.allergens]
        if not slugs:
            raise HTTPException(400, "ingen gyldige allergener angivet")
    elif bruger is not None:
        slugs = _active_slugs(db, prof.id) if prof else list(RULES.allergens)
    else:
        # En anonym kalder uden `allergens=` får ALLE 17 vurderet — ikke
        # barnets sæt. Faldt vi tilbage på profilen, ville selve svarets
        # LÆNGDE røbe, hvilke fire allergener barnet reagerer på, uden at
        # nogen havde spurgt om det. Appen selv sender altid parameteren
        # (frontend læser den af localStorage).
        slugs = list(RULES.allergens)

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
        # Køen er familiens egen: den føres kun, når nogen er logget ind.
        # Ellers kunne enhver på internettet fylde arbejdsbunken — og
        # genåbne poster, familien havde lukket.
        if bruger is not None:
            _queue(db, hh.id, ean, "not_found")
        db.commit()
        return {
            "ean": ean,
            "found": False,
            "result": "unknown",
            # Køen føres kun for familien, så beskeden må ikke love en
            # fremmed, at varen er lagt i den — eller bede dem om at gøre
            # noget, de ikke har adgang til.
            "message": (
                "Ikke i Open Food Facts. Lagt i bekræftelseskøen — "
                "tag et billede af varedeklarationen og tast den ind."
                if bruger is not None else
                "Ikke i Open Food Facts. Appen ved ingenting om den her vare — "
                "læs etiketten."
            ),
            "allergens": [],
        }

    rows, verdicts, stale = _verdict_rows(db, hh.id, product, slugs)
    if stale and bruger is not None:
        _queue(db, hh.id, ean, "recipe_changed")

    result = aggregate(verdicts)

    # Køen er familiens arbejdsbunke — se noten længere oppe. En fremmeds
    # opslag må hverken lægge noget i den eller genåbne en lukket post.
    if bruger is not None and (
        result in ("unverified", "caution") or not product.ingredients_text
    ):
        _queue(
            db,
            hh.id,
            ean,
            "no_ingredients" if not product.ingredients_text else "maybe_hit",
        )

    db.commit()

    return {
        "ean": ean,
        "found": True,
        "source": source,
        "result": result,
        "fotos": _foto_svar(db, hh.id, ean, bruger),
        "product": {
            "name": _visningsnavn(product),
            # Kan bekræftelsesskærmen RETTE dette navn? Kun hvis det er
            # familiens eget — OFF's eget gæt skal ikke kunne overskrives
            # via feltet uden videre. Se openConfirm() i static/index.html.
            "navn_er_vores": product.navn_manuelt is not None,
            "brand": product.brand,
            "quantity": product.quantity,
            "image_url": product.image_url,
            "ingredients_text": product.ingredients_text,
            "ingredients_parsed": normalize(product.ingredients_text),
            "ingredients_lang": product.ingredients_lang,
        },
        "allergens": rows,
        # Betyder KUN "lagt i bekræftelseskøen, hvis der var grund til
        # det" — der er ingen dagbog mere (se Scan i app/models.py). Er
        # sessionen løbet ud (30 dage), får man en helt normal dom — men
        # varen lander ikke i køen. Det skal kunne SES på skærmen, ikke
        # kun udledes af at knappen i headeren har skiftet tekst.
        "gemt": bruger is not None,
        # `Profile.name` findes ikke mere (se app/db.py) — der er intet
        # navn tilbage at holde ude af det offentlige opslagsværk. `id`
        # står, hvis noget en dag skal slå profilen op.
        "profile": {"id": prof.id} if (prof and bruger) else None,
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
    ean = "".join(ch for ch in ean if ch.isdigit())
    if len(ean) < 8:
        raise HTTPException(400, "stregkoden ser ikke rigtig ud")
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
def queue(
    # require_curator, ikke require_user: en inviteret bidragyder (contributor)
    # må fotografere en vare, men ikke se familiens arbejdsbunke.
    _: User = Depends(require_curator),
    db: Session = Depends(get_session),
):
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
                "name": _visningsnavn(p) if p else None,
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
    mail = body.email.strip().lower()
    ip = afsender(request)

    # Spærren rammer FØR argon2 overhovedet kører — den er både
    # gætte-spærren og loftet på RAM-forbruget. Den er nøglet på
    # afsenderen, ikke på mailadressen: en fremmed skal ikke kunne låse
    # familien ude af deres egen app ved at gætte forkert på deres mail.
    tilbage = spaerret(ip)
    if tilbage:
        raise HTTPException(
            429, f"For mange forsøg. Prøv igen om {tilbage // 60 + 1} minutter."
        )

    user = db.scalar(select(User).where(User.email == mail))
    # Samme svar uanset om mailen findes — ellers kan man opremse brugere.
    if user is None or not user.active or not user.password_hash:
        forsoeg_fejlede(ip)
        raise HTTPException(401, "Forkert mail eller adgangskode.")
    if not verify_password(user.password_hash, body.password):
        forsoeg_fejlede(ip)
        raise HTTPException(401, "Forkert mail eller adgangskode.")
    forsoeg_lykkedes(ip)

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

    Dette ER invitationen — der er intet token, intet link. Admin sætter
    adgangskoden og giver den videre til den inviterede, ligesom med
    `python -m app.cli adduser`.
    """
    from .auth import hash_password

    if body.role not in GYLDIGE_ROLLER:
        raise HTTPException(400, f"ukendt rolle: {body.role}")
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


@app.get("/api/auth/users")
def list_users(
    _: User = Depends(require_admin),
    db: Session = Depends(get_session),
):
    """
    Listen, der gør en invitation til en beslutning man kan se: hvem er
    allerede inviteret, med hvilken rolle, og har hun overhovedet logget
    ind. Kun det en admin skal bruge for at oprette en ny uden at lave en
    dublet — ALDRIG `password_hash`, `source` eller `household_id`.
    """
    hh = default_household(db)
    return [
        {
            "id": u.id,
            "email": u.email,
            "name": u.name,
            "role": u.role,
            "active": u.active,
            # Samme UTC-uden-zone-fælde som taget_at ovenfor — se den note.
            # timespec="seconds", samme som taget_at i _foto_svar() —
            # ellers får den her mikrosekunder, som ingen har brug for.
            "last_login": (u.last_login.isoformat(timespec="seconds") + "Z")
            if u.last_login else None,
        }
        for u in db.scalars(
            select(User).where(User.household_id == hh.id).order_by(User.id)
        )
    ]


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


@app.get("/api/soeg")
def soeg(
    q: str = "",
    status: str = "alle",
    fri_for: str | None = None,
    allergens: str | None = None,
    limit: int = 60,
    db: Session = Depends(get_session),
):
    """
    Flad, sorteret liste over de varer, I har scannet.

    (0.25.0 fjernede den gamle godkendt-liste fra regnearket, som før
    blev slået sammen med de scannede varer her — se
    _drop_imported_product_tabellen() i app/db.py. Det gamle regneark
    findes stadig hos jer; det er kun appens kopi, der er væk.)

    Sikkerheden er den samme som på scan-skærmen: domme kommer fra
    `_verdict_rows`, så en manuel godkendelse kun tæller med uændret
    opskrift. Søgningen kan aldrig GØRE noget grønt — kun vise frem.

    Filtre (alle valgfrie, kombineres):
      q         fritekst i navn og mærke (æ/ø/å-tolerant)
      status    alle | safe | unsafe | uafklaret
      fri_for   kommaseparerede allergen-slugs: skjuler varer, hvor
                allergenet ER fundet. Bemærk: det er IKKE det samme som
                bevist fri — ukendt er stadig ukendt, og hver vare
                beholder sin egen farve.

    Varerne sorteres med det gode først og det forbudte sidst — man
    søger for at finde noget, man kan spise.
    """
    gyldige = {"alle", "safe", "unsafe", "caution", "unverified", "uafklaret"}
    if status not in gyldige:
        raise HTTPException(400, f"status skal være en af: {', '.join(sorted(gyldige))}")
    if allergens is not None:
        slugs = [s for s in (t.strip() for t in allergens.split(",")) if s in RULES.allergens]
        if not slugs:
            raise HTTPException(400, "ingen gyldige allergener angivet")
    else:
        slugs = list(RULES.allergens)

    fri = [s for s in (t.strip() for t in (fri_for or "").split(",")) if s in RULES.allergens]
    hh = default_household(db)
    limit = max(1, min(limit, 200))

    # Alle domme i ét opslag — ellers bliver det N+1 forespørgsler, og
    # listen bliver langsom, netop som den bliver værd at bruge.
    domme: dict[str, dict] = {}
    for v, slug in db.execute(
        select(Verdict, Allergen.slug)
        .join(Allergen, Allergen.id == Verdict.allergen_id)
        .where(Verdict.household_id == hh.id)
    ):
        domme.setdefault(v.product_ean, {})[slug] = v

    kandidater: list[dict] = []
    for p in db.scalars(select(Product)):
        rows, verdicts, stale = _verdict_rows(db, hh.id, p, slugs, domme.get(p.ean, {}))
        kandidater.append({
            "ean": p.ean,
            "navn": _visningsnavn(p) or "Uden navn",
            "maerke": p.brand,
            "billede": p.image_url,
            "status": aggregate(verdicts),
            "stale": bool(stale),
            "problemer": [r["name"] for r in rows if r["state"] == "contains"],
            "spor": [r["name"] for r in rows if r["state"] == "trace_risk"],
            "_fundet": {r["slug"] for r in rows if r["state"] in ("contains", "trace_risk")},
        })

    ql = _soegenoegle((q or "").strip())

    def match_q(k: dict) -> bool:
        if not ql:
            return True
        blob = _soegenoegle(" ".join(filter(None, [k["navn"], k["maerke"]])))
        return ql in blob

    def match_status(k: dict) -> bool:
        if status == "alle":
            return True
        if status == "uafklaret":
            return k["status"] in ("caution", "unverified")
        return k["status"] == status

    def match_fri(k: dict) -> bool:
        return not (k["_fundet"] & set(fri))

    def filtrer(*undtag: str) -> list[dict]:
        proever = {"q": match_q, "status": match_status, "fri_for": match_fri}
        aktive = [f for navn, f in proever.items() if navn not in undtag]
        return [k for k in kandidater if all(f(k) for f in aktive)]

    uden_status = filtrer("status")
    status_antal = {
        "alle": len(uden_status),
        "safe": sum(k["status"] == "safe" for k in uden_status),
        "unsafe": sum(k["status"] == "unsafe" for k in uden_status),
        "uafklaret": sum(k["status"] in ("caution", "unverified") for k in uden_status),
    }
    facetter = {"status": status_antal}

    traef = filtrer()
    # Det gode først, det forbudte sidst — man søger for at finde noget,
    # man kan spise.
    rang = {"safe": 0, "unverified": 1, "caution": 1, "unsafe": 2}
    traef.sort(key=lambda k: (rang.get(k["status"], 9), (k["navn"] or "").lower()))
    for k in kandidater:
        k.pop("_fundet", None)

    return {
        "antal": len(traef),
        "vist": min(len(traef), limit),
        "varer": traef[:limit],
        "facetter": facetter,
    }


@app.get("/api/products")
def product_filter(
    exclude: str | None = None,
    include: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_session),
):
    """Fritekstfiltrering på hele indekset. Kommasepareret."""
    limit = max(1, min(limit, 200))   # samme loft som /api/soeg
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


SLAGS = {"front": "Forside", "deklaration": "Deklaration"}

# Deklarationen er dét, man skal kunne LÆSE igen — 6-punkts tryk på
# krøllet folie. Den gemmes derfor tæt på telefonens egen opløsning og
# uden farve-underprøvning (subsampling 0), som ellers smører netop de
# tynde bogstavstreger ud. Forsiden skal kun kunne genkendes.
# Et deklarationsfoto fylder ~2-4 MB; 583 varer bliver et par GB.
FOTO_MAX = {
    "front": int(os.getenv("FOTO_MAX_FRONT", "1600")),
    "deklaration": int(os.getenv("FOTO_MAX_DEKLARATION", "4000")),
}
FOTO_KVALITET = {"front": 82, "deklaration": 94}
# Miniaturen vises i listen. Uden den ville et tryk på en vare hente
# fuldbilledet over mobildata, midt i Netto.
MINI_MAX = 480


def _billedmappe() -> Path:
    from .db import DATA_DIR

    mappe = DATA_DIR / "billeder"
    mappe.mkdir(parents=True, exist_ok=True)
    return mappe


def _rens(ean: str, slags: str) -> tuple[str, str]:
    """Kun cifre og en kendt slags — filnavnet bygges af de to, så der er
    ingen vej fra en URL til en sti, brugeren selv har fundet på."""
    r = "".join(ch for ch in ean if ch.isdigit())
    if len(r) < 8:
        raise HTTPException(400, "stregkoden ser ikke rigtig ud")
    if slags not in SLAGS:
        raise HTTPException(400, f"slags skal være en af: {', '.join(SLAGS)}")
    return r, slags


def _foto_familie(bruger: User | None) -> bool:
    """`taget_af` er en VOKSENS navn og ryger ikke ud af huset — og siden
    0.20.0 dækker "indlogget" også en inviteret bidragyder. Familien, dem
    der rent faktisk bekræfter en vare og har brug for at vide hvis
    billede de kigger på, er curator/admin. En bidragyder har intet brug
    for at se sit eget navn ekko'et tilbage. Delt af _foto_svar() og
    _alle_fotos_svar(), så de to ikke kan komme til at gate forskelligt."""
    return bruger is not None and bruger.role in ("curator", "admin")


def _foto_kan_slette(f: ProductPhoto, bruger: User | None) -> bool:
    """Samme regel som slet_foto() håndhæver — delt, så en knap i
    grænsefladen aldrig kan blive vist for noget, brugeren rent faktisk
    får 403 på. Curator/admin må slette alt; en bidragyder kun sit eget
    (afgjort af `taget_af_user_id`, ikke af navnestrengen `taget_af`)."""
    if bruger is None:
        return False
    if bruger.role in ("curator", "admin"):
        return True
    return f.taget_af_user_id == bruger.id


def _foto_svar(db: Session, hh_id: int, ean: str, bruger: User | None = None) -> dict:
    """Ét indslag pr. slags — det NYESTE, hvis der ligger flere (siden
    0.21.0 erstatter et nyt foto ikke længere det gamle). ORDER BY
    (taget_at, id) ASC, så dict-tildelingen naturligt lader den seneste
    vinde — `id` er tiebreak ved samme sekund-præcise tidsstempel, ligesom
    hent_foto()s (taget_at DESC, id DESC), så de to ruter aldrig kan
    komme til at pege på to FORSKELLIGE billeder som "det nyeste". Se
    _alle_fotos_svar() for ALLE billeder, ikke kun det nyeste pr. slags."""
    ud = {}
    familie = _foto_familie(bruger)
    for f in db.scalars(
        select(ProductPhoto)
        .where(ProductPhoto.household_id == hh_id, ProductPhoto.product_ean == ean)
        .order_by(ProductPhoto.taget_at, ProductPhoto.id)
    ):
        v = int(f.taget_at.timestamp())
        ud[f.slags] = {
            "id": f.id,
            "url": f"/api/products/{ean}/foto/{f.slags}?v={v}",
            "mini_url": f"/api/products/{ean}/foto/{f.slags}?v={v}&mini=1",
            # "Z" med vilje: taget_at er UTC (models.now()) men gemmes
            # naivt, og uden zone læser browseren isoformat() som LOKAL
            # tid — et foto taget kl. 23:30 stod som 21:30, og et taget
            # mellem midnat og kl. 02 viste GÅRSDAGENS dato.
            "taget_at": f.taget_at.isoformat(timespec="seconds") + "Z",
            **({"taget_af": f.taget_af} if familie else {}),
            "bredde": f.bredde,
            "hoejde": f.hoejde,
        }
    return ud


def _alle_fotos_svar(db: Session, hh_id: int, ean: str, bruger: User | None) -> dict:
    """
    ALLE billeder af varen, grupperet pr. slags, nyeste først — i
    modsætning til _foto_svar() (kun det NYESTE pr. slags), som det
    lille galleri på scan-kortet bruger uændret.

    Findes, fordi intet endepunkt før udleverede et `foto_id` for et
    ÆLDRE billede: en curator kunne ikke rydde op i dem ved gennemgang,
    og en bidragyder kunne ikke selv slette et billede, hun havde
    fortrudt. Hvert billede får sin egen URL via hent_bestemt_foto()
    (`.../foto/{slags}/{id}`), ikke den "nyeste vinder"-rute — ellers
    ville to billeder af samme slags vise det SAMME billede i galleriet.
    """
    familie = _foto_familie(bruger)
    ud: dict[str, list[dict]] = {slags: [] for slags in SLAGS}
    for f in db.scalars(
        select(ProductPhoto)
        .where(ProductPhoto.household_id == hh_id, ProductPhoto.product_ean == ean)
        .order_by(ProductPhoto.taget_at.desc(), ProductPhoto.id.desc())
    ):
        v = int(f.taget_at.timestamp())
        ud.setdefault(f.slags, []).append({
            "id": f.id,
            "slags": f.slags,
            "url": f"/api/products/{ean}/foto/{f.slags}/{f.id}?v={v}",
            "mini_url": f"/api/products/{ean}/foto/{f.slags}/{f.id}?v={v}&mini=1",
            "taget_at": f.taget_at.isoformat(timespec="seconds") + "Z",
            **({"taget_af": f.taget_af} if familie else {}),
            "bredde": f.bredde,
            "hoejde": f.hoejde,
            # Beregnet server-side, ikke gættet i grænsefladen: samme
            # regel som slet_foto() selv håndhæver (_foto_kan_slette()),
            # så der aldrig kan vises en sletteknap, kaldet ville få 403
            # tilbage på.
            "kan_slette": _foto_kan_slette(f, bruger),
        })
    return ud


def _foto_filnavne(ean: str, slags: str) -> tuple[str, str]:
    """Unikt filnavn til fuldbillede + miniature. Før 0.21.0 var det altid
    "{ean}_{slags}.jpg" — ét billede pr. slags erstattede det forrige, så
    navnet kunne være forudsigeligt. Nu ligger flere billeder side om
    side, og har brug for hvert sit navn; formatet ender stadig på
    ".jpg", så _mini_fil() virker uændret på gamle OG nye filer."""
    token = secrets.token_hex(6)
    fil = f"{ean}_{slags}_{token}.jpg"
    return fil, _mini_fil(fil)


def _mini_fil(fil: str) -> str:
    return fil[:-4] + "_mini.jpg" if fil.endswith(".jpg") else fil + "_mini"


def _send_foto(f: ProductPhoto, mini: bool) -> FileResponse:
    mappe = _billedmappe()
    sti = mappe / f.fil
    if mini:
        lille = mappe / _mini_fil(f.fil)
        # Billeder gemt før miniaturerne fandtes har kun fuldudgaven.
        sti = lille if lille.exists() else sti
    if not sti.exists():
        raise HTTPException(404, "intet billede")
    return FileResponse(sti, media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=86400"})


@app.post("/api/products/{ean}/foto")
def gem_foto(
    ean: str,
    slags: str = "deklaration",
    image: UploadFile = File(...),
    # require_user, ikke require_curator: en inviteret bidragyder (contributor)
    # må sende billeder ind. `taget_af` bærer navnet videre, så familien
    # altid kan se og spørge, hvem der har fotograferet hvad.
    user: User = Depends(require_user),
    db: Session = Depends(get_session),
):
    """
    Gem et billede af varen — forsiden eller deklarationen — så I kan
    læse etiketten igen derhjemme uden at have pakken.

    Billedet er jeres eget og bliver på serveren. Det er IKKE et bevis:
    et foto gør ingen vare grøn, og dommen kommer stadig fra motoren
    eller fra en bekræftelse mod emballagen. Uploaderen kan være en
    inviteret bidragyder, ikke kun familien selv.

    Hvert kald opretter et NYT billede (siden 0.21.0) — intet erstattes
    automatisk. Ingredienslisten kan være ændret siden sidste foto, og en
    bidragyder skal altid kunne lægge et nyt til, uden at overskrive en
    andens arbejde. Ingen udsmidning; en curator rydder selv op (se
    DELETE herunder).
    """
    from PIL import Image, ImageOps

    ean, slags = _rens(ean, slags)
    data = image.file.read()
    if len(data) > 30 * 1024 * 1024:
        raise HTTPException(413, "Billedet er for stort (max 30 MB).")
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception as e:
        raise HTTPException(400, f"Kunne ikke læse billedet: {e}")

    maks = FOTO_MAX[slags]
    img.thumbnail((maks, maks), Image.LANCZOS)
    fil, mini_fil = _foto_filnavne(ean, slags)
    mappe = _billedmappe()
    img.save(mappe / fil, "JPEG", quality=FOTO_KVALITET[slags],
             subsampling=0 if slags == "deklaration" else 2, optimize=True)

    mini = img.copy()
    mini.thumbnail((MINI_MAX, MINI_MAX), Image.LANCZOS)
    mini.save(mappe / mini_fil, "JPEG", quality=78, optimize=True)

    hh = default_household(db)
    # Begge JPEG'er ligger allerede på disken (ovenfor) FØR databasen har
    # sagt god for det. Fejler indsættelsen eller commit'et, skal filerne
    # ikke blive stående uopnåelige for altid — næste forsøg får et helt
    # nyt, tilfældigt filnavn (se _foto_filnavne()), så det gamle par ville
    # aldrig blive fundet eller ryddet op igen.
    try:
        if db.get(Product, ean) is None:
            # Ukendt stregkode er netop dér, et billede er mest værd — så
            # opret varen, som bekræftelsen også gør. `product_ean` er en
            # RIGTIG fremmednøgle (app/models.py) — uden rækken her ville
            # selve indsættelsen fejle på Postgres, og varen ville samtidig
            # forblive usynlig for /api/soeg, som lister ud fra Product.
            db.add(Product(ean=ean, source="manual"))
        f = ProductPhoto(household_id=hh.id, product_ean=ean, slags=slags)
        f.fil = fil
        f.bredde, f.hoejde = img.size
        f.taget_af = user.name
        f.taget_af_user_id = user.id
        f.taget_at = now().replace(tzinfo=None)
        db.add(f)
        db.commit()
    except Exception:
        (mappe / fil).unlink(missing_ok=True)
        (mappe / mini_fil).unlink(missing_ok=True)
        raise
    return {
        "ok": True,
        "slags": slags,
        "foto_id": f.id,
        "fotos": _foto_svar(db, hh.id, ean, user),
    }


@app.get("/api/products/{ean}/foto/{slags}")
def hent_foto(ean: str, slags: str, mini: bool = False, db: Session = Depends(get_session)):
    """Åben læsning som resten — der er ingen personoplysninger i et
    billede af en pakke rugbrød. Findes der flere billeder af samme
    slags (siden 0.21.0), er det det NYESTE — se hent_bestemt_foto()
    for et bestemt billede."""
    ean, slags = _rens(ean, slags)
    hh = default_household(db)
    f = db.scalar(
        select(ProductPhoto)
        .where(
            ProductPhoto.household_id == hh.id,
            ProductPhoto.product_ean == ean,
            ProductPhoto.slags == slags,
        )
        .order_by(ProductPhoto.taget_at.desc(), ProductPhoto.id.desc())
        .limit(1)
    )
    if f is None:
        raise HTTPException(404, "intet billede")
    return _send_foto(f, mini)


@app.get("/api/products/{ean}/foto/{slags}/{foto_id}")
def hent_bestemt_foto(
    ean: str,
    slags: str,
    foto_id: int,
    mini: bool = False,
    db: Session = Depends(get_session),
):
    """Samme åbne læsning som ovenfor, men ÉT bestemt billede — tilføjet
    i 0.21.0, da et (vare, slags)-par ikke længere peger på præcis ét
    foto."""
    ean, slags = _rens(ean, slags)
    hh = default_household(db)
    f = db.scalar(
        select(ProductPhoto).where(
            ProductPhoto.id == foto_id,
            ProductPhoto.household_id == hh.id,
            ProductPhoto.product_ean == ean,
            ProductPhoto.slags == slags,
        )
    )
    if f is None:
        raise HTTPException(404, "intet billede")
    return _send_foto(f, mini)


@app.get("/api/products/{ean}/fotos")
def alle_fotos(
    ean: str,
    # Åben som resten af fotoruterne (hent_foto/hent_bestemt_foto): et
    # billede af en pakke bærer ingen personoplysninger. Sessionen er
    # VALGFRI — den bruges kun til at gate `taget_af` (kun familien) og
    # `kan_slette` (altid False for en anonym kalder; ellers beregnet af
    # samme regel som slet_foto() selv håndhæver).
    bruger: User | None = Depends(current_user),
    db: Session = Depends(get_session),
):
    """
    Alle billeder af varen, ikke kun det nyeste pr. slags — grundlaget
    for en gennemgang, hvor en curator rydder op i ældre billeder, og en
    bidragyder finder sit eget for at slette det igen.

    `_foto_svar()` (kun det NYESTE pr. slags, brugt af det lille galleri
    på scan-kortet og af /api/scan/{ean}) er URØRT af denne rute.
    """
    ean = "".join(ch for ch in ean if ch.isdigit())
    if len(ean) < 8:
        raise HTTPException(400, "stregkoden ser ikke rigtig ud")
    hh = default_household(db)
    return {
        "nyeste": _foto_svar(db, hh.id, ean, bruger),
        "alle": _alle_fotos_svar(db, hh.id, ean, bruger),
    }


@app.delete("/api/products/{ean}/foto/{slags}/{foto_id}")
def slet_foto(
    ean: str,
    slags: str,
    foto_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_session),
):
    """
    Curator og admin må slette et hvilket som helst foto — det er dem,
    der rydder op ved gennemgang. En bidragyder (require_user, ikke
    require_curator) må kun slette sit EGET: hun sender billeder ind til
    et åbent internet uden mulighed for at fortryde ellers. Ejerskabet
    afgøres af `taget_af_user_id`, ikke navnestrengen `taget_af` — to
    hjælpere med samme fornavn må ikke kunne slette hinandens billeder.
    """
    ean, slags = _rens(ean, slags)
    hh = default_household(db)
    f = db.scalar(
        select(ProductPhoto).where(
            ProductPhoto.id == foto_id,
            ProductPhoto.household_id == hh.id,
            ProductPhoto.product_ean == ean,
            ProductPhoto.slags == slags,
        )
    )
    if f is None:
        raise HTTPException(404, "intet billede")
    if not _foto_kan_slette(f, user):
        raise HTTPException(403, "du kan kun slette billeder, du selv har taget")
    fil, mini_fil = f.fil, _mini_fil(f.fil)
    db.delete(f)
    db.commit()
    mappe = _billedmappe()
    (mappe / fil).unlink(missing_ok=True)
    (mappe / mini_fil).unlink(missing_ok=True)
    return {"ok": True}


class NavnIn(BaseModel):
    # max_length matcher kolonnen (String(400)) — uden den blev et for
    # langt navn før stille afkortet (navn[:400]) i stedet for afvist.
    name: str = Field(min_length=1, max_length=400)


@app.post("/api/products/{ean}/navn")
def saet_produktnavn(
    ean: str,
    body: NavnIn,
    _: User = Depends(require_curator),
    db: Session = Depends(get_session),
):
    """
    Navnet på en vare, familien selv skriver ind — den naturlige plads er
    bekræftelsesskærmen, når I sidder med forsidefotoet af en stregkode,
    Open Food Facts ikke kender. Gemmes i `product.navn_manuelt`, IKKE i
    `product.name` (OFF's eget felt, se _ensure_product()): navngiver
    OFF varen senere, skal familiens eget navn stadig vinde i visningen
    (se _visningsnavn()), ikke blive overskrevet af OFF's gæt. BEVIDST en
    egen rute og ikke en del af /confirm: at navngive en vare afgør ingen
    dom, og bekræftelsesruten hører til allergen-domænet.

    Opretter varen, hvis den ikke findes endnu — ligesom /confirm og
    gem_foto allerede gør. Uden det mistede en forælder, der navngav OG
    tastede en hel deklaration ind på en ukendt EAN, ALT arbejdet på en
    404: frontend gemmer navnet FØR dommene (se saveConfirm() i
    app/static/index.html), og en fejl her stoppede hele gemningen.
    """
    ean = "".join(ch for ch in ean if ch.isdigit())
    if len(ean) < 8:
        raise HTTPException(400, "stregkoden ser ikke rigtig ud")
    navn = body.name.strip()
    if not navn:
        raise HTTPException(400, "navnet må ikke være tomt")
    product = db.get(Product, ean)
    if product is None:
        product = Product(ean=ean, source="manual")
        db.add(product)
    product.navn_manuelt = navn
    db.commit()
    return {"ok": True, "name": _visningsnavn(product)}


@app.post("/api/ocr")
def ocr_declaration(
    image: UploadFile = File(...),
    # require_user, ikke require_curator: en inviteret bidragyder (contributor)
    # skal kunne se, om billedet var læsbart, mens hun står med varen —
    # men OCR sætter aldrig en dom, så det kræver ikke curator-rollen.
    _: User = Depends(require_user),
):
    """
    Foto af varedeklarationen -> tekst. Kører lokalt i containeren; billedet
    forlader ikke serveren og bliver ikke gemt. Resultatet er et forslag,
    som skal rettes igennem i bekræftelsesskærmen.
    """
    from .ocr_klient import laes_deklaration

    data = image.file.read()
    if len(data) > 12 * 1024 * 1024:
        raise HTTPException(413, "Billedet er for stort (max 12 MB).")
    res = laes_deklaration(data)
    if not res.get("ok"):
        return res

    # Porten mod falske røde kryds født af grafik-støj: et rødt kryds fra
    # vrøvl lærer folk at ignorere de røde kryds.
    #
    # Den gælder KUN Tesseract-vejen. De to motorers konfidenstal betyder
    # ikke det samme: målt på familiens fotos scorer OCR-tjenesten 96-98 %
    # på alt — også det, Tesseract læste som volapyk — fordi tallet er
    # tegngenkendelsens sikkerhed, ikke "læste jeg det rigtige". Til
    # gengæld finder den slet ingen linjer i ren støj, og tom tekst sender
    # klienten videre til Tesseract. Porten ville derfor aldrig udløses
    # for tjenesten, og en fælles tærskel ville kun være til pynt.
    if res.get("engine") != "rapidocr" and res["confidence"] < 45:
        res["allergens"] = []
        res["hint"] = (
            "Billedet er for utydeligt til automatisk tjek. Tag et nyt — "
            "tættere på, uden genskin — eller ret teksten og læs den selv."
        )
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


@app.get("/api/korpus")
def korpus(
    # require_user, IKKE require_curator: en dedikeret, lav-rettighed
    # konto til OCR-arbejdet (rollen `contributor`) skal kunne læse
    # korpusset — men den kan aldrig bekræfte en vare, og læsning her
    # ændrer intet. Se ROADMAP.md, "rigtige fotos til OCR-arbejdet".
    #
    # IKKE fordi noget her er nyt hemmeligt: hvert foto og hver
    # deklarationstekst kan allerede hentes anonymt ét ad gangen
    # (foto-ruterne, /api/scan), og /api/soeg?q= udleverer i forvejen
    # alle EAN'er uden login — "kender ikke hver EAN i forvejen" er altså
    # ingen reel beskyttelse. require_user her er den forsigtige standard
    # for en NY rute (start lukket), og det eneste, den reelt sparer en
    # fremmed for, er at skulle kalde flere ruter i stedet for én.
    _: User = Depends(require_user),
    db: Session = Depends(get_session),
):
    """
    Korpus til at måle OCR-arbejdet mod virkeligheden i stedet for mod
    opdigtet tekst: hver vare med mindst ét eget foto ELLER en
    deklarationstekst.

    `deklaration_gik_gennem_bekraeftelse` (product.source == "manual") er
    IKKE et facit — det siger kun, at rækkens seneste skrivning gik
    gennem POST .../confirm, ikke om mennesket rettede et eneste tegn (et
    ombytteligt tryk på "Gem" gemmer OCR-teksten ordret), og heller ikke
    om et senere baggrunds-genhentning fra Open Food Facts (hver 14.
    dag, se _ensure_product()) siden har vippet den tilbage til falsk,
    selvom teksten stadig er den, mennesket tastede — `_ensure_product()`
    sætter `source = "off"` ubetinget ved enhver frisk hentning, uanset om
    OFF faktisk havde en ingrediensliste denne gang. Brug feltet som en
    grov sortering, ikke som et bevis. Den rigtige herkomst (hvornår
    NETOP denne tekst sidst blev bekræftet, uafhængigt af produktrækkens
    øvrige felter) er ikke bygget — den hører til allergen-domænet, fordi
    den ligger tæt på confirm()-ruten.

    BEVIDST UDELADT: `taget_af`/`taget_af_user_id`. Det er en voksens
    navn, det er irrelevant for OCR-arbejdet, og et felt, der ikke
    udleveres her, kan ikke lække. Tilføj det ikke, heller ikke i god tro.
    """
    hh = default_household(db)

    fotos_ved_ean: dict[str, list[ProductPhoto]] = {}
    for f in db.scalars(
        select(ProductPhoto)
        .where(ProductPhoto.household_id == hh.id)
        .order_by(ProductPhoto.taget_at, ProductPhoto.id)
    ):
        fotos_ved_ean.setdefault(f.product_ean, []).append(f)

    eaner = set(fotos_ved_ean)
    for p in db.scalars(select(Product).where(Product.ingredients_text.isnot(None))):
        if p.ingredients_text.strip():
            eaner.add(p.ean)

    produkter = {
        p.ean: p
        for p in db.scalars(select(Product).where(Product.ean.in_(eaner)))
    }

    ud = []
    for ean in sorted(eaner):
        p = produkter.get(ean)
        ud.append(
            {
                "ean": ean,
                "navn": _visningsnavn(p) if p else None,
                "deklaration": p.ingredients_text if p else None,
                "deklaration_gik_gennem_bekraeftelse": bool(p and p.source == "manual"),
                "fotos": [
                    {"id": f.id, "slags": f.slags,
                     "url": f"/api/products/{ean}/foto/{f.slags}/{f.id}"}
                    for f in fotos_ved_ean.get(ean, [])
                ],
            }
        )
    return ud


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
async def diagnostik(
    # require_curator, ikke require_user: en inviteret bidragyder (contributor)
    # skal ikke kunne se serversti, antal brugere eller rå OFF-fejl.
    _: User = Depends(require_curator),
    db: Session = Depends(get_session),
):
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
