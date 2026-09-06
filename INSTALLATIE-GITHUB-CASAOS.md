# Publiceren via GitHub en installeren in CasaOS

## 1. GitHub-repository

Maak op GitHub een lege repository met de naam `toolmigo-crm`. Upload daarna alle inhoud van deze map, inclusief de verborgen mappen `.github` en bestanden zoals `.gitignore`. Upload nooit een echt `.env`-bestand.

Na de push naar `main` bouwt GitHub Actions automatisch deze images:

- `ghcr.io/JOUW-GITHUB-NAAM/toolmigo-crm:latest`
- `ghcr.io/JOUW-GITHUB-NAAM/toolmigo-crm:1.1.0`

Controleer de voortgang via **GitHub → Actions**. Open na voltooiing het package bij je GitHub-profiel en wijzig **Package settings → Change visibility** naar **Public**. CasaOS kan het image dan zonder registry-login ophalen.

## 2. CasaOS-compose voorbereiden

Open `docker-compose.casaos.yml` en vervang:

1. Alle databasewachtwoord-velden door exact hetzelfde sterke wachtwoord.
2. De geheime sleutel bij zowel `app` als `backup-scheduler` door dezelfde uitvoer van `openssl rand -base64 64`.
3. Het beheerdersadres en beheerderswachtwoord.
4. `192.168.178.72` wanneer het IP-adres van CasaOS later verandert.

Sla een composebestand met echte geheimen niet opnieuw op in GitHub.

## 3. Installeren

Ga in CasaOS naar **App Store → Custom Install → Import** en importeer de aangepaste inhoud van `docker-compose.casaos.yml`. Controleer bij de app-service:

- Docker Image: `ghcr.io/JOUW-GITHUB-NAAM/toolmigo-crm`
- Tag: `latest`
- Hostpoort: `8088`
- Containerpoort: `8000`

Installeer de app en open daarna `http://192.168.178.72:8088`.

## Gegevens bewaren

De database, uploads, interne back-ups en Redis-data staan onder `/DATA/AppData/toolmigo-crm`. Verwijder deze mappen niet bij een herinstallatie. Download daarnaast regelmatig een back-up vanuit het CRM en bewaar die buiten de CasaOS-server.
