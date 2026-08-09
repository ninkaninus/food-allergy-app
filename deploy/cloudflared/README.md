# Cloudflare Tunnel

## Hvorfor tunnel gør mere end at spare en portforwarding

Kameraet er den egentlige grund. `navigator.mediaDevices.getUserMedia` kræver
et *secure context* — HTTPS eller `localhost`. På `http://192.168.1.x:8420`
nægter både Safari og Chrome at give adgang til kameraet, og så virker
stregkodescanneren slet ikke. Tunnellen giver dig et rigtigt certifikat på et
rigtigt domæne, og dermed virker scanneren på begge telefoner. Uden den skulle
du selv rode med certifikater for at få kernefunktionen til at fungere.

Derudover: ingen åbne porte på unRAID, ingen dynamisk DNS, og dagplejen skal
ikke installere noget.

## Opsætning

```bash
# 1. Opret tunnellen i Cloudflare Zero Trust-dashboardet
#    Networking -> Tunnels -> Create a tunnel -> Cloudflared
#    Kopiér tokenet. Udførlig klikvej: se deploy/UNRAID.md trin 4.

# 2. Læg det i .env
echo 'TUNNEL_TOKEN=DIT_TOKEN_HER' >> .env

# 3. Peg tunnellen på containeren (i dashboardet, under Public Hostnames)
#    Subdomain: allergi
#    Domain:    ditdomæne.dk
#    Service:   http://allergiscan:8000

# 4. Start
docker compose --profile tunnel up -d
```

Bemærk `http://allergiscan:8000` — cloudflared taler til containeren over
Docker-netværket. Der er ikke brug for Caddy, og porten er som default kun
bundet til 127.0.0.1 på værten (`APP_BIND` i `.env`), så tunnellen er den
eneste vej ind udefra.

## Adgangskontrol: to modeller

### A. Åben læsning, lokalt login til skrivning (enklest)

Lad hele sitet være offentligt. Læsning er alligevel ufarlig — der er ingen
personoplysninger i "indeholder denne yoghurt mælk". Bekræftelser kræver
login med de lokale brugere, du opretter med `app.cli adduser`.

Sæt i `.env`:

    COOKIE_SECURE=1
    TRUST_PROXY_AUTH=0

Det er nok til to voksne, og det er der, du bør starte.

### B. Cloudflare Access foran skrivestierne

Vil du undgå at vedligeholde adgangskoder, kan Access stå for identiteten.
Opret en Access-applikation i Zero Trust, sæt en politik der kun tillader
jeres to mailadresser, og læg den på stien `/api/products/*/confirm`,
`/api/ocr` og `/api/auth/users`.

Sæt i `.env`:

    CF_ACCESS_TEAM_DOMAIN=ditteam.cloudflareaccess.com
    CF_ACCESS_AUD=<Application Audience Tag>
    CF_ACCESS_ADMINS=dig@example.dk

Appen validerer da JWT'et i `Cf-Access-Jwt-Assertion` mod dit teams
offentlige nøgler og opretter brugeren ved første besøg.

## Det du IKKE skal gøre

**Sæt aldrig `TRUST_PROXY_AUTH=1` sammen med en tunnel, medmindre der står
en Caddy imellem, som strimler `Remote-*`.** Med tunnellen peger trafikken
direkte på containeren, og der er ingen, der fjerner headere undervejs.
Enhver, der kan nå containeren — fra LAN, fra et andet Docker-netværk, fra
en glemt portmapping — kan så sætte `Remote-User: dig@example.dk` og skrive
domme.

Cloudflare Access-modellen har ikke det problem: et JWT kan ikke forfalskes
uden Cloudflares private nøgle. Det er derfor `cfaccess.py` validerer
signaturen i stedet for bare at læse en header.
