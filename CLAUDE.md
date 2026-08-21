# AllergiScan — kontekst til en kodesession

Læs denne fil før du ændrer noget. Den forklarer *hvorfor* koden ser ud, som
den gør. Flere ting, der ligner overflødig kompleksitet, er der bevidst, og et
par af dem er der, fordi et barn ellers kunne blive syg.

## Hvad appen er til

Et barn tåler ikke mælkeprotein, mælk, æg, jordbær eller banan. Forældrene
står i Netto med en pakke i hånden og skal vide, om den kan spises. De scanner
stregkoden på telefonen og får ét af fire svar.

Brugerne er to voksne: en forælder og en dagplejer. Appen kører på en unRAID-
server derhjemme og nås via Cloudflare Tunnel.

## Invarianten, der ikke må brydes

**Motoren kan gøre en vare rød eller gul. Aldrig grøn.**

`State.FREE` sættes kun ét sted: `POST /api/products/{ean}/confirm`, som
kræver en indlogget bruger. Fandt motoren ingenting, er svaret `UNKNOWN` —
ikke "sikker". Fravær af bevis er ikke bevis for fravær.

Fire tests håndhæver det:
- `test_engine_never_returns_free`
- `test_ocr_mode_still_never_returns_free`
- `test_only_human_confirmation_produces_green`
- `test_unknown_barcode_returns_no_verdicts`

Hvis du står med en ændring, der ville få dem til at fejle, er ændringen
forkert — ikke testene.

## Fem ting, der ser mærkelige ud, men ikke er det

### 1. Maskering med `░` i stedet for at fjerne tekst

`matcher.py` erstatter undtagelser med blokke af *samme længde* i stedet for
at klippe dem ud. Det er for at bevare tegn-offsets, så frontend kan
highlighte præcis det ord, der udløste advarslen. Klipper du i stedet,
peger highlightet på det forkerte sted i lange deklarationer.

### 2. Ordgrænse før mønsteret, men ikke efter

`(?<![a-zæøå])mælk` rammer `mælkepulver` men ikke `kokosmælk`. Dansk
sammensætter ord, og allergenet betyder kun noget, når det står forrest.
Sammensætninger med allergenet bagest (`kærnemælk`, `skummetmælk`) står
eksplicit i `contains`. Fjerner du den lookbehind, bliver kakaosmør til
mejeri, og folk holder op med at stole på appen.

### 3. To pas med forskellig maskering

```
exclude + maybe maskeres  ->  contains-pass   (rød)
exclude maskeres          ->  maybe-pass      (gul)
                          ->  fuzzy-pass      (kun ved OCR)
```

Uden det første ville `jordbæraroma` blive rød på præfikset `jordbær`.
`_mask()` har desuden en `protect`-parameter, så en kort undtagelse
(`mælkesyre`) ikke skygger for et længere maybe-mønster (`mælkesyrekultur`).

### 4. Sporangivelser læses for sig, pr. allergen

"Kan indeholde spor af mælk" er ikke mælk i ingredienslisten, og forskellen
betyder noget: nogle tåler spor, andre gør ikke. `_spor_spans()` finder
teksten fra sporfrasen til punktum (med et loft på 200 tegn, fordi OCR taber
punktummer og ét spor-span ellers kunne sluge resten af listen og gøre et
rigtigt allergen til "kun spor" — under-advarsel er den farlige retning).

Spanet maskeres UD af contains-passet, og allergenets egne mønstre køres så
*inde i* spanet: træf dér giver `TRACE_STATEMENT` (gul), ikke rød. Står
allergenet både i listen og i sporangivelsen, vinder listen.

Nævner spanet mindst ét allergen, vi kender, er den konkret, og de øvrige
allergener rammes ikke. Nævner den intet genkendeligt, får alle
`TRACE_UNSPECIFIED`. Før gjorde enhver sporfrase alle 17 allergener gule —
en app, der råber ulv ved hver vare, holder folk op med at læse.

### 5. Fuzzy-matchning kun på OCR-tekst

Målt: Tesseract læser en dansk deklaration med 89,8 % konfidens og laver
`skummetmælkspulver` om til `skummetmaalkspulver`, `jordbær` til `jordbzer`.
Eksakt matchning missede begge — altså netop de allergener, der stod på
pakken. Derfor foldes æ/ø/å til ASCII og tillades 1-2 redigeringers afvigelse,
men **kun** når `ocr=True`. På ren tekst ville det give falske positiver uden
gevinst.

## To lag, der ikke må blandes sammen

| | `ingredients.py` | `matcher.py` |
|---|---|---|
| Dækning | alle ingredienser | 17 allergener (EU-14 + jordbær, banan, tomat) |
| Præcision | lav, substring | høj, maskeret |
| Fejler mod | overekskludering | overadvarsel |
| Bruges til | finde og filtrere | afgøre sikkerhed |

Filtret siger "uden mælk" og smider også kokosmælk-varen ud. Det er
irriterende, når man browser, og fuldstændig acceptabelt. Regelsættet ville
aldrig gøre det. **Lad aldrig filtreringslaget producere en dom** — det er den
mest sandsynlige måde at ødelægge appen på, fordi det ser ud som en oplagt
forenkling.

## Sikkerhed: hvorfor Cloudflare Access valideres kryptografisk

Med Tunnel går trafikken direkte til containeren; der er ingen proxy til at
strimle headere. Havde vi stolet på `Cf-Access-Authenticated-User-Email`,
kunne enhver med netværksadgang til containeren sætte den selv.

`cfaccess.py` validerer derfor JWT-signaturen i `Cf-Access-Jwt-Assertion` mod
Cloudflares offentlige nøgler og tjekker `aud`. Det kan ikke forfalskes.

`TRUST_PROXY_AUTH=1` (header-baseret) er kun sikkert bag en proxy, der
strimler `Remote-*` — se `deploy/Caddyfile.example`. Default er 0.
Der er tests for at begge headere ignoreres, når de ikke er beviste.

## Arkitektur

```
app/
  main.py         FastAPI-ruter
  matcher.py      allergen-regelmotoren    <- den sikkerhedskritiske
  ingredients.py  bredt ingrediensindeks   <- den upræcise
  auth.py         sessioner, argon2, HIBP, proxy/Access-identitet
  cfaccess.py     Cloudflare Access JWT-validering
  ocr.py          Tesseract + forbehandling  <- nu FALDSKÆRM, ikke hovedvej
  ocr_klient.py   kalder OCR-containeren, falder tilbage til ocr.py
  off.py          Open Food Facts-klient
  models.py       SQLAlchemy
  db.py           SQLite eller Postgres
  cli.py          adduser, reindex
  static/         PWA (én HTML-fil, ingen build)
ocr_service/main.py   OCR i EGEN container (rapidocr/PP-OCRv6)
data/allergens.yaml   reglerne — mountes read-only, redigeres uden rebuild
```

**OCR er delt i to med vilje.** `ocr_service/` er en dum tjeneste: pixels
ind, tegn ud. Den kender intet til dansk orddannelse, allergener eller
domme — al betydning lægges på i appen (`efterbehandl()` i `ocr.py`,
reglerne i `matcher.py`). Grunden er dobbelt: `onnxruntime` er native
kode, som ikke må kunne tage web-appen og databasen med sig i et
segfault, og sikkerhedslogikken skal bo ét sted.

Målt på 40 af familiens egne butiksfotos: 2,8× så mange rigtige danske
ord som Tesseract, 6× hurtigere, nul tabte allergener. De tre steder,
hvor Tesseract fandt et allergen, den nye motor ikke fandt, var alle
falske positiver fra fuzzy-matchning på grafikstøj — efterprøvet mod
etiketterne. Tesseract er beholdt som faldskærm, fordi OCR er
hovedvejen: OFF kender kun ~10 % af familiens varer med ingrediensliste.

Frontend er bevidst én fil uden byggetrin. Der er ingen node_modules, ingen
bundler, intet at holde opdateret. `zxing-wasm` er vendoret i
`static/vendor/zxing/`, fordi Safari mangler `BarcodeDetector`.

## Datamodel: to detaljer der bærer meget

**Domme hænger på parret (produkt, allergen)**, ikke på produktet. Tilføjes
soja i morgen, står de eksisterende godkendelser for mælk og æg uændret.

**Hver dom gemmer `ingredients_hash`.** Ændrer producenten opskriften på samme
EAN, matcher hashen ikke, dommen markeres `stale`, og varen ryger i køen.
Det er den eneste automatiske beskyttelse mod stille opskriftsændringer.

**`product` er ODbL-afledt, `verdict` er brugerens eget arbejde.** De ligger i
separate tabeller, så share-alike ikke smitter af på verifikationsarbejdet.
Bland dem ikke sammen. Se `NOTICE.md`.

**`imported_product` er familiens gamle regneark** — deres egne hyldenavne,
og 583 varer uden stregkoder. Den er en tredje tabel af samme grund:
den er hverken OFF's data eller en dom. I appen er den ÉN liste sammen med de
scannede varer (`/api/soeg` slår dem sammen i visningen, ikke i data).

**`product_photo` er jeres billeder** af forside og deklaration. Selve
filerne ligger på disken under `DATA_DIR/billeder`, ikke som blobs i
databasen — så de følger med backuppen af appdata, og databasen bliver
ved med at være lille nok til at kopiere. Ét billede pr. (vare, slags);
et nyt erstatter det gamle. Et foto er dokumentation, ikke bevis: det
gør ingen vare grøn.

Deklarationsfotos gemmes i op til 4000 px og JPEG q94 uden
farve-underprøvning: de skal kunne LÆSES igen, og subsampling smører
netop de tynde bogstavstreger ud. Forsiden nøjes med 1600 px. Hvert
billede får en miniature (480 px) ved siden af — uden den ville listen
hente flere MB fuldbillede over mobildata. Sletning skal tage begge
filer. `FOTO_MAX_DEKLARATION`/`FOTO_MAX_FRONT` kan skrue på det.

`imported_product.ean` er koblingen, der giver en række værdi: uden EAN kan
den aldrig bære en dom. Den sættes kun af et menneske
(`POST /api/liste/{id}/stregkode`, kræver login) og er **ikke** en dom — en
koblet række bliver ikke grøn af det. Er koblingen sat, slår den alle
navnegæt; er den ikke, arves kun kategori, og kun ved to fælles ord.

Arkets butikskolonne er FJERNET (0.18.0). Butik er ikke data, appen får om
fremtidige varer — en scannet vare har ingen — så et butiksfilter ville
skjule mere og mere, jo flere varer familien scanner. Samme prøve gælder
alt andet, arket måtte kunne: kan en scannet vare også have det?

## Kør og test

```bash
pip install -r requirements.txt
DATA_DIR=./data-runtime RULES_PATH=./data/allergens.yaml COOKIE_SECURE=0 \
  uvicorn app.main:app --reload

pytest tests/ -q          # 256 tests, 5 springes over uden Tesseract-dansk
python -m app.cli adduser dig@example.dk "Navn"
```

Tesseract med dansk sprogmodel skal være installeret, ellers fejler
OCR-stien: `apt install tesseract-ocr tesseract-ocr-dan`.

## Versionering og release notes — fast del af enhver ændring

Enhver brugervendt ændring — funktion eller rettelse — skal, i samme commit:

1. Bumpe `VERSION` i `app/version.py`. Semantisk: MAJOR ved brud, MINOR
   ved ny funktionalitet, PATCH ved rettelser.
2. Have en dateret post ØVERST i `CHANGELOG.md`, skrevet til de to
   voksne, der bruger appen — hvad betyder det for dem i Netto, ikke
   hvad der skete i koden.

Footeren i appen viser version og »Nyheder« automatisk; frontend skal
ikke røres. `tests/test_version.py` fejler, hvis `VERSION` mangler sin
post i changeloggen — de to følges ad, uden undtagelser.

## Agentroller

`.claude/agents/` definerer projektets underagenter. Rutningen er ikke
kosmetisk — den findes, fordi ét område i denne kodebase kan gøre et barn
sygt, og resten ikke kan:

| Agent | Område |
|---|---|
| `allergen-domaene` | **alt der kan ændre en dom**: `matcher.py`, `allergens.yaml`, OCR-efterbehandlingen |
| `implementer` | alt andet i appen; sender domsnære opgaver videre |
| `kodegennemgang` | den eneste gennemgang, før noget pushes til main |
| `testkoerer` | `pytest tests/ -q`, rapporterer kun fejl |
| `produktejer` | presser omfanget, skriver historier med acceptkriterier |
| `ux-gennemgang` | grænsefladen op mod en forælder med én hånd fri i Netto |
| `data-og-sikkerhed` | barnets data, adgangsmodellen, hvad der forlader systemet |
| `udgivelse` | versionsbump, changelog, risici — pusher aldrig selv |
| `Explore` | hurtig, læsende søgning (haiku) |

Viden bor i `.claude/skills/`: `allergen-regler` (motorens efterprøvede
mekanik), `ocr-deklarationer` (de to OCR-motorer, spaltelæsningen,
efterbehandlingen og de målte tal), `familiens-data` (persondata og
adgang), `designsystem` (de fire domme, tokens, copy-regler). **Ændrer du
mekanikken, ændrer du skillen i samme commit** — ellers gætter næste
session på noget, der ikke er sandt.

Rutningskommandoer i `.claude/commands/`: `/tjek`, `/regel`, `/ux`, `/data`,
`/afklar`, `/udgiv`, `/foer-udgivelse`.

To vagter i `scripts/`:

- `vagt-groen.sh` er registreret i frontmatter på `allergen-domaene` og
  `implementer` — de to agenter, der kan ændre en dom. **I hovedsessionen
  kører den kun, hvis du selv registrerer den** i `.claude/settings.json`
  (se `settings.json.forslag`); den fil er maskinlokal og ligger ikke i
  repoet. Vagten fanger to ting, der peger den farlige vej: en ny grøn dom uden for bekræftelsesruten, og et regelsæt der
  er blevet blødere (færre `contains`, flere `exclude`). Den beviser ingen
  fejl — den beder om en begrundelse.
- `vagt-udgivelse.sh` (PreToolUse på Bash, kun i `udgivelse`-agenten)
  blokerer push, tag, merge og deploy. Push til main ER deploy, og det trin
  hører til hovedsessionen med et menneske, der kigger med.

## Sprog

Kode, kommentarer, commits og UI er på dansk. Ingredienslisterne er danske,
og reglerne handler om dansk orddannelse — engelsk ville gøre koden sværere
at læse, ikke lettere. Behold det.
