# Verbeterplan OccasionIQ — van werkende MVP naar het doel

Opgesteld op 16-11-2026 op basis van de volledige code (v0.4.0, commit `4c1e54f`), een lokale proefrun met de demo-snapshot en `Doelstelling_OccasionIQ.md` (hierna: **het doel**, met §-nummers).

Dit document is geschreven om **zonder verdere context** te worden uitgevoerd door Claude Sonnet of Opus. Alle ontwerpkeuzes zijn hier al gemaakt; de uitvoerder hoeft niets te bedenken, alleen te bouwen en te controleren.

---

## 1. Zo gebruik je dit plan

**Eén werkpakket (WP) per sessie, in de volgorde van §5.** Elk WP is een afgerond geheel met eigen commit en versie-bump.

Startprompt voor een nieuwe sessie:

```text
Lees CLAUDE.md en docs/VERBETERPLAN.md §1–§4. Voer daarna werkpakket WP-<nr> uit §6 uit.
Houd je aan de vaste keuzes en aan "Klaar als". Werk daarna de voortgangstabel in §5 bij.
```

Regels voor de uitvoerder:

1. Lees eerst de bestanden die het WP noemt. Regelnummers verwijzen naar commit `4c1e54f`; na eerdere WP's zijn ze verschoven, zoek dan op de genoemde functienaam.
2. Wijk niet af van de **vaste keuzes** in een WP. Blijkt een keuze onuitvoerbaar, stop dan en leg het aan de gebruiker voor in plaats van zelf een alternatief te kiezen.
3. Een WP is pas klaar als alle punten onder **Klaar als** aantoonbaar kloppen (tests draaien, scherm bekeken op 1440 px én 375 px breed).
4. Punten gemarkeerd met **⚠ Eerst nagaan** zijn niet geverifieerd tegen live Gaspedaal-data. Controleer ze voordat je erop bouwt.
5. Bouw niets uit §8 (bewust niet doen).

Aanbevolen model per WP staat in §5: **Sonnet** voor afgebakend UI-, CRUD- en refactorwerk, **Opus** waar datamigratie of rekenmodellen fout kunnen gaan zonder dat een test het direct laat zien.

---

## 2. Spelregels van deze codebase

| Onderwerp | Regel |
|---|---|
| Bron van waarheid | Wijzig alleen `app/`, `tests/`, `docs/`, `homeassistant/`, `scripts/`. `addons/occasioniq/app/` is een **kopie**: draai na elke wijziging `bash scripts/sync_ha_addon.sh` (Windows: Git Bash) en bewerk die map nooit met de hand. |
| Versie | Staat nu op drie plekken en loopt uiteen (`app/main.py:35` en `:117` zeggen 0.3.0, `addons/occasioniq/config.yaml:2` zegt 0.4.0). WP-01 maakt hier één constante van; daarna per WP één minor-bump. |
| Tests | `python -m pytest -q` moet slagen (nulmeting: 35 geslaagd). Elk WP voegt tests toe voor nieuwe backendlogica. Daarnaast `python -m compileall -q app` en `node --check` op elk gewijzigd `.js`-bestand. |
| Frontend | Geen framework, geen build-stap, geen CDN of externe scripts/fonts. Alleen bestanden onder `app/static/`. Alle data uit de API gaat door `esc()` voordat ze in HTML komt. Nooit `prompt()`, `alert()` of `confirm()`. |
| Taal | Alle zichtbare tekst in het Nederlands, zonder interne codes (zie de woordenlijst in WP-03). |
| Database | SQLite. Schemawijzigingen uitsluitend via het migratiemechanisme uit WP-01. Nooit bestaande prijsobservaties wijzigen of weggooien. |
| Fail-closed | Een onvolledige of mislukte controle mag nooit leiden tot "verdwenen"-conclusies (`worker.py`, `scan_profile`). Dit gedrag blijft in elk WP intact. |
| Eerlijkheid | Vraagprijs ≠ verkoopprijs. Een verdwenen advertentie ≠ verkocht. Elke schatting heet in de UI "schatting" of "indicatie" en toont de steekproefomvang `n`. |
| Commit | Eén commit per WP, in de bestaande stijl: `feat: <omschrijving> (0.x.0)`. Niet pushen zonder vraag van de gebruiker. |

---

## 3. Wat er nu staat (kort)

- **Backend:** FastAPI + SQLite (`app/main.py`, `app/db.py`), één achtergrondworker (`app/worker.py`) die controles uit een wachtrij verwerkt. Home Assistant start een controle via `POST /api/v1/refresh-runs` met een bearer-token.
- **Bronnen:** Gaspedaal-zoekpagina uitlezen (`app/gaspedaal_site.py`), optionele JSON-API (`app/gaspedaal_api.py`), handmatige JSON-import, en optioneel de tekst van de oorspronkelijke advertentie op toegestane domeinen (`app/source_details.py`).
- **Uitrusting:** vaste lokale herkenning voor trekhaak en 22-inch (`app/extraction.py`), de rest via Gemini (`app/gemini.py`), score 70 % must / 30 % nice (`app/scoring.py`).
- **Frontend:** één `index.html`, één `app.js` van 155 zeer lange regels, één `style.css`. Zeven pagina's; detail van een auto in een modaal venster.

Goed en te behouden: de fail-closed scanner, prijsobservatie bij elke controle, meerdere aanbieders per auto, bewijs-validatie van Gemini-citaten, handmatige correcties die een refresh overleven, het uitvoerings- en Gemini-log, CSRF en sessiebeveiliging.

---

## 4. Waar de app nu tekortschiet ten opzichte van het doel

Elke bevinding is in de code of in de draaiende app vastgesteld, tenzij gemarkeerd met ⚠.

### 4.1 Functionele gaten

| # | Doel | Bevinding | Bewijs | WP |
|---|---|---|---|---|
| F1 | §4 uitrustingsmatch | ⚠ Bij live Gaspedaal-data is er vrijwel **geen advertentietekst**: de zoekpagina-adapter vult `description` niet. Tekst komt alleen via de detailpagina's, en die staan standaard uit en zijn begrensd op 5 per controle. Gevolg: bijna alles "Onbekend", score ≈ 0 %. | `gaspedaal_site.py:65-89`, `config.py:22-23` | 05 |
| F2 | §4 wensen indelen | Wensen kunnen niet worden toegevoegd of verwijderd; alleen groep en gewicht van de tien vaste zijn aanpasbaar. Synoniemen zijn niet zichtbaar of bewerkbaar. | `main.py:177-192` (alleen GET/PUT), `app.js:63-67` | 06 |
| F3 | §4 synoniemen | Lokale herkenning is hardgecodeerd voor precies twee sleutels. Elke nieuwe wens leunt volledig op Gemini. | `extraction.py:38-54` | 06 |
| F4 | §4 onbekend ≠ afwezig | In de score telt "onbekend" exact als "afwezig" (0 punten). Er is geen bovengrens ("tot 100 % mogelijk") en geen bewijsdekking. | `scoring.py:14` | 07 |
| F5 | §4 vragen aan verkoper | Ontbreekt volledig. | — | 07 |
| F6 | §4 corrigeren | Correctie gaat via twee `prompt()`-vensters waarin de gebruiker `PRESENT`/`ABSENT` moet typen. | `app.js:133` | 07 |
| F7 | §3 prijsgeschiedenis | De lijst toont alleen de actuele prijs. Dagen in beeld, eerste prijs, aantal en omvang van verlagingen worden nergens getoond, hoewel de data er is (`first_seen`, `listing_events`). | `app.js:61`, `main.py:288-295` | 08 |
| F8 | §3 verdwenen/terug | De beschikbaarheidsstatus staat niet in de UI: verdwenen auto's staan ongemarkeerd tussen actieve. "Opnieuw aangeboden" bestaat niet als gebeurtenis; een teruggekeerde auto wordt stil weer actief. | `app.js:61`, `worker.py:155-159` | 02, 08 |
| F9 | §5 vergelijkbare auto's | Vergelijkingsset negeert de zoekopdracht (alle actieve auto's van alle profielen) en eist een exact gelijke uitvoeringstekst. Met echte, vrije uitvoeringsnamen levert dat vrijwel nooit een match op. | `main.py:311-315` | 10 |
| F10 | §6 onderbouwd bod | Openingsbod is een vaste formule (`min(vraagprijs, P25) × 0,98`), dus precies het "vaste percentage" dat het doel afwijst. Er is geen grens (maximale prijs), de vergelijkbare auto's zelf worden niet getoond, kilometerstand wordt niet gecorrigeerd. | `scoring.py:38-57`, `app.js:95` | 10 |
| F11 | §5 marktbeeld | Het dashboard toont één lijn: het **gemiddelde** per dag, niet gecorrigeerd voor wisselend aanbod. Geen P25/P75, geen in- en uitstroom, geen prijsverlagingsstatistiek, geen tijd-in-beeld, geen prijs-versus-km. | `main.py:266-284` | 11 |
| F12 | §5 budget | Er bestaat geen budget of streefprijs in de app. | — | 04, 11 |
| F13 | §2, §8 meerdere zoekopdrachten | Dashboard, lijst en wensen zijn niet per zoekopdracht. De kruimel "VOLVO XC90" is hardgecodeerd. Een zoekopdracht kan niet worden hernoemd, gepauzeerd of verwijderd. Wensen zijn globaal. | `index.html:37`, `main.py:138-164` | 04, 13 |
| F14 | §2 filters wijzigen | Als de zoeklink van een profiel verandert, zouden auto's die buiten de nieuwe filters vallen als "verdwenen" worden gemarkeerd. | `worker.py:210-231` | 04 |
| F15 | §7 regie | Na "Nu verversen" verschijnt een melding met een run-ID en wordt de pagina na 1,4 s één keer herladen; geen voortgang, geen "klaar"-signaal. Nergens staat wanneer de laatste geslaagde controle was. | `app.js:114-118` | 09 |
| F16 | §7 herleidbaarheid | Lokale regels en Gemini krijgen dezelfde bron `AD_TEXT`; een oordeel is niet te herleiden naar het bijbehorende logrecord. Er is geen overzicht van auto's die nog op beoordeling wachten (limiet 20 per controle). | `worker.py:92`, `worker.py:55-56` | 12 |
| F17 | §9 signalen | Home Assistant kan een controle starten maar geen resultaten teruglezen, dus ook niet melden. | `main.py:194-244` | 14 |

### 4.2 Fouten en risico's in bestaand gedrag

| # | Bevinding | Bewijs | WP |
|---|---|---|---|
| B1 | **Prijshistorie kan breken bij wisselen van gegevensbron.** Het voertuig-ID bevat het providertype. Een profiel dat via de terugval live wordt gelezen krijgt `fixture:<id>`; na omschakelen naar "Gaspedaal zoeklink" wordt het `gaspedaal_site:<id>` en ontstaat een nieuwe auto zonder historie. | `worker.py:143`, `provider.py:85` | 02 |
| B2 | **Eén advertentie met een onwaarschijnlijke prijs laat de hele controle van dat profiel mislukken.** | `worker.py:109-111` | 02 |
| B3 | **Een gewicht aanpassen gooit alle beoordelingen weg.** Elke wijziging van een wens wist `analyzed_hash` van alle auto's, en gewicht en groep zitten in de vingerafdruk. Met de limiet van 20 Gemini-aanroepen per controle kan herstel bij een groot aanbod meerdere controles duren, terwijl alleen herrekenen nodig is. | `main.py:191`, `worker.py:43-44` | 06 |
| B4 | Kenteken wordt ingelezen maar nooit opgeslagen. | `provider.py:37`, `worker.py:163-166` | 02 |
| B5 | De lijst-API stuurt de volledige advertentietekst van maximaal 1000 auto's mee. | `main.py:288` (`l.*`) | 08 |
| B6 | Mediaan op het dashboard pakt bij een even aantal de bovenste waarde. | `main.py:278` | 11 |

### 4.3 UI en gebruiksgemak

| # | Bevinding | WP |
|---|---|---|
| U1 | Geen adressen per scherm: herladen of de terugknop brengt je altijd naar het overzicht; een auto is niet te bookmarken of te delen. | 01 |
| U2 | Autodetail is een modaal venster van 900 px met alles onder elkaar. Vastgesteld in de proefrun: `Escape` sluit het niet, en bij scrollen bewoog de pagina erachter mee (de achtergrond wordt niet vastgezet). | 08 |
| U3 | Lettertypen Manrope en DM Sans worden genoemd in `style.css:2` maar nergens geladen; de app valt terug op het systeemlettertype. Iconen zijn losse Unicode-tekens (◫ ▤ ⌕ ✦), die per apparaat anders ogen. | 03 |
| U4 | Geen sorteren, zoeken of filteren in het aanbod, behalve twee vinkjes. | 08 |
| U5 | Interne codes zichtbaar voor de gebruiker: `MANUAL_UI`, `AD_TEXT`, `SKIPPED_NO_KEY`, run-ID's in meldingen, "JSON snapshot", een bronkeuzelijst per profiel. | 03 |
| U6 | Lege en ladende toestanden zijn kale tekst ("Gegevens laden…", "Nog geen resultaten"). Een nieuwe gebruiker landt op een leeg dashboard zonder vervolgstap. | 03, 04 |
| U7 | Grafieken zijn statische SVG zonder aanwijswaarden; één meetdag toont één los punt; prijshistorie is een schuine lijn terwijl prijzen in stappen veranderen. | 08, 11 |
| U8 | Klikbare tabelrijen zijn niet met het toetsenbord te bereiken; veel tekst is 10–11 px in lichtgrijs. | 03 |
| U9 | Technische beheerschermen (Gemini-log, Home Assistant) staan op hetzelfde niveau als de dagelijkse schermen. | 03 |

---

## 5. Volgorde en voortgang

Werk van boven naar beneden. Werk deze tabel bij na elk WP (`☐` → `☑`, met datum en versie).

| WP | Titel | Lost op | Model | Status |
|---|---|---|---|---|
| 01 | Fundament: dev-omgeving, migraties, frontend in modules, adressen per scherm | U1 | Sonnet | ☑ 16-11-2026 · 0.5.0 |
| 02 | Betrouwbare voertuigidentiteit en scanrobuustheid | B1 B2 B4 F8 | **Opus** | ☑ 16-11-2026 · 0.6.0 |
| 03 | Ontwerpsysteem, navigatie en taal | U3 U5 U6 U8 U9 | Sonnet | ☑ 16-11-2026 · 0.7.0 |
| 04 | Zoekopdrachten beheren, kiezen en budget | F12 F13 F14 U6 | Sonnet | ☑ 16-11-2026 · 0.8.0 |
| 05 | Advertentietekst beschikbaar krijgen | F1 | Sonnet (eerst nagaan: Opus) | ☑ 16-11-2026 · 0.9.0 |
| 06 | Mijn wensen: toevoegen, synoniemen, direct herrekenen | F2 F3 B3 | Sonnet | ☑ 16-11-2026 · 0.10.0 |
| 07 | Matchscore met onzekerheid, vragen aan de verkoper, corrigeren | F4 F5 F6 | Sonnet | ☑ 16-11-2026 · 0.11.0 |
| 08 | Aanbodlijst en autopagina | F7 F8 B5 U2 U4 U7 | Sonnet | ☑ 16-11-2026 · 0.12.0 |
| 09 | Controles: voortgang, actualiteit, wat is er veranderd | F15 | Sonnet | ☑ 17-11-2026 · 0.13.0 |
| 10 | Marktwaarde en onderhandelingspositie | F9 F10 | **Opus** | ☑ 17-11-2026 · 0.14.0 |
| 11 | Marktoverzicht dat de zeven vragen beantwoordt | F11 F12 B6 U7 | **Opus** (rekenwerk), Sonnet (UI) | ☑ 17-11-2026 · 0.15.0 |
| 12 | Inzicht in de AI-beoordeling | F16 | Sonnet | ☐ |
| 13 | Wensen per zoekopdracht | F13 | **Opus** | ☐ |
| 14 | Optioneel, eerst bevestigen: meldingen via Home Assistant, shortlist vergelijken, dossier | F17, doel §9 | Sonnet | ☐ |

Na WP-08 is de app in dagelijks gebruik merkbaar beter; WP-10 en WP-11 leveren de kern van het doel (marktinzicht en onderhandelen).

---

## 6. Werkpakketten

### WP-01 — Fundament

**Doel.** De volgende WP's uitvoerbaar maken: lokaal kunnen draaien, schema veilig kunnen wijzigen, frontend in hanteerbare bestanden, en elk scherm een eigen adres. **Geen zichtbare functionele wijziging**, behalve dat adressen werken.

**Bouwen.**

1. `app/version.py` met `VERSION = '0.5.0'`. Gebruik deze in `main.py` (FastAPI-titel en `/health`). Zet `addons/occasioniq/config.yaml` op dezelfde waarde.
2. `scripts/dev_server.py`: zet, alleen als ze nog niet bestaan, de omgevingsvariabelen `UI_PASSWORD`, `SESSION_SECRET`, `HA_REFRESH_TOKEN` op duidelijke dev-waarden, `DATABASE_PATH=./data/dev.sqlite3`, `GEMINI_ENABLED=false`, en start `uvicorn app.main:app` op `127.0.0.1:8099`. (`data/` staat al in `.gitignore`.)
3. `scripts/seed_demo.py`: vult de dev-database **rechtstreeks via `app.db`** met `sample_data/xc90_demo_snapshot.json` en bouwt 45 dagen historie op: per auto een eerste waarneming op een gespreide datum, bij ongeveer een derde één of twee prijsverlagingen, twee auto's die verdwenen zijn, één die terugkwam. Vaste `random.seed(1)` zodat het resultaat reproduceerbaar is. Dit is nodig om grafieken en statistieken in latere WP's te kunnen beoordelen.
4. `.claude/launch.json` met één configuratie `occasioniq-dev` die `scripts/dev_server.py` start op poort 8099 met de Python uit een lokale `.venv` (`python -m venv .venv`, daarna `pip install -r requirements-dev.txt`). Voeg `.venv/` toe aan `.gitignore`.
5. **Migraties** in `app/db.py`: tabel `schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT)` en een lijst `MIGRATIONS = [(1, fn), …]`. `init_db()` voert ontbrekende migraties in volgorde uit, elk in een eigen transactie. Vóór de eerste migratie die data wijzigt: kopieer het databasebestand naar `<pad>.bak-v<versie>`. Verplaats de bestaande losse `ALTER TABLE … photos_json` (`db.py:137-139`) naar migratie 1.
6. **Frontend in ES-modules** onder `app/static/js/`, geladen met `<script type="module" src="/static/js/main.js">`:
   - `api.js` (fetch + CSRF), `format.js` (`fmt`, `euro`, `dt`, `esc`, nieuw: `relatief(datum)` → "2 uur geleden"), `ui.js` (`tag`, `table`, `toast`, `modal`, `head`), `charts.js`, `router.js`, `main.js`, en één bestand per pagina in `pages/`.
   - Normale opmaak: één statement per regel, maximaal ±120 tekens. De huidige regels van meer dan 1000 tekens zijn niet betrouwbaar te bewerken.
   - Voeg in `main.py` vóór het mounten van `/static` toe: `mimetypes.add_type('application/javascript', '.js')`. Op Windows levert Python anders soms `text/plain`, en dan weigert de browser modules.
7. **Router op de hash.** Routes: `#/overzicht`, `#/aanbod`, `#/auto/<id>`, `#/wensen`, `#/zoekopdrachten`, `#/controles`, `#/controles/<id>`, `#/ai-analyse`, `#/ai-analyse/<id>`, `#/instellingen`. Onbekend of leeg → `#/overzicht`. Navigatieknoppen worden `<a href="#/…">`. De bestaande modale vensters blijven in dit WP bestaan, maar openen via de route (zodat terugknop en herladen werken).

**Klaar als.**
- `python scripts/dev_server.py` + `python scripts/seed_demo.py` geeft een gevulde app; inloggen werkt.
- Elk scherm werkt als voorheen; herladen op `#/aanbod` blijft op het aanbod; de terugknop sluit een geopende auto.
- Bestaande 35 tests slagen; nieuwe test bewijst dat migraties precies één keer draaien.
- Geen `.js`-regel langer dan 160 tekens.

---

### WP-02 — Betrouwbare voertuigidentiteit en scanrobuustheid *(Opus)*

**Doel (§2, §3).** Dezelfde auto blijft dezelfde auto, wat er ook aan de instellingen verandert. Een controle strandt niet op één rare advertentie. Terugkeer wordt vastgelegd.

**Vaste keuzes.**

1. **ID per bron, niet per providertype.** In `scan_profile` (`worker.py:143` én de opzoeking op `:123-124`): `naamruimte = 'gaspedaal'` als `snapshot.metadata.get('source','')` begint met `GASPEDAAL`, anders `'import'`. `external_id = f'{naamruimte}:{ad.external_id}'`.
2. **Migratie van bestaande rijen** (met back-up uit WP-01):
   - `gaspedaal_site:X` → `gaspedaal:X`.
   - `fixture:X` → `gaspedaal:X` als de auto alleen voorkomt in profielen waarvan `fixture_payload IS NULL`; anders `import:X`.
   - Botst het nieuwe ID met een bestaande rij, dan **samenvoegen**: behoud de rij met de oudste `first_seen`; zet van de andere alle verwijzingen om (`price_observations`, `source_price_observations` met `INSERT OR IGNORE`, `listing_sources` bij conflict bestaande behouden, `listing_events`, `claims` waarbij `MANUAL_OVERRIDE` wint, `integration_requests`, `negotiation_notes`, `profile_listings`, `source_detail_attempts`), neem `favorite` over als één van beide favoriet is, en verwijder daarna de dubbele rij.
3. **Ongeldige prijs** (`worker.py:109-111`): niet meer de hele scan afbreken. Sla die advertentie over, log een `WARN`-gebeurtenis met het externe ID, tel `skipped_invalid` in de samenvatting. Belangrijk: het ID telt wél als "gezien", zodat de auto niet als verdwenen wordt gemarkeerd; er komt geen prijsobservatie.
4. **Terugkeer.** Als een bestaande auto wordt gezien terwijl `profile_listings.status` niet `ACTIVE` was: gebeurtenis `REAPPEARED` (met `new_price`) en teller `reappeared`.
5. **Kenteken.** Kolom `listings.license_plate` (migratie), gevuld bij insert en update.
6. ⚠ **Eerst nagaan:** bevat de Gaspedaal-stream een kenteken? Zo ja: als een **nieuwe** advertentie hetzelfde kenteken heeft als een auto met status `OFF_MARKET`, leg dan gebeurtenis `RELISTED` vast op de nieuwe auto en vul kolom `listings.relisted_from`. Zo nee: dit onderdeel overslaan en dat in dit document noteren.
   > **Uitkomst (16-11-2026):** nagegaan op een live zoekpagina (`/volvo/xc90`, 100 advertenties, met `scripts/inspect_occasion_fields.py`). De `occasions`-stream bevat **geen kenteken**. `RELISTED` en `listings.relisted_from` zijn daarom niet gebouwd. De kolom `license_plate` bestaat wel en wordt gevuld zodra een bron (JSON-import of API) een kenteken levert.

**Klaar als.** Tests voor: migratie zonder en met botsing (historie van beide rijen blijft, in tijdsvolgorde); wisselen van provider maakt geen nieuwe auto; ongeldige prijs → scan `COMPLETE`, auto niet verdwenen; verdwenen-en-terug → één `REAPPEARED`.

---

### WP-03 — Ontwerpsysteem, navigatie en taal

**Doel.** De uitstraling en het gemak van een goed SaaS-product: rustig, consistent, voorspelbaar. Dit WP verandert vormgeving en woorden, niet de functies.

**Vaste keuzes — vormgeving** (`app/static/style.css`, opnieuw opbouwen in secties: tokens, basis, layout, componenten, pagina's):

- **Tokens** als CSS-variabelen op `:root`: kleuren (behoud navy `#152037` en teal `#24baa7` als merk; voeg semantische kleuren toe: succes, waarschuwing, gevaar, info, elk met tekst-, vlak- en randtint), afstanden op een raster van 4 px (`--s1: 4px` … `--s8: 48px`), radius (6 / 10 / 14), schaduw (maximaal twee niveaus), lettergroottes (12 / 13 / 14 / 16 / 20 / 28).
- **Lettertype:** Inter Variable (OFL-licentie) zelf gehost in `app/static/fonts/` met `@font-face` en `font-display: swap`. Lukt downloaden niet, gebruik dan `system-ui, "Segoe UI", Roboto, sans-serif`. Verwijder in beide gevallen alle verwijzingen naar Manrope en DM Sans. Nooit via een CDN.
  > **Uitvoering (16-11-2026):** Inter is niet gedownload (downloaden van een extern bestand vraagt eerst akkoord van de gebruiker). De terugval `system-ui, "Segoe UI", Roboto, sans-serif` staat in `--font`; Inter toevoegen = bestand in `app/static/fonts/` plus `@font-face` en `--font` aanpassen.
- **Kleinste tekst 12 px.** Secundaire tekst minimaal contrast 4,5:1 op wit. Getallen in tabellen en kaarten: `font-variant-numeric: tabular-nums`, rechts uitgelijnd.
- **Iconen:** één SVG-sprite `app/static/icons.svg` met ongeveer twintig lijn-iconen in Lucide-stijl (ISC-licentie; 24 px, lijndikte 1,75), gebruikt via `<svg><use href="/static/icons.svg#naam"/></svg>`. Vervang alle Unicode-tekens die als icoon dienen.
- **Componenten** in `ui.js` + CSS, elk met hover-, focus- (`:focus-visible`-ring), uitgeschakelde en ladende toestand:
  knop (primair, secundair, tekst, gevaar; maten m en s), chip/badge, tabs met aantallen, segmentkeuze (drie of vier opties naast elkaar), tabel (vaste kop, sorteerbare kolomkoppen met `aria-sort`), kaart, kerncijfer, dialoog op basis van `<dialog>` (focus blijft binnen, `Escape` sluit, achtergrond scrolt niet), melding (gestapeld, variant succes/fout, `aria-live`), skelet-laadtoestand, lege toestand (icoon, titel, één zin, één actie), formulierveld met foutmelding onder het veld.
- **Laden:** elke pagina toont skeletblokken in de vorm van de uiteindelijke inhoud, geen tekst "laden…". **Fout:** kaart met uitleg en knop "Opnieuw proberen".
- **Toegankelijkheid:** alles wat klikbaar is, is een `<a>` of `<button>`. Tabelrijen zijn niet meer als geheel klikbaar; de titelcel bevat de link. Respecteer `prefers-reduced-motion`.
- **Responsief:** onder 760 px worden tabellen kaartlijsten; aanraakdoelen minimaal 40 px hoog.

**Vaste keuzes — navigatie** (`index.html`):

- Zijbalk, bovenste groep: Overzicht · Aanbod · Shortlist · Mijn wensen · Zoekopdrachten. Groep **Beheer**: Controles · AI-beoordeling · Instellingen (de Home Assistant-uitleg verhuist naar Instellingen).
- Bovenbalk links: de gekozen zoekopdracht (in dit WP nog een vaste tekst uit de API; de keuzelijst komt in WP-04). Verwijder de hardgecodeerde kruimel "VOLVO XC90" en het label "Configureerbare databron". Rechts: knop "Nu controleren".
- Voettekst over vraagprijzen blijft.

**Vaste keuzes — woordenlijst.** Vervang overal in de UI:

| Intern | Zichtbaar |
|---|---|
| refresh, run, scan | controle |
| zoekprofiel | zoekopdracht |
| `MANUAL_UI` / `HOME_ASSISTANT` | Handmatig / Home Assistant |
| `COMPLETE` / `PARTIAL` / `FAILED` / `RUNNING` / `QUEUED` | Geslaagd / Gedeeltelijk / Mislukt / Bezig / Wacht |
| `ACTIVE` / `MISSING_UNCONFIRMED` / `OFF_MARKET` | Te koop / Niet meer gezien / Uit het aanbod |
| `MATCH` / `UNVERIFIED` / `REJECTED` / `REVIEW` | Voldoet / Nog te controleren / Valt af / Tegenstrijdig |
| `PRESENT` / `ABSENT` / `UNKNOWN` / `CONFLICT` | Aanwezig / Afwezig / Onbekend / Tegenstrijdig |
| `AD_TEXT` / `MANUAL_OVERRIDE` | Uit de advertentie / Door jou bevestigd |
| `SUCCESS` / `ERROR` / `CACHE_HIT` / `LOCAL_ONLY` / `SKIPPED_NO_KEY` / `SKIPPED_BUDGET` | AI-beoordeling / Mislukt / Ongewijzigd / Zonder AI herkend / AI staat uit / Wacht op volgende controle |
| optieprofiel, criteria | mijn wensen |

Run-ID's en andere technische ID's staan alleen nog op de beheerschermen, nooit in meldingen.

**Klaar als.** Alle pagina's gebruiken uitsluitend de nieuwe componenten; geen inline `style=` meer in de JS; geen van de interne codes uit de tabel is zichtbaar op de dagelijkse schermen; met alleen het toetsenbord is elke actie bereikbaar; schermen gecontroleerd op 1440, 1024 en 375 px.

---

### WP-04 — Zoekopdrachten beheren, kiezen en budget

**Doel (§2, §5, §8).** Zelf bepalen welke markt je volgt, kunnen wisselen tussen zoekopdrachten, en een budget vastleggen.

**Bouwen.**

1. Migratie op `search_profiles`: `budget_eur INTEGER NULL`, `archived_at TEXT NULL`, `scope_changed_at TEXT NULL`.
2. API: `PATCH /api/v1/profiles/{id}` (titel, `search_url`, `budget_eur`, `enabled`) en `POST /api/v1/profiles/{id}/archive`. `GET /profiles` geeft per zoekopdracht ook: aantal te koop, aantal "Voldoet", tijdstip en uitkomst van de laatste controle.
3. **Zoekopdracht kiezen.** Keuzelijst in de bovenbalk met alle actieve zoekopdrachten plus "Alle zoekopdrachten". De keuze staat in `localStorage` (met try/catch) en gaat als `profile_id` mee naar `/dashboard`, `/listings` en later `/market`. Pas `/dashboard` aan zodat het `profile_id` respecteert (join op `profile_listings`).
4. **Pagina Zoekopdrachten.** Per zoekopdracht een kaart: naam, link "Open op Gaspedaal", aantallen, laatste controle, budget, schakelaar Actief/Gepauzeerd, menu met Bewerken, Nu controleren, Archiveren. De knop "JSON importeren" en de bronkeuze verhuizen naar een inklapbaar blok "Geavanceerd" binnen Bewerken.
5. **Toevoegen in één stap.** Eén veld: plak de Gaspedaal-link. De naam wordt voorgesteld uit het pad (`/volvo/xc90/…` → "Volvo XC90") en is aanpasbaar. Na opslaan start direct de eerste controle met zichtbare voortgang.
6. **Filters wijzigen zonder valse verdwijningen (F14).** Bij een gewijzigde `search_url`: zet `scope_changed_at`. De eerstvolgende **volledige** controle geeft niet-geziene auto's status `OUT_OF_SCOPE` (zichtbaar als "Buiten huidige filters") in plaats van `MISSING_UNCONFIRMED`, legt daarvoor **geen** verdwijn-gebeurtenis vast, en wist daarna `scope_changed_at`. `OUT_OF_SCOPE` telt bij de berekening van `listings.availability` niet als actief en niet als verdwenen. Toon bij het bewerken de waarschuwing: "Auto's die buiten de nieuwe filters vallen blijven bewaard, maar worden niet meer gevolgd."
7. **Eerste gebruik.** Zonder zoekopdrachten toont Overzicht een startlijst met vier stappen en hun status: zoekopdracht toevoegen → wensen kiezen → eerste controle → automatisch laten controleren via Home Assistant.

**Klaar als.** Tests voor `PATCH`, archiveren en het `OUT_OF_SCOPE`-pad (geen `MISSING`-gebeurtenis). Wisselen van zoekopdracht verandert de cijfers op Overzicht en Aanbod. Een lege installatie leidt de gebruiker zonder uitleg naar een eerste gevulde lijst.

---

### WP-05 — Advertentietekst beschikbaar krijgen

**Doel (§4).** Zonder tekst is er geen uitrustingsmatch. Dit is in de praktijk het grootste risico voor het doel (F1).

**⚠ Eerst nagaan** (dit bepaalt de rest van het WP):

1. Maak `scripts/inspect_occasion_fields.py`: leest een lokaal opgeslagen HTML-bestand van een Gaspedaal-zoekpagina, haalt met `_flight_occasions()` de advertenties eruit en print van de eerste drie de **sleutelstructuur** (geneste sleutelnamen en waardetypen, geen waarden). Vraag de gebruiker de pagina op te slaan en het script te draaien.
2. Leg het resultaat vast in een nieuw kopje onderaan dit document ("Veldinventarisatie Gaspedaal"): welke velden bestaan (opties/uitrusting, omschrijving, brandstof, vermogen, transmissie, kleur, datum eerste toelating, plaats, kenteken).

**Bouwen, afhankelijk van de uitkomst.**

- **A. Bestaan er uitrustings- of omschrijvingsvelden:** neem ze over in `_occasion_to_item()` (`gaspedaal_site.py:65`). Een lijst met opties wordt één regel per optie in `description`. Neem ook de overige bruikbare voertuigvelden over als kolommen op `listings` (migratie): `fuel`, `power_kw`, `transmission`, `color`, `first_registration`, `city`.
- **B. Altijd bouwen — zelf tekst toevoegen.** Op de autopagina een knop "Advertentietekst toevoegen": plakveld, opslaan via `POST /api/v1/listings/{id}/description`. Kolom `listings.description_source` (`SOURCE` / `DETAIL_PAGE` / `MANUAL`). Handmatige tekst wordt door een latere controle nooit overschreven. Na opslaan direct opnieuw beoordelen (zie WP-12 voor het mechanisme; tot die tijd bij de volgende controle).
- **C. Altijd bouwen — zichtbaar maken.** Auto's zonder tekst krijgen de status "Geen advertentietekst" in plaats van "Nog te controleren", en tellen niet mee in "gemiddelde match". Op Overzicht: "Tekst beschikbaar voor 14 van 62 auto's" met een link naar de uitleg in Instellingen over `ADVERTISER_DETAIL_HOSTS` en `MAX_DETAIL_FETCHES_PER_RUN`.

**Klaar als.** De inventarisatie staat in dit document; pad B en C werken met de demo-data; tests voor "handmatige tekst blijft behouden na een controle".

---

### WP-06 — Mijn wensen: toevoegen, synoniemen, direct herrekenen

**Doel (§4).** Zelf wensen toevoegen en indelen, zonder synoniemen te hoeven bedenken, en direct zien wat een wijziging doet.

**Vaste keuzes.**

1. **API:** `POST /api/v1/criteria` (sleutel wordt een slug van het label, uniek gemaakt met volgnummer) en `DELETE /api/v1/criteria/{key}` (zet `enabled=0`; claims blijven bewaard).
2. **Herrekenen in plaats van opnieuw beoordelen (B3).**
   - De vingerafdruk in `analyze_listing` (`worker.py:43-44`) bevat voortaan per wens alleen `key`, `description`, `synonyms`, `match_terms`; **niet** `weight` en `group_name`.
   - `PUT /criteria/{key}`: wijzigt alleen gewicht, groep of aan/uit → roep direct `recalculate_score` aan voor alle auto's en wis `analyzed_hash` **niet**. Wijzigt omschrijving, synoniemen of zoektermen → wis `analyzed_hash` wel.
3. **Algemene lokale herkenning (F3).** Nieuwe kolom `criteria.match_terms_json` (migratie): exacte woorden of woordgroepen die veilig genoeg zijn om zonder AI te beslissen. `local_claims()` krijgt de wensen mee en werkt per wens: een zinsdeel dat een zoekterm bevat (hele woorden, hoofdletterongevoelig, aanhalingstekens genormaliseerd) → Aanwezig; met een ontkenning (`NEGATION`) → Afwezig; met een voorbehoud (`HEDGED`) → Onbekend. De bestaande regex voor 22-inch blijft als uitzondering voor sleutel `wheels_22`.
   Vul bij de migratie `match_terms_json` voor de standaardwensen met alleen ondubbelzinnige termen (bijvoorbeeld trekhaak: `trekhaak`, `towbar`, `anhängerkupplung`; panoramadak: `panoramadak`, `panoramic roof`). Losse woorden als "velgen" of "wielen" horen er **niet** in: die staan nu in `synonyms` en zouden "19 inch velgen" als 22-inch laten tellen.
4. **Synoniemen laten voorstellen.** `POST /api/v1/criteria/suggest` met `{label}` → `{description, synonyms[], match_terms[], let_op[]}` via één Gemini-aanroep met gestructureerd antwoord (NL/EN/DE). Leg aanroep en antwoord vast in een nieuwe tabel `criterion_suggestions`. Zonder API-sleutel: antwoord 200 met lege lijsten en `ai_beschikbaar: false`; de UI zegt dan "Zonder AI kun je zelf zoekwoorden toevoegen".
5. **Scherm Mijn wensen.**
   - Twee kolommen (op mobiel onder elkaar): **Must-haves** en **Nice-to-haves**. Verslepen tussen de kolommen, en als alternatief een menu "Verplaats naar …".
   - Per wens: naam, belang als vijf-stappenregelaar ("Belang"), en uitklapbaar de omschrijving en zoekwoorden als verwijderbare chips met een invoerveld om er één toe te voegen.
   - Knop "Wens toevoegen": typ een naam → voorstel verschijnt (omschrijving en chips, aanpasbaar) → opslaan.
   - **Automatisch opslaan** bij elke wijziging, met melding "Opgeslagen"; geen knop per rij.
   - Bovenaan een live telling: "Met deze wensen: 9 voldoen · 14 nog te controleren · 3 vallen af".
   - Vaste uitlegregel: "Staat een optie niet in de advertentie, dan geldt die als onbekend, niet als afwezig."

**Klaar als.** Tests: gewicht wijzigen roept geen Gemini aan en verandert scores direct; nieuwe wens met zoekterm wordt lokaal herkend, inclusief ontkenning en voorbehoud; "19 inch velgen" levert geen 22-inch op. In de UI: een wens "Elektrische achterklep" toevoegen, tot must-have maken en de telling zien veranderen zonder herladen.

---

### WP-07 — Matchscore met onzekerheid, vragen aan de verkoper, corrigeren

**Doel (§4).** Een score die je begrijpt en kunt navragen: wat is bevestigd, wat ontbreekt, wat is onzeker.

**Vaste keuzes.**

1. `scoring.calculate()` geeft naast de bestaande velden terug, en `recalculate_score` slaat op (migratie, kolommen op `listings`):
   - `score_potential`: dezelfde formule, waarbij Onbekend en Tegenstrijdig als aanwezig tellen.
   - `evidence_coverage`: aandeel van het totale gewicht met status Aanwezig of Afwezig.
   - `must_present`, `must_count`, `must_unknown`, `must_absent`.
   De bestaande `score_total` blijft de **bevestigde** score. 100 % betekent nog steeds: alles aantoonbaar aanwezig.
2. **Weergave overal waar een score staat:** "75 % bevestigd · tot 100 % mogelijk", met één balk: dicht gevuld deel = bevestigd, licht gearceerd deel = nog mogelijk. Daaronder waar ruimte is: "Must-haves 1 van 2 bevestigd".
3. **Statuschip met reden:** "Voldoet" · "Nog te controleren: trekhaak" · "Valt af: trekhaak ontbreekt" · "Tegenstrijdig: 22-inch velgen" · "Geen advertentietekst" · "Nog niet beoordeeld" (als `analyzed_hash IS NULL`).
4. **Uitrusting op de autopagina** in drie groepen: Bevestigd · Ontbreekt · Onzeker. Per regel: naam, must/nice, het citaat uit de advertentie (gemarkeerd), de herkomst (zie woordenlijst WP-03) en de zekerheid in woorden: `confidence ≥ 0,85` "zeker", `≥ 0,6` "waarschijnlijk", anders "onzeker".
5. **Corrigeren (F6).** Vervang `prompt()` door een segmentkeuze per regel: Aanwezig · Afwezig · Onbekend, plus een optioneel notitieveld ("Bron, bijvoorbeeld: dealer bevestigd per mail op 14-11"). Opslaan zonder herladen; de score werkt direct bij. Een handmatig oordeel toont "Door jou bevestigd" en een knop "Terug naar automatisch" (nieuw: `DELETE /api/v1/listings/{id}/review/{key}`, verwijdert de override en zet de auto klaar voor herbeoordeling).
6. **Vragen aan de verkoper (F5).** Blok op de autopagina met één vraag per onzekere wens, must-haves eerst, daarna op gewicht. Sjabloon: "Heeft deze auto {label, kleine letters}? Kunt u dat bevestigen met een foto of de originele uitrustingslijst?" Knop "Kopieer alle vragen" zet ze als genummerd bericht op het klembord, met aanhef en de naam van de auto. Zijn er geen onzekere wensen: "Alle wensen zijn bevestigd of uitgesloten."

**Klaar als.** Tests voor `score_potential` en `evidence_coverage` (alles onbekend → 0 % bevestigd, 100 % mogelijk; must-have afwezig → mogelijk < 100 %, status Valt af). Een correctie in de UI kost twee klikken en geen paginawissel.

---

### WP-08 — Aanbodlijst en autopagina

**Doel (§3, §5, §6).** In één oogopslag zien wat er speelt, en per auto het hele verhaal.

**Backend.**

- `GET /api/v1/listings` stuurt geen `description` meer (B5) en per auto extra: `first_price` (eerste observatie), `price_change_total` (actueel − eerste), `price_drop_count`, `last_price_change_at`, `days_tracked` (van `first_seen` tot nu, of tot `last_seen` als de auto weg is), `seen_since_start` (waar als `first_seen` valt binnen de eerste geslaagde controle van de zoekopdracht), `availability`, `is_new` (eerste keer gezien in de laatste geslaagde controle), `photo` (alleen de eerste foto), de scorevelden uit WP-07 en `provider_count`.
- Sorteren, filteren en zoeken gebeurt in de browser (maximaal 1000 rijen).

**Aanbodlijst** (`#/aanbod`).

- **Tabs met aantallen:** Voldoet · Nog te controleren · Valt af · Verdwenen · Alles. De eerste drie tonen alleen auto's die te koop staan.
- **Kolommen:** foto · auto (titel, uitvoering, verkoper en plaats) · bouwjaar · km · vraagprijs (met eronder de totale wijziging, bijvoorbeeld "▼ € 2.500 sinds eerste prijs") · t.o.v. markt (gevuld vanaf WP-10, tot dan weggelaten) · match (balk uit WP-07) · in beeld ("23 dagen", of "≥ 45 dagen" als `seen_since_start`) · status · ster.
- **Labels in de titelcel:** "Nieuw", "Prijs verlaagd" (laatste 7 dagen), "Weer terug", "3 aanbieders".
- **Sorteren** door op een kolomkop te klikken. Standaard: tab Voldoet op vraagprijs oplopend; Nog te controleren op `score_potential` aflopend; Verdwenen op datum laatst gezien aflopend.
- **Filterbalk:** zoekveld (titel, verkoper), prijs van–tot, km tot, bouwjaar vanaf, vinkjes "Alleen prijsverlagingen", "Alleen nieuw", "Alleen shortlist". Actieve filters als verwijderbare chips. Tab, sortering en filters staan in het adres (`#/aanbod?tab=voldoet&sort=prijs`), zodat terugkeren uit een auto dezelfde lijst geeft.
- **Verdwenen-tab:** kolom "Laatst bekende vraagprijs" en "Laatst gezien", met boven de tabel: "Laatst bekende vraagprijzen. Dit zijn geen verkoopprijzen en geen bewijs van verkoop."
- Onder 760 px: kaarten met foto, titel, prijs, match en status.
- Lege toestand per tab met een zinnige vervolgstap.

**Autopagina** (`#/auto/<id>`, vervangt het modale venster; U2).

- **Kop (blijft in beeld bij scrollen):** terug naar de lijst · titel · vraagprijs · wijziging sinds eerste prijs · in beeld · statuschips · ster · knop "Bekijk advertentie" (bij meerdere aanbieders een menu met aanbieder en prijs).
- **Secties met ankernavigatie:** Overzicht · Prijs · Uitrusting · Onderhandelen (inhoud volgt in WP-10; tot dan de bestaande cijfers) · Notities.
- **Overzicht:** fotogalerij links, kerngegevens rechts (bouwjaar, km, uitvoering, verkoper, en de extra velden uit WP-05 als die er zijn).
- **Prijs:** trapgrafiek (prijzen veranderen in stappen) met markeringen voor eerste waarneming, elke prijswijziging, niet meer gezien en weer terug; aanwijswaarde met datum en bedrag. Daaronder een tabel: datum · van → naar · verschil in € en % · dagen sinds de vorige wijziging. Daaronder de bestaande tabel met prijzen per aanbieder; markeer de laagste.
- **Bij een verdwenen auto** bovenaan een balk: "Sinds {datum} niet meer gezien. Laatst bekende vraagprijs € X. Dit zegt niet of en voor welk bedrag de auto is verkocht."
- **Dagen in beeld** altijd met de kanttekening bij `seen_since_start`: "Stond al te koop toen het volgen begon; werkelijke looptijd is langer."
- **Uitrusting:** zoals vastgelegd in WP-07.
- **Notities:** bestaand formulier in de nieuwe vormgeving.

**Grafieken** (`charts.js`): één herbruikbare functie voor lijn, trap en (voor WP-11) puntenwolk. Assen met € en duizendtallen, datumlabels, aanwijswaarden bij muis en aanraking, een leesbare tekstsamenvatting in `aria-label`. Bij één meetpunt geen losse stip maar de waarde als getal met "eerste meting".

**Klaar als.** Met de seed-data is in de lijst zonder doorklikken te zien welke auto's in prijs zijn gedaald, welke nieuw zijn en welke weg zijn. Terugknop vanaf een auto geeft dezelfde tab, sortering en scrollpositie. Test voor de afgeleide velden van `/listings`.

---

### WP-09 — Controles: voortgang, actualiteit, wat is er veranderd

**Doel (§7).** Weten wanneer er gecontroleerd is, of het gelukt is en wat het opleverde.

**Bouwen.**

1. **Knop "Nu controleren"** krijgt een bezig-toestand. Na starten elke 2 seconden `GET /refresh-runs/{id}` tot de status eindigt. Daarna een melding in gewone taal ("Controle geslaagd: 62 auto's, 2 nieuw, 3 prijswijzigingen, 1 niet meer gezien") en worden de gegevens van het huidige scherm ververst. Loopt er al een controle (HTTP 409 `RUN_ALREADY_ACTIVE`), dan volgt de knop die lopende controle in plaats van een foutmelding te tonen. Verwijder de ongebruikte `state.running`.
2. **Actualiteitschip** in de bovenbalk: "Bijgewerkt 2 uur geleden" (groen), "Laatste controle mislukt, gegevens van gisteren 08:00" (rood), "Meer dan 36 uur niet gecontroleerd" (oranje). Klik → Controles. Nieuw endpoint `GET /api/v1/status`: laatste controle, laatste geslaagde controle, lopende controle.
3. **Bij een mislukte laatste controle** op Overzicht en Aanbod een balk: "De laatste controle is mislukt. Je ziet de stand van {datum}. Er zijn geen auto's als verdwenen gemarkeerd."
4. **Wat is er veranderd.** Nieuw endpoint `GET /api/v1/changes?profile_id=&run_id=` (standaard de laatste geslaagde controle) op basis van `listing_events`: nieuw, prijs omlaag, prijs omhoog, niet meer gezien, uit het aanbod, weer terug; elk met auto, bedragen en link.
5. **Pagina Controles.** Tabel: gestart · gestart door · duur · uitkomst · samenvatting in één zin. Detailpagina `#/controles/<id>`: eerst "Wat is er gevonden" (de lijsten uit punt 4), dan per zoekopdracht de volledigheid ("3 pagina's, 62 van 62 verwacht"), dan pas de technische tijdlijn, standaard ingeklapt.

**Klaar als.** Een controle starten toont zonder herladen het eindresultaat. Tests voor `/status` en `/changes`. Een gesimuleerde mislukte controle toont de balk en laat alle bestaande gegevens ongemoeid.

---

### WP-10 — Marktwaarde en onderhandelingspositie *(Opus)*

**Doel (§5, §6).** Onderbouwen met feiten en concrete vergelijkingen, met een helder onderscheid tussen wat bekend is en wat een schatting blijft.

**Vaste keuzes — rekenmodel** (nieuwe module `app/valuation.py`, alleen pure functies, volledig getest; `negotiation_snapshot` in `scoring.py` vervalt).

1. **Vergelijkingspool:** auto's die te koop staan in **dezelfde zoekopdracht(en)** als de gekozen auto, zonder de auto zelf (lost F9 op).
2. **Uitvoering vergelijken:** splits de uitvoeringstekst in tokens (kleine letters, alleen letters en cijfers), verwijder ruiswoorden (`aut`, `automaat`, `awd`, `4wd`, `7p`, `5p`, `pk`, `kw`), en bereken de Jaccard-overlap.
3. **Drie niveaus, van streng naar ruim; gebruik het eerste met `n ≥ 8`, anders het ruimste:**
   - Niveau 1: bouwjaar ± 1, km ± 20.000, uitvoering-overlap ≥ 0,5.
   - Niveau 2: bouwjaar ± 1, km ± 30.000.
   - Niveau 3: bouwjaar ± 2, km ± 50.000.
   Ontbrekende waarden sluiten een auto niet uit, maar worden wel als verschil getoond.
4. **Kilometercorrectie** alleen bij `n ≥ 8`: helling = mediaan van alle paarsgewijze hellingen prijs/km (Theil–Sen); een positieve helling wordt 0. Corrigeer elke vergelijkingsprijs naar de kilometerstand van de gekozen auto.
5. **Uitkomst naar steekproef:**
   - `n ≥ 8`: marktband = P25–P75 van de gecorrigeerde prijzen, middenwaarde = mediaan. Zekerheid "redelijk".
   - `5 ≤ n < 8`: zonder correctie, band en mediaan, zekerheid "laag".
   - `n < 5`: **geen** marktwaarde. Tekst: "Te weinig vergelijkbare auto's (n = 3) voor een marktwaarde." De vergelijkbare auto's worden wel getoond.
6. **Uitrusting wordt niet in euro's gecorrigeerd.** De matchscore van elke vergelijkbare auto staat ernaast, zodat het verschil zichtbaar blijft. Een optiepremie wordt alleen getoond als er minimaal 5 vergelijkbare auto's mét en 5 zónder zijn: het verschil in mediaan, gelabeld "indicatie, n = 6 / 7". Anders: "onvoldoende data".
7. **Drie bedragen, geen vast kortingspercentage (F10), afgerond op € 250:**
   - **Openingsbod (voorstel)** = laagste van vraagprijs en P25.
   - **Streefprijs (voorstel)** = laagste van vraagprijs en mediaan.
   - **Grens (voorstel)** = laagste van budget van de zoekopdracht en P75; zonder budget: P75.
   Ligt de vraagprijs al onder P25, dan geen openingsbod maar de tekst: "De vraagprijs ligt al onder het onderste kwart van vergelijkbare auto's; onderhandelingsruimte is niet uit de data af te leiden."
   De gebruiker kan alle drie per auto overschrijven (migratie: `listings.my_opening`, `my_target`, `my_max`); een eigen waarde heet "Jouw keuze".
8. **Argumenten:** een lijst feiten, elk met herkomst, alleen getoond als ze van toepassing zijn:
   - positie ten opzichte van de band ("€ 2.100 boven de mediaan van 9 vergelijkbare auto's");
   - looptijd ("minstens 41 dagen in beeld; mediaan van vergelijkbare auto's 23 dagen");
   - prijsgedrag ("twee keer verlaagd, samen € 2.500; laatste keer 19 dagen geleden" of "nog niet verlaagd");
   - alternatieven ("3 vergelijkbare auto's zijn goedkoper met een gelijke of betere match", met links);
   - uitrusting ("mist: luchtvering · onzeker: trekhaak");
   - aanbiedersverschil ("bij AutoTrack € 500 lager geadverteerd").

**Endpoint.** `GET /api/v1/listings/{id}/valuation` → niveau, `n`, zekerheid, band, middenwaarde, helling, de vergelijkbare auto's (id, titel, prijs, gecorrigeerde prijs, km, bouwjaar, uitvoering, match, dagen in beeld, verschillen), de drie bedragen en de argumenten.

**Sectie Onderhandelen op de autopagina.**

- Bovenaan één zin met de kern: "Vraagprijs € 78.650 ligt € 2.100 boven wat vergelijkbare auto's vragen (schatting, n = 9, redelijke zekerheid)."
- Een horizontale band P25–mediaan–P75 met de vraagprijs als markering, plus budget als dat is ingesteld.
- De drie bedragen als bewerkbare velden, elk met een label **Bekend**, **Schatting** of **Jouw keuze**.
- De argumentenlijst.
- Tabel "Vergelijkbare auto's" met links en de reden waarom ze vergelijkbaar zijn; kolom met gecorrigeerde prijs alleen als er gecorrigeerd is.
- Vaste voetregel: "Gebaseerd op vraagprijzen van auto's die nu te koop staan. Werkelijke verkoopprijzen zijn niet bekend."

**Aanbodlijst.** Vul de kolom "t.o.v. markt": "€ 1.600 onder" (groen), "€ 2.100 boven" (neutraal), "—" bij `n < 5`. Sorteerbaar; wordt de standaardsortering van tab Voldoet.

**Klaar als.** Tests met vaste invoer voor: elk niveau, de drempels 4/5/7/8, Theil–Sen op een bekende reeks, positieve helling → 0, vraagprijs onder P25, zoekopdrachten die niet mengen. In de UI is bij elk getal te zien of het bekend, geschat of zelf gekozen is.

---

### WP-11 — Marktoverzicht dat de zeven vragen beantwoordt *(Opus voor het rekenwerk)*

**Doel (§3, §5).** Het overzicht beantwoordt de vragen uit §5 van het doel, per zoekopdracht, met periodekeuze 30 dagen · 90 dagen · alles.

**Endpoint.** `GET /api/v1/market?profile_id=&days=` vervangt `/dashboard`. Elke statistiek geeft `n` mee; bij `n < 5` geeft de API `null` en toont de UI "te weinig data (n = 3)".

| Vraag uit het doel | Blok | Berekening |
|---|---|---|
| Wat is een gangbare vraagprijs? | Kerncijfer "Gangbare vraagprijs" | Echte mediaan (B6) en P25–P75 van auto's die te koop staan; daarnaast dezelfde cijfers voor auto's met status Voldoet of Nog te controleren. |
| Wat zijn de aantrekkelijkste aanbiedingen? | Lijst "Kansen" (top 5) | Status Voldoet of Nog te controleren, gesorteerd op "t.o.v. markt" uit WP-10; binnen budget eerst. |
| Hoe verschillen prijzen naar km, leeftijd, uitvoering? | Puntenwolk prijs tegen km | Kleur naar status, budget als horizontale lijn, klik opent de auto. Daaronder een tabel met mediaan per km-klasse (0–25, 25–50, 50–75, 75–100, 100+ duizend) met `n`. |
| Hoeveel aanbod, hoe snel verandert het, hoe lang zichtbaar? | Kerncijfers "Aanbod" en "Tijd in beeld" + staafgrafiek in- en uitstroom per week | Aantal te koop; nieuw en verdwenen per week; mediane dagen in beeld, apart voor nog te koop ("tot nu toe") en verdwenen. |
| Welke prijsverlagingen, na hoeveel tijd? | Blok "Prijsverlagingen" | Aandeel auto's met minstens één verlaging; mediane verlaging in € en %; mediane dagen tot de eerste verlaging (alleen auto's die **na** de start van het volgen verschenen). |
| Wat is nieuw en wat is verdwenen? | "Sinds de vorige controle" | De lijsten uit `/changes` (WP-09). |
| Beweegt de markt naar mijn budget; wachten of kopen? | Grafiek "Markt door de tijd" + kerncijfer "Binnen budget" | Zie hieronder. Geen advies, alleen feiten. |

**Markt door de tijd — twee lijnen die samenstelling en echte prijsdaling scheiden (§3):**

1. **Mediane vraagprijs van het aanbod per dag**, met een band P25–P75. Per auto per dag telt de laatste observatie.
2. **Prijsindex van dezelfde auto's.** Voor elk paar opeenvolgende meetdagen: het gemiddelde van `prijs_vandaag / prijs_vorige − 1` over auto's die op beide dagen zijn gezien. Keten die veranderingen aan elkaar, beginnend op 100. Deze lijn beweegt alleen als bestaande advertenties in prijs veranderen.
3. **Budgetlijn** als er een budget is.
4. Onder de grafiek één automatisch gevormde zin, volgens vaste regels:
   - mediaan veranderde meer dan 1 % en de index minder dan 0,5 % → "De mediaan daalde € X, maar dezelfde auto's werden nauwelijks goedkoper: vooral de samenstelling van het aanbod veranderde."
   - beide daalden meer dan 0,5 % → "Bestaande advertenties werden gemiddeld Y % goedkoper."
   - anders → "Vraagprijzen zijn in deze periode stabiel."
   > **Uitvoering:** de regel "beide daalden" is ook in spiegelbeeld opgenomen ("…werden gemiddeld Y % duurder"), anders zou een duidelijke prijsstijging als "stabiel" worden beschreven. De samenstellingsregel noemt "daalde" of "steeg".
   - minder dan 14 meetdagen → "Nog te kort gevolgd voor een trend (N dagen)."

**Kerncijfer "Binnen budget":** "7 van 62 auto's, waarvan 2 voldoen", met een kleine lijn van dat aantal door de tijd.

**Indeling van de pagina:** kop met zoekopdracht, periode en actualiteit → rij van vier kerncijfers (Aanbod · Gangbare vraagprijs · Binnen budget · Tijd in beeld) → "Sinds de vorige controle" naast "Kansen" → "Markt door de tijd" over de volle breedte → puntenwolk naast "Prijsverlagingen". De technische mededeling over de bron verdwijnt van deze pagina (staat in Instellingen).

**Klaar als.** Tests met een handgemaakte reeks waarin (a) alleen de samenstelling verandert → index blijft 100, mediaan beweegt; (b) alle auto's 2 % zakken → index 98; (c) herhaalde controles op één dag tellen één keer. Met de seed-data zijn alle zeven vragen op één scherm te beantwoorden.

---

### WP-12 — Inzicht in de AI-beoordeling

**Doel (§7).** Kunnen nagaan hoe een advertentie is geïnterpreteerd, hoe zeker dat is, en het kunnen herstellen.

**Bouwen.**

1. **Herkomst vastleggen (F16).** `claims.source` wordt `LOCAL_RULE` ("Zonder AI herkend"), `GEMINI` ("AI-beoordeling"), `NOT_MENTIONED` ("Niet genoemd in de advertentie") of `MANUAL_OVERRIDE` (nu altijd `AD_TEXT`, `worker.py:92`). Migratie van bestaande `AD_TEXT`-rijen op basis van het veld `reason`: gelijk aan `Lokale expliciete advertentievermelding` → `LOCAL_RULE`; gelijk aan `Niet aangetoond in toegestane advertentietekst` → `NOT_MENTIONED`; al het andere → `GEMINI`. Nieuwe kolom `claims.integration_id` verwijst naar het logrecord.
2. **Op de autopagina, sectie Uitrusting:** per oordeel een link "Bekijk beoordeling" naar het logrecord; een inklapbaar blok "Beoordeelde tekst" met exact de tekst die is gebruikt (uitvoer van `cleaned_text`); knop "Opnieuw beoordelen".
3. **Opnieuw beoordelen zonder scan.** `POST /api/v1/listings/{id}/reanalyze` maakt een controle met `scope = {"analyze_listing_ids": [id]}`. De worker slaat voor zo'n controle het ophalen over en voert alleen `analyze_listing` uit. Trigger heet in de UI "Herbeoordeling". Gebruik ditzelfde mechanisme na het plakken van tekst (WP-05) en na het terugzetten van een correctie (WP-07).
4. **Pagina AI-beoordeling.** Bovenaan vier kerncijfers: beoordeeld · wacht nog · mislukt · tokens deze maand. "Wacht nog" telt auto's met `analyzed_hash IS NULL`, met uitleg ("maximaal 20 per controle") en een knop "Wachtrij nu verwerken" (herbeoordeling voor die auto's, binnen dezelfde limiet per controle). Filters op uitkomst. Het detail toont eerst een leesbare tabel (wens · oordeel · citaat · zekerheid) en pas daaronder, ingeklapt, de ruwe JSON.

**Klaar als.** Van elk oordeel op de autopagina is in één klik te zien waar het vandaan komt. Tests voor de migratie van `source` en voor een controle met alleen herbeoordeling (geen netwerkverkeer naar de bron, geen verdwijn-logica).

---

### WP-13 — Wensen per zoekopdracht *(Opus)*

**Doel (§8).** Een tweede zoekopdracht voor een ander model mag niet op XC90-wensen worden beoordeeld.

**Vaste keuzes.**

1. `criteria` krijgt `profile_id`. Omdat SQLite de primaire sleutel niet kan wijzigen: nieuwe tabel met sleutel `(profile_id, key)`, data overzetten, oude tabel vervangen; `claims` krijgt eveneens `profile_id` in de sleutel. Bij migratie krijgt **elke** bestaande zoekopdracht een kopie van de huidige wensen en van de bijbehorende claims.
2. De scorevelden (`score_total`, `score_must`, `score_nice`, `score_potential`, `evidence_coverage`, `must_*`, `eligibility`) en `analyzed_hash` verhuizen van `listings` naar `profile_listings`, want één auto kan in twee zoekopdrachten vallen.
3. Alle API's die scores of wensen teruggeven vereisen dan een zoekopdracht; bij "Alle zoekopdrachten" toont de lijst per auto de score van de zoekopdracht waarin die het eerst werd gezien, met de naam erbij.
4. Mijn wensen krijgt bovenaan de zoekopdrachtkeuze en een knop "Wensen kopiëren van …".

**Klaar als.** Tests: twee zoekopdrachten met verschillende wensen geven voor dezelfde auto verschillende scores; migratie behoudt alle handmatige correcties. Back-up van de database is gemaakt vóór de migratie.

---

### WP-14 — Optioneel: eerst bevestigen bij de gebruiker

Deze punten komen uit §9 van het doel, dat ze uitdrukkelijk "nog geen bevestigde eisen" noemt. **Vraag per onderdeel om akkoord voordat je bouwt.**

- **A. Meldingen via Home Assistant.** `GET /api/v1/ha/summary` (bearer-token zoals de trigger): uitkomst en tijdstip van de laatste controle, aantallen, en lijsten "nieuwe auto's die voldoen", "prijsverlagingen op de shortlist", "auto's die binnen budget kwamen", elk met titel, prijs, match en een link naar `#/auto/<id>`. Voeg voorbeelden toe in `homeassistant/`: een REST-sensor en een automatisering die één gebundelde melding stuurt na een controle. De app stuurt zelf niets; Home Assistant blijft de regie houden.
- **B. Shortlist vergelijken.** Pagina `#/shortlist`: alle favorieten, ook verdwenen. Maximaal vier aanvinken → vergelijking naast elkaar: foto, prijs en verloop, km, bouwjaar, t.o.v. markt, match, en per wens een rij met de status per auto.
- **C. Onderhandelingsdossier.** Knop op de autopagina "Dossier kopiëren": Markdown met de kerngegevens, de prijsgeschiedenis, de argumenten en vergelijkbare auto's met links, de open vragen en de eigen notities.
- **D. Totale waarde** (afschrijving, onderhoud, garantie): niet bouwen zonder aparte uitwerking; de app heeft hier geen betrouwbare gegevens voor.

---

## 7. Samenhang met de bouwspecificatie

`docs/BOUWSPECIFICATIE.md` beschrijft een verdergaand eindbeeld. Dit plan neemt daaruit over wat het doel direct dient: mogelijke score en bewijsdekking (§4.1), tabs op geschiktheid (§4.3), marktband in plaats van één bedrag (§7.2), en het scheiden van samenstelling en prijsverandering (§6.2). Waar de twee botsen, geldt dit plan.

## 8. Bewust niet doen

- Geen frontend-framework, bundler of TypeScript: de app is klein en draait als Home Assistant-add-on zonder build-stap.
- Geen automatisch gegenereerd bod zonder onderbouwing, en geen vast kortingspercentage (doel §6, §10).
- Geen geschatte verkoopprijzen. De app kent alleen vraagprijzen (doel §3, §9).
- Geen eigen planning in de app: Home Assistant bepaalt wanneer er wordt gecontroleerd (doel §7).
- Geen omzeiling van toegangsbeperkingen van bronnen; de bestaande toegestane-domeinenlijst blijft leidend.
- Geen regressie- of machine-learningmodel voor marktwaarde: het aanbod per zoekopdracht is daarvoor te klein. Medianen, kwartielen en één robuuste kilometercorrectie zijn uitlegbaar en voldoende.
- Geen donkere modus in deze ronde. De tokens uit WP-03 maken dat later eenvoudig.

---

## Veldinventarisatie Gaspedaal

Vastgesteld op 16-11-2026 met `scripts/inspect_occasion_fields.py` op een live zoekpagina (`https://www.gaspedaal.nl/volvo/xc90`, 100 advertenties in de `occasions`-stream; alle advertenties hebben dezelfde sleutels).

| Gevraagd veld | Aanwezig | Sleutel in de stream |
|---|---|---|
| Opties / uitrusting | **Nee** | — |
| Omschrijving | **Nee** | — |
| Brandstof | Ja | `autogegevens.algemeen.brandstofsoort` |
| Vermogen | Ja | `autogegevens.motor.vermogenKw` (tekst) |
| Transmissie | Ja | `autogegevens.algemeen.transmissietype` |
| Kleur | Ja | `autogegevens.algemeen.kleur` |
| Datum eerste toelating | Nee | alleen `autogegevens.geschiedenis.bouwjaar` |
| Plaats | Ja | `aanbieder.aanbiedergegevens.plaatsnaam` |
| Kenteken | **Nee** | — |

Overige sleutels: `advertentieId`, `datumGeplaatst`, `prijs.totaalInclusiefBtw`, `autogegevens.algemeen.{merknaam, modelnaam, uitvoering, carrosserievorm, aantalDeuren}`, `autogegevens.geschiedenis.kilometerstand`, `autogegevens.motor.motorinhoud`, `aanbieder.aanbiedergegevens.{naamsvermelding, provincieHulpwaarde}`, `gpFotos.{fotoGroot, fotoKlein}`, `portalen[].{klikUrl, portaalBeschrijving, portaalType, portaalFotoUrl, portaalLogoUrl, siteNr}`.

**Gevolg voor WP-05:** er zijn geen uitrustings- of omschrijvingsvelden, dus pad A is niet gebouwd (ook de overige voertuigvelden niet, want die horen bij pad A). Pad B (zelf tekst plakken) en C (zichtbaar maken) zijn gebouwd. Advertentietekst komt alleen via de oorspronkelijke advertentie (`ADVERTISER_DETAIL_HOSTS`) of door hem zelf te plakken.
