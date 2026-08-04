# Licenser og kreditering

## Den vigtigste skelnen

ODbL skelner mellem den **afledte database** og et **produceret værk**.
Skemaet holder de to fra hinanden med vilje:

| Tabel | Hvad | Licens |
|---|---|---|
| `product`, `ingredient`, `product_ingredient` | Cache af Open Food Facts | **afledt database → ODbL 1.0** |
| `verdict`, `review_item`, `scan`, `profile` | Jeres egne domme og noter | **jeres eget arbejde** |

Hvorfor det betyder noget: deler I nogensinde databasen — med andre
allergiforældre, som eksport, som et offentligt site — udløser ODbL's
share-alike kun på produkt-cachen. Jeres 400 timers manuelle
verifikationsarbejde er jeres eget og kan licenseres som I vil.
Havde de to ligget i samme tabel, ville den skelnen være umulig at føre.

## Datakilder

### Open Food Facts — ODbL 1.0

- <https://openfoodfacts.org> · <https://opendatacommons.org/licenses/odbl/1-0/>
- Dækker: produktnavne, mærker, mængder, ingredienslister, allergen-tags,
  spor-tags, ingrediens-taksonomi.
- **Krav I skal opfylde:**
  1. **Kreditering.** Appen viser "Produktdata fra Open Food Facts (ODbL)"
     i bunden af hver domsskærm, og `GET /api/attribution` returnerer
     den fulde erklæring med antal poster.
  2. **Share-alike.** Distribuerer I en afledt database offentligt, skal
     den under ODbL 1.0.
  3. **Ingen teknisk spærring.** Deler I den, må den ikke være DRM-låst.
- Til privat brug i én familie udløses krav 2 og 3 ikke. Krav 1 gælder altid.
- **God skik:** retter I en fejl i en dansk deklaration, så ret den også
  hos Open Food Facts. Det er sådan dækningen bliver bedre for alle,
  og det er billigere end at gøre det to gange.

### Produktbilleder fra Open Food Facts — CC BY-SA 3.0

Billeder har en anden licens end data. De vises via OFF's egne URL'er
og hotlinkes, altså gemmes ikke lokalt. Gemmer I dem, skal fotografen
krediteres og billedet deles under samme licens.

### Have I Been Pwned, Pwned Passwords

Bruges til at afvise genbrugte adgangskoder. Frit tilgængeligt API.
Kun de første fem tegn af SHA-1-hashen sendes; adgangskoden forlader
aldrig maskinen. Kan slås fra med `CHECK_PWNED_PASSWORDS=0`.

## Software

| Komponent | Licens | Note |
|---|---|---|
| zxing-wasm 2.2.4 | MIT | Vendoret i `app/static/vendor/zxing/` med licensfil. Ikke CDN. |
| Tesseract OCR | Apache 2.0 | Fra Debian-pakke i imaget |
| tesseract-ocr-dan | Apache 2.0 | Dansk sprogmodel |
| FastAPI, Starlette | MIT | |
| SQLAlchemy | MIT | |
| Pydantic | MIT | |
| httpx | BSD-3-Clause | |
| Pillow | MIT-CMU (HPND) | |
| pytesseract | Apache 2.0 | |
| argon2-cffi | MIT | |
| PyYAML | MIT | |
| **psycopg 3** | **LGPL-3.0** | Se nedenfor |
| Archivo, Public Sans, JetBrains Mono | SIL OFL 1.1 | Se nedenfor |

### psycopg og LGPL

psycopg 3 er LGPL-3.0. Det er uproblematisk her: den installeres som en
separat pakke og importeres dynamisk, hvilket LGPL udtrykkeligt tillader
uden at smitte af på jeres kode. Vil I helt undgå spørgsmålet, så kør på
SQLite — den er default, og `psycopg` bliver aldrig importeret.

### Fonte

Prototypen henter Archivo, Public Sans og JetBrains Mono fra Google Fonts.
Alle tre er SIL OFL 1.1 og må hostes selv. **Gør det** — både fordi appen
så virker i en kælderbutik uden dækning, og fordi det fjerner et
tredjepartsopslag pr. sidevisning. Læg `.woff2`-filerne i
`app/static/vendor/fonts/` sammen med `OFL.txt` og ret `@font-face`.

## Ansvarsfraskrivelse

Appen er et hjælpeværktøj, ikke en medicinsk anordning. Data fra Open Food
Facts er brugerbidraget og hverken fuldstændig eller garanteret korrekt.
Producenter ændrer opskrifter uden at skifte stregkode. Læs altid etiketten.
