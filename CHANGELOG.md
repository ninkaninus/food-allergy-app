# Nyheder

Skrevet til dem, der bruger appen — ikke til dem, der læser commits.
Nyeste øverst. Vises i appen via »Nyheder« i bunden.

## 0.8.0 — 11. august 2026

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
