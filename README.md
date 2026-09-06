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

## E-mail instellen

Een bedrijfsbeheerder kan via **Beheer → E-mailinstellingen** per organisatie de SMTP-server, poort, gebruikersnaam, het wachtwoord, afzenderadres en TLS/SSL invoeren. Sla de instellingen op en verstuur daarna eerst een testmail. Het SMTP-wachtwoord wordt versleuteld opgeslagen. Bewaar daarom dezelfde `SECRET_KEY`; na wijziging daarvan moet het SMTP-wachtwoord opnieuw worden ingevoerd.

## Tests

```bash
docker compose exec app python manage.py test
```

De tests controleren login, rollen, organisatie-isolatie, klantdossiers, btw- en geldberekeningen, documentvergrendeling, goedkeuringsrechten, offerte- en factuurnummering, betalingen, credits, PDF-opbouw, batchverzending, agenda-isolatie, herhalingen, conflicten, Kanban-verplaatsingen, checklisten, beschermde bijlagen en auditregistratie.

## Huidige reikwijdte

Gereed: fundament, klanten, contactpersonen, dossieractiviteiten, productcatalogus, offertes, facturen, betalingen, creditfacturen, document-PDF's, gezamenlijke verzendwachtrij, teamagenda, Kanban-borden, taken, checklists, opmerkingen, beschermde bijlagen, CSV-import/export en Light/Dark mode. De volgende fase maakt de installatie productieklaar.
