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

## Fase 4 — Hvis I deler den (senere, måske aldrig)

Rækkefølgen her er ikke til forhandling, hvis fremmede skal have adgang:

1. [ ] **Multi-tenancy i routingen.** `default_household()` returnerer altid
       husstand 1. Skemaet understøtter flere, koden gør ikke.
2. [ ] **Rate limiting.** Læsesiden er åben. `slowapi` eller Cloudflare
       WAF-regler.
3. [ ] **Cloudflare Access** på skrivestierne i stedet for lokale
       adgangskoder — `cfaccess.py` er klar, det kræver kun konfiguration
4. [ ] **Postgres** i stedet for SQLite, når flere skriver samtidigt

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
