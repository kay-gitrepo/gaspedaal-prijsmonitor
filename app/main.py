"""Gaspedaal Price Monitor: authenticated REST API + static browser dashboard."""
import csv
import hashlib
import io
import json
import mimetypes
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from time import monotonic
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Depends, HTTPException, Header, Response
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings
from app.version import VERSION
from app.db import connect, dumps, init_db, now, rowdict, uid
from app.provider import Snapshot, validate_search_url
from app.scoring import negotiation_snapshot
from app.worker import start_worker, stop_worker, get_criteria, recalculate_score

ROOT = Path(__file__).parent

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.ui_password or not settings.session_secret or not settings.ha_refresh_token:
        raise RuntimeError('Stel UI_PASSWORD, SESSION_SECRET en HA_REFRESH_TOKEN in vóór het starten.')
    init_db()
    start_worker()
    yield
    stop_worker()

app = FastAPI(title='OccasionIQ',version=VERSION,lifespan=lifespan,docs_url=None,redoc_url=None)
# Op Windows levert Python soms text/plain voor .js; browsers weigeren dan ES-modules.
mimetypes.add_type('application/javascript', '.js')
app.mount('/static', StaticFiles(directory=ROOT/'static'), name='static')

@app.middleware('http')
async def headers_middleware(request,call_next):
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['X-Frame-Options']='SAMEORIGIN'
    response.headers['Cache-Control']='no-store'
    return response

class LoginBody(BaseModel):
    password: str

class ProfileBody(BaseModel):
    title: str = Field(min_length=2,max_length=150)
    search_url: str = Field(min_length=15,max_length=2048)

class SourceBody(BaseModel):
    provider: str

class CriterionBody(BaseModel):
    label: str = Field(min_length=2,max_length=90)
    group_name: str
    weight: int = Field(ge=1,le=5)
    description: str = Field(default='',max_length=350)
    synonyms: list[str] = Field(default_factory=list,max_length=30)
    enabled: bool = True

class RefreshBody(BaseModel):
    scope: str | dict = 'all'
    reason: str = Field(default='manual',max_length=80)

class ReviewBody(BaseModel):
    criterion_key: str
    status: str
    evidence: str | None = Field(default=None,max_length=400)
    reason: str = Field(default='Handmatige verificatie',max_length=300)

class NoteBody(BaseModel):
    offer_eur: int | None = Field(default=None,ge=0)
    actual_purchase_price: int | None = Field(default=None,ge=0)
    note: str = Field(min_length=1,max_length=2000)


def serializer():
    return URLSafeTimedSerializer(settings.session_secret,salt='gaspedaal-price-ui')


def session_data(request):
    raw=request.cookies.get('price_session')
    if not raw:return None
    try:
        data=serializer().loads(raw,max_age=86400)
        return data if data.get('authenticated') and data.get('csrf') else None
    except (BadSignature,SignatureExpired):
        return None


def require_ui(request:Request):
    data=session_data(request)
    if not data:raise HTTPException(status_code=401,detail='Aanmelden vereist')
    return data


def require_csrf(request:Request):
    data=require_ui(request)
    if not secrets.compare_digest(data['csrf'],request.headers.get('x-csrf-token','')):
        raise HTTPException(status_code=403,detail='CSRF-controle mislukt')
    return data


def connection():
    con=connect()
    try:yield con
    finally:con.close()

@app.get('/')
def index():return FileResponse(ROOT/'static'/'index.html')

@app.get('/health')
def health():return {'status':'ok','version':VERSION,'live_gaspedaal_configured':bool(settings.data_source_approved)}

@app.get('/api/v1/session')
def session(request:Request):
    data=session_data(request)
    return {'authenticated':bool(data),'csrf':data['csrf'] if data else None}

@app.post('/api/v1/login')
def login(body:LoginBody,response:Response):
    if not secrets.compare_digest(body.password,settings.ui_password):
        raise HTTPException(status_code=401,detail='Ongeldig wachtwoord')
    csrf=secrets.token_urlsafe(24)
    token=serializer().dumps({'authenticated':True,'csrf':csrf})
    response.set_cookie('price_session',token,httponly=True,secure=settings.secure_cookies,samesite='strict',max_age=86400)
    return {'authenticated':True,'csrf':csrf}

@app.post('/api/v1/logout')
def logout(response:Response,_=Depends(require_csrf)):
    response.delete_cookie('price_session',secure=settings.secure_cookies,samesite='strict')
    return {'ok':True}

@app.get('/api/v1/profiles')
def profiles(_=Depends(require_ui),con=Depends(connection)):
    rows=[dict(x) for x in con.execute('SELECT id,title,search_url,provider,enabled,created_at,updated_at,fixture_payload IS NOT NULL as has_snapshot FROM search_profiles ORDER BY title')]
    return {'items':rows, 'gaspedaal_api_configured':bool(settings.data_source_approved and settings.gaspedaal_api_search_template), 'gaspedaal_site_available':settings.data_source_approved}

@app.post('/api/v1/profiles',status_code=201)
def create_profile(body:ProfileBody,_=Depends(require_csrf),con=Depends(connection)):
    try:url=validate_search_url(body.search_url)
    except ValueError as exc:raise HTTPException(status_code=422,detail=str(exc))
    pid=uid('sp')
    provider='gaspedaal_site' if settings.data_source_approved else 'fixture'
    con.execute('INSERT INTO search_profiles(id,title,search_url,provider,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                (pid,body.title,url,provider,now(),now()))
    return {'id':pid,'provider':provider,'source_status':'DIRECT_SEARCH_URL' if provider=='gaspedaal_site' else 'MANUAL_IMPORT'}

@app.put('/api/v1/profiles/{profile_id}/source')
def change_profile_source(profile_id:str,body:SourceBody,_=Depends(require_csrf),con=Depends(connection)):
    if body.provider not in ('fixture','gaspedaal','gaspedaal_site'):
        raise HTTPException(422,'Onbekende gegevensbron')
    if body.provider=='gaspedaal_site' and not settings.data_source_approved:
        raise HTTPException(422,'Activeer DATA_SOURCE_APPROVED voor directe Gaspedaal URL-uitlezing')
    if body.provider=='gaspedaal' and not (settings.data_source_approved and settings.gaspedaal_api_search_template):
        raise HTTPException(422,'Gaspedaal API is nog niet geconfigureerd via de serverinstellingen')
    if not con.execute('SELECT 1 FROM search_profiles WHERE id=?',(profile_id,)).fetchone():
        raise HTTPException(404,'Zoekprofiel niet gevonden')
    con.execute('UPDATE search_profiles SET provider=?,updated_at=? WHERE id=?',(body.provider,now(),profile_id))
    return {'updated':profile_id,'provider':body.provider}

@app.post('/api/v1/profiles/{profile_id}/snapshot')
def import_snapshot(profile_id:str,snapshot:Snapshot,_=Depends(require_csrf),con=Depends(connection)):
    if not con.execute('SELECT 1 FROM search_profiles WHERE id=?',(profile_id,)).fetchone():
        raise HTTPException(404,'Zoekprofiel niet gevonden')
    if len(snapshot.listings)>5000:raise HTTPException(413,'Te veel advertenties')
    ids=[x.external_id for x in snapshot.listings]
    if len(set(ids))!=len(ids):raise HTTPException(422,'Dubbele advertentie-ID')
    con.execute('UPDATE search_profiles SET fixture_payload=?,updated_at=? WHERE id=?',
                (snapshot.model_dump_json(),now(),profile_id))
    return {'imported':len(ids),'complete':snapshot.complete,'message':'Snapshot opgeslagen. Druk op Nu verversen om observaties vast te leggen.'}

@app.get('/api/v1/criteria')
def criteria(_=Depends(require_ui),con=Depends(connection)):
    return {'items':get_criteria(con)}

@app.put('/api/v1/criteria/{key}')
def update_criterion(key:str,body:CriterionBody,_=Depends(require_csrf),con=Depends(connection)):
    if body.group_name not in ('MUST_HAVE','NICE_TO_HAVE'):
        raise HTTPException(422,'Ongeldige groep')
    if not con.execute('SELECT 1 FROM criteria WHERE key=?',(key,)).fetchone():
        raise HTTPException(404,'Criterium niet gevonden')
    con.execute('''UPDATE criteria SET label=?,group_name=?,weight=?,description=?,synonyms_json=?,enabled=?,updated_at=?
                   WHERE key=?''',
                (body.label,body.group_name,body.weight,body.description,dumps(body.synonyms),int(body.enabled),now(),key))
    # Criteria edits invalidate previous claims; do not silently preserve a stale score.
    con.execute('UPDATE listings SET analyzed_hash=NULL')
    return {'updated':key,'note':'Gemini-herbeoordeling wordt bij de volgende refresh uitgevoerd'}

@app.post('/api/v1/refresh-runs')
def enqueue_refresh(request:Request,body:RefreshBody,response:Response,
                    idempotency_key:str|None=Header(default=None,alias='Idempotency-Key'),con=Depends(connection)):
    bearer=request.headers.get('authorization','')
    via_ha=bool(settings.ha_refresh_token) and secrets.compare_digest(bearer,f'Bearer {settings.ha_refresh_token}')
    if via_ha:source='HOME_ASSISTANT'
    else:
        require_csrf(request)
        source='MANUAL_UI'
    scope=body.scope
    if scope!='all':
        if not isinstance(scope,dict) or not isinstance(scope.get('profile_ids'),list) or not scope['profile_ids']:
            raise HTTPException(400,'Ongeldige scope')
        if not all(isinstance(x,str) for x in scope['profile_ids']):raise HTTPException(400,'Ongeldige profile_ids')
        requested=set(scope['profile_ids'])
        existing={x['id'] for x in con.execute('SELECT id FROM search_profiles WHERE enabled=1')}
        if not requested <= existing:raise HTTPException(403,'Onbekend of uitgeschakeld zoekprofiel')
        scope={'profile_ids':sorted(requested)}
    if idempotency_key and len(idempotency_key)>128:
        raise HTTPException(400,'Idempotency-Key te lang')
    payload_hash=hashlib.sha256(dumps({'scope':scope,'reason':body.reason}).encode()).hexdigest()
    con.execute('BEGIN IMMEDIATE')
    try:
        attempt_id=uid('ta')
        prior=con.execute('SELECT * FROM refresh_runs WHERE idempotency_key=? ORDER BY created_at DESC LIMIT 1',
                          (idempotency_key,)).fetchone() if idempotency_key else None
        if prior:
            con.execute('INSERT INTO trigger_attempts VALUES(?,?,?,?,?,?)',
                        (attempt_id,source,prior['id'],'DUPLICATE',dumps({'scope':scope}),now()))
            con.execute('COMMIT')
            if prior['request_hash']!=payload_hash:
                raise HTTPException(409,detail={'code':'IDEMPOTENCY_KEY_REUSED'})
            return {'run_id':prior['id'],'status':prior['state'],'already_accepted':True}
        active=con.execute("SELECT * FROM refresh_runs WHERE state IN ('QUEUED','RUNNING') LIMIT 1").fetchone()
        if active:
            con.execute('INSERT INTO trigger_attempts VALUES(?,?,?,?,?,?)',
                        (attempt_id,source,active['id'],'REJECTED_OVERLAP',dumps({'scope':scope}),now()))
            con.execute('COMMIT')
            raise HTTPException(409,detail={'code':'RUN_ALREADY_ACTIVE','active_run_id':active['id'],'retryable':True})
        run_id=uid('rr')
        con.execute('INSERT INTO refresh_runs(id,trigger_source,state,scope_json,request_hash,idempotency_key,created_at) VALUES(?,?,?,?,?,?,?)',
                    (run_id,source,'QUEUED',dumps(scope),payload_hash,idempotency_key,now()))
        con.execute('INSERT INTO trigger_attempts VALUES(?,?,?,?,?,?)',
                    (attempt_id,source,run_id,'ACCEPTED',dumps({'scope':scope}),now()))
        con.execute('COMMIT')
        response.status_code=202
        return {'run_id':run_id,'status':'QUEUED','trigger_source':source,'status_url':f'/api/v1/refresh-runs/{run_id}','created_at':now()}
    except HTTPException:raise
    except Exception:
        con.execute('ROLLBACK')
        raise

@app.get('/api/v1/refresh-runs')
def runs(_=Depends(require_ui),con=Depends(connection)):
    items=[dict(r) for r in con.execute('SELECT * FROM refresh_runs ORDER BY created_at DESC LIMIT 100')]
    for r in items:
        r['summary']=json.loads(r.pop('summary_json'))
        r['scope']=json.loads(r.pop('scope_json'))
    return {'items':items}

@app.get('/api/v1/refresh-runs/{run_id}')
def run_detail(run_id:str,_=Depends(require_ui),con=Depends(connection)):
    row=con.execute('SELECT * FROM refresh_runs WHERE id=?',(run_id,)).fetchone()
    if not row:raise HTTPException(404,'Run niet gevonden')
    data=dict(row)
    data['summary']=json.loads(data.pop('summary_json'))
    data['scope']=json.loads(data.pop('scope_json'))
    data['events']=[dict(r) for r in con.execute('SELECT * FROM run_events WHERE run_id=? ORDER BY id',(run_id,))]
    data['gemini_requests']=[dict(r) for r in con.execute('''SELECT id,listing_id,decision,model_id,tokens_in,tokens_out,error,created_at
                                                     FROM integration_requests WHERE run_id=? ORDER BY created_at''',(run_id,))]
    return data

@app.get('/api/v1/dashboard')
def dashboard(_=Depends(require_ui),con=Depends(connection)):
    rows=[dict(r) for r in con.execute("SELECT id,price_eur,year,kilometers,eligibility,score_total FROM listings WHERE availability='ACTIVE'")]
    values=sorted(r['price_eur'] for r in rows)
    daily=con.execute('SELECT substr(observed_at,1,10) AS date, listing_id, price_eur FROM price_observations ORDER BY observed_at DESC,id DESC').fetchall()
    # Last observation per vehicle and calendar day, so repeat scans do not overweight a listing.
    seen=set(); dates={}
    for r in daily:
        key=(r['date'],r['listing_id'])
        if key in seen:continue
        seen.add(key);dates.setdefault(r['date'],[]).append(r['price_eur'])
    trend=[{'date':date,'mean_asking':round(sum(p)/len(p)),'count':len(p)} for date,p in sorted(dates.items())][-90:]
    return {'active_listings':len(rows),'median_asking':values[len(values)//2] if values else None,
            'matches':sum(r['eligibility']=='MATCH' for r in rows),
            'average_score':round(sum(r['score_total'] for r in rows)/len(rows),1) if rows else 0,
            'price_trend':trend,
            'source_status':'GASPEDAAL_SEARCH_URL_EXPERIMENTAL' if settings.data_source_approved else 'HANDMATIGE_IMPORT',
            'limitations':['Uitlezing van Gaspedaal-HTML is experimenteel en moet op de eigen server worden gevalideerd.' if settings.data_source_approved else 'Directe Gaspedaal-zoeklink is nog niet ingeschakeld; alleen geïmporteerde snapshots worden verwerkt.',
                           'Verdwenen advertenties zijn geen bewezen verkopen; getoonde prijzen zijn vraagprijzen.']}

@app.get('/api/v1/listings')
def listings(profile_id:str|None=None,_=Depends(require_ui),con=Depends(connection)):
    query='''SELECT l.*, (SELECT MIN(price_eur) FROM price_observations p WHERE p.listing_id=l.id) AS lowest_observed_price,
          (SELECT COUNT(*) FROM price_observations p WHERE p.listing_id=l.id) AS observations
          FROM listings l'''
    params=[]
    if profile_id:
        query+=' JOIN profile_listings pl ON pl.listing_id=l.id AND pl.profile_id=?';params.append(profile_id)
    query+=' ORDER BY (l.availability="ACTIVE") DESC,l.score_total DESC,l.price_eur ASC LIMIT 1000'
    return {'items':[dict(r) for r in con.execute(query,params)]}

@app.get('/api/v1/listings/{listing_id}')
def listing_detail(listing_id:str,_=Depends(require_ui),con=Depends(connection)):
    row=con.execute('SELECT * FROM listings WHERE id=?',(listing_id,)).fetchone()
    if not row:raise HTTPException(404,'Auto niet gevonden')
    listing=dict(row)
    listing['sources']=[dict(r) for r in con.execute('''SELECT * FROM listing_sources WHERE listing_id=? ORDER BY site''',(listing_id,))]
    for source in listing['sources']:
        source['history']=[dict(r) for r in con.execute('''SELECT observed_at,price_eur,run_id FROM source_price_observations WHERE listing_id=? AND portal_id=? ORDER BY observed_at''',(listing_id,source['portal_id']))]
    listing['detail_fetches']=[dict(r) for r in con.execute('''SELECT portal_id,source_url,status,text_length,error,created_at FROM source_detail_attempts WHERE listing_id=? ORDER BY created_at DESC LIMIT 15''',(listing_id,))]
    listing['history']=[dict(r) for r in con.execute('SELECT observed_at,price_eur,run_id FROM price_observations WHERE listing_id=? ORDER BY observed_at',(listing_id,))]
    listing['events']=[dict(r) for r in con.execute('SELECT * FROM listing_events WHERE listing_id=? ORDER BY created_at DESC',(listing_id,))]
    listing['claims']=[dict(r) for r in con.execute('''SELECT c.*,cr.label,cr.group_name,cr.weight FROM claims c JOIN criteria cr ON cr.key=c.criterion_key
                                           WHERE c.listing_id=? ORDER BY cr.group_name,cr.weight DESC''',(listing_id,))]
    listing['notes']=[dict(r) for r in con.execute('SELECT * FROM negotiation_notes WHERE listing_id=? ORDER BY created_at DESC',(listing_id,))]
    # Restrict comps to same model category, similar year and kilometers. Trim preference is conditional.
    comps=[dict(r) for r in con.execute("SELECT id,price_eur,year,kilometers,trim FROM listings WHERE availability='ACTIVE' AND id!=?",(listing_id,))]
    comps=[c for c in comps if (not row['year'] or not c['year'] or abs(c['year']-row['year'])<=2)
           and (row['kilometers'] is None or c['kilometers'] is None or abs(c['kilometers']-row['kilometers'])<=40000)
           and (not row['trim'] or not c['trim'] or row['trim'].casefold()==c['trim'].casefold())]
    listing['negotiation']=negotiation_snapshot(listing,comps)
    return listing

@app.post('/api/v1/listings/{listing_id}/favorite')
def toggle_favorite(listing_id:str,_=Depends(require_csrf),con=Depends(connection)):
    row=con.execute('SELECT favorite FROM listings WHERE id=?',(listing_id,)).fetchone()
    if not row:raise HTTPException(404,'Niet gevonden')
    value=1-int(row['favorite']);con.execute('UPDATE listings SET favorite=? WHERE id=?',(value,listing_id))
    return {'favorite':bool(value)}

@app.post('/api/v1/listings/{listing_id}/review')
def manual_review(listing_id:str,body:ReviewBody,_=Depends(require_csrf),con=Depends(connection)):
    if body.status not in ('PRESENT','ABSENT','UNKNOWN','CONFLICT'):raise HTTPException(422,'Ongeldige status')
    if not con.execute('SELECT 1 FROM listings WHERE id=?',(listing_id,)).fetchone():raise HTTPException(404,'Auto onbekend')
    if not con.execute('SELECT 1 FROM criteria WHERE key=?',(body.criterion_key,)).fetchone():raise HTTPException(404,'Optie onbekend')
    con.execute('''INSERT INTO claims(listing_id,criterion_key,status,evidence,reason,confidence,source,updated_at)
       VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(listing_id,criterion_key) DO UPDATE SET status=excluded.status,
       evidence=excluded.evidence,reason=excluded.reason,confidence=excluded.confidence,source=excluded.source,updated_at=excluded.updated_at''',
       (listing_id,body.criterion_key,body.status,body.evidence,body.reason,1,'MANUAL_OVERRIDE',now()))
    score=recalculate_score(con,listing_id,get_criteria(con))
    return {'updated':True,'score':score}

@app.post('/api/v1/listings/{listing_id}/notes')
def add_note(listing_id:str,body:NoteBody,_=Depends(require_csrf),con=Depends(connection)):
    if not con.execute('SELECT 1 FROM listings WHERE id=?',(listing_id,)).fetchone():raise HTTPException(404,'Auto onbekend')
    nid=uid('note')
    con.execute('INSERT INTO negotiation_notes VALUES(?,?,?,?,?,?)',
                (nid,listing_id,body.offer_eur,body.actual_purchase_price,body.note,now()))
    return {'id':nid}

@app.get('/api/v1/integrations')
def integrations(_=Depends(require_ui),con=Depends(connection)):
    return {'items':[dict(r) for r in con.execute('''SELECT i.id,i.run_id,i.listing_id,i.decision,i.model_id,i.tokens_in,i.tokens_out,
             i.duration_ms,i.error,i.created_at,l.title FROM integration_requests i JOIN listings l ON l.id=i.listing_id
             ORDER BY i.created_at DESC LIMIT 200''')]}

@app.get('/api/v1/integrations/{integration_id}')
def integration_detail(integration_id:str,_=Depends(require_ui),con=Depends(connection)):
    row=con.execute('SELECT * FROM integration_requests WHERE id=?',(integration_id,)).fetchone()
    if not row:raise HTTPException(404,'Integratie niet gevonden')
    result=dict(row)
    for key in ('request_json','parsed_json'):
        result[key]=json.loads(result[key]) if result[key] else None
    return result

@app.get('/api/v1/export/observations.csv')
def observations_export(_=Depends(require_ui),con=Depends(connection)):
    output=io.StringIO()
    writer=csv.writer(output)
    writer.writerow(['run_id','profile_id','listing_id','observed_at_utc','asking_price_eur'])
    for r in con.execute('SELECT run_id,profile_id,listing_id,observed_at,price_eur FROM price_observations ORDER BY observed_at'):
        writer.writerow([r['run_id'],r['profile_id'],r['listing_id'],r['observed_at'],r['price_eur']])
    return Response(content=output.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="price-observations.csv"'})
