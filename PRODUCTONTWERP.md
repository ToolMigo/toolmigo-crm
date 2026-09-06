# ToolMigo CRM — productontwerp v1

Status: functioneel ontwerp, 6 september 2026

## 1. Productdoel

ToolMigo CRM is een zelfstandig, Nederlandstalig bedrijfsplatform voor klantbeheer, offertes, facturatie, planning en taken. De eerste installatie bedient één bedrijf op een eigen CasaOS-server. De architectuur ondersteunt vanaf het begin meerdere strikt gescheiden organisaties, zodat het product later als betaalde dienst aan andere bedrijven kan worden aangeboden.

De eerste versie is geen volledige boekhouding. Zij beheert verkoopdocumenten, betalingen en rapportages en wordt voorbereid op latere koppelingen met boekhoudsoftware, betaalproviders, agenda's en Peppol.

## 2. Organisaties en gegevensscheiding

- Iedere organisatie is een tenant met een eigen naam, huisstijl, nummerreeksen, e-mailinstellingen, gebruikers, klanten en documenten.
- Alle zakelijke records dragen verplicht een `organization_id`.
- Toegang wordt zowel in applicatielogica als via geautomatiseerde tests per organisatie afgedwongen.
- Een gebruiker kan later lid zijn van meerdere organisaties, met per organisatie een andere rol.
- Platformbeheer ziet technische status en abonnementen, maar opent niet stilzwijgend klant- of factuurinhoud.
- Export en verwijdering worden per organisatie geregeld; fiscale documenten volgen hun wettelijke bewaartermijn.

Voor de eerste CasaOS-installatie wordt één organisatie geactiveerd. De platformlaag en abonnementsvelden zijn aanwezig maar nog niet zichtbaar voor gewone gebruikers.

## 3. Rollen en rechten

### Platformbeheerder

Beheert organisaties, abonnementstatus, systeemprestaties, herstel en updates. Heeft geen standaardtoegang tot bedrijfsinhoud.

### Bedrijfsbeheerder

Beheert bedrijfsgegevens, gebruikers, rollen, nummerreeksen, btw-instellingen, e-mail, sjablonen en alle modules binnen de eigen organisatie.

### Facturatie

Controleert offertes en facturen, keurt ze goed of wijst ze gemotiveerd af. Kan verzending autoriseren. In de eerste inrichting is één medewerker Facturatie voldoende; een organisatie kan zonder systeemwijziging meerdere gebruikers deze rol geven.

### Medewerker

Beheert klanten, afspraken en taken en kan offertes en facturen als concept voorbereiden. Heeft geen recht om documenten definitief te maken of te verzenden.

### Verkoop

Werkt met leads, klantrelaties en offertes.

### Klantbeheer

Onderhoudt klantdossiers, contactpersonen en dossieractiviteiten.

### Planning

Beheert afspraken, deelnemers en teamcapaciteit.

### Projectbeheer

Coördineert Kanban-borden, taken, deadlines en uitvoering.

### Support

Behandelt klantvragen, opvolgactiviteiten en ondersteunende taken.

### Scheiding van taken

Standaard kan de opsteller zijn eigen offerte of factuur niet goedkeuren. Een bedrijfsbeheerder kan dit uitsluitend via een expliciete organisatie-instelling toestaan. Elke goedkeuring, afwijzing en verzending komt in het auditlog.

## 4. Hoofdmodules

### Dashboard

- Afspraken van vandaag en komende zeven dagen
- Persoonlijke en achterstallige taken
- Offertes die op goedkeuring wachten
- Facturen die op goedkeuring wachten
- Openstaande en vervallen facturen
- Omzet exclusief btw per maand en kwartaal
- Recente activiteit
- Snelle invoer voor klant, offerte, factuur, afspraak en taak

### Klanten en contactpersonen

- Bedrijf of particulier
- Juridische naam, handelsnaam, bezoek- en factuuradres
- KvK-nummer en btw-identificatienummer
- Meerdere contactpersonen met functie, telefoon en e-mail
- Voorkeurstaal, betalingstermijn, standaardkorting en btw-behandeling
- Status, labels, eigenaar en herkomst
- Notities, bestanden en chronologische tijdlijn
- Gekoppelde offertes, facturen, betalingen, afspraken en taken
- Zoeken, filteren, CSV-import en CSV-export
- Detectie van mogelijke dubbele klanten

### Producten en diensten

- Artikelcode, omschrijving, type, eenheid en standaardprijs exclusief btw
- Nederlandse btw-tarieven als configureerbare belastingcodes
- Actief/inactief en optionele interne kostprijs
- Prijzen worden bij documentaanmaak gekopieerd zodat historische documenten niet veranderen

### Offertes

- Unieke en oplopende offertenummerreeks per organisatie en kalenderjaar met standaardformaat `TM-{jaar}-{nummer}`, bijvoorbeeld `TM-2026-0001`
- Regels voor producten/diensten, vrije tekst, aantallen, eenheidsprijzen en kortingen
- Btw per regel, subtotalen en eindtotaal
- Geldigheidsdatum, voorwaarden, interne notities en klantnotities
- PDF in de huisstijl van de organisatie
- Status: `concept → ter goedkeuring → goedgekeurd → verzonden → geaccepteerd/afgewezen/verlopen`
- Afwijzing vereist een reden en stuurt het document terug naar concept
- Geaccepteerde offerte kan één keer gecontroleerd worden omgezet naar factuur
- Versiehistorie van wijzigingen vóór goedkeuring

### Facturen

- Een definitief factuurnummer wordt pas bij goedkeuring/definitief maken toegekend
- Unieke en oplopende factuurnummerreeks per organisatie en kalenderjaar met standaardformaat `TM-{jaar}-{nummer}`, bijvoorbeeld `TM-2026-0001`
- Nummer is uniek en oplopend binnen een configureerbare reeks
- Factuurdatum, leverdatum of leverperiode en vervaldatum
- Bedragen exclusief btw, uitsplitsing per btw-tarief en btw-bedrag
- Betalingskenmerk en bankgegevens
- Status: `concept → ter goedkeuring → goedgekeurd → verzonden → deels betaald/betaald/vervallen/gecrediteerd`
- Verzonden factuur en bijbehorende PDF worden onveranderlijk bewaard
- Correcties na verzending verlopen via een gekoppelde creditfactuur
- Handmatige gehele of gedeeltelijke betalingen met datum, bedrag en omschrijving
- Herinneringsstatussen en e-mailsjablonen
- Export voor accountant in CSV; boekhoudkoppelingen volgen later

De factuurlay-out bevat ten minste de wettelijk vereiste namen, adressen, btw-id, KvK-nummer, uitreikdatum, uniek opeenvolgend nummer, leveringsgegevens, omschrijving/omvang, bedragen exclusief btw, btw-tarieven en btw-bedragen. Digitale originelen en verzendinformatie worden minimaal zeven jaar bewaard; voor relevante onroerende-zakendocumenten kan tien jaar worden ingesteld.

### Goedkeuringsinbox

- Centrale wachtrij voor offertes en facturen
- Voorvertoning van PDF en vergelijking met vorige versie
- Goedkeuren met optionele notitie
- Afwijzen met verplichte reden
- Alleen goedgekeurde documenten kunnen worden verzonden
- Goedkeuren verstuurt nooit direct: goedgekeurde documenten gaan naar de wachtrij `Klaar voor verzending`
- De actie `Alle goedgekeurde documenten verzenden` verzendt alle goedgekeurde offertes en facturen van de organisatie in één batch
- Voor de batch toont het systeem aantal documenten en ontvangers en vraagt het een definitieve bevestiging
- E-mailfouten veranderen de status niet stilzwijgend naar verzonden

### E-mail

- SMTP per organisatie
- Afzendernaam, antwoordadres en afzonderlijke sjablonen
- PDF automatisch als bijlage
- Testmail in instellingen
- Wachtrij met herhaalde afleverpogingen
- Registratie van ontvanger, tijdstip, onderwerp, status en technische foutmelding
- Geen trackingpixel in v1; privacyvriendelijk als uitgangspunt

### Agenda en planning

- Dag-, week- en maandweergave
- Persoonlijke agenda en gecombineerde teamagenda
- Afspraken gekoppeld aan klant, contactpersoon en verantwoordelijke gebruiker
- Type, kleur, locatie, begin/einde, notities en herinnering
- Herhalende afspraken
- Filters op gebruiker en afspraaktype
- Conflictwaarschuwing, maar geen harde blokkade
- Externe agenda-synchronisatie wordt als latere module voorbereid

### Taken en Kanban

- Meerdere borden per organisatie
- Kolommen vrij instelbaar; standaard: Inbox, Gepland, Bezig, Wachten, Afgerond
- Slepen tussen kolommen met vastlegging in het auditlog
- Titel, beschrijving, eigenaar, deelnemers, deadline, prioriteit en labels
- Checklist, opmerkingen en bijlagen
- Koppeling aan klant, offerte, factuur of afspraak
- `Mijn taken`, achterstallig en komende deadlines
- Afgeronde taken blijven doorzoekbaar

### Meldingen

- In-app meldingen voor toegewezen taken, afspraken, goedkeuringsverzoeken en afwijzingen
- Dagelijkse optionele e-mailsamenvatting
- Persoonlijke meldingsvoorkeuren

## 5. Goedkeuringsproces

1. Een medewerker maakt een concept.
2. Validatie controleert verplichte klant-, bedrijfs-, btw- en regelgegevens.
3. De medewerker kiest `Ter goedkeuring indienen`; het concept wordt voor hem vergrendeld.
4. Een bevoegde goedkeurder controleert inhoud en PDF.
5. Bij afwijzing wordt een reden opgeslagen en gaat het document terug naar concept.
6. Bij goedkeuring wordt een onveranderlijke momentopname gemaakt. Voor een factuur wordt nu het definitieve nummer gereserveerd. Het document krijgt de status `goedgekeurd` en wordt nog niet verzonden.
7. Een bevoegde gebruiker opent `Klaar voor verzending` en kiest `Alle goedgekeurde documenten verzenden`.
8. Na een bevestigingsscherm zet de applicatie ieder document afzonderlijk in de e-mailwachtrij. Een fout bij één ontvanger blokkeert de overige documenten niet.
9. De e-mailwachtrij verstuurt de berichten en legt per document resultaat en bijlagecontrole vast.
10. Elke stap bevat gebruiker, tijdstip, IP-adres en relevante wijzigingsgegevens in het auditlog.

## 6. Nederlandse facturatie

- Valuta standaard EUR en bedragen intern als decimalen, nooit als binaire floating-pointgetallen
- Btw-berekening en afronding worden centraal uitgevoerd en getest
- Configureerbare tarieven en bijzondere codes voor vrijstelling/verlegging
- Opeenvolgende unieke factuurnummers; concepten gebruiken een intern conceptnummer
- Offertes en facturen hebben elk een eigen nummerreeks, beide met dezelfde gewenste weergave `TM-{jaar}-{nummer}`. Het documenttype en de interne technische sleutel voorkomen verwarring; factuurnummers blijven binnen de factuurreeks uniek en opeenvolgend.
- Nummerreeksen starten per kalenderjaar opnieuw op `0001`; gebruikte nummers worden nooit hergebruikt
- Versie 1 ondersteunt uitsluitend binnenlandse Nederlandse facturatie in euro's; internationale btw, ICP en OSS zijn uitgesloten
- Klant- en bedrijfsgegevens worden als momentopname in de definitieve factuur opgeslagen
- Geen verwijdering van definitieve financiële documenten via de gebruikersinterface
- Bewaarbeleid, export en hersteltest worden onderdeel van beheer

Internationale btw, OSS, ICP, margeregelingen en volledige boekhouding vallen buiten v1 en vereisen per uitbreiding fiscale validatie.

## 7. ToolMigo-huisstijl

De actuele ToolMigo-website vormt het uitgangspunt:

- Primair mint: `#68DDB5`
- Donker mint: `#239F7F`
- Licht mint: `#DFF6EE`
- Crèmebasis: `#FFFBF6`
- Accenten: lime `#B8F06B`, abrikoos `#FFD9C2` en geel `#FFE585`
- Hoofdtekst: charcoal `#2B2F33`
- Secundaire tekst: `#667085`
- Randen: `rgba(43,47,51,.10)`
- Succes: groen; waarschuwing: amber; fout: rood
- Witte kaarten, afgeronde hoeken, lichte schaduwen en royale witruimte
- Mint-lime-abrikoosverlopen voor merkaccenten en belangrijke headers
- Zakelijk en rustig; geen zware JARVIS-effecten in dit CRM

Het definitieve logo, lettertype en documentbriefpapier worden als verwisselbare merk-assets ingericht. Iedere toekomstige klantorganisatie kan eigen logo, kleuren, adresgegevens en PDF-voettekst instellen, terwijl het platform herkenbaar `Powered by ToolMigo` kan tonen.

Het op 6 september 2026 aangeleverde vierkante robotbeeldmerk (`assets/toolmigo-logo.jpeg`) is het officiële actieve ToolMigo-logo. Eerdere gereconstrueerde beeldmerken mogen niet in de applicatie of documenten worden gebruikt.

## 8. Technische architectuur

### Applicatie

- Modulaire monoliet: één implementeerbare applicatie met duidelijk gescheiden domeinmodules
- Server-side webapp met een interactieve laag voor agenda en Kanban
- PostgreSQL als relationele database
- Redis voor sessies, caching, rate limiting en achtergrondtaken
- Aparte worker voor PDF-generatie, e-mail en periodieke taken
- Object-/bestandsopslag met per organisatie gescheiden paden
- REST API intern voorbereid, maar niet publiek geopend in v1

Een modulaire monoliet houdt beheer op CasaOS eenvoudig en kan later nog worden opgesplitst zonder nu de complexiteit van microservices te introduceren.

### Docker/CasaOS

Containers:

1. `toolmigo-crm-app`
2. `toolmigo-crm-worker`
3. `toolmigo-crm-scheduler`
4. `toolmigo-crm-postgres`
5. `toolmigo-crm-redis`
6. `toolmigo-crm-backup`

Persistente volumes bevatten database, documenten en back-ups. Geheimen staan niet in de image of repository. Een reverse proxy verzorgt HTTPS en een healthcheck bewaakt app, database, worker en wachtrij.

## 9. Beveiligingsbasis

- Moderne wachtwoordhashing, veilige sessiecookies en CSRF-bescherming
- Rate limiting en tijdelijke blokkering bij herhaalde mislukte logins
- Optionele TOTP-tweestapsverificatie in v1; verplicht te maken per organisatie
- Rechtencontrole op iedere serveractie, niet alleen in de interface
- Strikte tenantfiltering en tests die gegevenslekken tussen organisaties proberen uit te lokken
- Invoercontrole, veilige bestandsuploads en malware-scanmogelijkheid
- Encryptie tijdens transport en versleuteling van gevoelige configuratie
- Auditlog kan niet door gewone beheerders worden aangepast
- Back-ups versleuteld, met bewaarschema en periodieke hersteltest
- Beveiligde software-updates en database-migraties
- AVG-functies: export, bewaarbeleid, anonimisering waar toegestaan en registratie van verwerkingsacties

## 10. Eerste release en latere verkoop

### MVP / eerste bruikbare release

- Login, rollen, organisatie-instellingen en auditlog
- Klanten/contactpersonen en import/export
- Producten/diensten
- Offertes, PDF en goedkeuringsproces
- Facturen, betalingen, creditfacturen, PDF en goedkeuringsproces
- SMTP-verzending en verzendlog
- Agenda
- Kanban, taken en meldingen
- Dashboard en basisrapportage
- Back-up, herstelhandleiding en CasaOS Compose-installatie

### Later commercieel platform

- Selfservice-aanmelding en organisatie-onboarding
- Abonnementen, proefperiodes en licentiehandhaving
- Mollie, Peppol en bankkoppelingen
- Koppelingen met boekhoudpakketten
- Google/Outlook/CalDAV-synchronisatie
- Klantportaal voor offerteacceptatie en facturen
- Publieke API, webhooks en mobiele/PWA-functies
- Platformbrede support- en statusfuncties

## 11. Acceptatiecriteria v1

- Twee organisaties kunnen geen data van elkaar bekijken, wijzigen of raden via URL's/API-verzoeken.
- Meerdere gebruikers kunnen gelijktijdig werken zonder nummerbotsingen of overschreven wijzigingen.
- Een onbevoegde gebruiker kan geen offerte of factuur goedkeuren of verzenden.
- Een goedgekeurd en verzonden document blijft exact reproduceerbaar.
- Factuurnummers zijn uniek en opeenvolgend binnen hun reeks, ook bij gelijktijdige goedkeuring.
- E-mailproblemen zijn zichtbaar en kunnen veilig opnieuw worden geprobeerd zonder dubbele statusovergangen.
- Database en documenten kunnen aantoonbaar vanuit een back-up worden hersteld.
- De belangrijkste processen werken op desktop, tablet en mobiel.
- Alle geldberekeningen en btw-afrondingen hebben geautomatiseerde tests.

## 12. Nog vast te leggen vóór implementatie

1. Naam en rechtsvorm van het eerste bedrijf, KvK, btw-id, IBAN en standaard betalingstermijn.
2. Mailprovider/SMTP en het gewenste afzenderadres.
3. Definitieve teksten voor betalingsvoorwaarden, offertevoorwaarden en e-mailtemplates.
8. Back-uplocatie: uitsluitend lokaal, tweede schijf/NAS of ook versleuteld extern.
