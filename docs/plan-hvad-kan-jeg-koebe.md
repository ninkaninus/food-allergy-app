# Hvad kan jeg købe? — dagplejerens spørgsmål

Skrevet 3. september 2026, før noget blev bygget. Efterprøvet mod koden og
mod rigtige data fra Open Food Facts; hver påstand herunder har en fil og et
linjenummer eller et målt tal.

## Ønsket

Vedligeholderen, 3. september 2026:

> Opslag virker fint for dagplejeren, hvis hun HAR varen. Men står hun og
> skal se, hvad hun skal købe, er der ingen hjælp. »Jeg vil købe smør —
> hvilket smør må jeg købe?«

## Beslutningen: genkaldelse ja, opdagelse nej

Produktejeren pressede omfanget og skar sagen i to. Skellet er hele planen:

- **Opdagelse** — »hvilke smør er tilladt« blandt varer, ingen i familien har
  haft i hånden. **Bygges ikke.** Det er filtreringslaget, der producerer en
  dom, ganget med ti rækker. `ingredients.py` fejler mod overekskludering og
  må aldrig afgøre sikkerhed (se CLAUDE.md, »To lag der ikke må blandes
  sammen«).
- **Genkaldelse** — »hvad har I selv godkendt af den slags«. **Bygges.** Den
  producerer ingen ny dom; den henter en gammel frem. Den gør bekræftelser
  mere værd i stedet for at presse på invarianten.

Begrundelsen er strukturel, ikke sproglig. Grå på scan-skærmen er en
blindgyde: »Ved det ikke« → fotografér pakken. Grå i en LISTE er en
kandidat. Ti grå rækker under overskriften »smør« læses som en bruttoliste,
uanset prikkens farve. Ingen ordlyd retter op på det, fordi strukturen læses
før teksten.

Produktejerens fulde vurdering: `.claude/agent-memory/produktejer/slags-soegning-presset.md`.

## Hvorfor opdagelse dør på tallene

Målt 3. september 2026 med den rigtige motor (`Ruleset.evaluate`) på 100
rigtige danske brød hentet fra Open Food Facts, mod barnets allergener:

| Udfald | Antal |
|---|---|
| Grå — deklaration læst, intet fundet | 45 |
| Grå — **ingen deklaration overhovedet** | 23 |
| Gul (spor/måske) | 23 |
| Rød (contains) | 9 |

**68 % grå.** En »hvilket brød«-liste ville være to tredjedele grå, og en
liste over »ingen mælk fundet« er en liste over varer med dårlig
datadækning — ikke over mælkefri varer. Fejlretningen er under-advarsel,
altså den farlige.

Og spørgsmålet, der blev stillet, har et sjovt svar: OFF har 29 danske smør.
Motoren dømmer dem rød på `smør`, fordi smør ER mælk. Svaret er »ingen af
dem«. Dagplejerens rigtige spørgsmål er et **erstatnings**-spørgsmål, ikke et
kategorisøg — se trin 1.

Tekniske rammer, hvis nogen tager opdagelse op igen:

- OFF har 21.833 danske varer.
- Søge-API'et er 10 kald/min/IP, og dokumentationen fraråder eksplicit
  search-as-you-type. Vi blev throttlet to gange under denne research.
  Live-søgning mod OFF er ikke en mulighed.
- Bulk findes: fuld verdens-CSV ~0,9 GB pakket / ~9 GB udpakket, plus
  parquet på Hugging Face (`openfoodfacts/product-database`) med alle
  nødvendige kolonner. Ingen landeopdelte udtræk — filtrering på
  `countries_tags` skal ske lokalt. ODbL, altså samme licensspor som
  `product` (se `NOTICE.md`).
- `/api/soeg` henter i dag ALLE `Product`-rækker ind i Python og filtrerer
  der (`main.py:1014`). Fint ved 20 varer, umuligt ved 21.000. Et katalog
  kunne aldrig ligge i `product`.

## Fundet, der bærer planen

**Arket har allerede svaret, og appen bruger det ikke.**

`ImportedProduct.erstatning_for` (`models.py:299`) er regnearkets kolonne
»bruges fx som erstatning for«. Den importeres (`cli.py:164`), gemmes — og
læses ALDRIG. Der er ingen forekomster i `app/main.py` eller i
`app/static/index.html`.

Det er dagplejerens spørgsmål, familien selv besvarede for år siden. »Hvad
køber jeg i stedet for smør« står i deres eget regneark, i deres egne ord, om
varer de selv har valideret. Det er genkaldelse i reneste form: ingen ny
datakilde, ingen ny tabel, ingen ny dom.

**Kontrollen er lavet 3. september 2026** mod den rigtige import i
`data-runtime`. Svaret gør trin 1 MINDRE, ikke større:

| Hylde | Rækker | Med `erstatning_for` | Med EAN |
|---|---|---|---|
| **Erstatningsprodukter** | 41 | **40** | 0 |
| Pålæg | 194 | 0 | 0 |
| Bagning | 112 | 0 | 0 |
| Brød | 67 | 0 | 0 |
| Ris, Pasta og lignende | 57 | 0 | 0 |
| Diverse | 39 | 0 | 0 |
| Frugtgrønt | 34 | 0 | 0 |
| Snacks P | 19 | 0 | 0 |
| Kiks P | 13 | 0 | 0 |
| Drikkelse | 7 | 0 | 0 |

583 rækker i alt, 40 med erstatning, 10 hylder. Kolonnen er ikke spredt ud —
den er samlet på ÉN hylde, »Erstatningsprodukter«, hvor 40 af 41 rækker har
den udfyldt. De første poster i kolonnen er ordret **»Smør«** og **»Smørbar
smør«**: præcis det spørgsmål, der startede sagen.

**Ingen af de 583 rækker har en EAN.** Produktejerens modforslag — at knytte
stregkoder ved køkkenbordet — har haft nul optag. Uden EAN kan en række
aldrig bære en dom.

To ting følger:

1. Søgningen leder kun i navn, mærke og kategori (`main.py:1071`), så en
   søgning på »smør« finder IKKE familiens egne smørerstatninger. Svaret
   ligger i databasen og er usynligt for det spørgsmål, det besvarer.
2. Trin 1 er derfor ikke en ny funktion, men to små indgreb: tag
   `erstatning_for` med i søgeteksten, og vis den på rækken.

## De fire huller

**1. Svaret er mærket som et ikke-svar.**
De 583 arkrækker får `status: "uscannet"` (`main.py:1056`), og chippen hedder
»Ikke scannet« (`index.html:1581`). Familiens egen validering — den eneste
rigtige besvarelse af spørgsmålet — bærer det mest afvisende ord i
grænsefladen. `valideret_mod` vises dog allerede som »fra arket — bekræftet
uden mælk og æg« (`index.html:1640`).

**2. Listen er tom for en udlogget bruger — og værre end tom.**
Efterprøvet mod den ægte model 3. september 2026: familien bekræfter
mælkeprotein + æg manuelt som `free` på et rugbrød.

| Kald | Status på varen | »Sikre« i facetten |
|---|---|---|
| Udlogget, frisk telefon (alle 17) | **`unsafe`** | 0 |
| Familiens eget sæt (2 allergener) | `safe` | 1 |

`aggregate()` kræver, at ALLE vurderede allergener er manuelt `FREE`
(`matcher.py:401-406`), og `index.html:1994` sætter tavst en frisk telefon
til alle 17. Varen bliver ikke bare grå — den bliver **rød**, fordi motoren
finder gluten i rugmelet. En udlogget dagplejer får at vide, at et brød,
familien har godkendt, er »Ikke sikker«. Det rammer også enhver fremmed, jf.
den åbne flade.

**3. Kategori består ikke prøven »kan en scannet vare også have det?«.**
`Product` har ingen kategorikolonne (`models.py:101-126`). En scannet vare
får kun hylde ved at matche en arkrække; ellers »Uden kategori«
(`main.py:1140`). Samme mekanik som butikskolonnen, der blev fjernet i
0.18.0: dimensionen degraderer, jo mere familien scanner. Hylde-navnene er
regnearkets fanebladsnavne (`kategori=ws.title.strip()`, `cli.py:160`) — og
de ER slags-ord: CHANGELOG 0.11.0 nævner produktionens egne tal, **Pålæg 194,
Bagning 112, Brød 67**.

**4. Fanen hedder »Filtrér«.**
Dagplejeren er en sjælden bruger. Hun leder efter et svar, ikke efter et
filter. Søgefeltets pladsholder lover allerede slags-vokabularet: »brød,
yoghurt, pålæg …« (`index.html:337`).

## Dagplejeren er ikke forælderen

Den bedste begrundelse for funktionen er ikke »søgning«, men
**vidensoverførsel**. Forælderen har listen i hovedet efter to års indkøb;
dagplejeren har den kun i appen. Hun handler generisk til en gruppe børn,
hendes risikotolerance skal være lavere — det er ikke hendes barn — og hun
er en sjælden bruger, der ikke husker, hvor søgningen bor.

## Vedligeholderens beslutning om identitet

Truffet 3. september 2026:

> Dagplejeren kan både være logget ind og ikke logget ind. Svaret skal være
> det samme for de to muligheder — dog med den undtagelse, at den ikke
> indloggede bruger selv skal kende allergenerne og indtaste dem.

Altså:

| | Allergensæt | Svar |
|---|---|---|
| Logget ind | familiens delte sæt fra serveren | uændret |
| Udlogget, har valgt | hendes eget valg | **identisk mekanik** |
| Udlogget, har intet valgt | — | appen **spørger** i stedet for at gætte |

## Planen

### Trin 0 — ret den udloggede visning

Egen udgivelse, før noget andet. Det er ikke en del af den nye funktion; det
er den nuværende funktion, der er i stykker for præcis den bruger, sagen
handler om.

Den tavse alle-17 (`index.html:1994`) erstattes af et spørgsmål.

**Den ene ting, der skal holdes fast i:** intet valgt må ALDRIG komme til at
betyde »tjek ingenting«. Alle-17 over-advarer i dag, hvilket er den ufarlige
retning; et tomt sæt ville under-advare, hvilket er den farlige. Serveren
afviser allerede et tomt sæt med 400 (`main.py:481`), så vagten er halvt på
plads — frontend skal lade være med at kalde og vise spørgsmålet i stedet.

Acceptkriterier:

- En frisk telefon uden login bliver BEDT om at vælge allergener, før den
  får et svar. Den gætter ikke.
- Har hun valgt de samme allergener som familiens sæt, er dommen på enhver
  vare bit-for-bit den samme som for en indlogget bruger.
- Et tomt allergensæt kan ikke opstå: hverken frontend eller server må
  besvare et opslag uden mindst ét allergen.
- Ingen vare kan blive grøn af dette trin. De fire invariant-tests er
  uændrede og grønne.
- En test dækker den udloggede sti med et sæt, der IKKE er alle 17 — den
  nuværende suite sender altid `allergens` eksplicit og er derfor blind for
  fejlen (`tests/test_soeg.py:88`).

Ejer: `allergen-domaene` — trinnet ændrer, hvad der bliver rødt.

### Trin 1 — giv genkaldelsen et sted at blive stillet

Et indgangspunkt, der spørger »hvad skal du købe?« i stedet for at tilbyde et
filter, og som svarer fra arket og fra jeres bekræftede varer. Rygraden er
`erstatning_for` sammen med `kategori`.

Ingen ny datakilde, ingen ny tabel, ingen ny dom.

Acceptkriterier:

- Et slags-ord (»smør«, »brød«) giver familiens egne rækker af den slags,
  og — hvor arket siger det — hvad de bruger i stedet.
- Listen indeholder KUN ting, et menneske har taget stilling til. I det
  øjeblik den også viser »varer vi ikke ved noget om«, er den holdt op med
  at være genkaldelse.
- Intet i listen kan være grønt uden en dom fra bekræftelsesruten.
- Ingen træf siger det ærligt og peger på scanning — den siger ikke
  »ingen problemer fundet«.

Ejer: `implementer`, med `allergen-domaene` som modlæser på ordlyden af
enhver farve.

### Trin 2 — omdøb svaret

»Ikke scannet« er forkert på en række, familien selv har valideret. Ordlyden
skal skelne »bekræftet i appen mod emballagen« fra »markeret i jeres
regneark« uden at lade den anden ligne den første.

Acceptkriterier:

- En arkrække kan ikke forveksles med en bekræftet vare — hverken i farve,
  ikon eller ord.
- Glemmeprøven: en dagplejer, der læser rækken om tre måneder, kan stadig se,
  at hun selv skal læse emballagen.

Ejer: `ux-gennemgang`, med `allergen-domaene` som modlæser.

### Trin 3 — intet katalog

Opdagelsesvejen bygges ikke. Se tallene ovenfor.

Modforslaget, produktejeren stiller i stedet, koster ingen kode: knyt
stregkoder på arkrækkerne ved køkkenbordet
(`POST /api/liste/{id}/stregkode`). Det er den billigste vej til, at
søgningen kan svare, fordi en række uden EAN aldrig kan bære en dom.

## Advarselsbudgettet — bevidst ikke afgjort

En liste er en advarsels-multiplikator: ét scan = én advarsel, ét
slags-opslag = otte farvede rækker. Fem røde varer, hun aldrig ville have
overvejet, er fem advarsler brugt på ingenting. Men at skjule dem gør listen
ufuldstændig uden at sige det. Spørgsmålet står åbent og skal besvares, når
trin 1 har en rigtig skærm at se på.

## Relateret

- `.claude/agent-memory/produktejer/slags-soegning-presset.md` — den fulde
  produktvurdering
- `.claude/agent-memory/produktejer/situationen-er-butikken.md` — prøven
  »kan en scannet vare også have det?«
- `.claude/agent-memory/produktejer/appen-er-ikke-i-brug-endnu.md` — ~20
  varer i produktion; funktioner, der forudsætter mængde, er for tidlige
- `ROADMAP.md`, »Den ene ting, der kan gå galt« — appen kan blive for
  troværdig
