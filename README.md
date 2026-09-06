# ToolMigo CRM

Fase 1 t/m 6 van het zelfstandige ToolMigo CRM: organisaties, gebruikers, rollen, login, auditlog, klantenbestand, productcatalogus, offertes, Nederlandse facturatie, teamplanning en Kanban-taakbeheer. De applicatie draait in Docker met PostgreSQL en Redis en is geschikt voor CasaOS.

## Eerste installatie

1. Kopieer `.env.example` naar `.env`.
2. Vervang alle voorbeeldwachtwoorden en `SECRET_KEY`.
3. Zet bij `ALLOWED_HOSTS` het IP-adres of domein van de CasaOS-server.
4. Zet bij `CSRF_TRUSTED_ORIGINS` de volledige URL, inclusief `http://` of `https://` en eventuele poort.
5. Start de toepassing:

```bash
docker compose up -d --build
```

Open `http://SERVER-IP:8088`. De eerste organisatie en beheerder worden eenmalig aangemaakt uit de `BOOTSTRAP_*`-instellingen.

## HTTPS

Achter een reverse proxy met een geldig TLS-certificaat:

```env
COOKIE_SECURE=1
HTTPS_ENABLED=1
CSRF_TRUSTED_ORIGINS=https://crm.jouwdomein.nl
ALLOWED_HOSTS=crm.jouwdomein.nl
```

Activeer `HTTPS_ENABLED` pas wanneer HTTPS werkelijk correct werkt; HSTS wordt dan eveneens geactiveerd.

## Beheer

- Gezondheidscontrole: `/health/`
- Teambeheer: `/team/`
- Klantenbestand: `/klanten/`
- Producten en diensten: `/producten/`
- Offertes: `/offertes/`
- Facturen: `/facturen/`
- Verzendwachtrij: `/verzending/`
- Teamagenda: `/agenda/`
- Kanban en taken: `/taken/`
- SMTP-instellingen voor bedrijfsbeheerders: `/beheer/e-mail/`
- Poort wijzigen: pas `8088:8000` aan in `docker-compose.yml`
- Logs: `docker compose logs -f app`
- Stoppen zonder gegevensverlies: `docker compose down`

Gebruik nooit `docker compose down -v` op een productie-installatie: daarmee worden de databasevolumes verwijderd.

## Back-up en herstel

Maak lokaal een controleerbare back-up van PostgreSQL en alle uploads:

```bash
./scripts/backup.sh
```

Standaard worden back-ups onder `backups/` geplaatst en na 30 dagen verwijderd. Gebruik voor een andere locatie of bewaartermijn bijvoorbeeld `BACKUP_ROOT=/veilig/pad BACKUP_RETENTION_DAYS=90 ./scripts/backup.sh`.

Herstel uitsluitend tijdens gepland onderhoud:

```bash
./scripts/restore.sh /volledig/pad/naar/back-upmap
```

Het herstelscript controleert eerst checksums en maakt automatisch een veiligheidsback-up van de huidige toestand.

## E-mail instellen

Een bedrijfsbeheerder kan via **Beheer → E-mailinstellingen** per organisatie de SMTP-server, poort, gebruikersnaam, het wachtwoord, afzenderadres en TLS/SSL invoeren. Sla de instellingen op en verstuur daarna eerst een testmail. Het SMTP-wachtwoord wordt versleuteld opgeslagen. Bewaar daarom dezelfde `SECRET_KEY`; na wijziging daarvan moet het SMTP-wachtwoord opnieuw worden ingevoerd.

## Tests

```bash
docker compose exec app python manage.py test
```

De tests controleren login, rollen, organisatie-isolatie, klantdossiers, btw- en geldberekeningen, documentvergrendeling, goedkeuringsrechten, offerte- en factuurnummering, betalingen, credits, PDF-opbouw, batchverzending, agenda-isolatie, herhalingen, conflicten, Kanban-verplaatsingen, checklisten, beschermde bijlagen en auditregistratie.

## Huidige reikwijdte

Lokaal beschikbaar: fundament, rollen en auditlog, 2FA, bedrijfsprofiel, klanten en contactpersonen, verkoopkansen, offertes, facturen, betalingen, creditfacturen, terugkerende conceptfacturen, betalingsherinneringen, boekhoudexport, teamagenda, Kanban, projecten, uren, kilometers, onkosten, beschermde documenten, klantportaal, rapportages, zoekfunctie, prullenbak, back-upplanning en beheerst herstel.

De lokale 1.2-uitbreidingsronde voegt daar het e-mailcentrum, Mollie-betaallinks, bankimport en matching, documentsjablonen, voorraadbeheer, contracten, servicetickets, routes en mobiele werkbonnen, CalDAV/iCalendar, digitale ondertekening, geavanceerde dashboards, een proefimportwizard, tenant-API en webhooks, PWA/offline-cache en systeembewaking aan toe. Externe integraties blijven uitgeschakeld totdat een beheerder geldige test- of productiegegevens invoert en ze expliciet activeert. Zie `LOKALE-ACCEPTATIE.md` voordat een versie wordt gepubliceerd.
