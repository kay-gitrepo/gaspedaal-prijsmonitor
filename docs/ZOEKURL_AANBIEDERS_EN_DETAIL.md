# Gaspedaal-zoeklink → aanbiederspop-up → oorspronkelijke advertentie

## Implementatiestatus: v0.3 (experimentele live bron)

De applicatie kan een eigen zoeklink zoals `https://www.gaspedaal.nl/volvo/xc90/2025` bewaren en via een **experimentele** HTML-adapter uitlezen. Deze adapter haalt de zoekpagina op, zoekt daarin naar ingebedde gestructureerde advertentiegegevens, volgt paginering en slaat alleen resultaten met een **stabiele advertentie-ID** op. De adapter is met gesimuleerde HTTP-antwoorden getest, **niet met de echte ruwe HTML-response van Gaspedaal**. Als Gaspedaal een ander dataformaat gebruikt, faalt de parser bewust; hij fabriceert geen IDs en probeert geen blokkades te omzeilen.

De tussenstap die Gaspedaal bij aanklikken toont is een pop-up met aanbieders, niet noodzakelijk een eigen HTML-pagina. In een bronrecord kan de aanbiederslijst `portals` of `sources` heten. Voorbeeld:

```json
{
  "ad_id": "123456789",
  "title": "Volvo XC90 T8 Ultra met 22 inch velgen",
  "price": {"totaal": 74950},
  "year": 2025,
  "mileage": 21000,
  "portals": [
    {
      "occ_import_nr": 891,
      "portaal_beschrijving": "Dealersite",
      "portaal_type": "dealer",
      "prijs": 74950,
      "klik_url": "https://api.gaspedaal.nl/redirect/vehicle/891"
    },
    {
      "occ_import_nr": 892,
      "portaal_beschrijving": "AutoTrack",
      "portaal_type": "other",
      "prijs": 74950,
      "klik_url": "https://api.gaspedaal.nl/redirect/vehicle/892"
    }
  ]
}
```

Dit is **voorbeelddata**, geen live buitgemaakte advertentie. In het dashboard krijgt één auto meerdere aanbieders met hun eigen link en eventuele eigen vraagprijs. Zowel de hoofdvraagprijs als de afzonderlijke aanbiedersprijzen worden per geslaagde refresh historisch opgeslagen.

## Originele advertentietekst lezen voor Gemini

De brongegevens hebben niet altijd een `source_url` naar de eindadvertentie. De optionele module `app/source_details.py` doet dan, per maximaal `MAX_DETAIL_FETCHES_PER_RUN` nieuwe of nog niet verrijkte auto's:

1. Neem een rechtstreekse `source_url` of één Gaspedaal-doorkliklink `/redirect/vehicle/<nummer>`.
2. Lees bij de Gaspedaal-redirect alleen de `Location`-header; volg redirects niet automatisch.
3. Controleer of de bestemming exact op een door de beheerder ingestelde allowlist staat en HTTPS gebruikt.
4. Lees maximaal 800 KB HTML uit de oorspronkelijke advertentiepagina en selecteer `meta description`, schema.org/JSON-LD-beschrijving en zichtbare hoofdtekst. Navigatie, styles en scripts worden verwijderd.
5. Sla de leesstatus en een eventuele foutmelding per auto/run op in `source_detail_attempts`. De tekst is daarna beschikbaar voor de bestaande tokenzuinige Gemini-criteriamatching.
6. Als de detailpagina ontbreekt, verandert of niet uitgelezen kan worden, blijft de auto gewoon zichtbaar. Een onbewezen accessoire blijft `UNKNOWN`.

**Vereist:** stel bewust `ADVERTISER_DETAIL_HOSTS=www.autotrack.nl,www.autoscout24.nl` of je eigen selectie in. Standaard is dit **leeg**; er worden dan geen dealerpagina's opgevraagd. Sommige portals kunnen client-side renderen of een ander HTML-formaat gebruiken; dan blijft de beschrijving onbekend. Het oplossen van browser-challenges en anti-bot-omzeiling is niet geïmplementeerd.

## Live validatie op jouw server

1. Zet in `.env` `DATA_SOURCE_APPROVED=true` en herstart de container.
2. Open de app en voeg de exacte Gaspedaal-zoeklink toe als profiel. De bron wordt `Gaspedaal zoeklink` (of kies die bij een bestaand profiel).
3. Klik één keer **Nu verversen**, voordat je de Home Assistant-planning activeert.
4. Bekijk **Uitvoeringslog → Details**: aantal gevonden resultaten, verwerkte pagina's, `expected_listings`, `exhaustive`, fouten. Is de parser niet passend, dan meldt hij dat expliciet; hij verzint geen API-adressen.
5. Open een auto: onder **Alle aanbieders van deze auto** zie je de aanbiederslinks en het aantal metingen. Zijn er geen aanbieders, dan bevat de bron die mogelijk niet; controleer de werkelijke Gaspedaal-respons.
6. Optioneel: stel `ADVERTISER_DETAIL_HOSTS` in voor originele dealeradvertenties en controleer de uitleesstatus. Configureer daarna pas `GEMINI_API_KEY`.
7. Controleer twee opeenvolgende volledige runs voordat je de Home Assistant-automatisering inzet.

**Belangrijk:** bij een incomplete scan (`exhaustive=false`) worden geen advertenties als verdwenen gemarkeerd. Een verdwenen Gaspedaal-vermelding bewijst bovendien geen gerealiseerde verkoop.

### Live blokkade

In de gebruikte bouwomgeving was geen netwerktoegang beschikbaar om een ruwe Gaspedaal-response te downloaden of browser-XHR te inspecteren. Daardoor is **geen bevestiging mogelijk dat de HTML-adapter op de huidige live site advertenties vindt**. Het onderliggende datamodel, de aanbiederopslag en de doorklik-/detailuitleeslogica zijn wel door middel van mock-HTTP en database-integratietests getest.
