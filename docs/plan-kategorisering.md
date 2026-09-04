# Gruppering uden arkrækkerne

Skrevet 4. september 2026, før noget blev bygget. Efterprøvet mod koden;
hver påstand har en fil og et linjenummer eller et målt tal.

## Hvorfor

Arkrækkerne (`imported_product`) er fjernet. Med dem forsvandt hylderne i
søgningen, fordi `Product` ingen kategorikolonne har og hylderne kom fra
regnearkets fanebladsnavne (`kategori=ws.title.strip()`). Se
`docs/plan-hvad-kan-jeg-koebe.md`.

Vedligeholderen vil have grupperingen tilbage, udledt af varens eget navn.

## Vedligeholderens beslutninger, 4. september 2026

1. **Kilderækkefølgen er OFF → Salling → familiens eget navn.** Gratis og
   offentligt først, jeres eget til sidst.
2. **Det manuelle navn må kun komme fra en betroet bruger.** Ordret: »det
   skal nok kun være trusted (brugere der er logget ind der må lave manuelle
   navne)«. Kravet er allerede opfyldt i koden: `POST /api/products/{ean}/navn`
   kræver `require_curator` — ikke engang en bidragyder kan sætte det.
3. **Hele kæden bygges nu**, med de tre strukturelle rettelser nedenfor først.
4. **En mindre model**, ikke Opus. Klassifikation mod en fast liste på ti ord
   er en let opgave, og modelvalget er også misbrugets forstærkningsfaktor:
   prisen pr. misbrugt kald.

## Misbrugsfladen — to ting, der skal være løst FØR noget bygges

Begge er efterprøvet 4. september 2026.

### F1. Nøglen må ikke findes i webprocessen

`docker-compose.yml` har ÉN app-service (`allergiscan`) med `ports:`, og
compose-filens egen header dokumenterer CLI-kørslen som
`docker compose exec allergiscan python -m app.cli …`. Samme container, samme
miljø. Lægges `ANTHROPIC_API_KEY` under den service, står nøglen i miljøet hos
den uvicorn-proces, der besvarer anonyme kald fra internettet.

»Kaldet sker i en CLI-kommando« er en konvention om, hvor koden kaldes fra —
ikke en grænse.

Krav:

- Egen compose-service uden `ports:`, der deler volume og database, og som er
  det ENESTE sted, nøglen er sat.
- En test på importgrafen: kan `app.main` nå klientmodulet, kan en rute kalde
  det. Importér `app.main` og hævd, at modulet ikke er i `sys.modules`.

### F2. Arbejdsmængden må ikke kunne styres udefra

`spaerret()` slås op ÉT sted i hele appen: login-ruten (`main.py`). Der er
ingen rate limit på `GET /api/scan/{ean}`, som er åben uden login og opretter
en `Product`-række for enhver stregkode via `_ensure_product()`.

Angrebet, hvis jobbet arbejder på »alle varer uden kategori«:

1. En fremmed redigerer et varenavn i Open Food Facts. Alle må det, og navnet
   er fri tekst.
2. Han kalder `GET /api/scan/{ean}` mod appen. Rækken står nu i `product` med
   hans tekst i `name`.
3. Jobbet kører senere og betaler for hver række.

Gyldige EAN'er i mængde er gratis — OFF's bulkdump er ~0,9 GB pakket. **En
fremmed bestemmer altså både antallet af kald og deres indhold.**

Krav: arbejdsmængden bindes til varer, **et indlogget menneske har rørt** — en
dom, en post i `ReviewItem`, et foto, eller `navn_manuelt`. Samme afgrænsning
som køen allerede bruger, og af samme grund.

## Invarianter, der skal være KODE, ikke hensigt

- **Ingen værktøjer på kaldet.** Ingen web search, ingen code execution, ingen
  MCP. Det er dét, der holder outputkanalen smal. Med et værktøj er et
  fjendtligt produktnavn ikke længere bundet af, at kun ti ord kan komme retur
  — så kan der ske noget *undervejs*.
- **Én vare pr. kald.** Batching er den oplagte besparelse og den farlige: ét
  fjendtligt navn blandt 50 kan flytte de 49 andres svar.
- **Hårdt loft på inputlængden**, og kontroltegn og linjeskift fjernet. Ikke
  som forsvar mod injektion — det virker ikke — men fordi angriberen ellers
  bestemmer vores tokenforbrug pr. vare. Byg INGEN blokliste over »ignorér
  tidligere instruktioner«: den fanger intet og skaber falsk tryghed.
- **Eksakt medlemskab i den faste liste.** Ingen `startswith`, ingen fuzzy,
  ingen »nærmeste match«. Afvist svar → `kategori` forbliver `NULL`. Fald
  ALDRIG tavst tilbage på »Diverse«: så ligner en fejl et resultat, og ingen
  opdager, at kilden er holdt op med at virke.
- **EAN'et sendes ikke til Anthropic.** Modellen skal bruge navn og mærke for
  at vælge en hylde; stregkoden tilføjer nul præcision og er den eneste
  globalt sammenkædelige nøgle i payloaden. Koblingen holdes lokalt.
- **Kategorien rører ALDRIG en dom.** Den er filtreringslaget, ikke domslaget.
  Det skal være en test. CLAUDE.md kalder netop den sammenblanding den mest
  sandsynlige måde at ødelægge appen på, fordi den ser ud som en oplagt
  forenkling.
- **Logning i tal, ikke navne:** forsøgt / accepteret / afvist / kald brugt.
  Appkoden logger i dag ingenting selv, og det er værd at holde fast i.

## Omkostningsloft

Tre lag, alle tre nødvendige:

1. Loft pr. kørsel i koden.
2. **Akkumuleret** tæller i databasen med en dato. Et loft »pr. kørsel«
   betyder ingenting, hvis jobbet kører på en tidsplan.
3. Spend limit hos Anthropic på en **dedikeret nøgle i sin egen workspace**.
   Det er det eneste loft, der holder, når vores egen kode er forkert — og en
   lækket nøgle rammer så et beløb, ikke en konto.

**Første udgave kører ikke uovervåget.** Kør i hånden, tæl kaldene, se på
resultaterne. Ved ~20 varer er hele arbejdet en håndfuld kald. Tidsplan er en
beslutning, der kan tages senere, på tal.

## Hyldelisten

Ti generiske supermarkedsord, afledt af arkets gamle faneblade: Pålæg,
Bagning, Brød, Ris og pasta, Frugt og grønt, Snacks, Kiks, Drikkevarer,
Mejeri, Diverse.

**Listen skal blive ved med at være generisk.** Arkets ellevte fane hed
»Erstatningsprodukter« — den beskriver husstandens situation frem for maden.
Den skal ikke med tilbage. Listen ender i et PUBLIC repo og i grænsefladen.

## De to slags kilder — arkitekturen, som fundene gør den

Vedligeholderens kæde er OFF → Salling → familiens eget navn. Alle tre er
**navnekilder**. Kategorien kommer ét andet sted fra. Bland dem ikke sammen:

| | Kilder | Rækkefølge |
|---|---|---|
| **Navn** (og mærke) | OFF `product_name_da`/`product_name` → Salling `instore.name` + `description` → `navn_manuelt` | Gratis og offentligt først, familiens eget til sidst |
| **Kategori** | OFF `categories_tags` → modellen, fodret med det bedste navn, kæden fandt | Gratis først, betalt kun for resten |

Det betyder, at Salling ikke fjerner behovet for modellen. Den gør modellens
input bedre for netop de danske varer, OFF ikke kender — og det er dem, hullet
handler om.

## Salling, som den faktisk er

Efterprøvet mod `HA-setup/grocy-to-keep-integration/grocy_lists.py`, hvis
dokumentation er verificeret mod det levende API 13. august 2026.

**Endepunkt:** `GET https://api.sallinggroup.com/v2/products/{ean}` med
`Authorization: Bearer <token>` og `storeId` som parameter. Opslaget er altså
**butiksbundet** — det kræver et butiks-ID, ikke kun en stregkode.

**Svarform:**

```json
{"instore": {"ean": "5710405090951", "name": "KOKOSMÆLK",
             "description": "ASIA KITCHEN", "price": 9.5,
             "contents": 400, "contentsUnit": "ml",
             "unit": "l", "unitPrice": 23.75},
 "webshop": null}
```

`name` er varens navn med VERSALER, `description` er mærket. **Ingen
kategori.** `instore` først, `webshop` som fallback.

**Driftsviden, der allerede er betalt for én gang — genbrug den:**

- **404 er normaltilstanden, ikke en fejl.** Den betyder »den butik fører ikke
  varen«. Behandles den som en fejl, ligner et ærligt ikke-fundet et nedbrud.
- **429 må ikke genforsøges.** Der er en dagskvote bag; genforsøg brænder den
  næste kørsel i stedet for at redde denne.
- **1,5 sekunder mellem kald**, og et loft pr. kørsel (HA-koden bruger 90).
- **GS1-præfikser for andre kæders private label** (`5705830`, `5705001`)
  springes over uden at spørge — Salling fører dem aldrig. Gratis frafiltrering.
- **Negativ caching:** en stregkode, Salling har afvist nok gange, antages ikke
  at være i sortimentet.
- **Nøglen læses fra en miljøvariabel**, ikke fra en fil i repoet.

**Vedligeholderens svar på licensspørgsmålet, 4. september 2026:** caching og
genudstilling er i orden, så længe vi ikke deler mere end de data, vi allerede
deler. Det er dermed en grænse, der skal håndhæves: Salling må ikke udvide,
hvad appen offentliggør.

## Uafklaret — skal besvares, før de dele bygges

- **Salling: AFKLARET 4. september 2026.** Der findes fungerende
  forarbejde i familiens eget HA-repo
  (`HA-setup/grocy-to-keep-integration/grocy_lists.py`), efterprøvet mod det
  levende API 13. august 2026. Se afsnittet »Salling, som den faktisk er«
  nedenfor. Kort: den kan slå op på EAN, men den returnerer **ingen
  kategori**. Den er en navnekilde, ikke en grupperingskilde.
- **Salling er en dansk butikskæde.** Slår vi EAN'er op hos dem, fortæller vi
  en detailkæde, hvilke varer denne husstand kigger på. OFF er anonym
  infrastruktur; Salling er en konkurrent til den butik, familien står i.
- **Licens.** `categories_tags` fra OFF er ODbL. En kategori, en model UDLEDER
  af et ODbL-produktnavn, er noget tredje. `kategori_kilde` holder sporene
  adskilt, hvilket er rigtigt — men om `kategori_kilde='ai'`-rækkerne er
  ODbL-afledte, er et licensspørgsmål. **Meld det op; afgør det ikke i en
  kodesession.**

## Indsigelsen mod at sende familiens eget navn

`data-og-sikkerhed` frarådede at sende `navn_manuelt` til Anthropic. Ikke på
tillid — kun en curator kan skrive det — men på hvad der forlader huset: det er
400 tegns fritekst uden indholdsvalidering, og i dag forlader præcis tre ting
maskinen (EAN'et til OFF, fem tegn af en SHA-1 til HIBP, familiens eget
ark-URL). Ingen af dem er familie-fritekst.

**Vedligeholderen har besluttet at bruge det alligevel**, som tredje og sidste
kilde. Indsigelsen står her, så beslutningen er truffet med åbne øjne og ikke
skal genopdages. Afbødning: hårdt længdeloft, kontroltegn fjernet, intet EAN
med, én vare pr. kald.

`familiens-data`-skillens afsnit »Hvor data forlader systemet« skal opdateres
i samme commit som den kilde bygges — ellers gætter næste session på en liste
med tre modtagere.
