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

## Uafklaret — skal besvares, før de dele bygges

- **Salling: kan API'et overhovedet det, vi har brug for?** Bekræftet: gratis,
  kræver egen bruger og accept af vilkår, loft på 1.000 kald/dag, søgning på en
  query-streng. IKKE bekræftet: om det kan slå op på EAN, og om det returnerer
  en kategori. Dokumentationen ligger bag login. Kan den kun søge på navn uden
  at give en kategori, er den ikke en grupperingskilde — så er den kun en
  ekstra navnekilde.
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
