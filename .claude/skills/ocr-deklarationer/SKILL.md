---
name: ocr-deklarationer
description: Hvordan AllergiScan læser en varedeklaration af et foto — de to motorer, spaltelæsningen, redningsforsøgene, efterbehandlingen og de målte tal. Slå op før enhver ændring i ocr_service/, app/ocr.py, app/ocr_klient.py eller fotoruterne.
---

# OCR af varedeklarationer

Efterprøvet mod koden 21. august 2026 (efter 0.19.0). **Ændrer du
pipelinen, ændrer du denne fil i samme commit.**

## Hvorfor OCR er hovedvejen, ikke en nødløsning

Open Food Facts kender kun omkring **10 %** af familiens varer *med*
ingrediensliste. For resten er et foto af deklarationen den eneste vej til
et svar. Alt, hvad der gør fotovejen tungere eller mere upålidelig, rammer
9 ud af 10 varer — ikke kanten.

Det er også grunden til, at OCR-kvalitet er en sikkerhedssag og ikke en
finpudsning: taber læsningen ordet »skummetmælkspulver«, siger appen »Ved
det ikke« om en vare med mælk i.

## Vejen fra tryk til tekst

```
#ocrBtn (index.html)
  -> POST /api/ocr              app/main.py  (require_curator, def — ikke async)
     -> laes_deklaration()      app/ocr_klient.py
        -> POST {OCR_URL}/ocr   ocr_service/main.py   <- hovedvejen
        -> read_declaration()   app/ocr.py            <- faldskærm
     -> efterbehandl()          app/ocr.py            <- BETYDNINGEN lægges på her
     -> RULES.evaluate(..., ocr=True) for alle 17     <- kun til "efterse dette"
  -> bekræftelsesskærmen, hvor et menneske retter teksten
```

**Motoren afgør aldrig noget her.** OCR-resultatet lander som redigerbar
tekst; dommen opstår først, når et menneske trykker »Gem dom«. Se
`allergen-regler`-skillen for invarianten.

## To containere med vilje

`ocr_service/` er en **dum tjeneste**: pixels ind, tegn ud. Den kender
intet til dansk orddannelse, allergener eller domme. Tre grunde, som står
i filens egen docstring:

1. `onnxruntime` er native kode — et segfault må ikke tage web-appen og
   databasen med.
2. Modellerne fylder ~800 MB; app-imaget skal blive ved med at være
   hurtigt at rulle ud.
3. OCR er CPU-tungt og kan begrænses for sig (`OCR_THREADS`, `OCR_CPUS`).

App og OCR-image ruller altid ud som ét par, tagget med samme commit-sha
(`deploy/autodeploy.sh` kræver begge, før den rører noget).

**Læg aldrig betydning i tjenesten.** Ingen allergener, ingen
sektionsudklipning, ingen dansk orddannelse. Sikkerhedslogikken bor ét sted.

## Hovedvejen: `ocr_service/main.py` (rapidocr / PP-OCRv6)

- `RapidOCR` indlæses **dovent** i `engine()` — containeren skal svare på
  `/healthz` med det samme. `/klar` siger, om modellerne er inde; første
  kald koster ~5 s ekstra.
- EXIF-rotation rettes (`ImageOps.exif_transpose`) — telefoner gemmer
  stående billeder liggende. PP-OCR klarer selv tekst på tværs, så der er
  **ingen OSD-gymnastik** her, i modsætning til Tesseract-vejen.
- Nedskalering til `MAX_SIDE = 3200`. Loft på uploadet: 12 MB.
- Svaret er `text` (linjer adskilt af `\n`), `confidence` (0-100, middel af
  linjescores), `linjer`, `engine`, `sekunder`.

### `i_spalter()` — det vigtigste i tjenesten

Etiketter har næsten altid flere spalter, og OCR'en returnerer bokse
sorteret efter position. Uden spaltelæsning flettes venstre og højre
spalte linje for linje:

```
«Ingredienser:»          venstre
«højst +5 °C.»           HØJRE, flettet ind
«93 % grisekød, salt,»   venstre
```

Efter den fletning kan appen hverken finde begyndelsen eller slutningen på
ingredienslisten. Algoritmen:

- Spalter findes som **huller i boksenes x-midtpunkter**, ikke ved et fast
  lodret snit — skævt fotograferede etiketter driver vandret ned ad
  billedet.
- Linjehøjden måles som **venstre kants længde**, ikke boksens højde: en
  hældende boks er målt 103 px for en linje på 89.
- Et hul tæller, hvis det er både `2.5 × median_linjehøjde` **og**
  `0.12 × etiketbredde`. Kun det første ville splitte ernæringstabellers
  etiket/værdi-par; kun det andet misser smalle etiketter.
- `side_om_side()` kræver mindst 40 % lodret overlap — ellers er det ét
  afsnit over et andet, og et lodret snit ville stumpe teksten.
- Højst tre spalter (`dybde >= 2`), mindst 3 linjer i hver.

Er der intet tydeligt hul, er det én spalte, og rækkefølgen står som den er.

## Faldskærmen: `app/ocr.py` (Tesseract)

Bruges kun, når tjenesten ikke svarer (`_fra_tjeneste()` returnerer `None`
ved timeout, fejl, `ok: false` eller tom tekst). Frontend får det at vide
gennem `engine` og en tilføjet hint.

**`apt install tesseract-ocr tesseract-ocr-dan`** — uden den danske
sprogmodel læses danske deklarationer som forvrænget engelsk, og
OCR-testene bliver meningsløse.

Kæden i `read_declaration()`:

1. **`_grayscale()`** — EXIF-rotation, gråtoner, normalisering mod ~300 dpi
   (op hvis under 2200 px, ned hvis over 3200), `autocontrast(cutoff=2)`.
2. **`_binarize()`** — **adaptiv lokal tærskel** i ren PIL: hver pixel mod
   sit lokale gennemsnit (BoxBlur, radius `max(15, side/90)`), tærskel 12
   gråtoner under. Målt mod global Otsu på fotos med lysgradient og
   glansplet: **Otsu 26-42 % konfidens og volapyk, lokal tærskel 86-93 %
   og næsten fejlfri**. På jævnt lys er de ens (~94 %).
3. **`_candidates()`** — prøver begge polariteter (mange danske poser har
   lys tekst på mørk bund).
4. **`_reconstruct()`** — samler ord over konfidenstærsklen i læseorden,
   linjeskift ved ny block/par/line. Grafik og folder bliver til
   lav-konfidens vrøvleord og filtreres væk.
5. **OSD-rotation, hvis konfidens < 65.** Målt på pølser i mørk pose med
   etiketten på langs: uden rotation suppe (38 %), med rotation 73 %.
6. **To-pas-redning, hvis konfidens stadig < 65.** `_find_declaration_crop()`
   → `_crop_ved_markoer()` finder ordet »Ingredienser« fuzzy i ordlisten og
   beskærer til blokken; genlæses med `psm 4` (én spalte) og **tærskel 10**
   — et tabt allergenord er dyrere end et vrøvleord, mennesket alligevel
   ser. Målt på lys tekst på mørkerød pose: 28 % → 72 %, inklusive
   `bananchips* (banan*`, som er dét, matcheren skal se.

## `efterbehandl()` — hvor betydningen lægges på

Deles af begge veje. Kalder `extract_section()` og `clean()` og returnerer:

| felt | betydning |
|---|---|
| `text` | sektionen, eller hele den rensede råtekst hvis udklippet blev tomt |
| `raw` | hele den rensede tekst — det, »Vis hele teksten« viser |
| `found_section` | blev der faktisk klippet? **Beregnes, men bruges ingen steder** |
| `confidence` | motorens eget tal |
| `hint` | under 65: »tag et nyt billede tættere på, uden glans« |

**`_spor_omraader()` afgrænser ikke kun på punktum, linjeskift og 200
tegn, men også på `SECTION_MARKERS`** (0.19.0). En sporsætning indeholder
aldrig »Ingredienser:« — uden den grænse kunne området løbe fra
sporfrasen og hen over deklarationen, når OCR havde tabt punktummet, og
så blev en RØD vare gul. Matcheren har den samme grænse i `SEKTIONSORD`.

`extract_section()` er sikkerhedskritisk, selvom det ligner formatering —
se `allergen-regler`-skillen for de tre værn (spor fra begge sider,
`_klippet_forkert()` med sit komma-loft og stærk-markør-regel, og
spor-bagest når udklippet kasseres).

`clean()` retter det, Tesseract gør systematisk: `|` → `l`, bløde
bindestreger, linjeskift midt i en liste, orddeling over linjeskift
(**kun små bogstaver** — VERSALE deklarationer med `JORD-\nBÆR` slipper
igennem, kendt hul), dobbelte kommaer.

## Porten i `main.py`

```python
if res.get("engine") != "rapidocr" and res["confidence"] < 45:
    res["allergens"] = []      # motoren køres slet ikke
```

Kun Tesseract-vejen har porten — rapidocr's scores er ikke sammenlignelige.
Bemærk at `[]` er **truthy i JavaScript**; frontend skal skelne på
`d.allergens?.length`, ellers påstår den, at motoren ikke fandt noget, om
en kørsel der aldrig skete.

Ellers køres alle 17 allergener med `ocr=True` (fuzzy-tolerance), og
resultatet vises som »Efterse på pakken« — aldrig som en dom.

## Fotos på disken

`POST /api/products/{ean}/foto` (`require_curator`, `def` — ikke `async`,
så PIL ikke blokerer event-loopet).

- Deklaration: op til **4000 px**, JPEG **q94**, `subsampling=0` — de skal
  kunne LÆSES igen, og farve-underprøvning smører netop de tynde
  bogstavstreger ud. `FOTO_MAX_DEKLARATION`.
- Forside: 1600 px, `FOTO_MAX_FRONT`.
- Hvert billede får en **miniature på 480 px** (q78) ved siden af — uden
  den henter listen flere MB fuldbillede over mobildata. **Sletning skal
  tage begge filer.**
- Filerne ligger under `DATA_DIR/billeder`, ikke som blobs i databasen.

## Målte tal (rapidocr mod Tesseract, 40 af familiens egne butiksfotos)

- **2,8×** så mange rigtige danske ord
- **6×** hurtigere (2 s mod 9 s)
- **nul** tabte allergener
- De tre steder, hvor Tesseract fandt et allergen, rapidocr ikke fandt, var
  **alle falske positiver** fra fuzzy-matchning på grafikstøj — efterprøvet
  mod de fysiske etiketter.

## Sådan måler du en ændring

Der ligger kun **ét** rigtigt foto i `data-runtime/billeder/`
(`3017620422003_deklaration.jpg`). Et regelsæt eller en pipeline testet mod
opdigtet tekst er ikke testet — bed om flere fotos, før du tror på et tal.

```bash
# Tjenesten publicerer INGEN port — den er kun på compose-netværket
# (det er med vilje: kun appen skal kunne nå den). Vil du kalde den
# direkte, så start en engangs-container med en port:
docker compose run --rm -p 8001:8000 ocr
curl -s -F image=@foto.jpg http://localhost:8001/ocr | jq .

# Eller kald den fra appen, hvor den normalt nås:
docker compose exec allergiscan python -c "
from app.ocr_klient import _fra_tjeneste
print(_fra_tjeneste(open('/data/billeder/FIL.jpg','rb').read()))"

# Hele vejen lokalt (uden tjenesten kørende falder den til Tesseract —
# tjek 'engine' i svaret, så du ved hvilken motor du måler)
.venv/bin/python -c "
from app.ocr_klient import laes_deklaration
r = laes_deklaration(open('foto.jpg','rb').read())
print(r['engine'], r['confidence']); print(r['text'])"

pytest tests/test_ocr.py tests/test_ocr_sektion.py tests/test_ocr_klient.py -q
```

`tests/test_ocr.py` springes over uden `tesseract-ocr-dan` + DejaVu-font.
**Overspringet OCR-test er ikke en grøn OCR-test** — CI kører dem altid.

## Kendte huller (ikke konventioner — huller)

- **`found_section` bruges ingen steder.** Det er gratis signal om, at
  udklippet blev kasseret og hele pakketeksten står i boksen — netop det,
  mennesket har brug for at vide for at fange en falsk rød.
- **`clean()`s orddeling er versal-følsom.** `JORD-\nBÆR` bliver ikke
  samlet, og jordbær er ét af familiens fire allergener.
- **`_crop_ved_markoer()`s 16-linjers loft** (`y1 = top + 16*h` uden
  slutmarkør) klipper halen af en tætsat deklaration. Aldrig efterprøvet
  mod et rigtigt foto.
- **`_fuzzy_spans()` regner offsets på den FOLDEDE tekst**, men skærer
  `excerpt` af den originale. Står der æ/ø/å før træffet, peger
  frontend-highlightet forkert.
- **Samme billede uploades to gange** fra `#ocrBtn`: først til `/api/ocr`,
  derefter uawaitet til `/foto`. På butikssignal er det den dyreste del af
  hele appen. Nedskalering i browseren (canvas, 4000 px, q94) ville løse
  både det og de to forskellige størrelseslofter (12 MB mod 30 MB).
- **`Dockerfile.ocr` har ingen `--start-period`** på sit healthcheck, og
  modellerne indlæses først ved første OCR-kald.

## Næste skridt, hvis OCR skal videre

I rækkefølge efter hvad der giver mest for familien:

1. **Flere rigtige fotos.** Alt herunder er gætværk uden dem. 40 blev brugt
   til at vælge motor; der ligger ét i repoet.
2. **Vis `found_section` i bekræftelsesskærmen** — »appen kunne ikke finde
   ingredienslisten, her er hele teksten«. Ét felt, der allerede beregnes.
3. **Nedskalering i browseren** før upload. Fjerner dobbelt-uploadet, den
   lange ventetid og størrelsesgrænserne på én gang.
4. **Versal-orddelingen i `clean()`** — to tegn i et regex.
5. **Linjestruktur i `_klippet_forkert()`.** Kommaet alene kan ikke skelne
   en dansk næringstabel fra en ingrediensliste (kommaet er også
   decimaltegn), men rå OCR-tekst HAR linjestruktur, og den er ubrugt.
6. **En sprogmodel-fri stavekontrol mod et dansk ingrediensleksikon** —
   `app/ingredients.py` indeholder allerede familiens eget korpus.
