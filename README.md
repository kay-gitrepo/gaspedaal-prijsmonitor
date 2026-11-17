# OccasionIQ – Gaspedaal prijsmonitor en XC90 aankoopassistent

**Status: v0.18.0.** Het verbeterplan ([`docs/VERBETERPLAN.md`](docs/VERBETERPLAN.md)) is volledig uitgevoerd, inclusief meldingen via Home Assistant, de shortlist-vergelijking en het onderhandelingsdossier. Het exacte interne Gaspedaal-zoek-endpoint is **nog niet geïdentificeerd of live getest**; de API-adapter staat daarom standaard uit. Zie ook [`docs/DIRECTE_GASPEDAAL_API.md`](docs/DIRECTE_GASPEDAAL_API.md) en de oorspronkelijke [`bouwspecificatie`](docs/BOUWSPECIFICATIE.md).

## Nieuw sinds v0.5

- **Eigen adres per scherm** (`#/aanbod`, `#/auto/<id>`, …), nieuw ontwerpsysteem, Nederlandse woordenlijst zonder interne codes.
- **Zoekopdrachten beheren:** toevoegen in één stap, budget, pauzeren, archiveren, kiezen in de bovenbalk; gewijzigde filters leiden niet tot valse verdwijningen.
- **Stabiele voertuigidentiteit** per bron, terugkeer van een auto als gebeurtenis, één onwaarschijnlijke prijs laat een controle niet meer mislukken.
- **Mijn wensen per zoekopdracht:** zelf wensen toevoegen met zoekwoorden, lokale herkenning zonder AI, belang en indeling herrekenen direct.
- **Match met onzekerheid:** "x % bevestigd · tot y % mogelijk", statuschip met reden, corrigeren met één klik, vragen aan de verkoper.
- **Aanbodlijst en autopagina:** tabs, filters en sortering in het adres, prijsverloop als trapgrafiek, prijzen per aanbieder.
- **Marktwaarde en onderhandelen:** vergelijkbare auto's in dezelfde zoekopdracht, kilometercorrectie, band P25–P75, openingsbod, streefprijs en grens zonder vast kortingspercentage, met argumenten.
- **Marktoverzicht** dat de zeven marktvragen beantwoordt, met een prijsindex die samenstelling scheidt van echte prijsverandering.
- **Controles en AI-beoordeling:** voortgang en actualiteit, wat er veranderde, herkomst per oordeel en herbeoordelen zonder controle.

Alle bedragen zijn **vraagprijzen**; een verdwenen advertentie is geen bewijs van verkoop. Elke schatting toont de steekproefomvang.

## Nieuw in v0.3

- **Zelf een Gaspedaal-URL plakken:** een nieuwe experimentele `gaspedaal_site`-adapter kan ingesloten gestructureerde advertentiegegevens uit de zoekpagina lezen en paginering afhandelen. Vereist `DATA_SOURCE_APPROVED=true`. **Nog niet live gevalideerd op Gaspedaal.**
- **Aanbieders-pop-up als tweede informatielaag:** elk voertuig kan meerdere `portals` bevatten. Hun namen, doorkliklinks, prijzen en prijsobservaties verschijnen in het autodetail.
- **Oorspronkelijke advertentie als derde informatielaag:** bij expliciet opgegeven hostnames kan de applicatie beperkt een redirect naar de oorspronkelijke dealeradvertentie volgen en tekst gebruiken voor Gemini. De verwerkingsuitkomst wordt in het uitvoeringslog en autodetail vastgelegd.
- **Fail closed:** onvolledige paginering of ontbrekende stabiele advertentie-ID's leidt niet tot onterechte verkoopmeldingen.
- Zie [`docs/ZOEKURL_AANBIEDERS_EN_DETAIL.md`](docs/ZOEKURL_AANBIEDERS_EN_DETAIL.md) voor volledige configuratie, voorbeelden en validatiestappen.

## Wat werkt al?

- Zoekprofielen aanmaken met je eigen Gaspedaal-URL; JSON-snapshot importeren of directe Gaspedaal-API gebruiken zodra het endpoint is geconfigureerd en geverifieerd.
- Via Home Assistant een beveiligde `POST /api/v1/refresh-runs` starten; planning gebeurt **alleen** in Home Assistant.
- Handmatige knop **Nu verversen**, per zoekprofiel of voor alle profielen.
- Persistente SQLite-wachtrij voor refreshes, run-ID, audittrail, foutmeldingen, idempotency-key en overlapbeveiliging.
- Iedere geslaagde controle slaat de vraagprijs opnieuw op, ook bij onveranderde prijs. Prijswijzigingen staan als afzonderlijke events in de database.
- Verdwijnstatussen: `ACTIVE` → `MISSING_UNCONFIRMED` → `OFF_MARKET` (standaard na 7 dagen en minstens twee geslaagde controles). **Niet** gelijkstellen aan verkocht.
- Must-have/nice-to-have-criteria, configureerbare gewichten, 70/30-score, aparte selectieafkeur bij aantoonbaar ontbrekende must-have.
- Tokenzuinige lokale tekstextractie, synoniemen, conservatieve patroonherkenning en optionele Gemini-classificatie via de officiële Google GenAI SDK.
- Apart Gemini-integratielog met gesaniteerde verzonden payload, raw response, gevalideerde claims, tokenaantallen, timings en foutstatus.
- Nederlandse responsive UI met dashboards, optiebewijs, prijsverloop, onderhandelingsvergelijking, notities, handmatige correcties en CSV-export.
- Docker Compose, voorbeeld-HA-automatisering én een Home Assistant OS-app/add-on bronpakket.

## Snel installeren (Home Assistant Container / eigen Docker-host)

Vereist: Docker met Compose en toegang tot poort 8099 vanaf je Home Assistant-installatie.

```bash
cp .env.example .env
# Stel UI_PASSWORD, SESSION_SECRET en HA_REFRESH_TOKEN in op drie verschillende,
# lange willekeurige waarden. Optioneel: vul GEMINI_API_KEY in.
docker compose up -d --build
```

Open `http://<IP-van-je-server>:8099` en log in met `UI_PASSWORD`.

**Zo start je zonder API-validatie met demo-data:** maak in de webinterface een zoekprofiel aan met je Gaspedaal-URL. Open daarna **JSON importeren** en selecteer [`sample_data/xc90_demo_snapshot.json`](sample_data/xc90_demo_snapshot.json). Klik **Nu verversen**. Dit zijn duidelijk gemarkeerde **fictieve** auto's, uitsluitend voor een demonstratie. Importeer bij de volgende controle een gewijzigde snapshot om prijsverschillen te zien.

Zonder `GEMINI_API_KEY` blijft lokale tekstherkenning functioneren; in het integratielog staat `SKIPPED_NO_KEY`. Gemini-aanroepen zijn **niet end-to-end getest** met jouw betaalde Google-account omdat er geen API-sleutel is gedeeld. Een model-ID moet actief zijn voor jouw project; wijzig `GEMINI_MODEL` indien nodig. De standaard is `gemini-3.5-flash-lite`.

## Directe Gaspedaal-zoek-URL en JSON-API activeren

De directe HTML-adapter is gebouwd en offline getest, maar moet nog tegen de echte zoekpagina worden gevalideerd. Daarnaast is de generieke JSON-API-adapter beschikbaar; het daadwerkelijke JSON-zoekendpoint en de mapping zijn onbekend. Identificeer dit eerst via het browsernetwerk en configureer `GASPEDAAL_API_SEARCH_TEMPLATE`, `GASPEDAAL_API_ITEMS_PATH` en eventueel `GASPEDAAL_API_FIELDS_JSON` in `.env` (voor Home Assistant OS: in de appopties). Zet `DATA_SOURCE_APPROVED=true` als je de bron wilt activeren. Meer uitleg en valideringsstappen: [`docs/DIRECTE_GASPEDAAL_API.md`](docs/DIRECTE_GASPEDAAL_API.md).

**Live automatische Gaspedaal-refresh is nog niet bewezen werkend.** De JSON-import blijft beschikbaar als volledig werkende testmodus.

## Home Assistant tijdschema

Voeg de inhoud van [`homeassistant/configuration.yaml.example`](homeassistant/configuration.yaml.example) toe aan `configuration.yaml` en pas het server-IP aan. Zet de headerwaarde in `secrets.yaml` zoals in [`homeassistant/secrets.yaml.example`](homeassistant/secrets.yaml.example). Maak vervolgens via **Instellingen → Automatiseringen** een automatisering die `rest_command.gaspedaal_prijsmonitor_refresh` uitvoert. Een voorbeeld staat in [`homeassistant/automation.yaml.example`](homeassistant/automation.yaml.example).

Verzoek:

```http
POST /api/v1/refresh-runs
Authorization: Bearer <HA_REFRESH_TOKEN>
Content-Type: application/json

{"scope":"all","reason":"scheduled_ha"}
```

Verwacht `202` met een `run_id`; bij een overlappende run `409` en bij een idempotente herhaling `200`. De frontendknop gebruikt een sessiecookie en CSRF-header in plaats van de HA-token. Dit endpoint is niet bedoeld als publiek toegankelijke internetservice.

## Home Assistant OS (Supervisor-app)

Een app/add-on bronpakket staat in [`addons/occasioniq/`](addons/occasioniq/). De broncode wordt mee verpakt met `./scripts/sync_ha_addon.sh` (uitvoeren na codewijzigingen). Het pakket is **niet** op een Home Assistant OS-installatie getest en vereist een bereikbare GitHub-repository of een lokale add-on-repository voordat het in Supervisor geïnstalleerd kan worden. Open de app via poort 8099 op je LAN; de webinterface gebruikt eigen login, geen HA Ingress. De Supervisor-opties bevatten het UI-wachtwoord, refresh-token, sessiesleutel en optionele Gemini-sleutel. De database wordt in de persistente `/data`-map opgeslagen.

## Opties en scores

Een bewezen `PRESENT` levert het volledige gewicht op, `ABSENT`, `UNKNOWN` en `CONFLICT` leveren 0 op. Groepspercentages worden berekend uit de som van de actieve criteriumgewichten. `totale_score = 0.7 × must_have_pct + 0.3 × nice_to_have_pct`. Een **ontbrekende must-have** resulteert in `REJECTED`, ongeacht het percentage; onbekende must-haves in `UNVERIFIED`. Geen impliciete claims op basis van uitvoering alleen. Handmatige overrides worden bij reguliere refreshes bewaard.

De prijsvergelijking gebruikt vergelijkbare **vraagprijzen** en eenvoudige regels voor bouwjaar, kilometerstand en uitvoering. Onderhandelingsindicaties worden alleen getoond bij minimaal vijf vergelijkbare auto's en zijn geen betrouwbare voorspelling van een gerealiseerde verkoopprijs. De volledige statistische normalisatie en betrouwbare transactiedata uit de oorspronkelijke specificatie zijn nog vervolgwerk.

## De code lokaal testen

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q app
for f in app/static/js/*.js app/static/js/pages/*.js; do node --check "$f"; done
```

Lokaal draaien met demo-data (wachtwoord `dev`, database `data/dev.sqlite3`):

```bash
python scripts/seed_demo.py --reset
python scripts/dev_server.py
```

Open daarna `http://127.0.0.1:8099`. Elk scherm heeft een eigen adres, bijvoorbeeld `#/aanbod` of `#/auto/<id>`.

## Beveiliging en bewaren

- Gebruik lange unieke geheimen; commit `.env` nooit naar Git.
- UI: ondertekende, HttpOnly, SameSite=Strict sessiecookie + CSRF-header voor mutaties. HA: apart bearer-token.
- Geen aanroep van arbitraire URL's; profielen accepteren alleen HTTPS Gaspedaal-URL's. JSON-import leest geen remote websites.
- Gemini ontvangt uitsluitend relevante gestripte advertentietekst; telefoonnummers en e-mails worden lokaal verwijderd.
- Volledige Gemini-input/output wordt standaard na 90 dagen uit de integratietabel verwijderd; metadata blijft bestaan.
- Voer alleen data door waar je rechten voor hebt om die op te slaan en aan Gemini te verstrekken.
- De app is voor een **privé LAN** ontworpen. Zet hem niet onbeschermd op internet; gebruik HTTPS via reverse proxy of VPN. Extra productie-hardening (rate limiting, accounts, backupbeleid) is vervolgwerk.
- Zorg voor backups van de Docker-volume `price_monitor_data`. Bij de Home Assistant-app wordt `/data` persistent bewaard.

## Wat ontbreekt nog voor productiegebruik?

1. **Live Gaspedaal-bron valideren:** bevestig dat de huidige Gaspedaal-HTML ingesloten advertenties met stabiele ID’s bevat. Zo niet: inspecteer het browsernetwerk en implementeer op basis van de werkelijke requests een passende bronadapter. Test paginering en portaalpop-up met echte data.
2. **Echte Gemini-call testen** met jouw sleutel en gekozen model, inclusief quota- en kostengrenzen.
3. Geavanceerde herplaatsings-/kentekendeduplicatie en RDW-validatie. Meerdere advertentieportalen per auto worden inmiddels apart gevolgd.
4. Statistisch verbeterd waarderingsmodel, prijsniveau op termijn en onderhandelingsadvies met voldoende vergelijkbare voertuigen.
5. HA OS add-on in een echte Supervisor-installatie valideren, backup/restore en security-hardening testen.

Dit project is opzettelijk een functionele **MVP**, niet de claim dat de volledige bouwspecificatie al productierijp is.
