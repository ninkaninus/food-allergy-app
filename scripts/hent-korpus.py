#!/usr/bin/env python3
"""
Henter familiens eget OCR-korpus (fotos + menneskeverificerede
deklarationer) fra en kørende AllergiScan, uden at et eneste billede
nogensinde rører git. Se ROADMAP.md, afsnittet »rigtige fotos til
OCR-arbejdet, uden at de havner i git«, og
.claude/skills/ocr-deklarationer/SKILL.md for hvad korpusset bruges til.

Kør:

    KORPUS_URL=https://allergiscan.eksempel.dk \
    KORPUS_MAIL=dig@example.dk \
    python3 scripts/hent-korpus.py [mappe]

Sæt IKKE kodeordet som miljøvariabel i selve kommandoen — det lander
permanent i din shell-historik. Udelad KORPUS_KODEORD, så bliver du bedt
om det interaktivt uden ekko (`getpass`). Sæt den kun, hvis scriptet
kører uovervåget, fx i en cronjob med sin egen adgangsbegrænsning.

Mail/kodeord er en konto med rollen `contributor` — den kan læse
korpusset, men aldrig bekræfte en vare (se GET /api/korpus i app/main.py).

Mappen er valgfri og er som standard `~/allergiscan-korpus` — ALTID uden
for dette repo, ubetinget (se `_sikker_destination` for hvorfor). Kør
scriptet igen for kun at hente nye billeder; det springer over dem, der
allerede ligger på disken, IDET FILNAVNET (ean_slags_id.jpg) er unikt pr.
foto siden 0.21.0 og aldrig genbruges — knyt ikke idempotensen til andet
end det.
"""
from __future__ import annotations

import getpass
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import httpx

STANDARDMAPPE = Path.home() / "allergiscan-korpus"

JPEG_MAGIC = b"\xff\xd8"
LOOPBACK_VÆRTER = {"localhost", "127.0.0.1", "::1"}


def _repo_rod() -> Path | None:
    """Roden af DETTE repo, hvis scriptet kører fra en klon af det.
    Bruges kun til at nægte en destinationsmappe inde i den."""
    her = Path(__file__).resolve().parent.parent
    return her if (her / ".git").exists() else None


def _sikker_destination(mappe: Path) -> None:
    """
    Afviser enhver destination inde i DETTE repo — ubetinget, uanset om
    stien er gitignoreret. `.gitignore` beskriver kun, hvad `git status`
    VISER; det er ikke en udtalelse om, hvad der er sikkert at skrive
    familiens fotos til. Den tidligere udgave brugte `git check-ignore`
    til at afgøre "sikker", og tre kanaler viste sig at give falsk
    tryghed:

    1. `git check-ignore` matcher ikke en sti, der endnu ikke findes —
       kaldt FØR `mkdir` afviste den samme sti, kaldt ANDEN gang (efter
       mkdir) godkendte den. Samme kommando, to svar.
    2. Uankrede mønstre i `.gitignore` (`korpus/`) matcher i enhver
       dybde, så `app/static/korpus/`, `data/korpus/` og `app/korpus/`
       alle blev regnet som "gitignoreret" og dermed "sikre" — selvom
       det første er det, `app.mount("/static", ...)` udleverer
       offentligt, og de to sidste er det, `COPY app`/`COPY data` i
       Dockerfile lægger i det offentlige GHCR-image.
    3. Uden `.git` (en ZIP fra GitHub, `git archive`) returnerede
       `_repo_rod()` None, og vagten sagde OK uden at have tjekket noget.

    Derfor: findes repo-roden ikke, fejler vagten LUKKET (afviser), i
    stedet for at antage, at destinationen er sikker. Findes den, er ALT
    under den forbudt, uanset gitignore-status — der spørges ikke længere
    git om noget.
    """
    repo = _repo_rod()
    if repo is None:
        sys.exit(
            "Kan ikke finde repoets rod (intet .git her) — kan derfor ikke "
            "bekræfte, at destinationen ikke ligger inde i det. Kør "
            "scriptet fra en git-klon af AllergiScan, ikke fra en løsrevet "
            "kopi af filerne."
        )
    try:
        mappe.relative_to(repo)
    except ValueError:
        return  # uden for repoet — sikkert, uanset hvad .gitignore siger

    sys.exit(
        f"{mappe} ligger inde i repoet ({repo}). Familiens deklarationsfotos "
        "må aldrig kunne committes eller havne i det offentlige Docker-image "
        "ved et uheld — det gælder uanset om stien står i .gitignore. Vælg "
        f"en mappe uden for repoet. Standard er {STANDARDMAPPE}."
    )


def _miljoevariabel(navn: str, hemmelig: bool = False) -> str:
    v = os.environ.get(navn)
    if v:
        return v
    if hemmelig:
        v = getpass.getpass(f"{navn} (sæt aldrig kodeord i shell-kommandoen — tastes her, uden ekko): ")
        if v:
            return v
    sys.exit(f"{navn} mangler. Sæt den som miljøvariabel — aldrig i koden.")


def _kraev_sikker_url(url: str) -> None:
    """Nægter http:// til andet end localhost. Login-kaldet sender
    kodeordet i klartekst i request-body; over almindeligt http kan enhver
    på samme netværk læse det med. `localhost`/`127.0.0.1` undtages, så
    scriptet stadig kan afprøves mod en lokal `uvicorn --reload` uden
    certifikat."""
    dele = urlsplit(url)
    if dele.scheme == "https":
        return
    if dele.scheme == "http" and dele.hostname in LOOPBACK_VÆRTER:
        return
    sys.exit(
        f"{url} er ikke https:// — kodeordet ville gå i klartekst over "
        "netværket. Brug https://, eller http://localhost til lokal "
        "afprøvning af en server på din egen maskine."
    )


def _valider_foto_felter(ean: str, slags: str) -> None:
    """Forsvar i dybden: filnavnet bygges direkte af serverens svar. Det
    er ikke nåbart i dag (`_rens()` i app/main.py tvinger `ean` til cifre
    og `slags` til et kendt sæt), men koster to linjer at sikre her også,
    i tilfælde af at den regel nogensinde flytter sig."""
    if not ean.isdigit():
        sys.exit(f"EAN '{ean}' fra serveren er ikke rene cifre — afviser at bygge et filnavn af det.")
    if slags not in ("front", "deklaration"):
        sys.exit(f"Ukendt fotoslags '{slags}' fra serveren — afviser at bygge et filnavn af det.")


def _gem_billede(indhold: bytes, sti: Path) -> None:
    """
    Skriver ATOMISK: til en `.part`-fil, som omdøbes til det rigtige navn
    først når hele indholdet er på disken. `sti.write_bytes()` alene er
    ikke atomisk — disk fuld eller Ctrl-C midt i skrivningen ville
    efterlade en trunkeret JPEG, som `sti.exists()` i næste kørsel
    springer over for evigt.

    Tjekker desuden JPEG-magic FØR skrivning: uden det ville et udløbet
    login, der giver en HTML-loginside i stedet for et billede, blive
    gemt som en `.jpg`, og ingen ville opdage det før nogen åbnede filen.
    """
    if not indhold.startswith(JPEG_MAGIC):
        raise ValueError("svaret er ikke et JPEG (mangler JPEG-magic-bytes)")
    midlertidig = sti.with_name(sti.name + ".part")
    midlertidig.write_bytes(indhold)
    os.chmod(midlertidig, 0o600)
    os.replace(midlertidig, sti)


def brugbare_par(manifest) -> int:
    """
    Tæller PAR — foto + menneskelæst deklaration — ikke varer. Kun
    deklarationsfotos tæller: et forsidefoto alene siger ikke noget om,
    hvor godt OCR'en læste teksten, og har ingen deklarationstekst at
    holdes op imod. Tre deklarationsfotos på samme vare er tre par, ikke
    ét. Kræver `.strip()` på teksten, så en tom/blank streng ikke tæller
    som en brugbar deklaration.
    """
    total = 0
    for v in manifest:
        if not v.get("deklaration_gik_gennem_bekraeftelse"):
            continue
        if not (v.get("deklaration") or "").strip():
            continue
        total += sum(1 for f in v.get("fotos", []) if f.get("slags") == "deklaration")
    return total


def hent() -> None:
    url = _miljoevariabel("KORPUS_URL").rstrip("/")
    _kraev_sikker_url(url)
    mail = _miljoevariabel("KORPUS_MAIL")
    kodeord = _miljoevariabel("KORPUS_KODEORD", hemmelig=True)
    mappe = (
        Path(sys.argv[1]).expanduser().resolve()
        if len(sys.argv) > 1
        else STANDARDMAPPE
    )
    _sikker_destination(mappe)
    mappe.mkdir(parents=True, exist_ok=True)
    os.chmod(mappe, 0o700)  # mode= på mkdir virker ikke, hvis mappen findes i forvejen

    with httpx.Client(base_url=url, timeout=30.0) as klient:
        r = klient.post(
            "/api/auth/login", json={"email": mail, "password": kodeord}
        )
        if r.status_code != 200:
            sys.exit(f"Login fejlede ({r.status_code}). Tjek KORPUS_MAIL/KORPUS_KODEORD.")

        r = klient.get("/api/korpus")
        r.raise_for_status()
        varer = r.json()

        nye_billeder = 0
        allerede_der = 0
        fejlede = 0
        manifest = []
        for vare in varer:
            lokale_fotos = []
            for foto in vare["fotos"]:
                _valider_foto_felter(vare["ean"], foto["slags"])
                filnavn = f"{vare['ean']}_{foto['slags']}_{foto['id']}.jpg"
                sti = mappe / filnavn
                if sti.exists():
                    allerede_der += 1
                else:
                    try:
                        billede = klient.get(foto["url"])
                        billede.raise_for_status()
                        _gem_billede(billede.content, sti)
                        nye_billeder += 1
                    except (httpx.HTTPError, ValueError) as e:
                        fejlede += 1
                        print(f"  fejlede: {filnavn} ({e})", file=sys.stderr)
                        continue
                lokale_fotos.append({**foto, "fil": filnavn})
            manifest.append({**vare, "fotos": lokale_fotos})

        klient.post("/api/auth/logout")

    manifest_sti = mappe / "manifest.json"
    manifest_sti.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.chmod(manifest_sti, 0o600)

    total_billeder = sum(len(v["fotos"]) for v in manifest)
    linje = (
        f"{len(manifest)} varer i korpusset, {total_billeder} billeder i alt "
        f"({nye_billeder} nye, {allerede_der} lå der i forvejen"
    )
    if fejlede:
        linje += f", {fejlede} fejlede"
    linje += ")."
    print(linje)
    if fejlede:
        print(f"Hentede {nye_billeder} af {nye_billeder + fejlede} nye billeder — kør scriptet igen for resten.")
    print(f"Brugbare par til OCR-arbejdet (deklarationsfoto + bekræftet tekst): {brugbare_par(manifest)}.")
    print(f"Lagt i {mappe}")


if __name__ == "__main__":
    hent()
