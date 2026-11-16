"""Offline contract tests for the configurable direct site-API adapter."""
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app import gaspedaal_api as api
from app.gaspedaal_api import GaspedaalApiProvider, SourceError, at_path, euro_price, render_url

SEARCH = 'https://www.gaspedaal.nl/volvo/xc90/2025?prijs=60000-80000'


def config(**changes):
    defaults=dict(data_source_approved=True,
                  gaspedaal_api_search_template='https://api.gaspedaal.nl/verified-search?q={search_url}&page={page}',
                  gaspedaal_api_items_path='data.results',
                  gaspedaal_api_fields_json='{}',
                  gaspedaal_api_max_pages=5)
    defaults.update(changes)
    return SimpleNamespace(**defaults)


def test_format_url_is_encoded_and_restricted():
    u=render_url(config().gaspedaal_api_search_template,SEARCH,1)
    assert parse_qs(urlsplit(u).query)['q']==[SEARCH]
    assert parse_qs(urlsplit(u).query)['page']==['1']
    for template in ['https://bad.example/abc?q={search_url}',
                     'http://api.gaspedaal.nl?q={search_url}',
                     'https://api.gaspedaal.nl.evil.com/{page}',
                     'https://user:password@api.gaspedaal.nl/{page}']:
        with pytest.raises(SourceError):render_url(template,SEARCH,1)


def test_price_and_path():
    assert euro_price('€ 73.950')==73950
    assert euro_price({'totaal':72000})==72000
    assert at_path({'data':{'results':[1,2]}},'data.results')==[1,2]
    with pytest.raises(SourceError): euro_price('in overleg')


def test_all_pages_and_stable_id(monkeypatch):
    monkeypatch.setattr(api,'settings',config())
    def handler(req):
        page=int(parse_qs(req.url.query.decode())['page'][0])
        if page==1:
            body={'data':{'results':[{'ad_id':'gsp-001','title':'XC90 Ultra Trekhaak',
                         'price':{'totaal':73950},'year':2025,'mileage':30500,
                         'description':'22 inch velgen en trekhaak'}]},'pagination':{'hasNext':True}}
        else:
            body={'data':{'results':[{'ad_id':'gsp-002','title':'XC90 Ultra',
                         'price':{'totaal':'70.500'},'year':2025,'mileage':11000}]},
                         'pagination':{'hasNext':False}}
        return httpx.Response(200,json=body)
    original=httpx.Client
    monkeypatch.setattr(api.httpx,'Client',lambda **kw: original(transport=httpx.MockTransport(handler),**kw))
    result=GaspedaalApiProvider().fetch({'search_url':SEARCH})
    assert result.complete
    assert len(result.listings)==2
    assert result.listings[0].external_id=='gsp-001'
    assert result.listings[0].description=='22 inch velgen en trekhaak'
    assert result.listings[1].price_eur==70500


def test_missing_pagination_is_not_complete(monkeypatch):
    monkeypatch.setattr(api,'settings',config())
    original=httpx.Client
    def handler(req):
        return httpx.Response(200,json={'data':{'results':[{'ad_id':'gsp-3','title':'XC90', 'price':75000}]}})
    monkeypatch.setattr(api.httpx,'Client',lambda **kw: original(transport=httpx.MockTransport(handler),**kw))
    result=GaspedaalApiProvider().fetch({'search_url':SEARCH})
    assert not result.complete
    assert len(result.listings)==1


def test_source_error_if_unknown_shape(monkeypatch):
    monkeypatch.setattr(api,'settings',config())
    original=httpx.Client
    monkeypatch.setattr(api.httpx,'Client',lambda **kw: original(transport=httpx.MockTransport(
        lambda req: httpx.Response(200,json={'items':[]})),**kw))
    with pytest.raises(SourceError,match='advertenties-array'):
        GaspedaalApiProvider().fetch({'search_url':SEARCH})


def test_api_opt_in_is_enforced(monkeypatch):
    monkeypatch.setattr(api,'settings',config(data_source_approved=False))
    with pytest.raises(SourceError,match='DATA_SOURCE_APPROVED'):
        GaspedaalApiProvider().fetch({'search_url':SEARCH})
