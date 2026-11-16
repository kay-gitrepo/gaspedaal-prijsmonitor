# OccasionIQ — werkafspraken voor Claude

Persoonlijke occasionmonitor (FastAPI + SQLite + statische frontend) die als Docker-container of Home Assistant-add-on draait. Home Assistant start de controles; de app verzamelt vraagprijzen van Gaspedaal-zoekopdrachten, beoordeelt uitrusting en ondersteunt onderhandelen.

## Lopend werk

Het verbeterplan staat in [`docs/VERBETERPLAN.md`](docs/VERBETERPLAN.md). Lees §1–§4 voordat je iets wijzigt, voer één werkpakket per sessie uit in de volgorde van §5, en werk de voortgangstabel daar bij. De ontwerpkeuzes in een werkpakket staan vast: loop je vast, leg het voor in plaats van zelf een alternatief te kiezen.

## Regels

- Wijzig code alleen in `app/`. `addons/occasioniq/app/` is een kopie: draai na elke wijziging `bash scripts/sync_ha_addon.sh` en bewerk die map nooit met de hand.
- Controleer vóór elke commit: `python -m pytest -q`, `python -m compileall -q app` en `node --check` op elk gewijzigd `.js`-bestand.
- Frontend: geen framework, geen build-stap, geen CDN. Alle API-data door `esc()` voordat ze in HTML komt. Nooit `prompt()`, `alert()` of `confirm()`.
- Zichtbare tekst in het Nederlands, zonder interne statuscodes.
- Schemawijzigingen alleen via het migratiemechanisme in `app/db.py`. Prijsobservaties nooit wijzigen of verwijderen.
- Een onvolledige of mislukte controle mag nooit tot "verdwenen" leiden.
- Vraagprijs is geen verkoopprijs; verdwenen is niet verkocht. Elke schatting heet in de UI "schatting" of "indicatie" en toont de steekproefomvang.
- Eén commit per werkpakket (`feat: … (0.x.0)`), met versie-bump. Niet pushen zonder dat de gebruiker erom vraagt.
- Bekijk UI-wijzigingen altijd in de draaiende app, op 1440 px en 375 px breed.
