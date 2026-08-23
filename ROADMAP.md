# Vejen videre

Rækkefølgen er valgt efter én ting: hvor hurtigt kommer appen i hænderne på
jer i en rigtig butik. Alt andet er sekundært, fordi de fleste antagelser i
koden først kan efterprøves der.

---

## Fase 0 — I luften (en aften)

Målet er ikke en pæn app. Målet er at scanne én rigtig vare i Netto.

Trin-for-trin med verifikation undervejs: [`deploy/UNRAID.md`](deploy/UNRAID.md).
Kort fortalt:

- [ ] Klon repoet til `/mnt/user/appdata/allergiscan/repo`
- [ ] `cp .env.example .env`, sæt `OFF_USER_AGENT` til din egen mail
- [ ] `docker compose up -d --build` på unRAID
- [ ] `docker compose exec allergiscan python -m app.cli adduser dig@example.dk "William"`
- [ ] Opret Cloudflare Tunnel, peg den på `http://allergiscan:8000`
      (porten binder som default kun til loopback, så tunnellen er eneste vej ind)
- [ ] Åbn sitet på telefonen, læg det på hjemmeskærmen
- [ ] Scan ti varer fra dit eget køkken
- [ ] Slå auto-deploy til (afsnit 2 i `deploy/UNRAID.md`), så push til main
      er dit deploy fremover

**Det, du lærer her, er vigtigere end resten af listen.** Ti varer fortæller
dig, hvor stor andel Open Food Facts faktisk dækker for netop de mærker, I
køber — og om `BarcodeDetector` klarer krøllede etiketter i praksis.

Test scanneren på begge telefoner. iPhone bruger zxing-fallbacken, og den er
mærkbart langsommere; er den for langsom i praksis, er det den første ting,
der skal fikses.

---

## Fase 1 — Få jeres eksisterende viden ind ✓ (import som opslagsliste)

Gjort — men anderledes end planlagt, for arket viste sig ikke at have
EAN-koder, og domme hænger på (EAN, allergen). I stedet:

- [x] `python -m app.cli import [fil-eller-url]` læser arket (583 varer,
      alle kategoriark) ind i en separat opslagsliste uden domme. Med
      `LISTE_URL` i `.env` henter den selv nyeste udgave fra Google
      Sheets. Alle varer regnes som bekræftet uden æg, mælk, tomat og
      banan — det var kriteriet for at komme på listen; arkets gamle
      Valideret-kolonne ignoreres
- [x] Listen er søgbar under Filtrér-fanen, og ved scanning vises et hint,
      når varen ligner noget fra listen — "bekræft stadig mod emballagen"
- [x] Hver vare graduerer til en rigtig dom, første gang I scanner og
      bekræfter den. Genimport udskifter listen (idempotent).

Regnearket committes ALDRIG til git — det er jeres data. Læg det i
`/mnt/user/appdata/allergiscan/data/` og kør importen derfra.

---

## Fase 2 — Lav den brugbar i en butik (uge 2-3)

Nu ved du, hvad der faktisk irriterer. Sandsynlige kandidater:

- [ ] **Bekræftelseskøen har ingen skærm.** `GET /api/queue` findes, men
      frontend viser den ikke. Det er den mest sandsynlige mangel efter
      første indkøbstur — I opdager varer, I ville have bekræftet derhjemme.
- [ ] **Historik.** "Har vi scannet den her før?" `Scan`-tabellen har data,
      der er bare ingen visning.
- [ ] **Flere profiler i UI.** Modellen understøtter det, frontend viser kun
      den første.
- [ ] **Bedre kamera-UI.** Sigtefirkant, lommelygte-knap (`torch`-constraint),
      tydeligere feedback ved træf.

Gør ikke noget af det, før I har handlet med appen mindst to gange. Halvdelen
af listen viser sig at være ligegyldig, og der dukker noget op, der ikke står her.

---

## Fase 3 — Gør reglerne bedre med data (løbende)

- [ ] Brug `GET /api/ingredients/suggest?q=` efter hver indkøbstur til at se,
      hvilke stavemåder der faktisk dukker op i danske deklarationer, og
      tilføj dem til `allergens.yaml`
- [ ] Tilføj en test for hver ny regel — filen er allerede struktureret til det
- [ ] Overvej `maybe`-regler for de "måske"-ting, du nævnte i starten, med
      `severity: watch` i stedet for `strict`

**Bidrag rettelser tilbage til Open Food Facts.** Retter du en dansk
deklaration hos dem, får du den gratis næste gang, og alle andre danske
allergifamilier også. Det er billigere end at vedligeholde jeres egen kopi.

---

## Fase 4 — Den ER delt (skete august 2026)

Afsnittet hed »hvis I deler den, senere, måske aldrig«. Det skete i
stedet: appen ligger åbent på internettet gennem Cloudflare Tunnel, alle
kan scanne og se familiens bekræftelser, og kun familien godkender. Se
`.claude/skills/familiens-data/SKILL.md` for hvad der er offentligt, og
`tests/test_offentlig_flade.py` for grænsen skrevet som kode.

Det, listen sagde, og hvad der faktisk skete:

1. [ ] **Multi-tenancy i routingen.** Stadig sandt: `default_household()`
       returnerer altid husstand 1. Men det er nu et bevidst valg, ikke
       gæld — der er ÉN familie, og deres bekræftelser er det offentlige.
       Genåbnes kun af opgaven nedenfor.
2. [x] **Rate limiting** — på login (0.19.0), nøglet på afsenderens IP, så
       en fremmed ikke kan låse familien ude. Uploads behøvede den ikke:
       kun inviterede kan uploade.
3. [~] **Cloudflare Access på skrivestierne** — gjort ANDERLEDES og med
       vilje. Access står ikke foran; adgangen ligger i appen selv, rute
       for rute, med roller (`contributor` / `curator` / `admin`).
       `cfaccess.py` virker stadig, hvis Access nogensinde sættes op.
4. [x] **Postgres** — egen container siden 0.16.0, aktiv når
       `DATABASE_URL` er sat.

---

## Næste større spørgsmål — en profil, der kan deles

**Er det forsvarligt at lave en profil for et menneske, som kan deles?**
Et barn, eller en man bor sammen med og handler ind til.

Det er ikke en funktion, det er et spørgsmål — og det skal besvares, før
noget bygges. Fire ting gør det svært, og de skal alle fire have et svar:

1. **Det er helbredsoplysninger om et navngivet menneske.** Et
   profilnavn plus de aktive allergener er særlig kategori efter GDPR
   art. 9. At dele det er at videregive helbredsoplysninger — ikke at
   dele en indkøbsliste.
2. **Samtykke er ikke det samme for de to tilfælde.** En voksen, du bor
   sammen med, kan sige ja. Et barn kan ikke; forælderen siger ja på
   dets vegne — og barnet vokser op. Hvad sker der med profilen den dag,
   hun selv kan bestemme?
3. **Hvis dom gælder?** En dom hænger på (vare, allergen) pr. husstand,
   og grøn kræver et menneske, der har læst den fysiske pakke. Deler man
   en profil, stoler man så på en ANDENS bekræftelse for sit eget barn?
   Det er invarianten anvendt på tværs af mennesker, og det er det
   dybeste spørgsmål i hele opgaven.
4. **Appen er åben.** »Delt« skal defineres præcist: delt med én navngiven
   person, eller synlig for enhver med et link? De to har intet med
   hinanden at gøre teknisk, og kun det første er oplagt forsvarligt.

Rækkefølgen, hvis det skal bygges: `produktejer` presser spørgsmålet og
skriver historien, `data-og-sikkerhed` svarer på de fem faste spørgsmål
(formål, nødvendighed, opbevaring, adgang, følsomhed) FØR implementering.
Det er den slags, hvor en gættet beslutning er dyrere end en udskudt.

Og bemærk: punkt 1 i Fase 4 skal så genåbnes. `default_household()` er
kun forsvarlig, så længe der er én husstand.

---

## Fremtidig opgave — rigtige fotos til OCR-arbejdet, uden at de havner i git

**Problemet:** `ocr-deklarationer`-skillens egen første prioritet er »flere
rigtige fotos«. De 40 butiksfotos, der i sin tid valgte OCR-motoren,
findes ikke længere, og der ligger to i `data-runtime/billeder` på
udviklingsmaskinen. Enhver måling af en OCR-ændring er derfor gætværk —
og et regelsæt eller en pipeline, der kun er prøvet mod opdigtet tekst,
er ikke prøvet.

**Hvorfor det ikke bare er at lægge nogle billeder i repoet:** det er
PUBLIC. Deklarationsfotos er taget i familiens køkken og i butikker, og
et enkelt uheldigt billede er offentligt for altid, også efter en
sletning — git glemmer ikke.

**Formen, der skal bygges:**

1. **En lokal konto med lav rettighed** til det arbejde, så en agent kan
   hente fotos gennem appen i stedet for at få dem stukket i hånden.
   `contributor` kan allerede uploade; det, der mangler, er en måde at
   *hente ned* i bulk.
2. **En CLI-kommando**, fx `python -m app.cli fotos-ud <mappe>`, der
   kopierer fra `DATA_DIR/billeder` til en mappe, git ikke ser.
   `data-runtime/` er allerede gitignoreret — nye placeringer skal
   dækkes samme sted, FØR de bruges.
3. **En vagt i CI.** `hygiene`-jobbet i `.github/workflows/deploy.yml`
   afviser i dag `.db`, `.sqlite`, `.xlsx` og hemmeligheder — men ikke
   billeder. Tilføj en regel, der afviser nye `.jpg`/`.jpeg`/`.heic`
   med en hvidliste for de ikoner, der legitimt hører til
   (`app/static/apple-touch-icon.png` er den eneste i dag). Så er det
   ikke længere disciplin, der holder dem ude.

**Rækkefølge:** vagten (3) FØRST. Den koster fem linjer og gør de to
andre trin sikre at arbejde med. Derefter eksporten, og til sidst
kontoen, hvis der overhovedet viser sig et behov for at gå gennem
appen frem for filsystemet.

---

## Ting jeg bevidst har ladet være

**Offline-tilstand.** Du sagde, det ikke er nødvendigt, og en service worker
med cache-invalidering ville koste mere, end det smager. Men bemærk: mister
telefonen dækning midt i Bilka, dør appen. Sker det ofte, er et lille
localStorage-cache af de sidst scannede varer det billigste plaster.

**Nutrition-data, Nutri-Score, e-numre.** Open Food Facts har det hele. Det
er også den hurtigste vej til en app, der gør fire ting halvdårligt.

**Selvhostede fonte.** Beskrevet i `NOTICE.md`, ikke gjort. Ét
tredjepartsopslag pr. sidevisning, og appen virker uden dem.

**Push-notifikationer ved opskriftsændringer.** Lyder rigtigt, men OFF
opdaterer sjældent nok til, at det ville være støj snarere end signal.

---

## Den ene ting, der kan gå galt

Appen kan blive *for* troværdig. Når 200 varer er grønne, og systemet har haft
ret i et halvt år, holder man op med at læse etiketten. Og så ændrer
producenten opskriften.

`ingredients_hash`-mekanismen fanger det, når OFF opdaterer deres data — men
OFF opdateres af frivillige, ofte måneder efter. Der er et vindue, hvor appen
siger grønt om en vare, der har ændret sig.

Derfor står advarslen fast i bunden af hver domsskærm, og derfor må den ikke
fjernes, uanset hvor meget den fylder. Den er ikke juridisk pynt.
