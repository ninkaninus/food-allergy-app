---
name: familiens-data
description: Hvilke persondata AllergiScan gemmer, hvorfor, hvor længe, og hvem der kan se dem — plus hvor data forlader systemet. Slå op ved enhver ændring i models.py, adgangsmodellen, fotos, importen, logning eller kald til tredjepart.
---

# Persondata i AllergiScan

Efterprøvet mod `app/models.py`, `app/auth.py`, `app/main.py`, `app/off.py`,
`Dockerfile`, `Dockerfile.ocr`, `docker-compose.yml` og
`app/static/index.html` 21. august 2026 (efter 0.19.0). **UKENDT** betyder, at ingen har taget
stilling — det er en to-do-liste, ikke felter, der skal fyldes med gæt.

## Det, der gør dette projekt særligt

Databasen indeholder **et navngivet barns helbredsoplysninger**. Et
`Profile`-navn plus rækkerne i `profile_allergen` er "hvad reagerer dette
barn på" — særlig kategori efter GDPR art. 9, og barnet er mindreårigt.
`scan`-tabellen er samtidig en fødevaredagbog: hvad blev slået op, hvornår,
for hvem.

Det er ikke en grund til at gøre appen tungere. Det er grunden til, at
"det ligger jo bare på vores egen server" ikke er et argument, der holder,
hvis noget først forlader den.

## Beholdning

| Felt | Formål | Opbevaring | Hvem kan se det |
|---|---|---|---|
| `Profile.name` | Barnets navn i UI'et ("Tjekker for <barnets navn>") | UKENDT — ingen sletterute | **Kun indloggede** siden 0.19.0 (`/api/profiles` + `/api/scan`) |
| `ProfileAllergen.allergen_id/severity/active` | Hvad barnet ikke tåler — hele appens formål | Lever med profilen | **Kun indloggede** — en fremmeds opslag vurderer alle 17, så svaret ikke røber de fire |
| `Scan` (ean, result, profile_id, scanned_at) | Log: "hvornår gav vi hende den her sidst?" | UKENDT — ingen udløb, ingen oprydning | Ingen UI-visning. Skrives siden 0.19.0 KUN for indloggede — før skrev enhver på internettet i den |
| `User.email` | Login-identitet; nøglen der matcher proxy-/Access-identitet | UKENDT | Andre brugere via `/api/auth/me`? Nej — kun egen. Ellers: den, der har databasen |
| `User.name` | Gemmes som `decided_by` på domme | UKENDT | **Ingen udefra** — `decided_by` sendes ikke i noget svar (efterprøvet mod live) |
| `User.password_hash` | argon2id. NULL, når brugeren kun kommer ind via proxy/Access | Lever med brugeren | Ingen (hash) |
| `User.role`, `source`, `active`, `last_login` | Adgangsstyring og drift | Lever med brugeren | Den, der har databasen |
| `SessionToken.token_hash` | Kun sha256 af cookien gemmes — tabellen er værdiløs, hvis den lækker | UKENDT. `expires_at` (default 30 dage, `SESSION_DAYS`) er GYLDIGHED, ikke opbevaring: rækken slettes aldrig. Kun `revoke_session()` ved eksplicit logout fjerner én, og der er ingen oprydning af udløbne | Ingen |
| `SessionToken.user_agent` | Enhedsfingeraftryk; kunne bruges til "log andre enheder ud" | UKENDT — samme som token_hash ovenfor | Den, der har databasen |
| `Verdict.decided_by`, `decided_at`, `note` | Hvem bekræftede hvad hvornår — sporbarhed på en sikkerhedsafgørelse | Indefinit med vilje: dommen ER arbejdet | Alle, der læser en vare |
| `ImportedProduct` (navn, producent, kategori, **valideret_mod**, ean) | Familiens gamle regneark, 583 varer | Erstattes ved genimport | **Offentligt** via `/api/soeg` og `/api/scan` — det ER opslagsværket. Bemærk: `valideret_mod` er en konstant (»æg, mælk, tomat og banan«) på ~583 rækker, altså barnets allergensæt udledt af gentagelsen. Det er uadskilleligt fra at publicere bekræftelserne. `link` og `erstatning_for` importeres, men udstilles ingen steder |
| `ProductPhoto` + filerne under `DATA_DIR/billeder` | Jeres egne fotos af forside og deklaration | Ét pr. (vare, slags); nyt erstatter gammelt. Ingen historik | **Offentligt — bevidst.** Fotoet af deklarationen ER dokumentationen bag en bekræftelse. Prisen: stregkoder kan opremses, og billederne er taget i familiens køkken og i butikker. Står som `test_fotoruten_er_bevidst_offentlig`; lukkes med én dependency |
| `ProductPhoto.taget_af` | Hvem tog billedet | Lever med billedet | **Ingen udefra** — sendes ikke med i `/api/soeg`. UBESLUTTET: selve billedfilerne er stadig offentlige |
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

| Offentligt (skal blive ved med at være det) | Kræver login |
|---|---|
| `GET /api/scan/{ean}` — dommen* | `GET /api/profiles` — barnets navn og allergener |
| `GET /api/soeg` — listen | `GET /api/queue` — scan-historikken |
| `GET /api/products` | `GET /api/diagnostik` — serverdetaljer |
| `/api/allergens`, `/api/version`, `/api/changelog`, `/api/attribution` | alt skrivende (`require_curator`) |
| `/`, `/static`, `/healthz` | `/docs`, `/redoc`, `/openapi.json` (slået helt fra) |

\* **`GET /api/scan` svarer FORSKELLIGT alt efter, om der er en bruger.**
For familien: barnets profil følger med (`profile: {id, name}`), og kun
barnets aktive allergener vurderes. For en fremmed: `profile` er `null`,
og ALLE 17 vurderes. Det sidste er ikke kosmetik — faldt svaret tilbage
på profilen, ville selve dets LÆNGDE røbe, hvilke fire allergener barnet
reagerer på, uden at nogen havde spurgt.

Indtil 0.19.0 lå de tre i højre kolonnes øverste rækker **åbne på
internettet** — og `GET /api/scan` sendte barnets navn og de fire aktive
allergener med i svaret, hvis man blot undlod `?allergens=`. Begge dele
er efterprøvet mod det live site 2026-08-21. Det er helbredsoplysninger
om et navngivet, mindreårigt menneske (GDPR art. 9).

Det her er stadig den vigtigste enkeltkendsgerning i filen.

Også offentligt, men mindre følsomt: `/api/ingredients/suggest`
(familiens eget ingredienskorpus, afledt af hvad de har scannet),
`/api/attribution`, `/api/auth/me` (kun egen bruger).

**`GET /api/scan/{ean}` skriver stadig — men ikke om fremmede.** Ruten er
åben (det er hele pointen) og opretter `ReviewItem`- og `Product`-rækker
for alle. Fra 0.19.0 gælder derimod:

- `Scan`-rækken (dagbogen) skrives **kun for en indlogget bruger**. Før
  skrev enhver på internettet i den.
- `profile_id` fra query-strengen **ignoreres**. Før blev den slået op
  uden at tjekke husstanden, så kalderen selv valgte, hvilket barn linjen
  blev skrevet på.
- `?refresh=true` **kræver login**. Før kunne en ulogindet kalder tvinge
  et udgående Open Food Facts-kald pr. request.

- **Køen føres kun for indloggede.** En fremmeds opslag lægger ikke
  noget i bekræftelseskøen og kan ikke genåbne en post, familien har
  lukket. `created_at` bevares ved genåbning, så en vare, der køes igen
  ved hver scanning, ikke hopper til toppen.

- **`gemt: bool` i scan-svaret** siger, om opslaget blev ført i køen og
  dagbogen. Frontend viser en linje, når det er `false` — ellers ville
  familien selv miste kø-poster i tavshed, når deres session var udløbet.

Åben bivirkning, der står tilbage og er accepteret: **produktcachen kan
pumpes op udefra**, og et opslag på en ukendt stregkode koster ét kald
til Open Food Facts. Det er prisen for, at værktøjet er åbent.

Alt andet skrivende kræver `require_curator`; brugeroprettelse
`require_admin`; familiens egne visninger `require_user`.

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
- **Logning**: intet personhenførbart må i logs. Stillingen pr. 0.19.0:
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
  - **De gamle logfiler er der endnu.** `--no-access-log` virker
    fremadrettet; alt, der allerede står i `docker logs`, ligger uændret.
    `docker-compose.yml` har ingen `logging:`-sektion, så json-file-driveren
    kører uden `max-size`/`max-file` — intet er nogensinde roteret væk.
  - `app/cli.py`s import printer nu `MISTET: <ean> hørte til «<navn>»` til
    stdout. Uproblematisk kørt i hånden; ikke fra cron i containeren.

## Efterprøvet i orden — så det ikke tages op igen

Målt 21. august 2026 mod en kørende server:

- **EXIF og GPS overlever ikke et fotoupload.** PIL-genkodningen dropper
  dem. Et billede med GPS-IFD ind, tomt EXIF ud.
- **`Cache-Control: private`** på fotoruten holder Cloudflare fra at
  cache familiens billeder.
- **`slet_foto` tager begge filer** — fuldbillede og miniature.
- **`decided_by` og `taget_af` sendes ikke til anonyme.**
- **Frontend rører aldrig `/api/profiles` eller `/api/queue`**, så
  login-gatingen af dem knækker ingen skærm.
- **HIBP-opslaget sender kun `digest[:5]`** med `Add-Padding: true`.

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

## Åbne spørgsmål, ingen har afgjort

Skriv svaret ind her, når vedligeholderen tager stilling — det er dét, der
stopper den samme diskussion hvert kvartal.

- **Gælder GDPR overhovedet?** Rent privat husholdningsbrug er undtaget
  (art. 2, stk. 2, litra c). Men den ene bruger er en **dagplejer**, altså
  en professionel sammenhæng, og datamodellen er bygget til at kunne deles
  med andre familier. Undtagelsen er derfor ikke oplagt. Juridisk
  spørgsmål — meld op, afgør ikke selv.
- **Hvor længe skal `scan`-loggen leve?** Den vokser uden loft og er den
  eneste tabel, der beskriver barnets faktiske indtag over tid.
- **Skal fotos af deklarationer være ubeskyttede?** De er i praksis
  billeder taget i en butik, men ruten er åben for alle, der når appen.
- **Hvad sker der, hvis en bruger skal fjernes?** Der er ingen sletterute.
  `Verdict.decided_by` og `ProductPhoto.taget_af` er navnestrenge, ikke
  fremmednøgler, så de overlever brugeren.
