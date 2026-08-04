# Deploy på unRAID — manuelt først, automatisk derefter

To halvdele:

1. **Førstegangsopsætning** — manuel, én aften, svarer til fase 0 i
   [`ROADMAP.md`](../ROADMAP.md).
2. **Auto-deploy** — pull-baseret, som Argo CD kogt ned til én maskine:
   git er den ønskede tilstand, en agent på serveren poller og afstemmer.
   GitHub har **ingen** adgang til serveren — ingen SSH-nøgler i CI, ingen
   webhooks ind, ingen åbne porte. Serveren har kun *læse*-adgang den anden
   vej.

## Forudsætninger

- unRAID med **Docker Compose Manager**-plugin (`docker compose` skal virke
  i en terminal) og **User Scripts**-plugin (til cron).
- `git` på hosten. Tjek med `git --version`; mangler den, installér via
  **NerdTools**-plugin'et.

## Filsystem-layout

```
/mnt/user/appdata/allergiscan/
  repo/        git-klonen — compose køres herfra
  data/        databasen (DATA_PATH i .env)
  secrets/     deploy-nøgle og GHCR-token, chmod 700 — ALDRIG i git
  deploy.log   agentens log
```

`/root` på unRAID overlever ikke en genstart — derfor ligger nøglerne i
appdata og ikke i `~/.ssh`.

---

## 1. Førstegangsopsætning (manuel)

```bash
mkdir -p /mnt/user/appdata/allergiscan/{data,secrets}
chmod 700 /mnt/user/appdata/allergiscan/secrets
cd /mnt/user/appdata/allergiscan
git clone git@github.com:ninkaninus/food-allergy-app.git repo
cd repo

cp .env.example .env
nano .env        # OFF_USER_AGENT med din mail, TUNNEL_TOKEN, evt. mere

docker compose up -d --build
docker compose exec allergiscan python -m app.cli adduser dig@example.dk "William"
```

Cloudflare Tunnel (uddybet i [`cloudflared/README.md`](cloudflared/README.md)):

1. Zero Trust → Networks → Tunnels → opret, kopiér token til `TUNNEL_TOKEN`
   i `.env`, peg tunnellen på `http://allergiscan:8000`.
2. `.env` har allerede `COMPOSE_PROFILES=tunnel`, så `docker compose up -d`
   starter også cloudflared.
3. Når tunnellen virker: fjern `ports:` fra allergiscan-servicen i en lokal
   test — eller lad den stå og bind til LAN, hvis du vil kunne nå appen
   uden om Cloudflare. Tunnellen er ikke kun bekvem: kameraet kræver secure
   context, så uden HTTPS er scanneren død på telefonen.

Åbn sitet på telefonen, læg det på hjemmeskærmen, scan ti varer.
**Gør det før du sætter auto-deploy op** — så har agenten en kendt god
kørende version at falde tilbage på.

---

## 2. Auto-deploy

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

### GitHub-siden

Ingenting at konfigurere. `.github/workflows/deploy.yml` bruger det
indbyggede `GITHUB_TOKEN` — ingen secrets at oprette eller rotere.

Ét valg: **pakkens synlighed på GHCR.** Efter første push til main ligger
imaget under Packages på repoet. Er repoet offentligt, så sæt pakken til
public (Package settings → Change visibility) — så skal serveren slet ikke
bruge noget token, og der er én hemmelighed mindre at passe på.

### Serversiden — legitimationer (kun hvis privat)

Privat repo → read-only deploy-nøgle:

```bash
ssh-keygen -t ed25519 -N "" -C allergiscan-deploy \
  -f /mnt/user/appdata/allergiscan/secrets/deploy_key
ssh-keyscan github.com > /mnt/user/appdata/allergiscan/secrets/known_hosts
cat /mnt/user/appdata/allergiscan/secrets/deploy_key.pub
```

Læg `.pub`-indholdet ind under repoets Settings → Deploy keys — og lad
"Allow write access" være **slået fra**. Sammenlign gerne `known_hosts`
med GitHubs offentliggjorte fingerprints — søg "GitHub's SSH key
fingerprints" på docs.github.com.

Privat GHCR-pakke → classic PAT med **kun** `read:packages`:

```bash
nano /mnt/user/appdata/allergiscan/secrets/ghcr_token   # indsæt tokenet, én linje
chmod 600 /mnt/user/appdata/allergiscan/secrets/ghcr_token
```

Agenten samler selv begge op, hvis filerne findes.

### Serversiden — agenten

User Scripts → Add New Script → `allergiscan-deploy`, indhold:

```bash
#!/bin/bash
exec /mnt/user/appdata/allergiscan/repo/deploy/autodeploy.sh \
  >> /mnt/user/appdata/allergiscan/deploy.log 2>&1
```

Schedule: **Custom** → `*/5 * * * *`.

Stubben peger på scriptet *inde i repoet*, så agenten opdaterer sig selv
sammen med resten — den er struktureret så det er sikkert midt i en kørsel.
Loggen vokser kun, når der faktisk sker noget; afstemte kørsler er tavse.

Kør scriptet én gang i hånden først og se, at den finder den nyeste commit,
pinner imaget og melder healthy:

```bash
/mnt/user/appdata/allergiscan/repo/deploy/autodeploy.sh
```

### Hverdagen derefter

- **Deploy** = push (eller merge) til main. 5-10 minutter senere kører det —
  CI-byggetid plus op til ét polling-interval.
- **Rollback ved fejl er automatisk**, men kun mod fejl som healthchecket
  fanger (processen dør, `/healthz` svarer ikke). En logisk fejl, der svarer
  pænt på HTTP, ruller ikke tilbage — det er testenes job at fange den, før
  imaget overhovedet bygges.
- **Manuel rollback**: `git revert` af den dårlige commit, push. Agenten
  deployer reverten som enhver anden ændring. Historikken går kun fremad —
  også det er lånt fra GitOps.
- **`allergens.yaml`-rettelser** deployes samme vej og er live ved næste
  containerstart — commit dem, i stedet for at redigere på serveren, ellers
  overskriver næste `git reset --hard` dem.
- **Noget galt?** `cat /mnt/user/appdata/allergiscan/deploy.log`. Linjer med
  `FEJL:` kræver hænder.

### Bevidste fravalg

- **Ingen webhook/push-deploy.** Et webhook-endpoint er en ekstra dør i en
  app, hvis pointe er at have så få døre som muligt. Fem minutters polling
  er hurtigt nok til to brugere (Argo CD poller selv hvert 3. minut).
- **Ingen deploy af databaseskemaet.** Appen migrerer selv ved opstart;
  fejler det, fejler healthchecket, og der rulles tilbage — databasen på
  disk rører agenten aldrig.
- **Ingen image-signering (cosign).** Kæden commit → CI → GHCR → digest er
  sporbar nok til én husstand. Deler I appen en dag (fase 4), så genbesøg.
