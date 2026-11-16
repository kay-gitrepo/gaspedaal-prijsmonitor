"""Configurable direct Gaspedaal JSON API adapter.

The private website endpoint is deliberately *not guessed*. Supply the verified
browser request template after inspecting it in developer tools. This module
never attempts login bypass, challenge solving, hidden cookies, or proxies.
"""
from __future__ import annotations

import json
from urllib.parse import quote, urlsplit

import httpx
from pydantic import ValidationError

from app.config import settings
from app.provider import Advertisement, Snapshot


class SourceError(RuntimeError):
    """Fail closed: never infer disappearance from invalid or partial pages."""


def at_path(value, path: str, default=None):
    if path in ('', '@', '.'): return value
    result = value
    for part in path.split('.'):
        if isinstance(result, dict):
            if part not in result: return default
            result = result[part]
        elif isinstance(result, list) and part.isdigit():
            index = int(part)
            if index >= len(result): return default
            result = result[index]
        else:
            return default
    return result


def first(data, *paths):
    for path in paths:
        value = at_path(data, path)
        if value is not None and value != '': return value
    return None


def euro_price(value):
    if isinstance(value, dict):
        value = first(value, 'totaal', 'total', 'amount', 'value')
    if value is None or isinstance(value, bool): raise SourceError('Advertentie zonder geldige prijs')
    if isinstance(value, float):
        if not value.is_integer(): raise SourceError('Bedrag met onduidelijke valutaeenheid')
        return int(value)
    if isinstance(value, int): return value
    if isinstance(value, str):
        value = value.replace('€', '').replace(' ', '').strip()
        if value.isdigit(): return int(value)
        if value.replace('.', '').isdigit() and value.count('.') >= 1:
            return int(value.replace('.', ''))
    raise SourceError('Vraagprijs niet als eurobedrag herkenbaar')


def normalized_ad(item: dict, field_map: dict[str, str]) -> Advertisement:
    def field(name, *candidates):
        if name in field_map:
            return at_path(item, field_map[name])
        return first(item, *candidates)

    vehicle = {
        'external_id': field('external_id', 'ad_id', 'advertisementId', 'vehicle_id', 'vehicleId', 'id'),
        'title': field('title', 'title', 'name', 'headline', 'vehicle.title'),
        'price_eur': euro_price(field('price_eur', 'price.totaal', 'price.total', 'price.amount', 'price', 'askingPrice', 'asking_price')),
        'url': field('url', 'url', 'detailUrl', 'listing_url', 'click_out_url'),
        'year': field('year', 'year', 'constructionYear', 'vehicle.year'),
        'kilometers': field('kilometers', 'kilometers', 'mileage', 'km', 'odometer'),
        'trim': field('trim', 'trim', 'version', 'execution'),
        'seller': field('seller', 'seller.name', 'sellerName', 'dealer.name'),
        'description': field('description', 'description', 'advertisementText', 'vehicle.description'),
    }
    if vehicle['external_id'] is not None: vehicle['external_id'] = str(vehicle['external_id'])
    if isinstance(vehicle['description'], list): vehicle['description'] = '\n'.join(map(str, vehicle['description']))
    if vehicle['description'] is None: vehicle['description'] = ''
    if vehicle['url'] and str(vehicle['url']).startswith('/'):
        vehicle['url'] = 'https://www.gaspedaal.nl' + vehicle['url']
    try:
        return Advertisement.model_validate(vehicle)
    except ValidationError as exc:
        raise SourceError(f'Advertentieveld ontbreekt of is ongeldig (id={vehicle["external_id"]}): {exc.errors()[0]["loc"]}') from exc


def render_url(template: str, search_url: str, page: int) -> str:
    """Only a fixed allowlisted host; replacements cannot become a new host."""
    if not template:
        raise SourceError('GASPEDAAL_API_SEARCH_TEMPLATE ontbreekt; vul eerst het geverifieerde endpoint in')
    parsed = urlsplit(template)
    if parsed.scheme != 'https' or parsed.hostname not in {'api.gaspedaal.nl','www.gaspedaal.nl'} or parsed.username or parsed.password or parsed.port:
        raise SourceError('API-sjabloon moet uitsluitend HTTPS op api.gaspedaal.nl of www.gaspedaal.nl gebruiken')
    try:
        url = template.format(search_url=quote(search_url, safe=''), page=page)
    except (KeyError, ValueError) as exc:
        raise SourceError('API-sjabloon bevat niet-ondersteunde placeholders') from exc
    final = urlsplit(url)
    if final.scheme != 'https' or final.hostname not in {'api.gaspedaal.nl','www.gaspedaal.nl'} or final.username or final.password or final.port:
        raise SourceError('API-verzoek heeft een ongeldig doeldomein')
    return url


class GaspedaalApiProvider:
    """Read-only, low-volume provider; configured via verified endpoint template.

    Recognizes explicit pagination indicators. If none exist, the result is
    marked incomplete to prevent false disappearances.
    """
    def fetch(self, profile: dict) -> Snapshot:
        if not settings.data_source_approved:
            raise SourceError('DATA_SOURCE_APPROVED staat uit')
        if not settings.gaspedaal_api_search_template:
            raise SourceError('Configureer eerst het daadwerkelijk vastgestelde Gaspedaal API-endpoint')
        try:
            field_map = json.loads(settings.gaspedaal_api_fields_json)
            if not isinstance(field_map, dict) or not all(isinstance(x, str) for x in field_map.values()):
                raise ValueError()
        except ValueError as exc:
            raise SourceError('GASPEDAAL_API_FIELDS_JSON moet een JSON-object met veldpaden zijn') from exc
        all_ads: dict[str, Advertisement] = {}
        complete = False
        duplicate_count = 0
        pages_fetched = 0
        with httpx.Client(timeout=20, follow_redirects=False, trust_env=False,
                          headers={'Accept': 'application/json', 'User-Agent': 'OccasionIQ/0.2 (personal car price monitor)'}) as client:
            for page in range(1, settings.gaspedaal_api_max_pages + 1):
                url = render_url(settings.gaspedaal_api_search_template, profile['search_url'], page)
                try:
                    response = client.get(url)
                    response.raise_for_status()
                    data = response.json()
                except (httpx.HTTPError, ValueError) as exc:
                    raise SourceError(f'Gaspedaal API pagina {page} niet beschikbaar of geen geldige JSON') from exc
                pages_fetched += 1
                records = at_path(data, settings.gaspedaal_api_items_path)
                if not isinstance(records, list):
                    raise SourceError(f'Pagina {page}: verwacht advertenties-array op pad {settings.gaspedaal_api_items_path!r}')
                for raw in records:
                    if not isinstance(raw, dict): raise SourceError('Advertentie is geen JSON-object')
                    ad = normalized_ad(raw, field_map)
                    if ad.external_id in all_ads:
                        duplicate_count += 1
                        # Cross-page duplicate: same vehicle may be listed twice, keep first observation.
                        continue
                    all_ads[ad.external_id] = ad
                next_page = first(data, 'has_next', 'hasNext', 'pagination.has_next', 'pagination.hasNext', 'pageInfo.hasNextPage')
                total_pages = first(data, 'total_pages', 'totalPages', 'pagination.totalPages', 'pagination.total_pages')
                if isinstance(next_page, bool):
                    if not next_page:
                        complete = True
                        break
                elif isinstance(total_pages, int) and total_pages >= page:
                    if page >= total_pages:
                        complete = True
                        break
                elif not records:
                    # Empty page is not proof the preceding page was exhaustive.
                    complete = False
                    break
                elif '{page}' not in settings.gaspedaal_api_search_template:
                    # Single-page search cannot be considered exhaustive without explicit indicators.
                    break
            else:
                # Limit hit: must never mark missing ads based on truncated results.
                complete = False
        return Snapshot(complete=complete, listings=list(all_ads.values()), metadata={
            'source':'GASPEDAAL_DIRECT_API', 'pages_fetched':pages_fetched,
            'duplicate_ads':duplicate_count,'unique_ads':len(all_ads),
            'exhaustive':complete})
