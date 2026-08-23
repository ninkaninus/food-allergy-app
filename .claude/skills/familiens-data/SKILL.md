---
name: familiens-data
description: Hvilke persondata AllergiScan gemmer, hvorfor, hvor længe, og hvem der kan se dem — plus hvor data forlader systemet. Slå op ved enhver ændring i models.py, adgangsmodellen, fotos, importen, logning eller kald til tredjepart.
---

# Persondata i AllergiScan

Efterprøvet mod `app/models.py`, `app/auth.py`, `app/main.py`, `app/off.py`,
`Dockerfile`, `Dockerfile.ocr`, `docker-compose.yml` og
`app/static/index.html` 23. august 2026 (efter 0.20.0), med rigtige kald mod en
kørende uvicorn og en OFF-stub. **UKENDT** betyder, at ingen har taget
stilling — det er en to-do-liste, ikke felter, der skal fyldes med gæt.

## Det, der gør dette projekt særligt

Databasen indeholder **helbredsoplysninger om et mindreårigt barn**:
rækkerne i `profile_allergen` er "hvad reagerer dette barn på" — særlig
kategori efter GDPR art. 9.

Siden 0.20.0 er der hverken et navn på profilen eller en fødevaredagbog
(`Profile.name` holdes tom, `scan` er droppet — se »Afgjort«). Det gør
oplysningen mindre, ikke uskadelig: husstanden er stadig identificerbar
af domænet, og `imported_product.valideret_mod` udleder de fire
allergener af gentagelsen på ~583 offentlige rækker.

Det er ikke en grund til at gøre appen tungere. Det er grunden til, at
"det ligger jo bare på vores egen server" ikke er et argument, der holder,
hvis noget først forlader den.

## Beholdning

| Felt | Formål | Opbevaring | Hvem kan se det |
|---|---|---|---|
| `Profile.name` | INTET. Kolonnen findes (NOT NULL), men holdes tom | Ryddes ved HVER opstart, `init_db()` | Ingen. Sendes i intet svar; efterprøvet med en base, der havde et navn i sig |
| `ProfileAllergen.allergen_id/severity/active` | Hvad barnet ikke tåler — hele appens formål | Lever med profilen | **Alle indloggede, også `contributor`** (`/api/profiles`, `/api/scan`). En fremmeds opslag vurderer alle 17, så svaret ikke røber de fire |
| `User.email` | Login-identitet; nøglen der matcher proxy-/Access-identitet | UKENDT — ingen sletterute | Egen via `/api/auth/me`; ALLE husstandens mails via `/api/auth/users` (`require_admin`, 0.20.0) |
| `User.name` | Gemmes som `decided_by` på domme og `taget_af` på fotos | UKENDT — ingen sletterute | `decided_by` sendes i INTET svar. `taget_af` sendes til **enhver indlogget**, også en `contributor` — ikke til anonyme. Hele navnelisten til admin via `/api/auth/users` |
| `User.password_hash` | argon2id. NULL, når brugeren kun kommer ind via proxy/Access | Lever med brugeren | Ingen (hash) |
| `User.role` (`contributor`/`curator`/`admin`), `source`, `active`, `last_login` | Adgangsstyring og drift | Lever med brugeren | `role`+`active`+`last_login` til admin via `/api/auth/users`. `source` og `household_id` sendes bevidst IKKE med |
| `SessionToken.token_hash` | Kun sha256 af cookien gemmes — tabellen er værdiløs, hvis den lækker | UKENDT. `expires_at` (default 30 dage, `SESSION_DAYS`) er GYLDIGHED, ikke opbevaring: rækken slettes aldrig. Kun `revoke_session()` ved eksplicit logout fjerner én, og der er ingen oprydning af udløbne | Ingen |
| `SessionToken.user_agent` | Enhedsfingeraftryk; kunne bruges til "log andre enheder ud" | UKENDT — samme som token_hash ovenfor | Den, der har databasen |
| `Verdict.decided_by`, `decided_at`, `note` | Hvem bekræftede hvad hvornår — sporbarhed på en sikkerhedsafgørelse | Indefinit med vilje: dommen ER arbejdet | Alle, der læser en vare |
| `ImportedProduct` (navn, producent, kategori, **valideret_mod**, ean) | Familiens gamle regneark, 583 varer | Erstattes ved genimport | **Offentligt** via `/api/soeg` og `/api/scan` — det ER opslagsværket. Bemærk: `valideret_mod` er en konstant (»æg, mælk, tomat og banan«) på ~583 rækker, altså barnets allergensæt udledt af gentagelsen. Det er uadskilleligt fra at publicere bekræftelserne. `link` og `erstatning_for` importeres, men udstilles ingen steder |
| `ProductPhoto` + filerne under `DATA_DIR/billeder` | Jeres egne fotos af forside og deklaration | Ét pr. (vare, slags); nyt erstatter gammelt. Ingen historik | **Offentligt — bevidst.** Fotoet af deklarationen ER dokumentationen bag en bekræftelse. Prisen: stregkoder kan opremses, og billederne er taget i familiens køkken og i butikker. Står som `test_fotoruten_er_bevidst_offentlig`; lukkes med én dependency |
| `ProductPhoto.taget_af` | Hvem tog billedet — kan fra 0.20.0 være en inviteret bidragyder | Lever med billedet | **Ikke til anonyme** (efterprøvet). Til enhver indlogget, i `/api/scan` og fotosvaret. UBESLUTTET: selve billedfilerne er stadig offentlige |
| `ProductPhoto.taget_at` | Hvornår billedet blev taget | Lever med billedet | **Offentligt** — følger med fotosvaret til anonyme. Det er en tidslinje over, hvornår husstanden har fotograferet hvad |
| `ReviewItem` (ean, reason, status, created_at) | Bekræftelseskøen — arbejdsbunken | Ingen oprydning; løste poster bliver stående | `require_curator`. Nærmeste rest af »adfærd over tid«, men ÉN række pr. (husstand, EAN): ingen gentagelser, ingen profil, ingen anonyme opslag |
| `Household.token` | Genereres ved første start; ubrugt i dag | Lever med husstanden | Den, der har databasen |

Ikke persondata, men ODbL-afledt og skal holdes adskilt: `product`,
`ingredient`, `product_ingredient`. Se `NOTICE.md` — `verdict` og
`imported_product` er familiens eget arbejde og ligger i egne tabeller,
netop for at share-alike ikke smitter af.

## Adgangsmodellen: åbent opslagsværk, lukket familie

**Appen ligger på det åbne internet** — Cloudflare Tunnel uden Access
foran. (Adressen står i `.env` på serveren, ikke her: repoet er
offentligt.) Det er med vilje (se
[[aabent-opslagsvaerk]]): alle skal kunne scanne og se, hvad familien har
bekræftet. Kun familien må godkende.

Grænsen er derfor ikke længere »læsning mod skrivning«, men **»opslag mod
familiens egne ting«**. `tests/test_offentlig_flade.py` er det eneste
sted, den grænse står som kode — flyt aldrig en rute fra den ene liste
til den anden uden at ændre den fil.

Fra 0.20.0 er der tre roller oven på »anonym«: `contributor` (inviteret
hjælper — må fotografere og køre OCR), `curator` (familien — må bekræfte)
og `admin` (+ oprette brugere). `POST /api/auth/users` afviser alt andet
end de tre.

| Offentligt (skal blive ved med at være det) | `require_user` (også bidragyder) | `require_curator` | `require_admin` |
|---|---|---|---|
| `GET /api/scan/{ean}` — dommen* | `GET /api/profiles` — allergensættet, uden navn | `GET /api/queue` | `GET /api/auth/users` |
| `GET /api/soeg`, `GET /api/products` | `POST /api/products/{ean}/foto` | `GET /api/diagnostik` | `POST /api/auth/users` |
| `GET /api/products/{ean}/foto/{slags}` | `POST /api/ocr` | `POST .../confirm`, `DELETE .../foto/{slags}` | |
| `/api/allergens`, `/api/version`, `/api/changelog`, `/api/attribution` | | `POST /api/profiles/{id}/allergens`, `POST /api/liste/{id}/stregkode` | |
| `/`, `/static`, `/healthz`, `/api/ingredients/suggest`, `/api/auth/me` | | | |

`/docs`, `/redoc` og `/openapi.json` er slået helt fra (404, efterprøvet).

**Bemærk asymmetrien i fotoruterne.** En `contributor` må UPLOADE
(`require_user`), men ikke SLETTE (`require_curator`) — og GET er åben.
Hendes billede er dermed offentligt læsbart med det samme, og hun kan
ikke selv trække det tilbage. Hun kan desuden overskrive familiens
eksisterende deklarationsfoto, hvorefter `taget_af` skifter til hendes
navn og det gamle billede er væk uden historik. Begge dele er efterprøvet
mod live 2026-08-23 og står som åbne spørgsmål nedenfor.

\* **`GET /api/scan` svarer FORSKELLIGT alt efter, om der er en bruger.**
For en indlogget: `profile: {id}` (KUN id'et — der er ikke noget navn
mere), og kun barnets aktive allergener vurderes. For en fremmed: `profile` er `null`,
og ALLE 17 vurderes. Det sidste er ikke kosmetik — faldt svaret tilbage
på profilen, ville selve dets LÆNGDE røbe, hvilke fire allergener barnet
reagerer på, uden at nogen havde spurgt.

Indtil 0.19.0 lå `/api/profiles`, `/api/queue` og `/api/diagnostik`
**åbne på internettet** — og `GET /api/scan` sendte barnets navn og de
fire aktive allergener med i svaret, hvis man blot undlod `?allergens=`.
Begge dele blev efterprøvet mod det live site 2026-08-21. Det er
helbredsoplysninger om et mindreårigt menneske (GDPR art. 9).

Det her er stadig den vigtigste enkeltkendsgerning i filen: sådan én
opstår ved, at en rute får lov at eksistere uden at nogen har spurgt,
hvad den viser en fremmed.

`/api/ingredients/suggest` er offentligt og mindre følsomt, men det ER
familiens eget ingredienskorpus, afledt af hvad de har scannet.

**`GET /api/scan/{ean}` skriver stadig — men ikke om fremmede.** Ruten er
åben (det er hele pointen) og opretter `Product`-rækker for alle. Ellers:

- **Et anonymt opslag efterlader INTET.** Efterprøvet 2026-08-23 mod en
  ukendt stregkode: 0 nye rækker i alle 13 tabeller. Kender OFF varen,
  oprettes `product` + `product_ingredient` — varedata, ikke persondata.
- `profile_id` fra query-strengen **ignoreres** — parameteren står ikke
  længere i `scan()`s signatur overhovedet.
- `?refresh=true` **kræver login**. Ellers kunne en ulogindet kalder
  tvinge et udgående Open Food Facts-kald pr. request.
- **Køen føres kun for indloggede**, og det gælder også en `contributor`:
  hendes opslag kan lægge en post i familiens arbejdsbunke og genåbne en,
  familien har lukket — selv om hun ikke må LÆSE køen. `created_at`
  bevares ved genåbning, så en vare, der køes igen, ikke hopper til toppen.
- **`gemt: bool` i scan-svaret** siger, om opslaget blev ført i køen.
  Frontend viser en linje, når det er `false` — ellers ville familien
  miste kø-poster i tavshed, når deres session var udløbet.

Åben bivirkning, der står tilbage og er accepteret: **produktcachen kan
pumpes op udefra**, og et opslag på en ukendt stregkode koster ét kald
til Open Food Facts. Det er prisen for, at værktøjet er åbent.

Alt, der skriver en DOM, kræver `require_curator`; brugeroprettelse og
brugerlisten `require_admin`; fotoupload og OCR `require_user`.

Der er **ingen ingress, der beskytter noget**. Autorisationen ligger i
appen selv, rute for rute. Det betyder:

- **En ny GET-rute er offentlig, fra det øjeblik den findes.** Der er
  ingen Access til at fange den. Enhver ny rute skal svare på: hvad viser
  den til en fremmed? Og den skal med i
  `tests/test_offentlig_flade.py` — i den ene eller den anden liste.
- Multi-husstand er IKKE målet (se [[aabent-opslagsvaerk]]).
  `default_household()` returnerer den første husstand, og det er
  bevidst: der er én familie, og deres bekræftelser er det offentlige.

## Hvorfor Cloudflare Access valideres kryptografisk

Med Tunnel går trafikken direkte til containeren; der er ingen proxy til at
strimle headere. Havde vi stolet på `Cf-Access-Authenticated-User-Email`,
kunne enhver med netværksadgang til containeren sætte den selv.

`app/cfaccess.py` validerer JWT-signaturen i `Cf-Access-Jwt-Assertion` mod
Cloudflares offentlige nøgler og tjekker `aud`. Det kan ikke forfalskes.

`TRUST_PROXY_AUTH=1` (header-baseret `Remote-User`) er kun sikkert bag en
proxy, der strimler `Remote-*` — se `deploy/Caddyfile.example`. Default er 0,
og der er tests for, at begge headere ignoreres, når de ikke er beviste.

**Fejlede ÅBENT indtil 0.19.0** (rettet og efterprøvet 2026-08-21).
Kontrollen var `if TRUSTED_PROXY_HOSTS and peer not in ...`, så en tom
liste sprang peer-kontrollen helt over: en `Remote-User`-header alene gav
skriveadgang, og `Remote-Groups: admins` en ny admin. Nu returnerer
`_proxy_user()` `None`, når listen er tom — funktionen kan altså godt slås
til igen.

To ting skal stadig være rigtige, før den er sikker:

1. Proxyen SKAL strimle indgående `Remote-*`. Se `deploy/Caddyfile.example`.
2. `TRUSTED_PROXY_HOSTS` skal være én eller flere **eksakte IP-adresser**,
   kommasepareret. Sammenligningen er `peer not in TRUSTED_PROXY_HOSTS` på
   et `set` af strenge — **et CIDR-udtryk matcher aldrig**, og den
   dokumenterede default (`caddy` i `.env.example` og `docker-compose.yml`)
   kan heller ikke: `request.client.host` er en IP fra socket'en, aldrig et
   Docker-servicenavn. Følger man opskriften, fejler login nu lukket i
   stedet for åbent — men det virker stadig ikke.

**Enhver ændring i `auth.py` eller `cfaccess.py` er kontoovertagelses-flade.**
Meld den til vedligeholderen, også når den ser rigtig ud.

## Hvor data forlader systemet

- **Open Food Facts** (`app/off.py`): hver scannet EAN sendes til
  `world.openfoodfacts.org` sammen med `OFF_USER_AGENT`, som pr. konvention
  indeholder en rigtig kontaktmail. OFF får dermed en strøm af "denne
  husstand slog denne vare op nu". Det er prisen for varedata, men det er en
  udgående datastrøm, og en ændring, der sender mere end EAN'et, er en
  hændelse — ikke en optimering.
- **Have I Been Pwned** (`app/auth.py`, `CHECK_PWNED_PASSWORDS=1`):
  k-anonymitet — kun de første fem tegn af SHA-1-hashen forlader maskinen.
  Korrekt implementeret; lad være med at "forenkle" det til at sende hele
  hashen.
- **Cloudflare**: al trafik går gennem Tunnel. Der er INGEN Access foran — den ser altså ingen identiteter, og appen kan ikke regne med den.
- **Google Sheets** (`LISTE_URL`): importen henter familiens eget ark. Arket
  committes ALDRIG til git.
- **Produktbilleder fra OFF, hentet af browseren**: `index.html` rendrer
  `p.image_url` direkte, så familiens browser henter billedet fra Open Food
  Facts' egne servere. OFF får dermed BÅDE serverens opslag og et browser-hit
  pr. vist vare — to udgående kanaler, ikke én. Ingen CSP, ingen
  referrer-policy.
- **Logning**: intet personhenførbart må i logs. Stillingen pr. 0.20.0
  (0.20.0 tilføjer ingen `print`/`logger`, og begge Dockerfiles er urørte):
  - Appkoden logger ingenting selv (ingen `logger`/`print` i `app/` eller
    `ocr_service/` uden for `cli.py`).
  - **Adgangsloggen er lukket.** Begge containere starter nu uvicorn med
    `--no-access-log` (`Dockerfile`, `Dockerfile.ocr`). Før skrev den hele
    request-linjen — `GET /api/scan/5701234567890?...&profile_id=1` — altså
    samme fødevaredagbog som `scan`-tabellen, bare uden for databasen og
    uden for backup-modellen.
  - **Ufangede undtagelser er den eneste vej tilbage, og den er stadig
    åben.** SQLAlchemy skriver SQL-parametre i klartekst i tracebacken,
    så en fejlet skrivning kan lægge fritekst- og navnefelter i loggen.
    En `@app.exception_handler(Exception)`, der logger typen og ikke
    `str(e)`, ville lukke den.
  - **De gamle logfiler er der endnu**, og det er et bevidst valg — se
    »Afgjort« nedenfor. `docker-compose.yml` har ingen `logging:`-sektion,
    så json-file-driveren kører uden `max-size`/`max-file`.
  - `app/cli.py`s import printer nu `MISTET: <ean> hørte til «<navn>»` til
    stdout. Uproblematisk kørt i hånden; ikke fra cron i containeren.

## Efterprøvet i orden — så det ikke tages op igen

Målt 23. august 2026 mod en kørende server, anonymt og som hver af de tre
roller, med hvert svar grep'et for seedede navne, mails og stier:

- **Barnets navn er væk.** En base seedet med et navn i `profile.name`
  fik det ryddet til `""` ved næste opstart. Navnet optrådte i intet svar.
- **`scan`-tabellen er væk.** En base med en `scan`-tabel og en række i
  havde ingen `scan`-tabel efter opstart. `DROP TABLE` er idempotent og
  kører hver gang.
- **Ingen anden tabel er en dagbog under et andet navn.** `decided_at`,
  `updated_at`, `fetched_at` og `imported_at` sendes i intet svar.
  `ReviewItem.created_at` er ét tidsstempel pr. vare, kun for indloggede,
  kun bag `require_curator`. Se dog `taget_at` i beholdningen.
- **`/api/profiles` sender præcis `{id, allergens}`** — ingen `name`.
- **`/api/auth/users` sender præcis `{id, email, name, role, active,
  last_login}`** — ingen `password_hash`, `source` eller `household_id`.
  401 anonymt, 403 for contributor OG curator, 200 for admin.
- **`decided_by` sendes ingen steder. `taget_af` sendes ikke til anonyme.**
- **EXIF og GPS overlever ikke et fotoupload** (PIL-genkodningen), og
  **`slet_foto` tager begge filer** — fuldbillede og miniature.
- **`Cache-Control: private`** på fotoruten holder Cloudflare fra at
  cache familiens billeder.
- **HIBP-opslaget sender kun `digest[:5]`** med `Add-Padding: true`.
- **OFF får kun EAN'et.** Efterprøvet mod en loggende stub: URL'en
  indeholder stregkoden og en `fields=`-liste, headeren `OFF_USER_AGENT`
  med kontaktmailen. Intet andet forlader maskinen.
- **`Remote-User`, `Remote-Groups` og `Cf-Access-Authenticated-User-Email`
  ignoreres** — også med `TRUST_PROXY_AUTH=1` og tom
  `TRUSTED_PROXY_HOSTS`. Alt gav 401. Fejler LUKKET.
- **Frontend kalder nu `/api/profiles`** ved hvert login (`refreshAuth()`)
  — den gamle note om, at den aldrig rører ruten, gælder ikke længere.
  `/api/queue` røres stadig ikke.

## På disken

- `data-runtime/` og `DATA_PATH` på serveren: databasen og `billeder/`.
  Gitignoreret. Databasen indeholder domme, brugere og barnets profil —
  den hører hjemme i backup, ikke i git.
- Deklarationsfotos gemmes i op til 4000 px, JPEG q94 **uden**
  farve-underprøvning: de skal kunne LÆSES igen, og subsampling smører
  netop de tynde bogstavstreger ud. Forsiden nøjes med 1600 px. Hvert
  billede har en miniature (480 px) ved siden af. **Sletning skal tage
  begge filer** — en glemt miniature er data, der overlevede en sletning.

## Det, der IKKE findes (læs ikke op mod et fantasifoster)

Ingen fødselsdatoer, adresser, telefonnumre, CPR, betalingsdata, ingen
modellering af værger, ingen deling mellem husstande i praksis, ingen
analytics, ingen tredjeparts-scripts i frontend (fonte hentes dog fra
Google Fonts — det er et udgående kald fra brugerens browser).

## Afgjort — tag det ikke op igen

- **`scan`-tabellen er slettet.** Afgjort 23. august 2026 (0.20.0).
  Fødevaredagbogen — hvad blev slået op, hvornår, for hvilken profil —
  blev skrevet siden 0.1.0 og aldrig læst af noget. Vedligeholderens
  begrundelse: **familien scanner ikke alt, barnet spiser**, så loggen
  kunne aldrig blive fuldstændig nok til at finde en synder efter en
  reaktion. Værre end svag — vildledende: man kigger i den, ser
  ingenting, og konkluderer forkert. En log, man ikke kan stole på, er
  dårligere end ingen log, og den var den mest følsomme rest i basen.
  Tabellen droppes én gang i `init_db()`. Foreslå den ikke igen uden en
  konkret læser og en måde at gøre den fuldstændig på.

- **Barnets navn gemmes ikke længere.** Afgjort 23. august 2026 (0.20.0).
  `Profile.name` sendes ikke i noget svar, sættes ikke ved opstart, og
  den eksisterende værdi overskrives. Headeren viser i stedet, HVAD der
  tjekkes for — en hjælper kan efterprøve en liste, men ikke et navn.
  Bemærk ærligt: det fjerner ikke GDPR helt (domænet bærer et efternavn,
  så husstanden er identificerbar), men det flytter data fra »en
  navngiven journal« til »denne app tjekker for fire ting«.

- **Allergensættet kommer fra serveren for alle indloggede.** Afgjort
  23. august 2026. Før valgte hver browser sit eget i `localStorage`,
  så en hjælper kunne slå de forkerte til og få grønt om noget, appen
  ikke havde kigget efter. Nu kan hun ikke vælge forkert, fordi hun ikke
  vælger. Kun `curator`/`admin` kan ændre sættet, og det gælder alle
  indloggede enheder.

- **De gamle containerlogfiler ryddes ikke.** Afgjort 22. august 2026.
  `--no-access-log` stopper nye linjer; det, der allerede står i
  `docker logs`, bliver stående. Begrundelsen er vedligeholderens:
  det er hans eget barn, på hans egen server, og logfilerne forlader
  den ikke. Kildens rettelse (flaget i begge Dockerfiles) var det, der
  betød noget — oprydningen er et driftsstykke uden modtager.
  Vurderingen ville ændre sig, hvis appen nogensinde deles med en anden
  husstand, eller hvis logopsamlingen sendes ud af maskinen.

## Åbne spørgsmål, ingen har afgjort

Skriv svaret ind her, når vedligeholderen tager stilling — det er dét, der
stopper den samme diskussion hvert kvartal.

- **Gælder GDPR overhovedet?** Rent privat husholdningsbrug er undtaget
  (art. 2, stk. 2, litra c). Men den ene bruger er en **dagplejer**, altså
  en professionel sammenhæng, og datamodellen er bygget til at kunne deles
  med andre familier. Undtagelsen er derfor ikke oplagt. Juridisk
  spørgsmål — meld op, afgør ikke selv.
- **Skal fotos af deklarationer være ubeskyttede?** De er i praksis
  billeder taget i en butik, men ruten er åben for alle, der når appen.
  0.20.0 gør spørgsmålet skarpere: en inviteret `contributor` kan nu
  lægge et billede på den åbne rute, og kun en curator kan fjerne det
  igen. Det er ikke længere kun familiens egen dømmekraft, der afgør,
  hvad der havner på det offentlige.
- **Må en `contributor` overskrive familiens deklarationsfoto?** Hun kan
  i dag (ét foto pr. vare+slags, nyt erstatter gammelt, ingen historik),
  og `taget_af` skifter til hendes navn. Fotoet er dokumentationen bag en
  bekræftelse, så det er en integritetsbeslutning, ikke kun en om adgang.
- **Hvad sker der, hvis en bruger skal fjernes?** Der er ingen sletterute.
  `Verdict.decided_by` og `ProductPhoto.taget_af` er navnestrenge, ikke
  fremmednøgler, så de overlever brugeren.
