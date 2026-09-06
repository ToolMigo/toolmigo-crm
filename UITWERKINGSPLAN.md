# ToolMigo CRM — lokale doorontwikkeling

Publicatie naar GitHub vindt pas plaats na een volledige lokale acceptatieronde en expliciete toestemming.

## 1. Productiebasis

- Dagelijkse PostgreSQL- en mediaback-ups met controlesom en bewaartermijn.
- Beheerst herstel met expliciete bevestiging en automatische veiligheidsback-up.
- TOTP-tweestapsverificatie, herstelcodes en beheerder-reset.
- Bedrijfsprofiel met logo, adres, KvK, btw, IBAN, huisstijl en documentstandaarden.
- Applicatieversie, update-indicator en veilige upgrade-instructies.

**Gereed wanneer:** herstel aantoonbaar werkt, 2FA niet te omzeilen is en alleen een bedrijfsbeheerder organisatie-instellingen kan wijzigen.

## 2. Dagelijks overzicht

- Dashboardcijfers uit echte klant-, offerte-, factuur-, agenda- en taakgegevens.
- Persoonlijke en rolgerichte meldingen.
- Organisatiebrede zoekfunctie met tenant-isolatie.
- Prullenbak met hersteltermijn en auditregistratie.

## 3. Verkoop en uitvoering

- Leads, verkoopkansen, fasen, verwachte omzet en opvolgdatum.
- Projecten met klant, budget, team, status, taken en documenten.
- Urenregistratie met goedkeuring en omzetting naar factuurregels.
- Kilometerregistratie en onkosten met bewijsstukken.
- Documenten per klant en project met beschermde downloads.

## 4. Financiële automatisering

- Terugkerende factuurschema's met veilige conceptgeneratie.
- Betalingsherinneringen met niveaus, termijnen en verzendhistorie.
- Bewerkbare e-mailsjablonen met variabelen en voorbeeldweergave.
- Boekhoudexport met controlebestand en reproduceerbare exportperiode.

## 5. Klantportaal

- Tijdelijk en intrekbaar portaalaccount per klant/contactpersoon.
- Inzien en downloaden van offertes en facturen.
- Offerte accepteren of afwijzen met naam, tijdstip, IP-adres en documenthash.
- Veilige documentuitwisseling zonder toegang tot interne notities.

## 6. Rapportages en oplevering

- Omzet, btw, openstaande posten, verkooppijplijn, uren en projectmarges.
- Tenant-, rollen- en objectautorisatietests voor alle nieuwe onderdelen.
- Hersteltest, beveiligingscontrole, mobiele controle en lokale acceptatielijst.
- Pas daarna versie verhogen en GitHub/CasaOS publiceren.

## Ontwerpregels

- Iedere query en mutatie is aan een organisatie gebonden.
- Financiële historie wordt gearchiveerd, niet hard verwijderd.
- Gevoelige bestanden lopen nooit rechtstreeks via een publieke media-URL.
- Externe verzending is herhaalbaar, gelogd en beschermd tegen dubbel verzenden.
- Achtergrondautomatisering maakt standaard concepten; definitieve financiële handelingen vragen een bevoegde gebruiker.
