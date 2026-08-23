from __future__ import annotations

import os
import secrets
from pathlib import Path

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from .matcher import Ruleset
from .models import Allergen, Base, Household, Profile, ProfileAllergen, ProductPhoto

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
RULES_PATH = Path(os.getenv("RULES_PATH", "/app/data/allergens.yaml"))

DATA_DIR.mkdir(parents=True, exist_ok=True)

# Appen SKAL vide, hvilken database den kigger i. Før faldt den tavst
# tilbage på en SQLite-fil, hvis DATABASE_URL manglede:
#
#     DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///..."
#
# Forsvandt variablen — en tastefejl i .env, en ændring i compose,
# `${DATABASE_URL:-}` der resolver tomt — fejlede appen ikke. Den lavede
# en splinterny, TOM database i /data og startede grønt op. Alle varer,
# domme, brugere og billeder var væk fra appens synsfelt, mens de rigtige
# data lå uberørt i Postgres. Healthchecket bestod. Autodeploy meldte
# fuldført. Det er samme fejlform som en migrering, der tier: et tavst
# fald tilbage, der ligner succes.
#
# Nu skal SQLite vælges udtrykkeligt. Til lokal udvikling:
#     TILLAD_SQLITE=1 DATA_DIR=./data-runtime uvicorn app.main:app --reload
_url = (os.getenv("DATABASE_URL") or "").strip()
if not _url:
    if (os.getenv("TILLAD_SQLITE") or "").strip().lower() not in {"1", "true", "ja"}:
        raise RuntimeError(
            "DATABASE_URL er ikke sat, og TILLAD_SQLITE er ikke slået til.\n"
            "\n"
            "Appen nægter at starte frem for at oprette en TOM SQLite-database "
            "og lade som om alt er i orden — det ville se ud, som om alle varer, "
            "domme, brugere og billeder var forsvundet.\n"
            "\n"
            "  I drift:  sæt DATABASE_URL i .env, fx\n"
            "            postgresql+psycopg://allergiscan:<kodeord>@postgres:5432/allergiscan\n"
            "  Lokalt:   sæt TILLAD_SQLITE=1\n"
        )
    _url = f"sqlite:///{DATA_DIR / 'allergiscan.db'}"

DATABASE_URL = _url

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=5)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
RULES = Ruleset(RULES_PATH)

# Sig højt ved opstart, hvilken database det blev. Uden den linje kunne
# man ikke se forskel på "kører på Postgres" og "kører på en tom fil"
# uden at logge ind som curator og slå /api/diagnostik op.
print(
    "AllergiScan: database = "
    + ("sqlite (" + str(DATA_DIR / "allergiscan.db") + ")"
       if engine.dialect.name == "sqlite" else engine.dialect.name),
    flush=True,
)


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


# Arbejdsnavnet, den nye fototabel bygges under, indtil den er færdig og
# kan overtage det rigtige navn. Se _byg_fototabellen_om().
_FOTO_SKRABETABEL = "product_photo_ny"


def _vagt_mod_afbrudt_fotoombygning() -> None:
    """
    Køres FØR create_all(). Nægter at starte, hvis en tidligere
    ombygning af `product_photo` er endt halvvejs.

    Vagten findes, fordi det SKETE. Den første udgave af migreringen
    herunder omdøbte tabellen til `product_photo_gammel` og byggede så
    en ny — men SQLite flytter ikke indeksene med ved en omdøbning, så
    `CREATE INDEX ix_product_photo_household_id` fejlede på et
    navnesammenstød. pysqlite kører DDL uden for transaktionen, så
    omdøbningen stod allerede fast: familiens fotos lå i
    `product_photo_gammel`, og ved siden af stod en tom `product_photo`.

    Det farlige var ikke nedbruddet. Det farlige var ANDEN opstart:
    `create_all()` så en `product_photo`, der fandtes, migreringen fandt
    ingen begrænsning på den tomme tabel og gik hjem, healthchecket blev
    grønt, og appen så ud, som om familien aldrig havde taget et
    billede. Et rollback til forrige version hjalp heller ikke.

    Ombygningen er atomar nu, så den her burde aldrig fyre. Gør den det,
    er rækkerne der stadig — og en opstart, der stopper med at sige
    hvor, er uendeligt meget bedre end en, der starter og tier.
    """
    insp = inspect(engine)
    for rest in ("product_photo_gammel", _FOTO_SKRABETABEL):
        if not insp.has_table(rest):
            continue
        with engine.connect() as con:
            antal = con.execute(text(f'SELECT count(*) FROM "{rest}"')).scalar() or 0
        raise RuntimeError(
            f'Tabellen "{rest}" ligger tilbage efter en afbrudt ombygning af '
            f"product_photo og indeholder {antal} fotorække(r). Appen starter "
            "ikke, for de rækker ville ellers se ud, som om de aldrig havde "
            "eksisteret. Kopiér dem over i product_photo og drop "
            f'"{rest}" — så starter den igen.'
        )


def _byg_fototabellen_om() -> None:
    """
    Bygger `product_photo` om uden den unikke begrænsning. SQLite har
    ingen ALTER TABLE ... DROP CONSTRAINT: begrænsningen står i selve
    CREATE TABLE, og eneste vej er at bygge tabellen om.

    To ting skal være rigtige, og begge var forkerte i første forsøg:

    **Rækkefølgen.** SQLite flytter ikke indeks med ved en omdøbning.
    Omdøber man den gamle tabel først, bliver `ix_product_photo_*`
    siddende på den, og den nye tabels indeks kan ikke oprettes. Derfor
    bygges den nye tabel under et arbejdsnavn, og den gamle DROPPES —
    hvilket frigør indeksnavnene — før omdøbningen.

    **Atomariteten.** pysqlite committer DDL uden for transaktionen i
    sin standardtilstand, så et nedbrud midtvejs blev permanent. SQLite
    kan i virkeligheden godt rulle DDL tilbage; det er driverens
    autocommit, der er i vejen. Derfor køres hele ombygningen på en rå
    forbindelse med `isolation_level = None` og et eksplicit BEGIN.
    Fejler noget som helst undervejs, er databasen bagefter præcis som
    før — med rækker og indeks i behold.

    Rækkerne tælles før og efter og sammenlignes inde i transaktionen.
    Den forrige udgave efterprøvede kun, at begrænsningen var væk, og
    det er den jo også på en tom tabel.
    """
    from sqlalchemy import MetaData
    from sqlalchemy.schema import CreateIndex, CreateTable

    tabel = ProductPhoto.__table__
    kolonner = ", ".join(f'"{c.name}"' for c in tabel.columns)
    # Kopiér HELE metadataen, ikke kun fototabellen. Kopieres den alene,
    # kan SQLAlchemy ikke slå `household`, `product` og `app_user` op og
    # dropper de tre fremmednøgler på gulvet — og FK'en på product_ean er
    # netop den, der forhindrer en fotorække uden vare.
    md = MetaData()
    for t in Base.metadata.tables.values():
        t.to_metadata(md)
    skrab = md.tables["product_photo"].to_metadata(md, name=_FOTO_SKRABETABEL)
    skrab.indexes.clear()       # indeksene får deres rigtige navne til sidst

    raa = engine.raw_connection()
    try:
        dbapi = raa.driver_connection
        forrige = dbapi.isolation_level
        dbapi.isolation_level = None        # vi styrer selv transaktionen
        cur = dbapi.cursor()
        try:
            cur.execute("BEGIN")
            foer = cur.execute("SELECT count(*) FROM product_photo").fetchone()[0]
            cur.execute(str(CreateTable(skrab).compile(engine)))
            cur.execute(
                f"INSERT INTO {_FOTO_SKRABETABEL} ({kolonner}) "
                f"SELECT {kolonner} FROM product_photo"
            )
            cur.execute("DROP TABLE product_photo")
            cur.execute(f"ALTER TABLE {_FOTO_SKRABETABEL} RENAME TO product_photo")
            for ix in tabel.indexes:
                cur.execute(str(CreateIndex(ix).compile(engine)))
            efter = cur.execute("SELECT count(*) FROM product_photo").fetchone()[0]
            if efter != foer:
                raise RuntimeError(
                    f"{foer - efter} af {foer} fotorække(r) forsvandt under "
                    "ombygningen af product_photo. Ruller tilbage."
                )
            cur.execute("COMMIT")
        except Exception:
            cur.execute("ROLLBACK")
            raise
        finally:
            dbapi.isolation_level = forrige
    finally:
        raa.close()


def _fjern_foto_unik_constraint() -> None:
    """
    Fjerner den gamle "ét foto pr. (vare, slags)"-begrænsning fra 0.21.0.

    `UniqueConstraint("household_id", "product_ean", "slags")` forhindrede
    netop det, en bidragyder har mest brug for: at lægge et NYT billede
    til, uden at det gamle forsvinder. `create_all()` opretter kun
    tabeller, der mangler helt — en fjernet begrænsning på en tabel, der
    allerede findes, rører den aldrig. Idempotent: køres ved hver
    opstart, men rører kun databasen, hvis begrænsningen stadig findes.
    """
    insp = inspect(engine)
    if not insp.has_table("product_photo"):
        return
    kolonner = {"household_id", "product_ean", "slags"}
    # Slå den OP, gæt ikke på navnet. En tidligere udgave hardkodede
    # Postgres' navnekonvention (<tabel>_<kolonner>_key). Ramte den ved
    # siden af, var DROP ... IF EXISTS en tavs no-op: begrænsningen blev
    # siddende, opstarten lykkedes, og først den anden bidragyder, der
    # uploadede til samme vare, fik en 500. Inspektøren kender det
    # rigtige navn på begge databaser.
    fundet = [
        u for u in insp.get_unique_constraints("product_photo")
        if set(u["column_names"]) == kolonner
    ]
    if not fundet:
        return
    if engine.dialect.name == "sqlite":
        _byg_fototabellen_om()
    else:
        with engine.begin() as con:
            for u in fundet:
                if not u.get("name"):
                    continue        # unavngivet: kan ikke droppes ved navn
                con.execute(text(
                    f'ALTER TABLE product_photo DROP CONSTRAINT IF EXISTS "{u["name"]}"'
                ))

    # Efterprøv. Blev den siddende, er 0.21.0's hele formål ude af drift,
    # og den anden upload på samme vare ville give 500. Så er et fejlet
    # deploy med automatisk rollback det rigtige udfald — ikke en app,
    # der starter og lyver om, hvad den kan.
    if any(set(u["column_names"]) == kolonner
           for u in inspect(engine).get_unique_constraints("product_photo")):
        raise RuntimeError(
            "product_photo har stadig sin unikke begrænsning på "
            "(household_id, product_ean, slags) efter migreringen. "
            "Flere billeder pr. vare ville fejle i drift."
        )


def _foto_bruger_fk_faar_ondelete() -> None:
    """
    Giver `product_photo.taget_af_user_id` sin `ON DELETE SET NULL`.

    Fjernes en hjælper en dag, skal hendes billeder blive stående uden
    hendes bruger-id — ikke blokere sletningen af hende. Modellen siger
    det (app/models.py), men en fremmednøgle på en tabel, der allerede
    findes, laves aldrig om af `create_all()`.

    **Kun Postgres.** En ny database får reglen med fra fødslen, og en
    gammel SQLite-base får den gratis, fordi hele tabellen alligevel
    bygges om for den unikke begrænsning lige ovenfor. Tilbage står den
    kørende Postgres — og uden det her ville testen af sletningen bevise
    noget, der kun gælder på udviklermaskinen. Det er den slags falske
    grønt, der kostede en fejlrettelse tidligere i samme udgivelse.

    Navnet slås op, det gættes ikke: en `DROP CONSTRAINT IF EXISTS` på et
    forkert gættet navn er en tavs no-op.
    """
    if engine.dialect.name == "sqlite":
        return
    insp = inspect(engine)
    if not insp.has_table("product_photo"):
        return
    for fk in insp.get_foreign_keys("product_photo"):
        if fk["constrained_columns"] != ["taget_af_user_id"]:
            continue
        if (fk.get("options") or {}).get("ondelete", "").upper() == "SET NULL":
            return                      # allerede på plads — no-op ved næste opstart
        navn = fk.get("name")
        if not navn:
            return                      # unavngivet: kan ikke ændres ved navn
        with engine.begin() as con:
            con.execute(text(f'ALTER TABLE product_photo DROP CONSTRAINT "{navn}"'))
            con.execute(text(
                f'ALTER TABLE product_photo ADD CONSTRAINT "{navn}" '
                "FOREIGN KEY (taget_af_user_id) REFERENCES app_user (id) "
                "ON DELETE SET NULL"
            ))
        break

    # Efterprøv. Tog ændringen ikke, ville en fremtidig sletning af en
    # bruger fejle med en fremmednøglefejl i stedet for at give slip —
    # og det ville først vise sig den dag, nogen faktisk skulle fjernes.
    for fk in inspect(engine).get_foreign_keys("product_photo"):
        if fk["constrained_columns"] == ["taget_af_user_id"]:
            if (fk.get("options") or {}).get("ondelete", "").upper() != "SET NULL":
                raise RuntimeError(
                    "product_photo.taget_af_user_id mangler stadig ON DELETE "
                    "SET NULL efter migreringen. En bruger ville ikke kunne "
                    "fjernes, sålænge hun har taget et billede."
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
    _vagt_mod_afbrudt_fotoombygning()
    Base.metadata.create_all(engine)
    tilfoej_manglende_kolonner()
    _fjern_foto_unik_constraint()
    _foto_bruger_fk_faar_ondelete()
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
