# Lokale acceptatie ToolMigo CRM

Publicatie naar GitHub en installatie in CasaOS blijven geblokkeerd totdat de eigenaar deze lijst expliciet accepteert.

## Automatisch gecontroleerd

- Database-migraties hebben geen ontbrekende modelwijzigingen.
- Django-systeemcontrole en volledige testsuite slagen.
- Login met actieve 2FA geeft zonder geldige tweede factor geen sessie.
- Rollen, tenant-isolatie en beschermde downloads worden met negatieve tests gecontroleerd.
- Terugkerende facturen maken uitsluitend concepten en zijn per vervaldatum idempotent.
- Herinneringen worden één keer per niveau klaargezet en nooit zonder bevoegde handmatige actie verzonden.
- Boekhoudexport bevat periode, tellingen en SHA-256-controlesommen.
- Portaaltoegang verloopt en is intrekbaar; offertebeslissingen bewaren documenthash, naam, tijdstip en IP-adres.
- PostgreSQL dump/drop/create/restore wordt op een geïsoleerde testdatabase gecontroleerd.
- Back-upchecksums, bewaarlimiet, herstelwachtrij en veiligheidsback-up zijn gecontroleerd.

## Handmatige acceptatie vóór publicatie

- [ ] Desktopweergave in Brave/Chromium controleren.
- [ ] Mobiele weergave op smal scherm controleren: menu, tabellen, formulieren en klantportaal.
- [ ] Bedrijfslogo en documentteksten invullen en PDF’s visueel beoordelen.
- [ ] SMTP-test uitvoeren met het definitieve zakelijke afzenderaccount.
- [ ] Eén authenticator koppelen en herstelcodes buiten de server bewaren.
- [ ] Testklant uitnodigen voor het portaal en toegang weer intrekken.
- [ ] Back-up downloaden en extern bewaren.
- [ ] Definitieve versie/tag bepalen.
- [ ] Expliciet toestemming geven voor GitHub-publicatie en daarna CasaOS-upgrade.

## Aanvullende acceptatie voor versie 1.2

- [ ] SMTP-uitgaand en inkomende communicatie-API met een testmailbox beproeven.
- [ ] Mollie uitsluitend met een test-API-key activeren en een testbetaling plus webhook controleren.
- [ ] Een bank-CSV eerst als kopie/proefbestand importeren en de gevonden factuurmatching beoordelen.
- [ ] Offerte en factuur met elk documentsjabloon visueel als PDF beoordelen.
- [ ] Voorraadcorrectie, contractwaarschuwing, serviceticket en mobiele werkbon doorlopen.
- [ ] CalDAV met een testagenda synchroniseren; Google/Microsoft vereisen eigen OAuth-registratie.
- [ ] Ondertekenlink in een privévenster testen en controleren dat hergebruik wordt geweigerd.
- [ ] API- en webhookgeheimen aanmaken, buiten het CRM bewaren en daarna met testdata controleren.
- [ ] PWA op iPhone/Brave en Android/Chromium installeren en online/offline gedrag beoordelen.
- [ ] Alle systeemwaarschuwingen nalopen en pas daarna een definitief versienummer kiezen.

## Veilige upgradevolgorde

1. Maak en download een actuele back-up.
2. Lees migratie- en release-informatie.
3. Bouw lokaal met `docker compose build`.
4. Voer `python manage.py test` en `python manage.py check --deploy` uit.
5. Werk pas daarna de image-tag in CasaOS bij.
6. Controleer health, login/2FA, documenten, planner en e-mailwachtrijen.
