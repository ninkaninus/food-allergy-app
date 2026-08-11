# Nyheder

Skrevet til dem, der bruger appen — ikke til dem, der læser commits.
Nyeste øverst. Vises i appen via »Nyheder« i bunden.

## 0.16.0 — 11. august 2026

- **Ny OCR-motor: appen læser nu deklarationer markant bedre.** Målt på
  40 af jeres egne butiksfotos læser den næsten tre gange så mange
  rigtige ord som før — og den er seks gange hurtigere (2 sekunder mod
  9). Fotos, der før gav det rene volapyk, læses nu: tekst på klar
  plast, mørke poser, etiketter der ligger på tværs.
- **Færre falske advarsler.** På en Bierwurst-pakke advarede den gamle
  læsning om æg, som slet ikke stod på etiketten — og overså selleri,
  som gjorde. Den nye rammer rigtigt begge steder.
- OCR kører nu i sin egen container ved siden af appen. Svarer den ikke,
  bruger appen den gamle læsning i stedet, så scanning aldrig går helt
  i stå.
- Databasen har også fået sin egen container. Jeres data ligger uændret,
  til I selv vælger at flytte dem (fremgangsmåde i deploy/UNRAID.md).

## 0.15.0 — 11. august 2026

- **Billeder af deklarationen gemmes nu i telefonens fulde opløsning.**
  Før blev de skaleret ned, så det fineste tryk blev grødet, når man
  forstørrede. Målt på et rigtigt foto: 3008×4000 i stedet for
  1203×1600.
- Forsidebilleder skaleres stadig ned — de skal kunne genkendes, ikke
  læses.
- **Listen henter kun små miniaturer** (~30 KB), så et tryk på en vare
  ikke koster flere MB mobildata i butikken. Fuldbilledet hentes først,
  når I forstørrer.

## 0.14.0 — 11. august 2026

- **Nu kan I gemme billeder af varen** — både forsiden og
  deklarationen — så I kan læse etiketten igen derhjemme uden at have
  pakken. Billederne bliver på jeres egen server.
- **Fotograferer I deklarationen for at læse den, gemmes billedet
  automatisk.** I skal ikke tage det samme billede to gange.
- **Tryk på et billede for at forstørre det.** »Forstør« viser det i
  fuld opløsning, så småt tryk kan læses — og I kan stadig zoome med
  fingrene oveni.
- Et billede er dokumentation, ikke en godkendelse: en vare bliver
  ikke grøn af at have et foto.

## 0.13.0 — 11. august 2026

- **Nu kan I knytte arkets varer til en stregkode.** Det er dét, der
  gør de 583 rækker til rigtige varer: uden stregkode kan en vare
  aldrig blive grøn, for godkendelser hænger på stregkoden.
- **To veje til det.** Står I med varen: scan den, og tryk »det er
  denne vare« på linjen, der siger, den ligner noget fra listen.
  Sidder I derhjemme med listen: tryk »knyt stregkode« ved en vare, og
  scan den — så husker appen, hvad I var i gang med.
- Når en vare er knyttet, er den ÉN linje i listen med sin egen dom,
  arkets hylde og butik. Knytningen er ikke en godkendelse: varen
  bliver først grøn, når I bekræfter den mod emballagen som altid.
- Fortrudt? »Fjern koblingen« sætter rækken tilbage på listen.

## 0.12.0 — 11. august 2026

- **Én liste med hylder — ikke to lister længere.** Varerne fra
  regnearket og de varer, I har scannet, står nu i samme liste, delt op
  i jeres egne kategorier: Pålæg, Bagning, Brød, Ris og pasta …
  Hver hylde viser de første seks og et »vis alle« til resten.
- **Har I scannet noget, der står på arket, er det én linje.** Den
  scannede vare vinder — den har dommen — og arket giver den sin hylde
  og butik. Varen får mærket »også på arket«.
- Varer, der ikke er scannet endnu, står stadig i listen med teksten
  »fra arket, ikke scannet endnu«. De kan ikke blive grønne af sig
  selv; det kræver stadig, at I scanner og læser emballagen.
- Filteret »Fra jeres liste« hedder nu »Ikke scannet«, for det er dét,
  det betyder.

## 0.11.0 — 11. august 2026

- **Filtrér-fanen er nu én søgning, som i en netbutik.** Ét søgefelt
  finder på tværs af BÅDE de varer, I har scannet, og hele jeres gamle
  godkendt-liste — I skal ikke længere lede to steder.
- **Filtre med tal, som på en webshop:** Alle · Sikre · Ikke tilladt ·
  Skal tjekkes · Fra jeres liste, og derunder jeres egne kategorier
  (Pålæg 194, Bagning 112, Brød 67 …) og butikker (Netto, Rema1000 …).
  Tallene opdaterer sig efter de filtre, I allerede har valgt.
- **»Fri for«-knapper pr. allergen.** Slår I mælk fra, forsvinder de
  varer, hvor mælk ER fundet. Bemærk: det er ikke et løfte om, at
  resten er fri — farven på hver enkelt vare gælder stadig, og grøn
  kræver stadig, at et menneske har læst emballagen.
- Søgningen er ligeglad med æ, ø og å: »palaeg«, »pålæg« og »paalaeg«
  finder det samme.
- Rettet: skrev man hurtigt, kunne et gammelt, langsomt søgesvar
  overhale det nye og vise forkerte resultater.
- Rettet: en databasekolonne fra 0.10.0 blev aldrig oprettet på
  eksisterende installationer, så listen kunne fejle ved opslag.

## 0.10.0 — 11. august 2026

- **Importen henter selv regnearket.** Sæt `LISTE_URL` i `.env` til
  jeres Google Sheets-link én gang — derefter er genimport bare
  `python -m app.cli import`, ingen filer at downloade og kopiere.
- **Hele listen tæller nu som bekræftet** — uden æg, mælk, tomat og
  banan, sådan som den faktisk blev valideret, før den kom ind i
  regnearket. Både søgningen og scan-hintet siger det nu: »bekræftet
  uden æg, mælk, tomat og banan — men tjek stadig emballagen«.
  (Arkets gamle Valideret-kolonne ignoreres.)

## 0.9.0 — 11. august 2026

- **Filtrér-fanen kan nu gennemse jeres scannede varer.** Søg på fx
  »brød« og se alt brød, I har scannet — og skift mellem *Alle*,
  *Kun sikre* (dem et menneske har bekræftet mod emballagen), *Ikke
  tilladt* og *Skal tjekkes*. Er en godkendt vares opskrift ændret
  siden, står den som »opskrift ændret« og tæller ikke som sikker.
- **Jeres gamle godkendt-liste er nu i appen.** Regnearket (583 varer)
  kan importeres med én kommando og søges under Filtrér-fanen —
  kategori, producent, butik og ✓ for de validerede følger med.
- **Scanner I en vare, der ligner noget fra listen, siger appen det** —
  som et hint, aldrig som en grøn dom. Arket har ingen stregkoder, så
  hver vare bliver først grøn, når I scanner og bekræfter den mod
  emballagen, som alle andre.
- Genimport udskifter listen, så I kan opdatere regnearket og køre
  importen igen.

## 0.8.0 — 11. august 2026

- **Appen har fået et logo:** en stregkode med rød scanlinje. Det står
  øverst i appen, og gemmer du appen på hjemmeskærmen, får den sit eget
  ikon i stedet for et gråt standardbogstav.
- **OCR er kalibreret mod 106 rigtige butiksfotos.** Andelen med god
  læsning steg fra 39 til 48 af 106, og andelen, der måtte afvises,
  faldt fra 39 til 28.
- **Etiketter, der vender på tværs, læses nu.** Mange pakker ligger på
  siden, når man fotograferer dem — appen opdager selv rotationen og
  vender billedet, før den læser.
- OCR er blevet hurtigere på svære billeder: blok-søgningen genbruger
  arbejde i stedet for at læse billedet forfra.

## 0.7.0 — 11. august 2026

- **OCR er kalibreret mod syv rigtige fotos af en mørk pose** og læser
  nu også nærbilleder af lys tekst på mørk baggrund — også når ordet
  »Ingredienser« ikke er med i rammen. Seks af de syv fotos læses;
  banan (som faktisk står på pakken) fanges i alle seks.
- **Ubrugelige billeder giver ikke længere falske røde kryds.** Er
  læsningen for dårlig til automatisk tjek, siger appen det, og du
  læser selv teksten eller tager et nyt billede — uskarpt vrøvl kan
  ikke længere blive til advarsler.
- Rettet: teksten kunne blive klippet fra ernæringstabellen i stedet
  for ingredienslisten, fordi »indhold« matchede inde i
  »Næringsindhold«.

## 0.6.0 — 11. august 2026

- **Fejl gemmer sig ikke længere som »ingen data«.** Kan serveren ikke
  nå Open Food Facts, siger skærmen nu tydeligt »Opslag fejlede — varen
  er IKKE slået op« i stedet for at ligne en ukendt vare. Mister
  telefonen forbindelsen til serveren, står der også besked i stedet
  for ingenting.
- Ny diagnoseside til fejlsøgning: `/api/diagnostik` viser, hvilken
  database appen kigger i, hvor mange varer/domme/brugere den har, og
  om Open Food Facts kan nås fra serveren.
- Databasen kan nu flyttes til en rigtig databaseserver (Postgres) med
  én kommando — alle scannede varer, domme og brugere følger med.
  Fremgangsmåde i deploy/UNRAID.md.

## 0.5.0 — 11. august 2026

- **OCR finder nu selv ingredienslisten på et foto af hele posen** —
  også når teksten er lys på mørk baggrund, som på mange danske poser.
  Før skulle billedet være et nærbillede af selve deklarationen; nu
  leder appen efter »Ingredienser«, beskærer og læser kun det. Testet
  på et rigtigt foto, der før gav volapyk: nu læses deklarationen,
  inklusive de allergener, der faktisk står på pakken.

## 0.4.0 — 11. august 2026

- Appen viser nu sit versionsnummer nederst på siden, med et link til
  disse nyheder — så kan I se, om jeres telefon har fået den seneste
  udgave.

## 0.3.0 — 11. august 2026

- **Alle 14 EU-allergener** kan nu vælges til, plus tomat — oven i de
  oprindelige (mælkeprotein, æg, jordbær, banan). Jeres eksisterende
  valg og bekræftede varer er uændrede.
- **»Fotografér deklaration« åbner kameraet direkte** igen. Gemte
  billeder har fået deres egen knap ved siden af.
- **OCR læser markant bedre** på billeder med skygge eller genskin —
  før kunne den give det rene volapyk på et ellers fint foto.

## 0.2.0 — 9. august 2026

- Appen nås udefra gennem Cloudflare Tunnel med rigtigt HTTPS — det er
  også det, der får kameraet til at virke på telefonen.
- Nye versioner ruller automatisk ud på serveren, når de har bestået
  alle tests. Fejler en ny version ved opstart, ruller den selv tilbage.

## 0.1.0 — 4. august 2026

- Første udgave: scan en stregkode, få ét af fire svar. Motoren kan
  gøre en vare rød eller gul — grøn kræver et menneske, der har læst
  den fysiske pakke.
