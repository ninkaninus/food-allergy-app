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

**Gjort i 0.23.0:** `GET /api/korpus` (`require_user`, så en `contributor`
kan læse det uden at kunne bekræfte noget) samler, pr. vare med mindst ét
foto eller en deklarationstekst, navn, deklaration,
`deklaration_gik_gennem_bekraeftelse` (`product.source == "manual"` —
IKKE et facit, se `ocr-deklarationer`-skillen for begge de forkerte
retninger, det kan vippe) og fotoenes URL'er. `scripts/hent-korpus.py`
logger ind (kodeord tastes interaktivt, hvis `KORPUS_KODEORD` ikke er
sat), henter korpusset og lægger billeder + `manifest.json` i en mappe
uden for repoet (`~/allergiscan-korpus` som standard), idempotent, og
siger hvor mange par der rent faktisk er BRUGBARE (deklarationsfoto +
bekræftet tekst), ikke bare hvor mange billeder der ligger der.

**Vagten i CI ER lavet** (`hygiene`-jobbet i
`.github/workflows/deploy.yml`), men dækker for lidt — se »Hullet i
vagten« herunder. At UDVIDE den regel rører stadig
`.github/workflows/`, som hører til vedligeholderens
infrastruktur-område, ikke `implementer`-agentens — den efterprøvede,
endnu ikke anvendte regel står der i stedet for i selve workflow-filen.

**Problemet, oprindeligt:** `ocr-deklarationer`-skillens egen første
prioritet er »flere rigtige fotos«. De 40 butiksfotos, der i sin tid
valgte OCR-motoren, findes ikke længere, og der ligger to i
`data-runtime/billeder` på udviklingsmaskinen. Enhver måling af en
OCR-ændring er derfor gætværk — og et regelsæt eller en pipeline, der kun
er prøvet mod opdigtet tekst, er ikke prøvet.

**Hvorfor det ikke bare er at lægge nogle billeder i repoet:** det er
PUBLIC. Deklarationsfotos er taget i familiens køkken og i butikker, og
et enkelt uheldigt billede er offentligt for altid, også efter en
sletning — git glemmer ikke.

### Hullet i vagten

`hygiene`-jobbet afviser i dag committede `.jpe?g`/`.png`/`.heic`/
`.webp`/`.gif`/`.tiff?`/`.bmp` mod en eksplicit hvidliste
(`app/static/apple-touch-icon.png`). Efterprøvet lokalt: det overser
`manifest.json` (husstandens fulde varefortegnelse i én fil — den mest
sandsynlige fil at få committet fra en korpusmappe), en fil helt uden
endelse, og `.avif`/`.jfif`/`.dng`/`.pdf`. Og den kører EFTER et push til
et public repo — den stopper udgivelsen af imaget, ikke selve
eksponeringen; det er stadig kun en lokal pre-commit-hook, der ville gøre
det. Skriv ikke, at »disciplin holder dem ude« — jobbet ER disciplinen,
bare for sent i forløbet til at forhindre selve committet.

Den udvidede regel, testet lokalt mod en synteseliste af filnavne (ikke
mod en rigtig commit):

```bash
BILLED_HVIDLISTE='^app/static/apple-touch-icon\.png$'
if git ls-files | grep -iE '\.(jpe?g|png|heic|heif|webp|gif|tiff?|bmp|avif|jfif|dng|pdf)$' \
     | grep -Ev "$BILLED_HVIDLISTE"; then
  echo "::error::et billede er committet — familiens fotos må aldrig i git."
  fail=1
fi
if git ls-files | grep -E '(^|/)manifest\.json$'; then
  echo "::error::manifest.json er committet — det er husstandens fulde varefortegnelse (scripts/hent-korpus.py)"
  fail=1
fi
# Filer uden endelse, der reelt ER et billede — grep på filnavn ser dem ikke.
while IFS= read -r f; do
  case "$(basename "$f")" in *.*) continue ;; esac
  mime=$(git cat-file -p "HEAD:$f" 2>/dev/null | file -b --mime-type -)
  case "$mime" in
    image/*|application/pdf)
      echo "::error::$f har ingen filendelse, men ER et billede ($mime)"
      fail=1 ;;
  esac
done < <(git ls-files)
```

Efterprøv ved midlertidigt at `git add -f` en jpg, en `manifest.json` og
en billedfil uden endelse, og se jobbet fejle på alle tre, før reglen
regnes for færdig.

**Endnu et lag, samme grund til ikke selv at røre det:** en `.dockerignore`
i repo-roden, så en korpusmappe aldrig kan havne i imaget, selv hvis
`_sikker_destination()` i `scripts/hent-korpus.py` en dag skulle blive
omgået. Rører `Dockerfile`s byggekontekst, derfor samme
infrastruktur-grænse:

```
/korpus/
/allergiscan-korpus/
manifest.json
*.jpg
*.jpeg
*.png
*.heic
*.webp
*.gif
!app/static/apple-touch-icon.png
```

**Næste skridt herfra, i rækkefølge:**

1. Udvid vagten (regel ovenfor) — af nogen med adgang til at røre
   `.github/workflows/`.
2. Brug scriptet i praksis, et par gange, mens korpusset stadig er lille
   (20 varer, 3 med fotos i skrivende stund) — det finder formodentlig
   noget, beskrivelsen ikke forudså.
3. **Et måleapparat**, når korpusset rent faktisk er stort nok til at
   sige noget: et lille script, der kører begge OCR-motorer mod hvert
   billede i `manifest.json` og sammenligner med `deklaration` for de
   par, hvor `deklaration_gik_gennem_bekraeftelse` er sand — præcis den
   slags tal, der stod i `ocr-deklarationer`-skillen om de 40 forsvundne
   fotos. Ikke bygget nu, fordi et måleapparat til n=3 kun ville måle
   støj.

---

## Fremtidig opgave — én database i stedet for to

Bekræftet 23. august 2026: prod kører **Postgres**. Vagten i 0.21.1 er
beviset — havde `DATABASE_URL` ikke været sat, ville containeren have
nægtet at starte.

Men koden understøtter stadig begge, og det koster mere, end det ligner:

- **Migreringer skal skrives to gange.** Postgres kan
  `ALTER TABLE ... DROP CONSTRAINT`; SQLite kan ikke og skal have hele
  tabellen bygget om. I 0.21.0 var det SQLite-grenen, der havde en test,
  og Postgres-grenen, der kørte i drift. Vendt på hovedet.
- **Den testede vej er ikke produktionsvejen.** Fremmednøgler håndhæves
  ikke på SQLite uden `PRAGMA foreign_keys=ON`. Præcis den forskel gav en
  500 i drift i 0.20.0, som testene ikke kunne se.
- **Falsk grønt.** SQLite-testen af fotomigreringen bestod på kode, der
  slettede alle fotorækker, fordi fiksturet var skrevet i hånden uden de
  indeks, produktionen har.

**Rækkefølgen betyder noget.** Først testene over på Postgres — en
`services: postgres` i GitHub Actions og en docker-container lokalt, det
tager fire sekunder at starte. FØRST derefter kan SQLite-grenen slettes.
At fjerne kode, man ikke har dækning for, er den forkerte vej rundt.

Prøven, der afgør om det er værd at gøre: kan en fejl i den ene dialekt
slippe forbi CI? I dag: ja.

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
