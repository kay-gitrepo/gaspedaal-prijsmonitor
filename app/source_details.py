"""Read advertiser text only from explicitly permitted hosts, with bounded requests.

The portal's click_url may be a Gaspedaal redirect. Inspect its Location without
following arbitrary redirects and fetch only HTTPS hosts in the configured list.
"""
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin,urlsplit
import html
import ipaddress
import json
import re
import httpx
from app.config import settings

@dataclass
class DetailResult:
    portal_id: str | None
    status: str
    source_url: str | None = None
    text: str = ''
    error: str | None = None
    photos: list = None

def allowed_detail_url(url, hosts):
    try:
        p=urlsplit(url);host=(p.hostname or '').lower()
        try:ipaddress.ip_address(host);return False
        except ValueError:pass
        return p.scheme=='https' and host in hosts and not p.username and not p.password and p.port is None and len(url)<=2048
    except ValueError:return False

def allowed_redirect_url(url):
    try:
        p=urlsplit(url)
        return (p.scheme=='https' and p.hostname=='api.gaspedaal.nl' and not p.username and
                not p.password and p.port is None and not p.query and
                bool(re.fullmatch(r'/redirect/vehicle/\d+',p.path)))
    except ValueError:return False

class AdText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip=0;self.text=[];self.ld=False;self.ld_parts=[];self.ld_list=[];self.description=[];self.images=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag in ('script','style','nav','footer','header','noscript'):self.skip+=1
        if tag=='script' and a.get('type')=='application/ld+json':self.ld=True;self.ld_parts=[]
        if tag=='meta' and a.get('name','').lower()=='description':self.description.append(a.get('content',''))
        if tag=='meta' and a.get('property','').lower()=='og:image' and a.get('content'):self.images.append(a['content'])
        if tag=='img' and not self.skip:
            for k in ('data-src','src'):
                if a.get(k):self.images.append(a[k]);break
        if tag in ('p','li','h1','h2','h3','dd','dt','br') and not self.skip:self.text.append('\n')
    def handle_endtag(self,tag):
        if tag=='script' and self.ld:self.ld_list.append(''.join(self.ld_parts));self.ld=False
        if tag in ('script','style','nav','footer','header','noscript'):self.skip=max(self.skip-1,0)
    def handle_data(self,data):
        if self.ld:self.ld_parts.append(data)
        if not self.skip:self.text.append(data)

def extract_advertiser_text(raw):
    p=AdText();p.feed(raw[:800_000]);parts=[]
    for value in p.ld_list:
        try:obj=json.loads(value)
        except ValueError:continue
        for item in obj if isinstance(obj,list) else [obj]:
            if isinstance(item,dict) and isinstance(item.get('description'),str):parts.append(item['description'])
    parts.extend(p.description[:1]);parts.append(''.join(p.text))
    return '\n'.join(html.unescape(re.sub(r'[ \t]+',' ',v)).strip() for v in parts if len(v.strip())>=30)[:16000]

def extract_photos(raw,base_url):
    """Foto-URL's (https) uit og:image, JSON-LD `image` en <img>; kleine pictogrammen worden overgeslagen."""
    p=AdText();p.feed(raw[:800_000]);found=[]
    for value in p.ld_list:
        try:obj=json.loads(value)
        except ValueError:continue
        for item in obj if isinstance(obj,list) else [obj]:
            img=item.get('image') if isinstance(item,dict) else None
            found.extend([img] if isinstance(img,str) else [i for i in (img or []) if isinstance(i,str)])
    found.extend(p.images)
    out=[]
    for u in found:
        u=urljoin(base_url,html.unescape(u).strip())
        low=u.lower().split('?')[0]
        if urlsplit(u).scheme!='https' or not low.endswith(('.jpg','.jpeg','.png','.webp')):continue
        if any(w in low for w in ('logo','icon','sprite','avatar','placeholder')):continue
        if u not in out:out.append(u)
    return out[:30]

def fetch_advertiser_text(offers,client=None):
    hosts={x.strip().lower() for x in settings.advertiser_detail_hosts.split(',') if x.strip()}
    if not hosts:return DetailResult(None,'DISABLED',error='Geen ADVERTISER_DETAIL_HOSTS')
    own=client is None
    client=client or httpx.Client(timeout=15,trust_env=False,follow_redirects=False,
                                  headers={'Accept':'text/html','User-Agent':'OccasionIQ/0.3 personal monitor'})
    try:
        for offer in sorted(offers,key=lambda x:('dealer' not in (x.kind or x.site).lower(),x.site)):
            url=offer.source_url
            if not url and offer.click_url and allowed_redirect_url(offer.click_url):
                try:
                    r=client.get(offer.click_url)
                    if r.status_code in (301,302,303,307,308):url=urljoin(offer.click_url,r.headers.get('Location',''))
                except httpx.HTTPError:continue
            if not url or not allowed_detail_url(url,hosts):continue
            try:
                with client.stream('GET',url) as r:
                    r.raise_for_status()
                    if not r.headers.get('content-type','').lower().startswith('text/html'):
                        return DetailResult(offer.portal_id,'INVALID_CONTENT',url,error='Geen HTML')
                    chunks=[];length=0
                    for c in r.iter_bytes():
                        length+=len(c)
                        if length>800_000:return DetailResult(offer.portal_id,'TOO_LARGE',url,error='Meer dan 800 KB')
                        chunks.append(c)
                    content=b''.join(chunks).decode(r.encoding or 'utf-8',errors='replace')
                text=extract_advertiser_text(content)
                if len(text)<80:return DetailResult(offer.portal_id,'NO_DETAIL_TEXT',url,error='Geen bruikbare advertentietekst')
                return DetailResult(offer.portal_id,'SUCCESS',url,text,photos=extract_photos(content,url))
            except httpx.HTTPError as exc:
                return DetailResult(offer.portal_id,'HTTP_ERROR',url,error=type(exc).__name__)
        return DetailResult(None,'NO_ALLOWED_SOURCE',error='Geen toegestane detailpagina')
    finally:
        if own:client.close()
