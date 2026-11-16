"""Experimental adapter reading structured search results from a Gaspedaal search URL.

No undocumented API endpoint is guessed; if the page does not contain complete
stable IDs in embedded JSON, the result is incomplete or fails closed.
Gevalideerd tegen de live Next.js-pagina (nov 2026): advertenties staan in de `occasions`-stream.
"""
from __future__ import annotations
import html
import json
import re
from html.parser import HTMLParser
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
import httpx
from app.config import settings
from app.gaspedaal_api import normalized_ad, SourceError
from app.provider import Snapshot, validate_search_url

class SearchHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.script=False; self.script_attrs={}; self.current=[]
        self.jsons=[]; self.text=[]; self.skip=0
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='script':
            self.script=True;self.script_attrs=a;self.current=[]
        if tag in ('style','script','noscript'):self.skip+=1
        for key,val in attrs:
            if key in ('data-vehicle','data-ad','data-listing') and val:
                self.jsons.append(val)
    def handle_endtag(self,tag):
        if tag=='script' and self.script:
            body=''.join(self.current).strip()
            if body and (self.script_attrs.get('type')=='application/json' or
                         self.script_attrs.get('id')=='__NEXT_DATA__' or
                         body.startswith(('window.__INITIAL_STATE__','window.__PRELOADED_STATE__'))):
                self.jsons.append(body)
            self.script=False
        if tag in ('style','script','noscript'):self.skip=max(0,self.skip-1)
    def handle_data(self,data):
        if self.script:self.current.append(data)
        elif not self.skip:self.text.append(data)

def _documents(raw):
    p=SearchHTML();p.feed(raw)
    total_match=re.search(r'([\d.]+)\s+occasions?\s+gevonden',' '.join(p.text),re.I)
    total=int(total_match.group(1).replace('.','')) if total_match else None
    return p.jsons,total

_FLIGHT=re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')

def _flight_occasions(raw):
    """Advertenties uit de Next.js-streamdata (sleutel `occasions`) van een Gaspedaal-zoekpagina."""
    parts=[]
    for m in _FLIGHT.finditer(raw):
        try:parts.append(json.loads(m.group(1)))
        except ValueError:continue
    text=''.join(parts)
    idx=text.find('"occasions":[')
    if idx<0:return []
    try:data,_=json.JSONDecoder().raw_decode(text[idx+len('"occasions":'):])
    except ValueError:return []
    return data if isinstance(data,list) else []

def _occasion_to_item(o):
    car=o.get('autogegevens') or {}
    alg=car.get('algemeen') or {}
    hist=car.get('geschiedenis') or {}
    seller=((o.get('aanbieder') or {}).get('aanbiedergegevens')) or {}
    title=' '.join(str(x) for x in (alg.get('merknaam'),alg.get('modelnaam'),alg.get('uitvoering')) if x)
    portals=[]
    for p in o.get('portalen') or []:
        click=p.get('klikUrl')
        pid=str(click).rstrip('/').rsplit('/',1)[-1] if click else None
        portals.append({'portaal_beschrijving':p.get('portaalBeschrijving'),'portaal_type':p.get('portaalType'),
                        'vehicle_id':pid,'klik_url':click})
    fotos=o.get('gpFotos') or {}
    photos=[]
    for key in ('fotoGroot','fotoKlein'):
        u=fotos.get(key)
        if isinstance(u,str) and u.startswith('https://'):
            # Gaspedaal levert dezelfde afbeelding in meerdere formaten; neem de grote variant.
            photos.append(u.replace('/images/small/','/images/large/'))
    return {'ad_id':o.get('advertentieId'),'title':title,'photos':list(dict.fromkeys(photos)),
            'price':(o.get('prijs') or {}).get('totaalInclusiefBtw'),
            'year':hist.get('bouwjaar'),'kilometers':hist.get('kilometerstand'),
            'trim':alg.get('uitvoering'),
            'seller':seller.get('naamsvermelding') or seller.get('plaatsnaam'),
            'portals':portals}

def parse_search_page(raw):
    if len(raw)>8_000_000:raise SourceError('HTML groter dan 8 MB')
    docs,total=_documents(raw)
    found={}
    for o in _flight_occasions(raw):
        if not isinstance(o,dict):continue
        try:ad=normalized_ad(_occasion_to_item(o),{})
        except (ValueError,SourceError):continue
        found[ad.external_id]=ad
    if found:return list(found.values()),total
    for raw_json in docs:
        raw_json=html.unescape(raw_json).strip()
        for prefix in ('window.__INITIAL_STATE__','window.__PRELOADED_STATE__'):
            if raw_json.startswith(prefix):raw_json=raw_json.split('=',1)[1].strip()
        try:data,_=json.JSONDecoder().raw_decode(raw_json)
        except ValueError:continue
        nodes=[data];limit=80000
        while nodes and limit>0:
            node=nodes.pop();limit-=1
            if isinstance(node,list):
                nodes.extend(v for v in node if isinstance(v,(dict,list)))
            elif isinstance(node,dict):
                nodes.extend(v for v in node.values() if isinstance(v,(dict,list)))
                if not (any(node.get(k) is not None for k in ('ad_id','advertisementId','vehicleId','vehicle_id','id'))
                        and any(isinstance(node.get(k),str) for k in ('title','headline','name'))
                        and any(k in node for k in ('price','price_eur','askingPrice','asking_price'))):
                    continue
                try:ad=normalized_ad(node,{})
                except (ValueError,SourceError):continue
                found[ad.external_id]=ad
    return list(found.values()),total

def paged_url(search_url,page):
    validate_search_url(search_url)
    p=urlsplit(search_url)
    query=[(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if k!='page']
    if page>1:query.append(('page',str(page)))
    return urlunsplit((p.scheme,p.netloc,p.path,urlencode(query),''))

class GaspedaalSiteProvider:
    def fetch(self,profile):
        if not settings.data_source_approved:raise SourceError('DATA_SOURCE_APPROVED staat uit')
        original=validate_search_url(profile['search_url'])
        ads={};expected=None;pages=0
        with httpx.Client(timeout=25,trust_env=False,follow_redirects=False,
                headers={'Accept':'text/html','User-Agent':'OccasionIQ/0.3 (personal monitor)'}) as client:
            for page in range(1,settings.gaspedaal_api_max_pages+1):
                try:
                    response=client.get(paged_url(original,page));response.raise_for_status()
                except httpx.HTTPError as exc:
                    raise SourceError(f'Zoekpagina {page} niet bereikbaar') from exc
                if not response.headers.get('content-type','').startswith('text/html'):
                    raise SourceError('Zoekpagina leverde geen HTML')
                current,count=parse_search_page(response.text)
                pages+=1
                if count is not None:
                    if expected is not None and expected!=count:
                        raise SourceError('Resultaataantal wijzigde tijdens scannen')
                    expected=count
                if not current and (expected or count):
                    raise SourceError('Geen stabiele advertentie-ID in gestructureerde HTML; parser niet passend')
                previous=len(ads)
                ads.update({ad.external_id:ad for ad in current})
                if expected is not None and len(ads)>=expected:break
                if len(ads)==previous or not current:break
        complete=expected is not None and len(ads)==expected
        return Snapshot(complete=complete,listings=list(ads.values()),metadata={
            'source':'GASPEDAAL_SEARCH_URL','pages_fetched':pages,'expected_listings':expected,
            'unique_ads':len(ads),'exhaustive':complete,'parser':'embedded_json'})
