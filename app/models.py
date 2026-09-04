"""
Datamodel.

To designbeslutninger bærer det hele:

1. En dom (Verdict) hænger på PARRET (produkt, allergen) — ikke på produktet.
   Derfor kan I tilføje "soja" i morgen uden at ugyldiggøre de 400 varer,
   I allerede har godkendt for mælk og æg. Og hvis hun vokser fra banan,
   slår I den bare fra i profilen; historikken bevares.

2. Hver dom gemmer ingredients_hash fra dengang den blev truffet.
   Ændrer producenten opskriften — samme EAN, ny ingrediensliste —
   matcher hashen ikke længere, og den manuelle godkendelse falder
   automatisk tilbage til "skal bekræftes igen". Det er den eneste
   automatiske beskyttelse mod stille opskriftsændringer, der findes.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Base(DeclarativeBase):
    pass


class Household(Base):
    """Én husstand = ét datasæt. Gør det muligt at dele appen med andre familier."""

    __tablename__ = "household"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    token: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)

    profiles: Mapped[list["Profile"]] = relationship(back_populates="household")


class Profile(Base):
    """Et barn. Flere børn pr. husstand, hver med sit sæt allergener."""

    __tablename__ = "profile"
    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("household.id"))
    # Holdes bevidst tom (""). Barnets navn er ikke en del af det, appen
    # gemmer på serveren — headerens "Tjekker for …" kommer udelukkende
    # fra telefonens egen localStorage. NOT NULL, så en tom streng, ikke
    # NULL, er den rensede tilstand — se init_db() i app/db.py.
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)

    household: Mapped[Household] = relationship(back_populates="profiles")
    allergens: Mapped[list["ProfileAllergen"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )


class Allergen(Base):
    """Seedes fra data/allergens.yaml. Reglerne bor i YAML, ikke i databasen."""

    __tablename__ = "allergen"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name_da: Mapped[str] = mapped_column(String(120))
    off_tag: Mapped[str | None] = mapped_column(String(64), nullable=True)
    eu14: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProfileAllergen(Base):
    __tablename__ = "profile_allergen"
    __table_args__ = (UniqueConstraint("profile_id", "allergen_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profile.id"))
    allergen_id: Mapped[int] = mapped_column(ForeignKey("allergen.id"))
    # strict = må absolut ikke. watch = "måske", vis advarsel men bloker ikke rødt.
    severity: Mapped[str] = mapped_column(String(16), default="strict")
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    profile: Mapped[Profile] = relationship(back_populates="allergens")
    allergen: Mapped[Allergen] = relationship()


class Product(Base):
    """Cache af varedata. EAN er nøglen — den er global og stabil."""

    __tablename__ = "product"
    ean: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(400), nullable=True)
    # Familiens EGET navn (POST /api/products/{ean}/navn) — IKKE Open Food
    # Facts' felt (det er `name` ovenfor, ODbL-afledt, se NOTICE.md).
    # Additiv kolonne (se tilfoej_manglende_kolonner() i app/db.py). Sat,
    # vinder den ALTID i visningen (se _visningsnavn() i app/main.py), og
    # `_ensure_product()` rører den aldrig — ellers forsvandt et navn,
    # familien selv skrev ind på en vare OFF ikke kendte, den dag OFF
    # senere lærte varen at kende og udfyldte `name` med sit eget gæt.
    navn_manuelt: Mapped[str | None] = mapped_column(String(400), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(200), nullable=True)
    quantity: Mapped[str | None] = mapped_column(String(80), nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    ingredients_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingredients_lang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    ingredients_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)

    off_allergen_tags: Mapped[list] = mapped_column(JSON, default=list)
    off_trace_tags: Mapped[list] = mapped_column(JSON, default=list)

    source: Mapped[str] = mapped_column(String(32), default="off")  # off | manual
    fetched_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now, onupdate=now)

    @property
    def visningsnavn(self) -> str | None:
        """
        Navnet et menneske skal se — familiens eget, hvis de har skrevet
        ét, ellers Open Food Facts' eget. Reglen bor HER, ikke kun i en
        hjælpefunktion i app/main.py (_visningsnavn()), fordi den før blev
        glemt netop dér, hvor den ikke lå: `filter_products()` i
        app/ingredients.py returnerede `p.name` rå, og en vare familien
        selv har navngivet stod som »Uden navn« i »Fri for«-fanen.
        """
        return self.navn_manuelt or self.name


class Verdict(Base):
    """Dom for ét (produkt, allergen)-par i én husstand."""

    __tablename__ = "verdict"
    __table_args__ = (UniqueConstraint("household_id", "product_ean", "allergen_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("household.id"))
    product_ean: Mapped[str] = mapped_column(ForeignKey("product.ean"))
    allergen_id: Mapped[int] = mapped_column(ForeignKey("allergen.id"))

    state: Mapped[str] = mapped_column(String(16))   # contains|trace_risk|unknown|free
    basis: Mapped[str] = mapped_column(String(32))   # manual|off_allergen_tag|text_match|...
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Snapshot af ingredienslisten da dommen blev truffet.
    # Ændrer den sig, er dommen forældet.
    ingredients_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)

    decided_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    decided_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)

    allergen: Mapped[Allergen] = relationship()


class ReviewItem(Base):
    """
    Bekræftelseskøen — varer som skal dobbelttjekkes mod den fysiske emballage.

    `product_ean` er med vilje IKKE en fremmednøgle. Køens vigtigste post
    er netop `reason="not_found"`: en stregkode, som Open Food Facts ikke
    kender, og som derfor ikke har nogen række i `product`. Kravet om et
    produkt ville gøre det umuligt at huske "den her skal I fotografere"
    — altså dét, køen er til for.

    SQLite håndhæver ikke fremmednøgler, så begrænsningen var i praksis
    uden virkning; den viste sig først, da databasen skulle flyttes til
    Postgres, hvor 14 køposter ikke kunne indsættes.
    """

    __tablename__ = "review_item"
    __table_args__ = (UniqueConstraint("household_id", "product_ean"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("household.id"))
    product_ean: Mapped[str] = mapped_column(String(20), index=True)
    # new_from_off | no_ingredients | recipe_changed | maybe_hit | not_found
    reason: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


# `Scan` (fødevaredagbogen: hvad blev slået op, hvornår, for hvilken
# profil) er FJERNET i 0.20.0, ikke migreret — se init_db() i app/db.py
# for begrundelsen og den destruktive DROP TABLE. Kort version: familien
# scanner ikke alt, barnet spiser, så en delvis log ville ikke bare være
# svag som efterforskningsværktøj — den ville vildlede. Man kigger efter
# en reaktion, ser ingenting, og konkluderer forkert, at synderen ikke
# var der. Det var også den mest følsomme rest af persondata i basen.
# Led du efter klassen, fordi noget stadig importerer den: det skal det
# ikke længere, og importen er fejlen, ikke denne kommentar.


# ---------------------------------------------------------------------------
# Auth
#
# Læsning kræver intet. Skrivning kræver en bruger.
# To veje ind, som kan bruges samtidig:
#   1. lokal bruger med adgangskode (argon2id)
#   2. betroet reverse proxy (Authelia/authentik) der sætter Remote-User
# ---------------------------------------------------------------------------


# Delt mellem app/main.py (opretter/lister brugere via API'et) og
# app/cli.py (opretter via `adduser`) — begge skal afvise en ukendt
# rolle med samme svar, i stedet for hver sin gættede tjekliste. "viewer"
# har aldrig eksisteret i en udgivet version og hører ikke med.
GYLDIGE_ROLLER = {"contributor", "curator", "admin"}


class User(Base):
    __tablename__ = "app_user"
    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("household.id"))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    # NULL når brugeren udelukkende kommer ind gennem proxy-auth
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Fire trin, hvoraf det første ikke er en rolle: anonym (ingen
    # konto) kan scanne, søge og se familiens bekræftelser — det er
    # appens åbne opslagsværk. GYLDIGE_ROLLER ovenfor lægger tre trin
    # oveni:
    #   contributor = + fotografere en vare, køre OCR, og SE (ikke ændre)
    #                 familiens allergensæt. IKKE bekræfte, og IKKE se
    #                 familiens egne ting (kø, diagnostik). Til betroede
    #                 bedsteforældre eller den faste dagplejer — ikke til
    #                 en gæstedagplejer, som forbliver anonym.
    #   curator     = + bekræfte varer, ændre allergensættet
    #   admin       = + oprette brugere
    role: Mapped[str] = mapped_column(String(16), default="curator")
    source: Mapped[str] = mapped_column(String(16), default="local")  # local | proxy
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    last_login: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class SessionToken(Base):
    __tablename__ = "session_token"
    id: Mapped[int] = mapped_column(primary_key=True)
    # Kun sha256 af tokenet gemmes. Tabellen er værdiløs hvis den lækker.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)


# ---------------------------------------------------------------------------
# Fuldt ingrediensindeks
#
# Adskilt fra allergen-reglerne med vilje. Se README, afsnittet
# "To lag, to opgaver": indekset er til at finde og filtrere,
# regelsættet er til sikkerhed. Indekset afgør aldrig noget.
# ---------------------------------------------------------------------------


class Ingredient(Base):
    """Én ingrediens, som vi har set den. `tag` er OFF's taksonomi-id når den findes."""

    __tablename__ = "ingredient"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    tag: Mapped[str | None] = mapped_column(String(200), nullable=True)  # fx en:whole-milk
    label: Mapped[str] = mapped_column(String(300))
    lang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    seen_count: Mapped[int] = mapped_column(Integer, default=0)


# `ImportedProduct` (jeres gamle godkendt-liste fra regnearket) er FJERNET
# i 0.25.0, ikke migreret — se _drop_imported_product_tabellen() i
# app/db.py for den destruktive DROP TABLE. Kort version: 0 af 583 rækker
# havde en EAN, og domme hænger på (EAN, allergen), så ingen af dem kunne
# nogensinde blive grøn — de stod som "Ikke scannet" for evigt. Rækkerne
# havde heller ingen plads at høre til, jo mere familien scannede: en
# scannet vare får kun kategori ved at matche en arkrække (Product har
# ingen kategorikolonne), samme mekanik som butikskolonnen, der blev
# fjernet i 0.18.0. Regnearket findes stadig hos familien — det var kun
# appens egen kopi, der forsvandt. Led du efter klassen, fordi noget
# stadig importerer den: det skal det ikke længere, og importen er
# fejlen, ikke denne kommentar.


class ProductPhoto(Base):
    """
    Jeres egne billeder af varen: forsiden og deklarationen.

    Samme grund som `verdict`: det er jeres arbejde, ikke Open Food
    Facts' data (se NOTICE.md). Selve filerne ligger på disken under
    DATA_DIR/billeder — ikke som blobs i databasen — så de følger med
    jeres backup af appdata, og databasen forbliver lille nok til at
    kopiere.

    FLERE billeder pr. (vare, slags) siden 0.21.0 — den gamle
    UniqueConstraint("household_id", "product_ean", "slags") er fjernet
    (se _fjern_foto_unik_constraint() i app/db.py). En bidragyder skal
    ALTID kunne lægge et nyt billede til: ingredienslisten kan være
    ændret siden sidst, og det er ikke 1:1 mellem person og billede.
    Intet slettes automatisk — en curator rydder op ved gennemgang.
    `fil` er derfor et UNIKT filnavn pr. billede, ikke længere afledt
    alene af (ean, slags); `GET .../foto/{slags}` giver det NYESTE.
    """

    __tablename__ = "product_photo"

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("household.id"), index=True)
    product_ean: Mapped[str] = mapped_column(ForeignKey("product.ean"), index=True)
    slags: Mapped[str] = mapped_column(String(16))       # front | deklaration
    fil: Mapped[str] = mapped_column(String(200))
    bredde: Mapped[int | None] = mapped_column(nullable=True)
    hoejde: Mapped[int | None] = mapped_column(nullable=True)
    taget_af: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Nullable FK, additiv (se tilfoej_manglende_kolonner()). `taget_af`
    # er kun en navnestreng — to hjælpere med samme fornavn kunne slette
    # hinandens billeder. Ejerskab til sletning afgøres af DENNE kolonne,
    # ikke af navnet. NULL for billeder taget før 0.21.0.
    #
    # `ondelete="SET NULL"`: fjernes en hjælper en dag, skal hendes fotos
    # blive stående som dokumentation, ikke blokere for at brugeren kan
    # slettes. Bemærk at det kun gør en FORSKEL, hvor fremmednøgler rent
    # faktisk håndhæves: Postgres altid, SQLite kun med
    # `PRAGMA foreign_keys=ON` (kun slået til i tests/conftest.py — IKKE
    # i drift, se app/db.py). En allerede kørende SQLite-database i
    # familiens drift rammes derfor slet ikke af dette (fraværet af
    # håndhævelse betød, at en brugersletning ALDRIG blev blokeret der).
    # En allerede kørende POSTGRES-database får derimod IKKE denne klausul
    # af sig selv — `tilfoej_manglende_kolonner()` er kun additiv og
    # ændrer ingen eksisterende fremmednøgle, og det er bevidst ikke
    # rørt her (se CLAUDE.md om app/db.py's migreringskode). Kun en NY
    # database (create_all() fra bunden) får klausulen med det samme.
    taget_af_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    taget_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class ProductIngredient(Base):
    __tablename__ = "product_ingredient"
    __table_args__ = (UniqueConstraint("product_ean", "ingredient_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_ean: Mapped[str] = mapped_column(ForeignKey("product.ean"), index=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredient.id"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    percent: Mapped[float | None] = mapped_column(nullable=True)
