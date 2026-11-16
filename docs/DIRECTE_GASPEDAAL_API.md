> Update v0.3: rechtstreeks een Gaspedaal-zoeklink lezen via experimentele HTML-parser en meerdere aanbieders per auto volgen is toegevoegd. Zie [ZOEKURL_AANBIEDERS_EN_DETAIL.md](ZOEKURL_AANBIEDERS_EN_DETAIL.md). Deze handleiding gaat specifiek over de alternatieve JSON-API-adapter.

# Directe Gaspedaal-API: technische integratiestappen

**Status:** configureerbare adapter gebouwd en offline getest; het exacte browserzoek-endpoint is nog niet geïdentificeerd of tegen de live site getest. Er staat **bewust geen fictieve endpoint-URL** in de code.

## Wat de adapter al kan

- Bestaande Gaspedaal-zoek-URL doorgeven aan een geverifieerde HTTP GET-API, zonder externe aggregatiedienst.
- Paginering via `{page}`; meerdere advertenties per pagina, ontdubbelen op advertentie-ID.
- Velden (`id`, `title`, `price`, `year`, `mileage`, `description`) naar uniform intern formaat omzetten.
- Zoekresultaten via een configureerbare JSON-arraylocatie, bijvoorbeeld `data.results`, inlezen.
- Advertenties en elke vraagprijs per geslaagde scan historisch vastleggen.
- Fout of onduidelijke paginering: run faalt of wordt onvolledig gemarkeerd; **geen verdwenen advertenties vaststellen** uit onvolledige data.
- HTTP(S) naar alleen `api.gaspedaal.nl` en `www.gaspedaal.nl`, zonder redirects, logintrucs, anti-bot-omzeiling of proxies.

## Nog nodig om live te draaien

1. Open Gaspedaal.nl in een desktopbrowser, stel jouw Volvo XC90-filters in.
2. Druk `F12` → **Network** → **Fetch/XHR**, herlaad de pagina en ga naar pagina 2.
3. Controleer welke aanvragen JSON-lijsten van auto's bevatten. Kopieer alleen het pad, de queryparameter**namen** en de vorm van de JSON-respons.
4. Optioneel: exporteer een HAR, **uitsluitend lokaal**. HAR-bestanden bevatten vaak cookies, tokens en persoonlijke gegevens: nooit committen of delen. Analyseer lokaal met:

   ```bash
   python scripts/inspect_gaspedaal_har.py ~/Downloads/netwerk.har
   ```
5. Verifieer of het zoek-endpoint GET ondersteunt, hoe de huidige Gaspedaal-zoek-URL wordt vertaald naar queryparameters, hoe paginering en omschrijving werken, en of de respons zonder tijdelijke browsercredentials toegankelijk is.
6. Stel de container- of Home Assistant-appopties in. Stel **alleen bij geschikt bevonden toegang** `DATA_SOURCE_APPROVED=true` in.
7. Voeg een zoekprofiel toe via de applicatie of wissel een bestaand profiel via **Gebruik API**.
8. Start eerst één handmatige run. Controleer uitvoeringslog, aantal pagina's, complete-vlag, steekproefadvertenties en Gemini-invoer vóór dagelijkse Home Assistant-planning.

## Configuratie

```dotenv
DATA_SOURCE_APPROVED=true
# Vervang PAD en parameters door het daadwerkelijk gevonden browser-zoekendpoint.
# Dit is uitsluitend een STRUCTUURVOORBEELD, geen bestaand Gaspedaal-endpoint.
GASPEDAAL_API_SEARCH_TEMPLATE=https://api.gaspedaal.nl/<GEVERIFIEERD_PAD>?search_url={search_url}&page={page}
GASPEDAAL_API_ITEMS_PATH=data.results
# Alleen velden opgeven die niet op gebruikelijke sleutelnaam beschikbaar zijn.
GASPEDAAL_API_FIELDS_JSON={"external_id":"ad_id","price_eur":"price.totaal","description":"description"}
GASPEDAAL_API_MAX_PAGES=10
```

De adapter plaatst de volledig URL-gecodeerde originele zoek-URL in `{search_url}`. Als het daadwerkelijke endpoint afzonderlijke merk-, model- en jaarparameters verlangt in plaats van één URL, moet de connector na inspectie een filtervertaling toevoegen. De huidige generieke template ondersteunt die omzetting nog niet. De API kan ook `POST`, dynamische sessiecookies of andere response-structuren vereisen; die gevallen zijn **niet** geverifieerd.

`GASPEDAAL_API_ITEMS_PATH` is het pad naar de advertentielijst. Ondersteunde pagineringsvelden: `has_next`, `hasNext`, `pagination.has_next`, `pagination.hasNext`, `pageInfo.hasNextPage`, `totalPages`, `total_pages`, `pagination.totalPages`, `pagination.total_pages`. Als geen bruikbaar eind-van-resultaten-signaal bestaat, volgt geen uit-aanbod-classificatie.

## Grenzen

Een menselijke browserweergave garandeert niet dat geautomatiseerde toegang onder dezelfde voorwaarden valt. De website publiceert beperkingen op geautomatiseerde gegevensverzameling. De gebruiker bepaalt of hij een bron activeert; de software omzeilt geen toegangscontroles.

Indien de zoekresultaten geen volledige advertentiebeschrijving bevatten, moet later ook een geverifieerd detail-endpoint worden gekoppeld. Zonder beschrijving blijft de Gemini-optieherkenning conservatief (`UNKNOWN`).
