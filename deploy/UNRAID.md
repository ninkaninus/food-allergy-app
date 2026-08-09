# Deploy på unRAID — trin for trin

To halvdele:

1. **Førstegangsopsætning** — manuel, én aften, fase 0 i [`ROADMAP.md`](../ROADMAP.md).
2. **Auto-deploy** — pull-baseret, som Argo CD kogt ned til én maskine:
   git er den ønskede tilstand, en agent på serveren poller og afstemmer.
   GitHub har **ingen** adgang til serveren — ingen SSH-nøgler i CI, ingen
   webhooks ind, ingen åbne porte. Serveren har kun *læse*-adgang den anden vej.

Hvert trin slutter med et **Tjek** — gå ikke videre, før det er grønt.

> Efterprøvet august 2026: plugin-navne, klikveje i Cloudflare/GitHub og
> versionsnumre i CI-workflowet er slået op, ikke husket. Afviger et
> menupunkt, er det formentlig omdøbt siden — led efter det nærmeste.

## Det skal du have på forhånd

- **unRAID 7.x** med terminaladgang (ikonet `>_` øverst til højre i web-UI'et,
  eller SSH som root).
- **Et domæne i din Cloudflare-konto.** Tunnellen skal hænge et hostnavn på
  et domæne, som Cloudflare styrer DNS for. Gratis-planen er nok. Har du
  intet domæne, er det her, du starter — alt andet kan vente.
- **Repoet pushet til GitHub** (`ninkaninus/food-allergy-app`).
- To plugins fra **Apps**-fanen (Community Applications):
  - **Compose Manager Plus** — det gamle plugin "Docker Compose Manager" er
    udgået og skal ikke bruges; Plus er den vedligeholdte afløser.
  - **User Scripts**
- **git skal du IKKE installere.** Stock unRAID har ingen git, og det er
  indregnet: både første klon og agenten kører git i en engangs-container
  (`alpine/git`), når kommandoen mangler på hosten.

Filsystem-layout, som alle kommandoer herunder antager:

```
/mnt/user/appdata/allergiscan/
  repo/        git-klonen — compose køres herfra
  data/        databasen (DATA_PATH i .env)
  secrets/     nøgler og tokens, chmod 700 — ALDRIG i git
  deploy.log   agentens log
```

`/root` på unRAID ligger i RAM og overlever ikke en genstart — derfor bor
nøglerne i appdata og ikke i `~/.ssh`.

---

## Del 1: Førstegangsopsætning

### Trin 1 — mapper og klon

Åbn unRAID-terminalen og kør:

```bash
mkdir -p /mnt/user/appdata/allergiscan/{data,secrets}
chmod 700 /mnt/user/appdata/allergiscan/secrets

# Offentligt repo: klon over https (kræver ingen nøgler)
docker run --rm -v /mnt/user/appdata/allergiscan:/work -w /work \
  alpine/git clone https://github.com/ninkaninus/food-allergy-app.git repo
```

Er repoet **privat**, skal der en read-only deploy-nøgle til *før* klonen —
lav den nu (trin 6b) og klon så over SSH:

```bash
docker run --rm -v /mnt/user/appdata/allergiscan:/work -w /work \
  -v /mnt/user/appdata/allergiscan/secrets:/mnt/user/appdata/allergiscan/secrets:ro \
  -e GIT_SSH_COMMAND="ssh -i /mnt/user/appdata/allergiscan/secrets/deploy_key -o UserKnownHostsFile=/mnt/user/appdata/allergiscan/secrets/known_hosts -o StrictHostKeyChecking=accept-new" \
  alpine/git clone git@github.com:ninkaninus/food-allergy-app.git repo
```

Valget her afgør, hvordan agenten senere henter: https-klon → ingen nøgle
nødvendig; ssh-klon → agenten finder selv nøglen i `secrets/`.

**Tjek:** `ls /mnt/user/appdata/allergiscan/repo` viser `app`,
`docker-compose.yml`, `deploy` m.m.

### Trin 2 — .env

```bash
cd /mnt/user/appdata/allergiscan/repo
cp .env.example .env
nano .env
```

Ret som minimum:

| Linje | Til |
|---|---|
| `OFF_USER_AGENT=` | din rigtige mailadresse i parentesen — OFF kræver det |
| `HOUSEHOLD_NAME=`, `PROFILE_NAME=` | jeres navne, valgfrit |

Lad resten stå. `COMPOSE_PROFILES=tunnel` og `DATA_PATH` passer allerede
til layoutet, og `APP_IMAGE` skal du aldrig selv røre — den ejes af agenten.

**Tjek:** `grep OFF_USER_AGENT .env` viser din mail.

### Trin 3 — byg, start, opret bruger

```bash
cd /mnt/user/appdata/allergiscan/repo
docker compose up -d --build allergiscan
```

Første byg henter python-imaget og installerer Tesseract med dansk
sprogmodel — regn med nogle minutter. (`allergiscan` til sidst er med vilje:
tunnel-containeren kan først starte, når der er et token i trin 4.)

Opret din bruger — kommandoen spørger efter adgangskode (mindst 14 tegn,
og den slås op mod Have I Been Pwned):

```bash
docker compose exec allergiscan python -m app.cli adduser dig@example.dk "William"
```

**Tjek:**

```bash
docker ps --filter name=allergiscan     # STATUS skal ende med "(healthy)" efter ~1 min
curl -s http://127.0.0.1:8420/healthz   # skal svare {"ok":true}
```

Bemærk: porten er kun bundet til 127.0.0.1 på hosten. Du kan *ikke* nå appen
fra en anden maskine på LAN — det er meningen; tunnellen bliver den eneste
vej ind. (Vil du alligevel LAN-teste: sæt `APP_BIND=0.0.0.0` i `.env`,
`docker compose up -d`, og husk at kameraet stadig kun virker over HTTPS.)

### Trin 4 — Cloudflare Tunnel

Klikvej i Cloudflare (menupunkter pr. august 2026):

1. [dash.cloudflare.com](https://dash.cloudflare.com) → vælg din konto →
   **Zero Trust** i venstremenuen (åbner one.dash.cloudflare.com).
2. **Networking → Tunnels → Create a tunnel**.
3. Vælg **Cloudflared** som connector, giv den navnet `allergiscan`,
   **Save tunnel**.
4. På siden "Install and run a connector": vælg **Docker**. Du får vist en
   kommando med `--token eyJhbGci…`. **Kopiér kun den lange streng efter
   `--token`** — kommandoen selv skal ikke køres; compose-filen har allerede
   en cloudflared-service.
5. I unRAID-terminalen:

   ```bash
   cd /mnt/user/appdata/allergiscan/repo
   nano .env          # find TUNNEL_TOKEN-linjen, fjern # og indsæt tokenet
   docker compose up -d
   ```

6. Tilbage i Cloudflare-guiden: connectoren skifter til **Connected**
   (ellers: `docker logs allergiscan-tunnel`).
7. Videre til ruten (hedder **Routes**/"Published application" eller
   **Public hostname** afhængigt af dashboard-udgave):
   - Subdomain: `allergi` — Domain: dit domæne
   - Service/URL: **`http://allergiscan:8000`** (containernavnet på
     Docker-netværket — ikke serverens IP)
   - **Save**.

**Tjek:** åbn `https://allergi.ditdomæne.dk/healthz` på din *telefon* over
mobilnet (ikke wifi) — svarer den, virker hele kæden udefra.

### Trin 5 — telefonerne og de ti varer

1. Åbn `https://allergi.ditdomæne.dk` på begge telefoner.
2. Læg på hjemmeskærmen: iPhone → del-ikonet → "Føj til hjemmeskærm";
   Android/Chrome → menu → "Føj til startskærm".
3. Sæt kryds i de allergener, der skal tjekkes for (gemmes i telefonens
   localStorage — dagplejerens telefon skal sætte sine egne kryds).
4. Log ind på din egen telefon med brugeren fra trin 3.
5. Scan ti varer fra køkkenet. Noter to ting: hvor mange OFF kender, og om
   scanningen på iPhone (zxing-fallbacken) er til at holde ud.

**Tjek:** kameraet åbner, en stregkode giver et svar. Første grønne vare
kræver, at du bekræfter den mod den fysiske emballage — det er meningen,
motoren kan ikke sige grønt selv.

Gør trin 1-5 færdige, *før* du tænder auto-deploy — så har agenten en kendt
god kørende version at falde tilbage på.

---

## Del 2: Auto-deploy

### Sådan hænger det sammen

```
push til main ──► GitHub Actions: 52 tests ──► image til GHCR, tagget sha-<commit>
                                                        ▲
   unRAID (hvert 5. minut, User Scripts):               │ pull (read-only)
   git fetch ── ny commit? ── findes sha-imaget? ───────┘
        │                          │
        │                          └─ nej: CI kører stadig eller fejlede → vent
        └─ ja: reset --hard, pin APP_IMAGE, compose up
                    │
                    ├─ healthy  → gem commit som "sidste gode"
                    └─ unhealthy → rul tilbage til sidste gode commit + image
```

Sikkerhedsegenskaberne, i rækkefølge efter hvor meget de bærer:

- **Pull, ikke push.** Der findes ingen vej ind til serveren for at deploye.
  CI'en kender ikke serveren; den lægger bare et image på en hylde.
- **Testene er porten.** Fejler én test — herunder de fire invariant-tests,
  der forbyder motoren at sige grønt — bygges der intet image, og agenten
  har bogstaveligt talt ingenting at rulle ud.
- **Alt er pinned til commit-SHA.** Agenten deployer `sha-<commit>`, aldrig
  `latest`. Compose-filer og image kommer fra præcis samme commit, og
  rollback er bare den forrige SHA.
- **Serverens legitimationer kan kun læse.** Deploy-nøglen er read-only,
  GHCR-tokenet har kun `read:packages`. Bliver serveren kompromitteret,
  kan den ikke skrive til jeres repo.

### Trin 6a — GitHub: første CI-kørsel og pakkens synlighed

Workflowet ligger allerede i repoet (`.github/workflows/deploy.yml`) og
bruger det indbyggede `GITHUB_TOKEN` — der er **ingen secrets at oprette**.

1. Push til main (eller lav en tom commit: `git commit --allow-empty -m "CI" && git push`).
2. GitHub → repoet → **Actions**-fanen → kørslen "Test, byg og udgiv" skal
   ende grøn. Test-jobbet kører de 52 tests; byg-jobbet skubber imaget.
3. Gå til repoets forside → **Packages** i højre spalte →
   `food-allergy-app`. Findes den, virker CI-kæden.

**Anbefalet: gør pakken offentlig**, så serveren intet token skal bruge
(koden er allerede åben, og imaget indeholder intet hemmeligt — `.env` og
databasen ligger uden for imaget):

Pakkesiden → **Package settings** (tandhjul, nederst til højre) →
**Danger Zone → Change package visibility → Public** → skriv pakkenavnet →
bekræft.

Vil du holde pakken privat i stedet: GitHub → dit profilbillede →
**Settings → Developer settings → Personal access tokens → Tokens (classic)**
→ **Generate new token (classic)** → sæt **kun** fluebenet `read:packages` →
generér, kopiér. (Det *skal* være classic — fine-grained tokens virker
fortsat ikke pålideligt mod ghcr.io, efterprøvet august 2026.) Læg det på
serveren:

```bash
nano /mnt/user/appdata/allergiscan/secrets/ghcr_token    # indsæt, én linje
chmod 600 /mnt/user/appdata/allergiscan/secrets/ghcr_token
```

**Tjek** (fra unRAID, uanset valg):
`docker pull ghcr.io/ninkaninus/food-allergy-app:latest` lykkes.
(Privat pakke: log først ind med
`docker login ghcr.io -u ninkaninus --password-stdin < /mnt/user/appdata/allergiscan/secrets/ghcr_token`.)

### Trin 6b — kun privat repo: deploy-nøgle

Offentligt repo klonet over https: **spring dette trin over.**

```bash
ssh-keygen -t ed25519 -N "" -C allergiscan-deploy \
  -f /mnt/user/appdata/allergiscan/secrets/deploy_key
ssh-keyscan github.com > /mnt/user/appdata/allergiscan/secrets/known_hosts
cat /mnt/user/appdata/allergiscan/secrets/deploy_key.pub
```

GitHub → repoet → **Settings → Deploy keys → Add deploy key** → indsæt
`.pub`-linjen → lad **"Allow write access" være slået fra** → Add key.
Sammenlign gerne `known_hosts` med GitHubs offentliggjorte fingerprints —
søg "GitHub's SSH key fingerprints" på docs.github.com.

**Tjek:**

```bash
cd /mnt/user/appdata/allergiscan/repo
GIT_SSH_COMMAND="ssh -i /mnt/user/appdata/allergiscan/secrets/deploy_key -o UserKnownHostsFile=/mnt/user/appdata/allergiscan/secrets/known_hosts" \
  git fetch origin main && echo OK
```

(Uden git på hosten: agenten tester det samme i næste trin.)

### Trin 7 — agenten

Kør den først **én gang i hånden** og se, hvad den gør:

```bash
/mnt/user/appdata/allergiscan/repo/deploy/autodeploy.sh
```

Forventet output, linje for linje (SHA'er vil variere):

```
2026-08-06 21:03:12  deployer 664d505... (fra ac73ad2)
2026-08-06 21:03:31  ok — 664d505... kører og er healthy
```

Kører du den straks igen, skal den være **helt tavs** — afstemt tilstand er
ingen output. Fejler den i stedet med "intet image for … endnu", er CI ikke
færdig eller pakken ikke læselig — tilbage til trin 6a's tjek.

Så på skema. unRAID → **Settings → User Scripts** (under User Utilities) →
**Add New Script** → navn `allergiscan-deploy` → klik på tandhjulet ved
scriptet → **Edit Script** → indsæt:

```bash
#!/bin/bash
#description=Pull-baseret auto-deploy af AllergiScan. Log: /mnt/user/appdata/allergiscan/deploy.log
exec /mnt/user/appdata/allergiscan/repo/deploy/autodeploy.sh \
  >> /mnt/user/appdata/allergiscan/deploy.log 2>&1
```

**Save**. I dropdown'en ved scriptet: vælg **Custom** → skriv `*/5 * * * *`
i cron-feltet → **Apply**.

Stubben peger på scriptet *inde i repoet*, så agenten opdaterer sig selv
sammen med resten. Den er struktureret, så det er sikkert midt i en kørsel,
og en fil-lås gør overlappende starter harmløse.

**Tjek — spring ikke dette over.** Der er en kendt fejl i User Scripts på
nogle unRAID 7.1.x-udgaver, hvor Custom-skemaet vises i UI'et, men aldrig
skrives til cron:

```bash
grep -A1 allergiscan /etc/cron.d/root
```

Der skal stå en linje med `*/5 * * * *` og scriptets sti. Gør der ikke det:
kør `update_cron` og tjek igen. Stadig ingenting → åbn User Scripts-siden,
sæt skemaet igen, Apply, `update_cron`. Efter en genstart af serveren er
det værd at tjekke én gang til.

**Slut-tjek af hele kæden:** lav en ufarlig commit (fx en linje i
README), push, og vent. Inden for ~10 minutter (CI-byggetid + op til ét
polling-interval):

```bash
tail -5 /mnt/user/appdata/allergiscan/deploy.log   # "ok — <ny sha> kører og er healthy"
docker inspect allergiscan --format '{{.Config.Image}}'   # ghcr.io/…:sha-<ny sha>
```

---

## Hverdagen derefter

- **Deploy** = push (eller merge) til main. 5-10 minutter senere kører det.
- **Rollback ved fejl er automatisk**, men kun mod fejl som healthchecket
  fanger (processen dør, `/healthz` svarer ikke). En logisk fejl, der svarer
  pænt på HTTP, ruller ikke tilbage — det er testenes job at fange den, før
  imaget overhovedet bygges.
- **Manuel rollback**: `git revert` af den dårlige commit, push. Agenten
  deployer reverten som enhver anden ændring. Historikken går kun fremad —
  også det er lånt fra GitOps.
- **`allergens.yaml`-rettelser** deployes samme vej. Commit dem — rediger
  ikke på serveren, for næste `git reset --hard` overskriver lokale
  ændringer i repo-mappen. (`.env` er undtaget: den er gitignoreret, og git
  rører ikke filer, den ikke kender.)

## Fejlfinding

| Symptom | Kig her | Sandsynlig årsag |
|---|---|---|
| Loggen siger "intet image for … endnu" i mere end 10 min | GitHub → Actions | Testene fejlede — imaget bygges med vilje ikke |
| `docker pull` siger `unauthorized`/`denied` | Trin 6a | Pakken er privat og token mangler/er udløbet, eller synligheden er ikke sat til Public |
| Loggen siger "ruller tilbage til …" | `docker logs allergiscan` | Ny version crasher ved opstart; appen kører videre på sidste gode |
| Scriptet virker manuelt, men kører aldrig selv | `grep allergiscan /etc/cron.d/root` | User Scripts-fejlen — kør `update_cron` |
| `git fetch` fejler med `Permission denied (publickey)` | Trin 6b | Privat repo klonet over ssh uden (gyldig) deploy-nøgle |
| Tunnel-hostname giver 502/530 | `docker logs allergiscan-tunnel` | Token forkert, eller Service-URL er ikke `http://allergiscan:8000` |
| Alt ser dødt ud efter server-genstart | `docker ps`, cron-tjekket | Compose-stakken autostarter via `restart: unless-stopped`; cron-linjen kan kræve `update_cron` igen |

Linjer med `FEJL:` i deploy.log kræver hænder — dem skriver agenten kun,
når den hverken kunne deploye eller rulle tilbage.

## Bevidste fravalg

- **Ingen webhook/push-deploy.** Et webhook-endpoint er en ekstra dør i en
  app, hvis pointe er at have så få døre som muligt. Fem minutters polling
  er hurtigt nok til to brugere (Argo CD poller selv hvert 3. minut).
- **Ingen deploy af databaseskemaet.** Appen migrerer selv ved opstart;
  fejler det, fejler healthchecket, og der rulles tilbage — databasen på
  disk rører agenten aldrig.
- **Ingen image-signering (cosign).** Kæden commit → CI → GHCR → digest er
  sporbar nok til én husstand. Deler I appen en dag (fase 4), så genbesøg.
