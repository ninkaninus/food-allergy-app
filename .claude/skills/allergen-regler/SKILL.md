---
name: allergen-regler
description: Hvordan AllergiScans regelmotor faktisk læser en deklaration — maskering, ordgrænser, spor, fuzzy-matchning og de kendte huller. Slå op, før du ændrer noget i matcher.py, allergens.yaml eller OCR-efterbehandlingen.
---

# Regelmotorens mekanik

Efterprøvet mod koden 21. august 2026 (efter 0.19.0); afsnittet »Sættet, der
vurderes« er efterprøvet 3. september 2026 (0.24.0). **Ændrer du mekanikken,
ændrer du denne fil i samme commit** — ellers gætter næste session på noget,
der ikke er sandt.

## Invarianten, alt andet hænger på

Motoren kan gøre en vare **rød** (`CONTAINS`) eller **gul** (`TRACE_RISK`).
Aldrig grøn. `State.FREE` sættes ét sted: `POST /api/products/{ean}/confirm`
(`app/main.py`), som kræver `require_curator`. Fandt motoren ingenting, er
svaret `UNKNOWN` med `Basis.NOT_FOUND_IN_TEXT` — ikke "sikker".

Fire tests håndhæver det, og de er også CI's port til at udgive et image:

| Test | Fil |
|---|---|
| `test_engine_never_returns_free` | `tests/test_matcher.py` |
| `test_ocr_mode_still_never_returns_free` | `tests/test_matcher.py` |
| `test_only_human_confirmation_produces_green` | `tests/test_auth.py` |
| `test_unknown_barcode_returns_no_verdicts` | `tests/test_auth.py` |

En ændring, der får dem til at fejle, er forkert. Testene er ikke til
forhandling.

## Rækkefølgen i `Ruleset.evaluate()`

Rækkefølgen ER reglen. Bytter du om på trinnene, ændrer du domme:

1. **OFF's strukturerede tag vinder.** Er `off_tag` (fx `en:milk`) i
   `off_allergen_tags`, returneres `CONTAINS` / `OFF_ALLERGEN_TAG` med det
   samme — ingen tekstlæsning. Kun EU-14 har `off_tag`; jordbær, banan og
   tomat har `null` og kan derfor kun findes i teksten.
2. **Ingen tekst → `UNKNOWN` / `NO_TEXT`.** Tom deklaration er ikke en dom.
3. **Maskering, to udgaver** (se nedenfor).
4. **contains-passet** på den maskerede tekst → `CONTAINS` / `TEXT_MATCH`.
5. **OFF's spor-tag** → `TRACE_RISK` / `OFF_TRACE_TAG`.
6. **fuzzy-passet, kun når `ocr=True`** → `CONTAINS` / `OCR_FUZZY`.
7. **Sporangivelserne, læst for sig** → `TRACE_RISK` / `TRACE_STATEMENT`
   eller `TRACE_UNSPECIFIED`.
8. **maybe-passet** → `TRACE_RISK` / `TEXT_MAYBE`.
9. **Ingenting fundet → `UNKNOWN` / `NOT_FOUND_IN_TEXT`.**

`aggregate()` samler til `unsafe` / `caution` / `safe` / `unverified`.
`safe` kræver at ALLE valgte allergener står som `FREE` **og** `MANUAL`.

### Sættet, der vurderes, er en del af dommen (0.24.0)

Fordi `aggregate()` kræver ALLE vurderede allergener, er listen af slugs
lige så domsbærende som teksten. Samme vare, samme database, to sæt:

| `allergens=` | Dom på et rugbrød med manuel FREE på mælk+æg |
|---|---|
| `maelkeprotein,aeg` | `safe` |
| udeladt (= alle 17) | **`unsafe`** — gluten i `Rugmel` |

De to indgange, der tager parameteren, er `GET /api/scan/{ean}` og
`GET /api/soeg`. Begge:

- **afviser et TOMT eller ugyldigt sæt med 400**, før varen slås op. Et
  tomt sæt ville betyde »tjek ingenting« — den farlige retning.
- **udelader man parameteren, vurderes alle 17.** Over-advarsel, altså
  den ufarlige retning, men det er et gæt: for en anonym kalder er det
  også bevidst, at profilen IKKE bruges, for svarets længde ville ellers
  røbe barnets sæt.

Frontend sender altid parameteren og gætter aldrig. Indtil 0.23.1 satte
opstarten i `index.html` tavst en frisk telefon uden login til alle 17,
og en dagplejer fik derfor »Ikke sikker« på et brød, familien selv havde
godkendt. Nu spørger appen (`harValgtAllergener()` + vagt i både
`lookup()` og `soeg()`); `tests/test_udlogget_allergensaet.py` holder
begge indgange og begge retninger fast på serversiden.

Fem ting i frontend hører til mekanikken og er lige så domsbærende som
vagten selv (0.24.0). Alle fem er efterprøvet ved at KØRE modulet i node
med en DOM-stub — `tests/frontend_stub.mjs` + `tests/test_frontend_adfaerd.py`,
ni scener, som alle fejler mod 0.23.1's `index.html`:

1. **`glemVistDom()` er ét sted.** Grundlaget for en vist dom kan holde op
   med at gælde, uden at nogen scanner noget: hun logger ud, eller hun
   slår et allergen til. Så ryger dommen af skærmen — `opslagNr++`,
   `#confirmPanel` og `#verdict`. Kaldes fra `startCam()`,
   `malVaelgPanel()`s mangler-gren og chip-klikket i `paintPrefChips()`.
   Uden det kunne et grønt »SIKKER« om et rugbrød stå uændret, mens appen
   øverst på samme skærm spurgte, hvad den skulle tjekke for.
2. **`localStorage`-nøglen hedder `allergiscan.prefs.v2`.** v1 indeholder
   på hver eneste telefon, der har åbnet 0.23.0 eller tidligere,
   `{"allergens":[alle 17]}` — den GAMLE opstart skrev dem selv med
   `savePrefs()`. Læses v1 videre, svarer `harValgtAllergener()` »ja« på
   appens eget gæt, og spørgsmålet bliver aldrig stillet. **Bumper du
   sættets betydning igen, skal nøglen bumpes med.**
3. **`lookup()` venter på `authFaerdig`**, før vagten prøves.
   `autostartCam()` kaldes under parsing og kan afkode en stregkode, før
   `/api/auth/me` har svaret; uden porten ville en indlogget telefon med
   tomt lokalt valg se `USER === null` og kaste scanningen væk. Porten
   åbnes i `refreshAuth()` OG i opstartens `finally`, og `/api/allergens`
   og `/api/auth/me` er begge pakket ind — en lukket port er en scanning,
   der forsvinder lydløst.
4. **Vagtens besked er en konstant (`VAELG_FOERST`), fordi den skal kunne
   tages ned igen.** Bliver den stående, efter hun har valgt, er det
   eneste på skærmen en opfordring til at gøre det, hun lige har gjort —
   og den sandsynlige reaktion er at slå FLERE allergener til.
5. **`vaelgBesked()` er den ene kilde til de to tekster** på begge
   indgange. En bidragyder må ikke loves et valg, chipsene ikke lader
   hende træffe, og en 401 fra `/api/profiles` må ikke ligne »ingen
   allergener slået til« — den skal sige, at det er serveren, der ikke
   svarede (`if(!r.ok) throw` i `refreshAuth()`).

**Retningen, sættet åbner:** et smallere sæt advarer om MINDRE end alle
17. Det er kun i orden, fordi et menneske udtrykkeligt har valgt det —
derfor står »appen advarer kun om det, der er valgt her« over chipsene i
`#view-prefs`, og derfor må intet i koden fylde sættet ud på egen hånd.

## De fem mekanismer, der ser mærkelige ud

### 1. Maskering med `░` (U+2591), ikke udklipning

`_mask()` erstatter med blokke af **samme længde**. Tegn-offsets skal holde,
så frontend kan highlighte præcis det ord, der udløste advarslen. Klipper du
i stedet, peger highlightet forkert i lange deklarationer.

`protect`-parameteren beskytter et span, der allerede er ramt af et længere,
mere specifikt mønster: undtagelsen `mælkesyre` må ikke maskere de første ni
tegn af maybe-mønsteret `mælkesyrekultur` og dermed gøre det usynligt.

### 2. Ordgrænse FØR mønsteret, ikke efter

`_compile()` sætter `(?<![a-zæøåéü0-9])` foran hvert mønster og ingenting
bagefter. Derfor rammer `mælk` → `mælkepulver` (præfiks) men ikke `kokosmælk`
(suffiks). Dansk sammensætter ord, og allergenet betyder kun noget, når det
står forrest.

**Konsekvens, der skal huskes ved hver regeltilføjelse:** sammensætninger med
allergenet bagest (`kærnemælk`, `skummetmælk`, `sødmælk`, `tykmælk`) skal stå
eksplicit i `contains`. Fjerner du lookbehind'en, bliver `kakaosmør` til
mejeri, og folk holder op med at stole på appen.

### 3. To pas med forskellig maskering

```
exclude + maybe maskeres  ->  for_contains  ->  rød
exclude maskeres          ->  for_maybe     ->  gul
                                            ->  fuzzy (kun ved OCR)
```

Uden det første ville `jordbæraroma` blive rød på præfikset `jordbær`.

### 4. Sporangivelser læses for sig, pr. allergen

`_spor_spans()` finder teksten fra en `trace_markers`-frase til første `.`,
`;`, `!` — eller til et af ordene i `SEKTIONSORD` (`ingrediens`, `indhold`,
`sammensætning`, `ingredients`) — med **loft på 200 tegn**. Sektionsordene
kom til i 0.19.0: en sporsætning indeholder aldrig starten på en
ingrediensliste, og uden dem kunne spanet løbe hen over deklarationen, når
OCR havde tabt punktummet — så blev en RØD vare gul. Loftet er der, fordi OCR taber
punktummer: uden det kunne ét spor-span sluge resten af listen og gøre et
rigtigt allergen til "kun spor". Under-advarsel er den farlige retning.

Spanet maskeres **ud af** contains-passet, og allergenets egne mønstre køres
så *inde i* spanet. Træf dér giver `TRACE_STATEMENT` (gul), ikke rød. Står
allergenet både i listen og i sporangivelsen, vinder listen — fordi kun
spanet maskeres.

`_naevner_allergen()` afgør, om spanet er konkret: nævner det mindst ét
allergen, motoren kender, gælder det kun de nævnte. Nævner det intet
genkendeligt ("kan indeholde spor af andre kornsorter"), får alle
`TRACE_UNSPECIFIED`. Før gjorde enhver sporfrase alle 17 allergener gule — en
app, der råber ulv ved hver vare, holder folk op med at læse.

Cachen i `_spor_cache` tømmes ved 256 poster. Den er pr. `Ruleset`-instans.

### 5. Fuzzy-matchning KUN på OCR-tekst

`FOLD` folder æ/ø/å + de cifre, OCR forveksler med bogstaver (`0→o`, `1→l`,
`5→s`, `@→o`, `|→l`), ned til ASCII. `_fuzzy_spans()` tillader
Levenshtein-afstand 1 for mønstre under 9 tegn, 2 for længere, kun for
mønstre på **mindst 5 tegn** og uden mellemrum.

Målt: Tesseract læser en dansk deklaration med 89,8 % konfidens og laver
`skummetmælkspulver` om til `skummetmaalkspulver`, `jordbær` til `jordbzer`.
Eksakt matchning missede begge — netop de allergener, der stod på pakken.
På ren tekst ville det give falske positiver uden gevinst, derfor `ocr=True`.

Fuzzy-passet kører først, når det eksakte pass fandt nul — derfor springes
`word == pat` bevidst ikke over: `aeggeblomme` er et ord, der kun matcher
efter foldning.

## `data/allergens.yaml`

17 allergener: EU-14 plus `jordbaer`, `banan`, `tomat`. Udvidet i
0.19.0 med ~45 danske etiketord, mest oste (`feta`, `brie`, `gouda`,
`havarti`, `danbo`) — lookbehind'en fanger dem ikke, så de SKAL stå
eksplicit. Pr. allergen:
`slug`, `name_da`, `name_en`, `off_tag` (null uden for EU-14), `eu14`,
`note`, og listerne `contains` / `maybe` / `exclude`.

Filen mountes read-only i containeren og kan redigeres uden rebuild —
`RULES_PATH` peger på den. En regelændring kræver altså ikke en udgivelse,
men den kræver stadig en test.

**Retningen betyder alt.** At tilføje `contains` eller fjerne `exclude` er
over-advarsel: irriterende, ufarligt. At fjerne `contains` eller tilføje
`exclude` er under-advarsel: det er sådan et barn bliver sygt.
`scripts/vagt-groen.sh` fanger den retning automatisk og beder om en
begrundelse.

Ved hver ny undtagelse: navngiv den rigtige falske positive, den er til for
(`kakaosmør`, `kokosmælk`, `mælkebøtte`, `ægte vanilje`), og kontrollér at
den ikke skygger for et længere maybe-mønster.

## De to lag må ikke blandes sammen

| | `app/ingredients.py` | `app/matcher.py` |
|---|---|---|
| Dækning | alle ingredienser | 17 allergener |
| Præcision | lav, substring | høj, maskeret |
| Fejler mod | overekskludering | overadvarsel |
| Bruges til | finde og filtrere | afgøre sikkerhed |

Filtret siger "uden mælk" og smider også kokosmælk-varen ud. Det er
irriterende, når man browser, og fuldstændig acceptabelt. Regelsættet ville
aldrig gøre det.

**Lad aldrig filtreringslaget producere en dom.** Det er den mest
sandsynlige måde at ødelægge appen på, fordi det ser ud som en oplagt
forenkling.

## OCR: hvor betydningen lægges på

`ocr_service/` er en dum tjeneste (rapidocr/PP-OCRv6): pixels ind, tegn ud.
Den kender intet til dansk orddannelse, allergener eller domme. Al betydning
lægges på i appen — `efterbehandl()` og `extract_section()` i `app/ocr.py`,
reglerne i `matcher.py`. To grunde: `onnxruntime` er native kode, som ikke må
kunne tage web-appen og databasen med sig i et segfault, og sikkerhedslogikken
skal bo ét sted.

`app/ocr_klient.py` kalder tjenesten på `OCR_URL` og falder tilbage til
Tesseract i `app/ocr.py`, hvis den ikke svarer.

Målt på 40 af familiens egne butiksfotos: 2,8× så mange rigtige danske ord
som Tesseract, 6× hurtigere, nul tabte allergener. De tre steder, hvor
Tesseract fandt et allergen, den nye motor ikke fandt, var alle falske
positiver fra fuzzy-matchning på grafikstøj.

**`extract_section()` klipper i teksten, FØR reglerne ser den.** Det er et
sikkerhedskritisk sted, selvom det ligner formatering: klipper den en
sporangivelse eller en ingrediensliste væk, forsvinder en advarsel. Tre
mekanismer holder den i skak (alle tre kom til i 0.19.0 efter en
gennemgang, der fandt fire etikettyper, hvor hele listen blev smidt væk):

1. **Sporadvarsler hentes fra BEGGE sider af udklippet** — `_spor_uddrag()`
   køres på `text[:start]` og `text[slut:]`. Står »Kan indeholde spor af
   mælk« ØVERST på etiketten, ligger den i hovedet, ikke i halen.
2. **`_klippet_forkert()`** kasserer udklippet, hvis det kasserede har
   mindst to kommaer mere end det beholdte — kommaet er ingredienslistens
   signatur. To spærrer mod overreaktion: vagten fyrer kun, når det
   beholdte har **under tre kommaer** (danske næringstabeller bruger komma
   som decimaltegn, så en normal etiket har flere kommaer uden for listen
   end i den), og **kun når startmarkøren var svag eller manglede**.
   `STRONG_SECTION_MARKERS` — »ingredienser« og slægtninge — tros;
   »indhold« og »sammensætning« gør ikke, for de står også på pakker om
   noget helt andet (»Indhold: 500 g«).
3. **Når vagten fyrer, bruges råteksten IKKE i original rækkefølge.**
   Sporsætningerne flyttes bagest først. Ellers ville et spor-span, hvis
   punktum OCR har tabt, sluge ingredienslisten — og en RØD vare blive
   GUL. I den vej stopper spanet også ved linjeskift; i den normale vej
   gør det ikke, for dér ville en sporsætning brudt over to linjer miste
   sine allergennavne.

Enhver ændring i udklipningen skal svare på: hvad kan nu blive klippet væk,
som før nåede frem til motoren?

## Kendte huller (ikke konventioner — huller)

- **Fuzzy-passet kan finde allergener i grafikstøj.** Det er prisen for ikke
  at misse `skummetmaalkspulver`. Rigtig retning, men det betyder, at et
  OCR-resultat altid skal gennem et menneske.
- **`_spor_spans()`' 200-tegns loft er et skøn**, ikke en målt grænse.
  Sektionsordene lukker det almindelige tilfælde, men hullet står stadig
  åbent i én form: en tekst UDEN punktum, UDEN linjeskift og UDEN et
  sektionsord, hvor sporfrasen står før listen — fx
  `"KAN INDEHOLDE SPOR AF NØDDER hvedemel, skummetmælkspulver
  Næringsindhold pr. 100 g: ..."`. Der bliver mælk stadig gul i stedet
  for rød. Efterprøvet 2026-08-21; det er en pre-eksisterende tilstand,
  ikke en regression.
- **Spor-passet ser ikke `exclude`.** `_find(udsnit, udsnit, contains)`
  kører på RÅ tekst, ikke på den maskerede. Derfor giver »spor af
  mælkesyre« GULT, mens »mælkesyre« i ingredienslisten giver gråt — de
  to pas svarer forskelligt på samme ord. Retningen er den sikre
  (over-advarsel), så det er ikke rettet. `test_spor_passet_ser_ikke_exclude`
  er vagten: ændres det, skal det være bevidst.
- **`SEKTIONSORD` her og `SECTION_MARKERS` i `app/ocr.py` er et par**, men
  to lister, matchet på hver sin måde (`str.find` mod `_markoer()` med
  ordgrænse). Ændrer du den ene, så se på den anden.
- **Fuzzy-passet giver kendte falske positiver på almindelige danske ord.**
  Målt: `helæg` ← »belægning«, `havarti` ← »havari«. Begge er
  over-advarsel og derfor tålelige, men de ses kun ved OCR. `akkar` blev
  fjernet igen af samme grund — den ramte »bakker« og »makkaroni«, og
  `blæksprutte` dækker den alligevel.
- **Danske `-ost`-suffikser mangler stadig**: `vesterhavsost`, `rygeost`,
  `danablu`, `koldskål`. Samme klasse som de oste, 0.19.0 tilføjede.
  Ligeledes `flagemandler`/`smuttemandler` (nødder), `grønlandsrejer`
  (krebsdyr) og `laktose`, som slet ikke står nogen steder.
- **`aggregate()` kender ikke `severity`** (`strict` vs. `watch` på
  `ProfileAllergen`). Et `watch`-allergen vejer lige så tungt som et
  `strict` i den samlede dom.
- **`ingredients_hash` beskytter kun varer, I allerede har bekræftet.**
  Ændrer producenten opskriften på en vare, der aldrig blev bekræftet,
  opdager ingen det.
