"""Fail-closed data providers. No unauthorised internal Gaspedaal endpoint is called."""
import json
from urllib.parse import urlsplit
from typing import Protocol
from pydantic import BaseModel, Field, field_validator

class PortalOffer(BaseModel):
    """One Gaspedaal vehicle can have multiple advertiser pages."""
    portal_id: str = Field(min_length=1, max_length=180)
    site: str = Field(min_length=1, max_length=100)
    kind: str | None = None
    price_eur: int | None = Field(default=None, ge=1)
    click_url: str | None = None
    source_url: str | None = None

    @field_validator('click_url', 'source_url')
    @classmethod
    def valid_portal_url(cls, value):
        if value:
            p=urlsplit(value)
            if p.scheme!='https' or not p.hostname or p.username or p.password or p.port:
                raise ValueError('Aanbiederslink moet HTTPS zijn')
        return value


class Advertisement(BaseModel):
    external_id: str = Field(min_length=1, max_length=180)
    title: str = Field(min_length=1, max_length=350)
    price_eur: int = Field(ge=1)
    url: str | None = None
    year: int | None = Field(default=None, ge=1950, le=2100)
    kilometers: int | None = Field(default=None, ge=0, le=9999999)
    trim: str | None = None
    seller: str | None = None
    description: str = Field(default='', max_length=50000)
    portals: list[PortalOffer] = Field(default_factory=list,max_length=50)
    license_plate: str | None = Field(default=None,max_length=20)

    @field_validator('url')
    @classmethod
    def valid_listing_url(cls, v):
        if v and urlsplit(v).scheme != 'https':
            raise ValueError('Advertentielink moet HTTPS zijn')
        return v

class Snapshot(BaseModel):
    complete: bool = True
    metadata: dict = Field(default_factory=dict)
    listings: list[Advertisement] = Field(default_factory=list)

class ListingProvider(Protocol):
    def fetch(self, profile: dict) -> Snapshot: ...

class FixtureProvider:
    def fetch(self, profile: dict) -> Snapshot:
        if not profile.get('fixture_payload'):
            raise ValueError('Geen JSON-import aanwezig. Importeer eerst advertentiegegevens.')
        snapshot = Snapshot.model_validate_json(profile['fixture_payload'])
        keys = [x.external_id for x in snapshot.listings]
        if len(keys) != len(set(keys)):
            raise ValueError('Onbetrouwbare bron: dubbele external_id in snapshot')
        return snapshot



def provider_for(profile):
    if profile['provider'] == 'fixture':
        return FixtureProvider()
    if profile['provider'] == 'gaspedaal_site':
        from app.gaspedaal_site import GaspedaalSiteProvider
        return GaspedaalSiteProvider()
    if profile['provider'] == 'gaspedaal':
        from app.gaspedaal_api import GaspedaalApiProvider
        return GaspedaalApiProvider()
    raise ValueError('Onbekende provider')


def validate_search_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme != 'https' or (parsed.hostname or '').lower() not in {'gaspedaal.nl','www.gaspedaal.nl'}:
        raise ValueError('Gebruik een HTTPS-zoeklink van gaspedaal.nl')
    if parsed.username or parsed.password or parsed.port:
        raise ValueError('Ongeldige zoeklink')
    if len(url) > 2048:
        raise ValueError('Zoeklink te lang')
    return url.strip()
