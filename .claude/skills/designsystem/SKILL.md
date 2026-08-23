---
name: designsystem
description: AllergiScans visuelle og sproglige vokabular — de rigtige tokens, de fire domme, de påkrævede tilstande og copy-reglerne. Slå op, før du bygger eller gennemgår noget i app/static/index.html.
---

# AllergiScans designsystem

Efterprøvet mod `app/static/index.html` 21. august 2026.

## Konteksten, der styrer hver beslutning

En forælder står i Netto med en pakke i den ene hånd og telefonen i den
anden. Måske et barn i vognen. Måske dårligt signal i butikken. Svaret skal
kunne læses på under et sekund på armslængde — og det skal være rigtigt.

Den anden bruger er en dagplejer, som bruger appen sjældnere og aldrig har
læst en vejledning.

Det her er ikke en app, man bruger dagligt i ro. Design til **sjælden brug
under mild stress**, ikke til øvede brugere. Tæthed er ikke en dyd her.

## Én fil, intet byggetrin

Hele frontend er `app/static/index.html`: markup, CSS og et ES-modul i
samme fil. Ingen node_modules, ingen bundler, intet at holde opdateret.
`zxing-wasm` er vendoret i `static/vendor/zxing/`, fordi Safari mangler
`BarcodeDetector`.

Det er et bevidst valg, ikke gæld. Foreslår du et framework, en bundler
eller en CSS-fil mere, skal du kunne sige, hvad de to voksne brugere får ud
af det.

## Tokens (som de faktisk står i `:root`)

```
--paper:#E4E9EC   --surface:#fff   --ink:#12181C   --muted:#5D6B73   --rule:#C6D0D6
--unsafe:#C2251B  --caution:#B26A00  --unverified:#42545F  --safe:#0E6B4E
--pad:18px
```

Ingen nye farver. De fire domsfarver er systemet — indfører du en femte,
har du indført en femte dom, og der er kun fire.

Skrift: **Archivo** (variabel, til `.shout` og logoet), **Public Sans**
(brødtekst), **JetBrains Mono** (stregkoder og mønstre). Hentes fra Google
Fonts; alt andet er lokalt.

## De fire domme — appens hele grammatik

`.slab[data-r="…"]` sætter baggrunden, og `COPY` i scriptet sætter ordene.
Rækkefølgen er eyebrow / shout / forklaring:

| `data-r` | Eyebrow | Shout | Farve |
|---|---|---|---|
| `unsafe` | Fundet | **Ikke sikker** | `--unsafe` |
| `caution` | Usikker | **Skal tjekkes** | `--caution` |
| `unverified` | Ikke bekræftet | **Ved det ikke** | `--unverified` |
| `safe` | Bekræftet | **Sikker** | `--safe` |
| `unknown` | Ukendt vare | **Ingen data** | `--unverified` |
| `error` | Opslag fejlede | **Prøv igen** | `--caution` |

To ting må aldrig gå tabt i en ændring:

1. **"Ved det ikke" må aldrig komme til at ligne "sikker".** Det er hele
   invarianten oversat til farve og ord. Grå er ikke en svag grøn.
2. **`safe` kan kun opstå efter en menneskelig bekræftelse.** Findes der en
   sti gennem UI'et, hvor den grønne flade vises uden det, er det en
   BLOKERENDE fejl, uanset hvor pænt det ser ud.

`BASIS`-kortet oversætter motorens `basis` til dansk, brugeren kan læse
("SPOR ifølge etiketten — ikke i ingredienslisten"). Tilføjer motoren en ny
`Basis`, skal den oversættes her, ellers vises den rå enum-værdi.

## Struktur

Tre visninger, skiftet af `nav.tabs` i bunden (fast, med
`env(safe-area-inset-bottom)`):

- `#view-scan` — kamera/stregkode, dommen, deklarationen som appen læste
  den, fotoknapper, bekræftelsespanelet
- `#view-filter` — søgning i familiens varer, statuschips, facetter
- `#view-prefs` — profil, allergener, login, »Nyheder«

Element-id'er er bærende — `$('#slab')`, `$('#rows')`, `$('#declEdit')` og
resten slås op direkte. Omdøbning er en fejl, ikke oprydning.

Tabbaren er `aria-current="true"` på den aktive knap, ikke en klasse.

## Påkrævede tilstande

Hver visning af data skal håndtere alle fire. En skærm, der kun kan det
lykkelige tilfælde, er ikke færdig:

1. **Tom** — ingen varer endnu, med en klar næste handling.
2. **Henter** — aldrig en blank skærm. Et opslag mod Open Food Facts kan
   tage sekunder i en butik med dårligt signal.
3. **Fejl** — `error`-dommen er den rigtige form: hvad skete der, og hvad
   gør man nu. Aldrig en rå HTTP-status til en forælder.
4. **Udfyldt** — det normale.

Særligt for denne app: **kameraet kan nægte**. Ingen tilladelse, iPhone der
falder tilbage til zxing (mærkbart langsommere), krøllet stregkode. Der skal
altid være vejen udenom — indtastningsfeltet — synlig samtidig.

## Copy-regler

- **Dansk.** Ingredienslisterne er danske, brugerne er danske. Ingen
  engelske ord i UI'et, hvor der findes et dansk.
- **Knapper navngiver handlingen**: »Bekræft mod emballagen«, »Fotografér
  deklaration« — ikke »Gem« eller »OK«.
- **Sig hvad appen ikke ved.** »Appen fandt ingenting — men den har ikke
  set pakken. Det er ikke det samme som frit« er den vigtigste sætning i
  appen. Bliv ved med at skrive sådan: ærligt, uden at pynte.
- **Ingen udråbstegn. Ingen emoji.** En rød flade er alvorlig nok i sig selv.
- Brug familiens ord: vare, deklaration, spor, stregkode, dom — ikke
  »produkt-entitet«, »record«, »verdict object«.
- Advarslen nederst på scan-fanen (»Grøn kræver et menneske«) er ikke
  pynt. Den må gerne omformuleres, men den skal blive stående.

## Tilgængelighedsgulv

- Læsbar på armslængde i butiksbelysning. Kontrasten på de fire flader er
  valgt til hvid tekst — ændrer du en farve, skal du regne den efter.
- **Aldrig farve alene.** Hver dom har eyebrow + overskrift + forklaring
  netop derfor; en rød og en grøn flade må aldrig kun adskille sig ved kulør.
- Fokusmarkering er `3px solid var(--caution)` med offset — den er synlig
  med vilje. Fjern den ikke.
- Trykflader i tommelhøjde. Den primære handling må aldrig ligge under
  folden på en lille telefon.
- `aria-label` på inputs uden synlig label (`#ean`, `#sQ`, `#declEdit`).

## Ting, der plejer at gå galt her

- Et nyt `.slab`-tema bliver tilføjet uden en tilsvarende `COPY`-post →
  fladen viser farven, men ingen tekst.
- Et nyt felt fra API'et bliver renderet med `innerHTML` uden `esc()` →
  deklarationstekst kommer fra OCR og kan indeholde hvad som helst.
- Highlight af træf regner på tegn-offsets fra motoren
  (`highlight()` + `Hit.start/end`). Ændrer nogen maskeringen i
  `matcher.py` til at klippe i stedet for at maskere, peger highlightet
  det forkerte sted. De to hænger sammen.
