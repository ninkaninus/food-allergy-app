# Nyheder

Skrevet til dem, der bruger appen — ikke til dem, der læser commits.
Nyeste øverst. Vises i appen via »Nyheder« i bunden.

## 0.25.0 — 4. september 2026

**Den gamle godkendt-liste fra jeres regneark er væk fra appen**

Søgningen viste før to lister som én: jeres 583 varer fra regnearket, ved
siden af de varer, I selv har scannet — i skrivende stund omkring 20,
samlet i hylder som Brød og Pålæg. Regnearkets varer har ingen
stregkode, og en dom hænger altid på (stregkode, allergen) — så ingen af
de 583 rækker kunne nogensinde blive grønne. De stod for evigt som »Ikke
scannet«, og noten »bekræftet uden mælk, æg, tomat og banan« på dem var
arkets egen, gamle påstand — ikke noget, appen selv havde tjekket.

Hylderne forsvinder med det samme: de kom fra regnearket, og en scannet
vare fik kun sin egen hylde ved at ligne en arkrække, så grupperingen
blev tommere og tommere, jo mere I selv scannede — samme grund som
butiksfilteret, der forsvandt i 0.18.0. Knappen, der kunne knytte en
stregkode til en arkrække, er væk af samme årsag.

Søgningen er nu kun de varer, I selv har scannet — en enkelt, flad
liste, sorteret med det sikre først og det forbudte sidst. Fritekst og
»Fri for«-knapperne virker som før; af statusknapperne er kun »Ikke
scannet« væk, den handlede om arkrækkerne, og der er ingen tilbage at
vise den for. Filtrér-fanen fortæller nu selv om ændringen, og søger I
på en vare, der ikke findes, siger listen det direkte i stedet for at
foreslå jer at fjerne et filter, I ikke har sat.

**Det, I mærker ved scanning i morgen.** Lignede en scannet vare før en
række fra regnearket, viste skærmen en linje som »Ligner Havregryn Øko
(Urtekram) fra jeres liste — bekræftet uden æg, mælk, tomat og banan,
men tjek stadig emballagen.« Den linje er væk. Den hvilede kun på, at to
ord i navnet var ens — ikke på nogen sammenligning af opskriften — og
kunne berolige jer om den forkerte vare. Er I i tvivl om en vare
fremover, er svaret det samme som for enhver anden ukendt vare:
fotografér deklarationen, og bekræft den selv.

**Jeres regneark er urørt** — men vejen tilbage til appen er lukket. Det
er kun appens egen kopi af arket, der er væk; arket selv ligger stadig,
hvor det altid har ligget, og I kan slå op i det direkte, ligesom før
appen fandtes. Fortryder I, er der ingen kommando, der henter det ind
igen — den er fjernet fra appen. At få en vare fra arket tilbage skal nu
gå gennem det samme, som enhver anden vare: scan den, og bekræft den mod
emballagen.

## 0.24.0 — 3. september 2026

**Appen spørger nu, hvad den skal tjekke for — og I skal svare én gang
på hver telefon**

Åbnede man appen på en telefon uden login — dagplejerens, en ny telefon,
eller efter at have logget ud — slog appen i al stilhed alle 17
allergener til. Det lyder forsigtigt, men det var det ikke: et rugbrød,
I selv havde bekræftet uden mælk og æg, kom op som »Ikke sikker«, fordi
der er gluten i rugmel. Hun fik altså at vide, at en vare, I havde
godkendt, ikke måtte spises. Det samme skete i listen under »Filtrér«,
hvor varen slet ikke blev talt med under »Sikre«.

**Det her skal I gøre, én gang på hver telefon:** åbn »Indstillinger« og
tryk på de allergener, appen skal holde øje med — også på dagplejerens
telefon. Indtil det er gjort, står der »Hvad skal appen tjekke for?« på
scan-skærmen og det samme spørgsmål øverst i listen under »Filtrér«, og
appen svarer ikke på en vare. Er I logget ind, kommer sættet fra
serveren som hidtil, og så skal I ikke gøre noget.

Alle telefoner skal svare — også dem, der har brugt appen længe. Det,
der lå gemt i telefonen før i dag, var appens eget gæt på alle 17 og
ikke et valg, nogen havde truffet, så det er kasseret.

**Appen advarer kun om det, I har valgt.** Det er den vigtigste sætning i
denne opdatering. Er et allergen ikke valgt, siger appen ingenting om
det — heller ikke når det står i deklarationen. Derfor står listen nu
under overskriften »Hvad skal appen tjekke for?«, med den samme
påmindelse over knapperne: listen skal være komplet, og er I i tvivl, så
tag allergenet med.

To ting mere, I kan mærke:

- Ændrer I, hvad der tjekkes for — eller logger ud — forsvinder svaret på
  den vare, der står på skærmen. Det var regnet ud fra det gamle valg, og
  et grønt »Sikker« om et rugbrød måtte ikke blive stående, mens appen
  øverst på samme skærm spurgte, hvad den skulle tjekke for.
- Kan appen ikke hente jeres allergener fra serveren, siger den det og
  beder jer genindlæse siden — i stedet for at påstå, at I ikke har
  slået nogen til.

Det ene, der ikke kan ske: intet valgt kommer aldrig til at betyde »tjek
ingenting«. Appen svarer hellere slet ikke end at svare på et gæt — og
ingen vare bliver grøn af den her ændring. Det kræver stadig, at en af
jer har læst pakken.

## 0.23.0 — 23. august 2026

**Jeres billeder bliver brugt til at gøre aflæsningen bedre**

De fotos, I allerede har taget af deklarationer, kan nu hentes samlet og
bruges til at gøre appens læsning af varedeklarationer bedre — særligt de
billeder, hvor en af jer har rettet teksten til under en bekræftelse.
Billederne er offentlige, ligesom de altid har været — det er
dokumentationen bag en bekræftelse, og de kunne allerede ses ét ad gangen
af hvem som helst med et link til varen. Det nye er kun en samlet vej til
at hente dem alle på én gang, og den kræver stadig, at en af jer (eller en
betroet hjælper) er logget ind. Ingenting ændrer sig i den måde, I bruger
appen på.

## 0.22.0 — 23. august 2026

**Kameraet er tændt, når I åbner appen — og véd nu, hvornår det skal slukke**

I skal ikke længere trykke »Scan« først. Har telefonen allerede givet
appen lov til at bruge kameraet, står det klar med det samme — det
tryk, I stod og manglede med én hånd fri i Netto, er væk. Kører det
allerede, hedder knappen »Stop«, så den altid gør det, den siger. Og
skifter I til »Filtrér« eller »Indstillinger«, eller lægger telefonen
fra jer, slukker kameraet af sig selv i stedet for at filme videre uden
grund. Har I ikke givet lov endnu, sker der ingenting af sig selv: I ser
præcis det, I plejer, og »Scan«-knappen virker som altid.

Scanner I en ny vare, mens den forrige stadig stod som »Sikker« på
skærmen, forsvinder den forrige dom, i samme øjeblik kameraet tænder —
den må aldrig kunne forveksles med varen, I lige har i hånden.

**Et tal, der kun vises, når det betyder noget**

Efter et foto af en deklaration viste appen altid et tal for, hvor godt
den kunne tyde bogstaverne — også når tallet ikke sagde jer noget, fordi
det næsten altid ligger omkring 97. Nu står tallet kun der, når
læsningen rent faktisk er usikker, og så som en klar opfordring: tag et
nyt billede, tættere på, uden genskin.

**Fejlbeskeder, der siger, hvad I skal gøre**

Gik et foto ikke igennem, kunne beskeden før være en teknisk sætning,
ingen af jer skulle se. Nu står der altid almindeligt dansk: tag et nyt
billede tættere på, log ind igen, eller tast teksten ind selv.

**»Motor« og »OCR« er væk fra teksten**

De ord betød ikke noget for jer. Appen taler nu om sig selv som
»appen«, og om at fotografere en deklaration som at »læse« den —
samme mening, almindeligt sprog.

## 0.21.1 — 23. august 2026

**Appen starter ikke længere, hvis den er i tvivl om, hvor jeres data er**

Der var en fælde, ingen havde set: forsvandt den indstilling, der
fortæller appen, hvilken database den skal bruge, sagde den ikke fra. Den
lavede stille og roligt en ny, tom database og startede op, som om intet
var galt. I ville have åbnet appen og fundet den fuldstændig tom — ingen
varer, ingen bekræftelser, ingen billeder — mens alt det rigtige lå
uberørt og ventede.

Nu nægter den at starte og siger hvorfor. Sker det, ruller serveren
automatisk tilbage til den forrige udgave, og I mærker ingenting. Det er
ikke noget, I skal gøre — det er en fælde, der er klappet i.

## 0.21.0 — 23. august 2026

**Billeder af varer, appen slet ikke kender, virker nu pålideligt**

Fotograferer en hjælper en vare, Open Food Facts aldrig har hørt om,
dukker den nu selv op i jeres søgning — før kunne den forsvinde
sporløst. I kan altså finde den bagefter og give den et navn.

**Et nyt billede erstatter ikke længere det gamle**

Har opskriften måske ændret sig siden sidst, eller vil en hjælper bare
tage et bedre billede? Nu ligger begge — det gamle forsvinder ikke, før
en af jer aktivt sletter det. Der er ingen grænse for, hvor mange
billeder en vare kan have.

**Bekræftelsesskærmen viser nu både forsiden og deklarationen**

Står I med en ukendt vare, kan I se begge billeder side om side, når I
skal bekræfte den — og skrive varens navn ind med det samme, mens I
kigger på forsidefotoet.

**En hjælper kan nu selv slette et billede, hun selv har taget**

Ramte hun forkert, eller kom der noget uvedkommende med i billedet, kan
hun rette det uden at bede jer om det. Hun kan stadig ikke slette jeres
egne billeder eller nogen andens — kun sine egne. I kan som altid
slette et hvilket som helst billede. Billeder taget FØR denne
opdatering kan kun I slette — appen huskede dengang ikke, hvem der
havde taget dem.

## 0.20.0 — 23. august 2026

**I kan nu invitere en person til at hjælpe med billeder**

Bedsteforælderen eller den faste dagplejer kan få sin egen konto, uden
at kunne bekræfte varer. Hun logger ind, fotograferer forsiden eller
deklarationen, og får med det samme besked om, at billedet er sendt
ind og gemt hos jer. Kun familien kan stadig godkende en vare — det
ændrer sig ikke, uanset hvem der har taget billedet, og hun kan hverken
se et automatisk tjek af billedet eller trykke sig igennem en
bekræftelse. En gæstedagplejer skal ikke have en konto — hun kan
stadig scanne og slå varer op uden at logge ind, ligesom alle andre.

En sådan konto kan ikke se jeres kø af varer, der venter på at blive
tjekket, eller driftsoplysninger om serveren. Det er stadig kun jeres
eget. Den kan derimod se, hvilke allergener I tjekker for — se næste
punkt om hvorfor det er meningen.

Åbner I »Bekræft mod emballagen« på en vare med et deklarationsfoto,
står der nu, hvem der har taget det og hvornår — fx »Foto taget af
Mormor, 22. august« — med et link der åbner billedet i fuld størrelse,
så I kan bekræfte varen uden at skulle scrolle op til miniaturen.

**En administrator kan nu oprette de nye konti fra telefonen**

Under Indstillinger er der et afsnit »Brugere«, hvis I er logget ind
som administrator. Der kan I se, hvem der allerede er oprettet, og
oprette en ny med mail, navn og en af tre roller, hver med sin egen
forklaring, plus en adgangskode I selv sætter og giver videre — der er
intet invitationslink at sende. Koden bliver stående i feltet efter
oprettelsen, så I kan læse den op med det samme. Kommandoen på
serveren virker stadig, hvis I foretrækker den.

**Jeres allergenvalg gælder nu på alle telefoner, der er logget ind**

Før valgte hver telefon sit eget sæt af de fire allergener under
Indstillinger — også en hjælpers. Glemte hun at slå de rigtige til,
tjekkede appen for det forkerte, uden at nogen opdagede det. Det sker
ikke længere: er I logget ind, kommer sættet fra serveren og gælder alle
telefoner med det samme, en hjælper kan se det, men ikke ændre det, og
kun familien kan rette det. Ikke logget ind er intet ændret — telefonen
husker stadig sit eget valg. Overskriften øverst viser nu selve listen
i stedet for et navn, så en hjælper kan tjekke, at det er de rigtige
fire allergener, hun har fået at vide.

**Barnets navn ligger ikke længere på serveren**

Det har aldrig været brugt til andet end at vise et navn i toppen af
skærmen — og det kom altid fra telefonens egen lagring, aldrig fra
serveren. Nu gemmer serveren det slet ikke, og et navn, der eventuelt
lå der fra før, er ryddet automatisk.

**Historikken over jeres scanninger er slettet**

Appen har siden starten lagt en log over hvert opslag — hvilken
stregkode, hvornår, for hvem — uden at vise jer den noget sted. Den
kunne aldrig blive en pålidelig fødevaredagbog, for I scanner ikke alt,
barnet spiser: en ufuldstændig log er værre end ingen, fordi man kan slå
op i den efter en reaktion, se ingenting, og fejlagtigt tro at synderen
ikke var der. Den var også den mest følsomme oplysning, appen gemte.
Den er derfor slettet, ikke bare skjult — jeres domme og bekræftelser
(hvem, hvornår, hvad) er upåvirkede.

## 0.19.0 — 21. august 2026

Ingen store nye funktioner. Bekræftelsesskærmen har fået en tredje
tilstand — og en række fejl er rettet, hvor appen sagde for lidt. Det er
den farlige retning.

**Appen kunne overse hele ingredienslisten**

- Står »Opbevares ved højst +5 °C« i venstre spalte og deklarationen i
  højre, læste appen opbevaringen først og smed resten væk. Så stod der
  »Ved det ikke« om en vare, hvor der tydeligt stod mælk på pakken. Det
  samme skete, hvis læsningen ramte ét bogstav forkert i ordet
  »Ingredienser«. Nu opdager appen, at den har klippet det forkerte
  sted, og bruger hele teksten i stedet.
- Står »Kan indeholde spor af mælk« ØVERST på etiketten, blev sætningen
  klippet væk. Den følger nu med, uanset hvor på pakken den står.

**Appen kendte ikke nok danske ord**

- De danske oste manglede helt — feta, brie, gouda, havarti og et dusin
  til gav ingen advarsel, selvom de italienske gjorde. Det samme gjaldt
  gedemælk, skovjordbær, helæg, stangselleri, råmarcipan, cherrytomater
  og alaskasej. Alle er nu med.
- Stod der »spor af nødder og gedemælk«, hørte I kun om nødderne:
  gedemælk kendte appen ikke, og så blev mælk slet ikke nævnt. Nu giver
  den gult.

**Fire ting omkring bekræftelse og opslag**

- **Bekræftelsesskærmen foreslog »fri« om ting, den ikke vidste noget
  om.** Åbnede I en vare uden ingrediensliste, stod alle allergener
  allerede på »fri«, og to tryk gjorde varen grøn på grundlag af
  ingenting. Nu er der tre tilstande: **ikke afgjort**, fri og
  indeholder, hver med sin farve, sin form og sit ord. Kun to ting er
  valgt på forhånd: det motoren FANDT, og det I selv har afgjort før.
  »Fri« foreslås aldrig — appen kan ikke se forskel på en ingrediensliste
  fra Open Food Facts og en, den selv har læst af et foto, og OCR taber
  ord. Til gengæld er der en knap, **»Jeg har læst pakken — de uden
  advarsel er fri«**, så det er ét tryk i stedet for fire. Den springer
  bevidst de allergener over, hvor etiketten advarer om spor: dér siger
  etiketten noget, og forskellen mellem spor og indhold er jeres
  beslutning, ikke knappens. Uafgjorte allergener gemmes ikke.
- **Et tryk på en urørt allergen gør den ikke længere fri med det
  samme.** Rundgangen er nu ikke afgjort → indeholder → fri. Det
  farligste valg skal ikke være det letteste, og knappen ovenfor dækker
  tilfældet, hvor mange skal være fri på én gang.
- **Gem dom kunne ramme den forkerte vare.** Dommen blev gemt på det,
  der stod i stregkodefeltet — ikke på den vare, skærmen viste. Efter et
  mislykket opslag kunne de to være forskellige. Nu står varens navn og
  stregkode øverst på bekræftelsesskærmen, så I kan se hvilken.
- **Den forrige vares svar blev stående.** Scannede I en ny vare, mens
  signalet var dårligt, stod det gamle — måske grønne — svar på
  skærmen, indtil den nye var hentet. Fejlede opslaget, stod det der for
  altid. Nu skifter skærmen til »Henter …« med det samme, og et svar,
  der kommer for sent, kan ikke længere overhale det nye.
- **En bekræftet vare kunne ikke scannes igen.** Havde I bekræftet en
  vare uden at taste deklarationen ind, svarede appen »Opslag
  mislykkedes (500)« hver eneste gang derefter — netop på de varer, I
  havde gjort arbejdet på.

**Fem ting, I ikke ser, men som betyder noget**

- **Jeres tastede deklarationer bliver ikke længere slettet.** Hentede
  appen varen fra Open Food Facts igen efter 14 dage, og der ingen
  ingrediensliste var, blev jeres egen tekst overskrevet med ingenting.
  Arbejdet skulle gøres om.
- **Genimport af regnearket sletter ikke længere jeres stregkoder.** De
  koblinger, I selv har lavet mellem arkets rækker og rigtige varer,
  bæres nu over, og importen skriver, hvor mange den fandt.
- **Appen fryser ikke længere for den ene, mens den anden læser et
  foto.** En deklarationslæsning tager 2-9 sekunder og spærrede før hele
  appen imens.
- **Serveren skriver ikke længere hver scanning i sin log.** Hver
  stregkode, I slog op, og hvilket barn den blev slået op for, stod i
  containerens log med tidsstempel.
- **Et login-smuthul er lukket.** Det krævede en indstilling, I ikke
  bruger (`TRUST_PROXY_AUTH`), men det skulle aldrig have været muligt.
  Slår I den nogensinde til, skal `TRUSTED_PROXY_HOSTS` være en
  IP-adresse — ikke »caddy«.

**Sitet er åbent — nu er det kun det rigtige, der er åbent**

Appen ligger på internettet, så alle kan scanne og slå op. Det er
meningen. Men et par sider viste mere end det:

- **Barnets navn og allergener kunne ses af enhver.** To steder: siden,
  appen bruger til at huske, hvem I tjekker for — og selve
  vareopslaget, som sendte barnets navn og præcis de fire allergener med
  i svaret, hvis man bare undlod at spørge om noget bestemt. Begge dele
  er lukket. Slår en fremmed en vare op, vurderes alle 17 allergener.
  Appen starter heller ikke længere med jeres fire allergener valgt på
  forhånd — de stod i selve siden, som alle kan hente. Er I logget ind
  på en telefon uden gemte valg, henter appen dem fra profilen i stedet;
  ellers slås alle 17 til, indtil I vælger under Indstillinger. Valget
  bliver i jeres egen telefon.
- **Bekræftelseskøen og diagnosesiden kræver også login.** Køen viser,
  hvilke varer I har scannet og hvornår; diagnosesiden viser detaljer om
  serveren.
- **Fremmede skriver ikke længere i jeres historik.** Når nogen slår en
  vare op uden at være logget ind, gemmes opslaget ikke længere som
  jeres. Jeres egne opslag gemmes som før.
- **Login spærres efter fem forkerte forsøg** fra samme sted i et
  kvarter. Uden det kan hvem som helst blive ved med at gætte — og hvert
  gæt belaster serveren. Spærren rammer den maskine, der banker på, ikke
  jeres mailadresse: en fremmed skal ikke kunne låse jer ude af jeres
  egen app ved at gætte forkert, mens I står i Netto.
- **Fremmede kan ikke fylde jeres bekræftelseskø.** Når nogen udefra slår
  en vare op, lægges den ikke længere i køen, og en vare, I har afsluttet,
  bliver ikke åbnet igen.

- **En fremmed ser nu, hvad »Sikker« er målt imod.** Før stod der bare
  »Alle valgte allergener er manuelt afkrydset«. Nu står der hvilke — og
  at andre allergener ikke er tjekket. Nogen med et nøddeallergisk barn
  må ikke læse jeres bekræftelse som en garanti.
- **Knapper, kun I kan bruge, vises ikke længere for andre.** Før pegede
  de mod låste døre og svarede med en besked øverst på siden, som var
  scrollet ud af syne.

**Alt det, værktøjet er til for, er uændret:** alle kan stadig scanne en
stregkode, få dommen, søge i listen og se, hvad I har bekræftet.

## 0.18.0 — 12. august 2026

- **Butiksfilteret er væk.** Butik stod kun på arkets varer — en vare,
  I scanner, har ingen butik. Filteret ville derfor skjule flere og
  flere af jeres rigtige varer, jo mere I scanner. Kategorierne
  (Pålæg, Bagning, Brød …) er der uændret; de gælder begge slags.
- Regnearket må gerne beholde sin Butik-kolonne — appen ser bare bort
  fra den ved import.

## 0.17.0 — 11. august 2026

- **Nu får I kun ingredienslisten — ikke hele etiketten.** Den nye
  OCR-motor læser alt, hvad der står på pakken, og det betød
  opbevaring, holdbarhed, ernæringstabel og producentadresse midt i
  ingredienslisten. Målt på 20 af jeres fotos er der nu en tredjedel så
  meget tekst tilbage, og det er den rigtige tredjedel.
- **Etiketter med to spalter læses i den rigtige rækkefølge.** Før blev
  spalterne flettet linje for linje, så »Ingredienser:« blev efterfulgt
  af »højst +5 °C« fra nabospalten.
- **Sporadvarsler klippes aldrig væk.** Står »Kan indeholde spor af
  nødder« nede ved producentadressen, følger sætningen med op til
  ingredienslisten — den er dét, der afgør, om varen kan spises.
- **Rammer automatikken forkert, er der to knapper:** »Klip fra
  markøren og ned« fjerner resten, og »Vis hele teksten« henter alt
  tilbage. I skal aldrig fotografere igen.
- Sidegevinst: færre falske advarsler. På en pølsepakke advarede appen
  før om mælk og tomat, fordi den fuzzy-matchede på ernæringstabellens
  støj. Nu står der kun det, etiketten faktisk siger.

## 0.16.1 — 11. august 2026

- Rettet: flytningen af databasen til den nye databaseserver stoppede
  halvvejs, fordi bekræftelseskøen husker stregkoder, appen endnu ikke
  har en vare for — hvilket er selve pointen med »ikke fundet«-poster.
  Køen må nu gerne pege på en ukendt stregkode, og flytningen tjekker
  desuden alt igennem, FØR den rører noget.

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
- **»Spor af mælk« er ikke længere det samme som mælk.** Står allergenet
  kun i sporadvarslen nederst på pakken, er varen nu GUL med teksten
  »spor ifølge etiketten — ikke i ingredienslisten«. Står det i selve
  ingredienslisten, er den stadig rød. Det var den vigtigste forskel at
  få rigtig: nogle tåler spor, andre gør ikke.
- **Sporadvarsler gælder kun dét, etiketten faktisk nævner.** Før gjorde
  »kan indeholde spor af nødder« ALLE jeres allergener gule — også mælk
  og æg, som pakken slet ikke nævnte. Nu rammer den kun nødder.
- Siger etiketten bare »kan indeholde spor« uden at nævne hvad, advarer
  appen stadig bredt. Vi ved det ikke, og så siger vi det.
- Står allergenet både i ingredienslisten og i sporadvarslen, er varen
  rød. Ingredienslisten vinder altid.

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
