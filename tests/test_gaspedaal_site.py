import json
from types import SimpleNamespace
from urllib.parse import parse_qs,urlsplit
import httpx
import pytest
from app import gaspedaal_site as site
from app.gaspedaal_api import SourceError

SEARCH='https://www.gaspedaal.nl/volvo/xc90/2025?prmin=55000'

def page(ad_ids,total):
    cars=[{'ad_id':str(a),'title':'Volvo XC90 T8 Ultra','price':{'totaal':74000+a},'year':2025,
           'mileage':13000,'portals':[{'portaal_beschrijving':'Dealersite','occ_import_nr':a*10,
             'klik_url':f'https://api.gaspedaal.nl/redirect/vehicle/{a*10}','prijs':74000+a}]} for a in ad_ids]
    return f'<html><body>{total} occasions gevonden<script id="__NEXT_DATA__" type="application/json">'+json.dumps({'props':{'search':{'cars':cars}}})+'</script></body></html>'

def client_patch(monkeypatch,handler):
    original=httpx.Client
    monkeypatch.setattr(site.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))

def test_popup_data_stable_id_and_portals():
    items,total=site.parse_search_page(page([7],1))
    assert total==1 and len(items)==1
    assert items[0].external_id=='7'
    assert items[0].url=='https://www.gaspedaal.nl/zoeken#7'
    assert items[0].portals[0].price_eur==74007

def test_full_search_two_pages(monkeypatch):
    monkeypatch.setattr(site,'settings',SimpleNamespace(data_source_approved=True,gaspedaal_api_max_pages=3))
    def handler(req):
        q=parse_qs(req.url.query.decode());assert q['prmin']==['55000']
        n=int(q.get('page',['1'])[0]);return httpx.Response(200,headers={'content-type':'text/html'},text=page([n],2))
    client_patch(monkeypatch,handler)
    result=site.GaspedaalSiteProvider().fetch({'search_url':SEARCH})
    assert result.complete and len(result.listings)==2 and result.metadata['pages_fetched']==2

def test_incomplete_search_never_full(monkeypatch):
    monkeypatch.setattr(site,'settings',SimpleNamespace(data_source_approved=True,gaspedaal_api_max_pages=2))
    client_patch(monkeypatch,lambda r:httpx.Response(200,headers={'content-type':'text/html'},text=page([1],20)))
    assert not site.GaspedaalSiteProvider().fetch({'search_url':SEARCH}).complete

def test_no_stable_id_fails_closed(monkeypatch):
    monkeypatch.setattr(site,'settings',SimpleNamespace(data_source_approved=True,gaspedaal_api_max_pages=3))
    client_patch(monkeypatch,lambda r:httpx.Response(200,headers={'content-type':'text/html'},text='<p>214 occasions gevonden</p><h2>Volvo XC90</h2>€ 75000'))
    with pytest.raises(SourceError,match='Geen stabiele advertentie-ID'):
        site.GaspedaalSiteProvider().fetch({'search_url':SEARCH})

def test_invalid_host_disallowed():
    with pytest.raises(ValueError):site.paged_url('https://www.gaspedaal.nl.evil.test/a',2)
    assert parse_qs(urlsplit(site.paged_url(SEARCH,2)).query)['page']==['2']
