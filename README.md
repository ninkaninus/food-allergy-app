# AllergiScan

Selvhostet stregkode-tjek af fødevarer mod en familiespecifik allergiliste.
Kører på unRAID, nås via Cloudflare Tunnel. Data fra Open Food Facts,
domme fra mennesker.

Læsning er åben for alle. Kun bekræftelser kræver login.

**Start her:** [`ROADMAP.md`](ROADMAP.md) for hvad du gør nu ·
[`deploy/UNRAID.md`](deploy/UNRAID.md) for deploy og auto-deploy ·
[`CLAUDE.md`](CLAUDE.md) hvis du (eller en kodeassistent) skal ændre i koden ·
[`deploy/cloudflared/README.md`](deploy/cloudflared/README.md) for ingress ·
[`NOTICE.md`](NOTICE.md) for licenskrav.

---

## Den ene regel, alt andet hænger på

**Motoren kan kun gøre en vare rød eller gul. Aldrig grøn.**

`State.FREE` kan udelukkende sættes gennem `POST /api/products/{ean}/confirm`,
som kræver en session. Fandt motoren ingenting, er svaret `unknown` — ikke
"sikker". To tests håndhæver det (`test_engine_never_returns_free`,
`test_ocr_mode_still_never_returns_free`).

---

## Adgangsmodellen

| | Kræver login | Hvorfor |
|---|---|---|
| Scanne en vare | nej | Dagplejen skal bare kunne scanne |
| Vælge hvad der tjekkes for | nej | Ligger i `localStorage`, sendes som `?allergens=` |
| Filtrere i ingredienser | nej | Ingen personoplysninger involveret |
| Bekræfte en vare | **ja** | En grøn vare er en påstand, nogen skal stå på mål for |
| OCR | **ja** | Beskytter mod at fremmede kører billeder gennem din CPU |

Valgene ligger i browserens `localStorage` under `allergiscan.prefs.v1`.
Ingen cookie-banner, ingen konto, ingenting at oprette for dagplejen —
hun åbner linket, sætter kryds i Mælkeprotein og Æg, og scanner.

### Hvilken auth skal du vælge?

Du nævnte fire muligheder. Kort om hver:

**Supabase auth** — virker, men trækker en online afhængighed ind i en app,
der ellers er selvindeholdt, og løser ikke det, du faktisk er bekymret for:
serveren skal stadig kunne nås fra butikken.

**Google auth** — god brugeroplevelse for dagplejen (hun har en Google-konto),
men kræver OAuth-opsætning og et registreret redirect-domæne. Overkill til to
brugere.

**Lokal brugernavn/adgangskode** — bygget og default. argon2id, sessioner hvor
kun `sha256(token)` gemmes, og oprettelse afvises hvis adgangskoden findes i
kendte datalæk. Det sidste er svaret på "sikre der ikke er genbrugte
passwords": `auth.py` slår op hos Have I Been Pwned med k-anonymitet — kun de
første fem tegn af SHA-1-hashen forlader maskinen, HIBP sender ~800 suffikser
retur, og matchningen sker lokalt. Adgangskoden sendes aldrig nogen steder.
Slå fra med `CHECK_PWNED_PASSWORDS=0`.

**Authelia foran** — også bygget, som en profil i compose. Appen stoler på
`Remote-User`/`Remote-Groups` når `TRUST_PROXY_AUTH=1`, og opretter brugeren
ved første besøg. `deploy/Caddyfile` strimler de headere fra indgående
requests først — uden det er headeren et gratis login, og det er ikke til
forhandling.

De to sidste kan køre samtidig. Start med lokale brugere; læg Authelia på
hvis I bliver flere end en håndfuld.

### Ingress: Cloudflare Tunnel

Tunnellen gør mere end at spare en portforwarding. **Kameraet kræver HTTPS** —
`getUserMedia` virker ikke i et usikkert context, så på `http://192.168.1.x:8420`
nægter både Safari og Chrome adgang til kameraet, og stregkodescanneren er død.
Tunnellen giver et rigtigt certifikat, og dermed virker kernefunktionen.

Fuld opsætning i [`deploy/cloudflared/README.md`](deploy/cloudflared/README.md).

**Vigtigt:** sæt aldrig `TRUST_PROXY_AUTH=1` sammen med tunnellen uden en
Caddy imellem. Trafikken går direkte til containeren, og ingen strimler
`Remote-*` undervejs. Brug i stedet Cloudflare Access — `app/cfaccess.py`
validerer JWT-signaturen, og den kan ikke forfalskes.

---

## To lag, to opgaver

Du spurgte, om data bare kunne have alle ingredienser, så man kan filtrere på
det hele. Svaret er ja, og du bør — men det må aldrig blive det, der afgør,
om noget er sikkert.

Grunden er dækningsasymmetri. Open Food Facts' parser opløser en pæn del af
danske ingredienstekster til taksonomi-id'er (`en:whole-milk`), men resten
kommer tilbage som `da:<rå tekst>` eller slet ikke. Filtrerer du kun på tags,
er en uopløst ingrediens usynlig — og usynlig ligner fraværende.

|  | Indeks (`ingredients.py`) | Regelsæt (`matcher.py`) |
|---|---|---|
| Dækning | alle ingredienser, alle varer | 17 allergener (EU-14 + jordbær, banan, tomat) |
| Præcision | lav, substring-matchning | høj, maskering og ordgrænser |
| Fejler mod | **overekskludering** | **overadvarsel** |
| Bruges til | at finde og filtrere | at afgøre sikkerhed |
| Kan sige "sikker" | nej | nej (kun mennesker kan) |

Begge fejler i den ufarlige retning. Filtrerer du "uden mælk", ryger
kokosmælk-varen også ud — irriterende, men harmløst når du browser.
Regelsættet ville aldrig gøre det.

**Broen mellem dem** er `GET /api/ingredients/suggest?q=`. Når I finder noget
nyt, hun ikke tåler, graver den i jeres eget korpus efter de stavemåder, der
faktisk optræder i danske deklarationer — så synonymlisten i `allergens.yaml`
skrives ud fra virkeligheden i stedet for fantasien.

---

## Sådan læser matcheren en deklaration

Dansk sammensætter ord, og det ødelægger naiv substring-matchning:

| Tekst | Naiv match | AllergiScan |
|---|---|---|
| kakaosmør | smør → mælk | intet |
| kokosmælk | mælk | intet |
| ægte vanilje | æg | intet |
| mælkebøtterod | mælk | intet |
| **laktosefri mælk** | — | **mælk** |
| jordbæraroma | rød | gul |

To mekanismer:

1. **Ordgrænse før, ikke efter.** `(?<![a-zæøå])mælk` rammer `mælkepulver`
   (præfiks) men ikke `kokosmælk` (suffiks). Sammensætninger med allergenet
   bagest — `kærnemælk`, `skummetmælk` — står eksplicit i `contains`.
2. **Maskering før matchning.** Undtagelser erstattes med `░` af samme længde,
   *før* de positive mønstre kører. Offsets bevares, så frontend kan
   highlighte præcist. `laktosefri` maskeres væk, og det efterfølgende `mælk`
   fanges stadig — korrekt, laktosefri mælk indeholder fuld mængde kasein.

Passene i rækkefølge:

```
exclude + maybe maskeres  →  contains-pass   (rød)
exclude maskeres          →  maybe-pass      (gul)
                          →  fuzzy-pass      (kun ved OCR)
```

---

## OCR

Foto af deklarationen → tekst → matcher → redigerbar bekræftelsesskærm.
Kører lokalt med Tesseract og dansk sprogmodel. Billedet gemmes ikke og
forlader ikke serveren.

**Målt på et syntetisk emballagefoto:** 89,8% konfidens, og alligevel blev
`skummetmælkspulver` læst som `skummetmaalkspulver` og `jordbær` som
`jordbzer`. Eksakt matchning missede begge — altså netop de to allergener,
der stod på pakken.

Derfor har matcheren et fuzzy-pas, der kun kører på OCR-tekst: æ/ø/å foldes
til ASCII, cifre der ligner bogstaver rettes (`0→o`, `1→l`, `@→o`), og
derefter tillades en til to redigeringers afvigelse på ord over fem tegn.
`maalk` og foldede `maelk` er én redigering fra hinanden. Begge allergener
fanges nu, uden falske positiver på rene deklarationer — der er tests for
begge dele.

Fuzzy-træf markeres `approximate: true`, og skærmen siger "OCR læste
«skummetmaalkspulver»" i stedet for at påstå noget. Det er stadig et gæt,
og et menneske skal stadig kigge på pakken.

---

## Kør det

```bash
cd /mnt/user/appdata
git clone git@github.com:ninkaninus/food-allergy-app.git allergiscan
cd allergiscan

cp .env.example .env
$EDITOR .env                 # sæt mindst OFF_USER_AGENT

docker compose up -d --build
docker compose exec allergiscan python -m app.cli adduser dig@example.dk "William"
```

Alle indstillinger kommer fra `.env`, som er gitignoreret. `.env.example`
dokumenterer dem hver især — læs kommentaren ved `TRUST_PROXY_AUTH`, den er
den eneste, der kan give fremmede skriveadgang hvis den sættes forkert.

Åbn `http://<unraid-ip>:8420`, læg den på hjemmeskærmen.

Valgfrie profiler:

```bash
docker compose --profile postgres up -d    # Postgres i stedet for SQLite
docker compose --profile proxy up -d       # Caddy + Authelia
```

Proxy-profilen kræver, at du først kopierer eksempelfilerne og udfylder dem —
de rigtige udgaver er gitignoreret, netop så en rigtig Authelia-hemmelighed
aldrig havner i repoet:

```bash
cp deploy/Caddyfile.example deploy/Caddyfile
cp deploy/authelia/configuration.example.yml deploy/authelia/configuration.yml
cp deploy/authelia/users_database.example.yml deploy/authelia/users_database.yml

# tre uafhængige hemmeligheder til configuration.yml
for i in 1 2 3; do openssl rand -base64 48; done

# password-hash til users_database.yml
docker run --rm authelia/authelia:latest \
  authelia crypto hash generate argon2 --password 'din-adgangskode'
```

Postgres er ikke nødvendigt for én husstand — SQLite klarer det fint. Slå den
til hvis flere skriver samtidigt. `DATABASE_URL` styrer det; `psycopg`
importeres aldrig når du kører på SQLite (relevant for LGPL, se `NOTICE.md`).

Lokalt:

```bash
pip install -r requirements.txt
DATA_DIR=./data RULES_PATH=./data/allergens.yaml COOKIE_SECURE=0 \
  uvicorn app.main:app --reload
python -m pytest tests/ -q     # 52 tests
```

---

## iOS

`BarcodeDetector` findes kun i Chrome på Android. Safari har den ikke, så
frontend falder tilbage til `zxing-wasm`, som ligger vendoret i
`app/static/vendor/zxing/` — ikke fra et CDN. Fallbacken er lidt langsommere
(den kører på canvas-frames med 120 ms mellemrum) og siger det i UI'et.

Fontene hentes stadig fra Google Fonts. Alle tre er OFL og må hostes selv;
`NOTICE.md` beskriver hvordan, hvis du vil af med opslaget.

---

## Datamodel

```
household ──┬── app_user ─── session_token   (kun sha256 af tokenet gemmes)
            ├── profile ──── profile_allergen ──── allergen
            ├── verdict ──── (product_ean, allergen_id, state, basis,
            │                 evidence, ingredients_hash, decided_by)
            ├── review_item
            └── scan
product ────── product_ingredient ──── ingredient
```

**Domme hænger på parret (produkt, allergen)** — ikke på produktet. Tilføjer I
soja i morgen, står de varer, I allerede har godkendt for mælk og æg, uændret.
Vokser hun fra banan, slår I den fra i profilen, og historikken bevares.

**Hver dom gemmer `ingredients_hash`.** Ændrer producenten opskriften på samme
EAN, matcher hashen ikke, godkendelsen markeres `stale`, og varen ryger tilbage
i køen med `reason=recipe_changed`. Det er den eneste automatiske beskyttelse
mod stille opskriftsændringer, der findes.

**Product-tabellen er ODbL-afledt, verdict-tabellen er jeres eget arbejde.**
Se `NOTICE.md` — den adskillelse er hele grunden til, at I kan dele appen uden
at share-alike smitter af på jeres verifikationsarbejde.

---

## API

| | Login | |
|---|---|---|
| `GET /api/scan/{ean}?allergens=a,b` | nej | slå op, evaluér, log, kø-tilføj |
| `GET /api/allergens` | nej | regelsæt med mønstertællinger |
| `GET /api/products?exclude=&include=` | nej | filtrering på hele indekset |
| `GET /api/ingredients/suggest?q=` | nej | synonymforslag fra korpus |
| `GET /api/attribution` | nej | ODbL-kreditering med antal poster |
| `POST /api/auth/login` `logout` `me` | — | sessioner |
| `POST /api/products/{ean}/confirm` | **ja** | eneste vej til grøn |
| `POST /api/ocr` | **ja** | foto → tekst + forhåndstjek |
| `POST /api/auth/users` | **admin** | opret bruger, HIBP-tjekket |

---

## Kendte begrænsninger

- **Ingen rate limiting.** Læsesiden er åben; brug Cloudflare WAF-regler eller
  `slowapi` hvis den skal være offentligt tilgængelig.
- **Ingen billedlagring.** OCR-billeder kastes væk efter læsning. Vil I have
  et arkiv af deklarationer, skal der en volume og en oprydningspolitik til.
- **Ingen Excel-import.** `confirm` er idempotent, så et importscript mod jeres
  eksisterende ark er ~30 linjer.
- **`default_household()` returnerer altid husstand 1.** Multi-tenancy er i
  skemaet, men ikke i routingen.

Licenser og krediteringskrav: se `NOTICE.md`.
