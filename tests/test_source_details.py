from types import SimpleNamespace
import httpx
from app import source_details as details
from app.provider import PortalOffer

def test_advertiser_host_allowlist():
    hosts={'www.autotrack.nl'}
    assert details.allowed_detail_url('https://www.autotrack.nl/a/xc90',hosts)
    for u in ('http://www.autotrack.nl/a','https://127.0.0.1','https://www.autotrack.nl.evil.com/a'):
        assert not details.allowed_detail_url(u,hosts)
    assert details.allowed_redirect_url('https://api.gaspedaal.nl/redirect/vehicle/123')
    assert not details.allowed_redirect_url('https://api.gaspedaal.nl/private')

def test_from_popup_redirect_to_original_text(monkeypatch):
    monkeypatch.setattr(details,'settings',SimpleNamespace(advertiser_detail_hosts='www.autotrack.nl'))
    def handler(req):
        if req.url.host=='api.gaspedaal.nl':return httpx.Response(302,headers={'Location':'https://www.autotrack.nl/volvo/xc90/detail'})
        return httpx.Response(200,headers={'content-type':'text/html'},text='''<html><meta name="description" content="Volvo XC90 met trekhaak en 22 inch wielen"><header>Cookie banner</header>
        <main><h1>Volvo XC90 T8</h1><p>Deze XC90 heeft elektrische trekhaak, 22 inch velgen en Bowers & Wilkins audio.</p></main></html>''')
    with httpx.Client(transport=httpx.MockTransport(handler),follow_redirects=False) as client:
        result=details.fetch_advertiser_text([PortalOffer(portal_id='1',site='Dealersite',
            click_url='https://api.gaspedaal.nl/redirect/vehicle/123')],client=client)
    assert result.status=='SUCCESS' and '22 inch velgen' in result.text
    assert 'Cookie banner' not in result.text

def test_redirect_to_unapproved_target_is_not_followed(monkeypatch):
    monkeypatch.setattr(details,'settings',SimpleNamespace(advertiser_detail_hosts='www.autotrack.nl'))
    visited=[]
    def handler(req):
        visited.append(str(req.url));return httpx.Response(302,headers={'Location':'https://localhost/private'})
    with httpx.Client(transport=httpx.MockTransport(handler),follow_redirects=False) as client:
        result=details.fetch_advertiser_text([PortalOffer(portal_id='1',site='Dealer',
            click_url='https://api.gaspedaal.nl/redirect/vehicle/123')],client=client)
    assert result.status=='NO_ALLOWED_SOURCE' and len(visited)==1
