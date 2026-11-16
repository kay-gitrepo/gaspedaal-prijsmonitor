"""OccasionIQ: authenticated REST API + static browser app."""
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
from app.db import connect, dumps, init_db, insert_default_criteria, now, rowdict, uid
from app.extraction import cleaned_text, sha256 as text_hash
from app.insights import first_photo, listing_insights
from app import changes as run_changes
from app.valuation_data import market_positions, valuation_for
from app.market_data import market_overview
from app.provider import Snapshot, validate_search_url
from app.worker import (start_worker, stop_worker, get_criteria, recalculate_score, recalculate_all,
                        apply_local_claims, profiles_of)
from app.scope import PL_SCORES, context_profile, criteria_labels, scored_listings

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

class ProfilePatch(BaseModel):
    title: str | None = Field(default=None,min_length=2,max_length=150)
    search_url: str | None = Field(default=None,min_length=15,max_length=2048)
    budget_eur: int | None = Field(default=None,ge=1000,le=2_000_000)
    enabled: bool | None = None

class SourceBody(BaseModel):
    provider: str

class CriterionBody(BaseModel):
    label: str = Field(min_length=2,max_length=90)
    group_name: str
    weight: int = Field(ge=1,le=5)
    description: str = Field(default='',max_length=350)
    synonyms: list[str] = Field(default_factory=list,max_length=30)
    match_terms: list[str] = Field(default_factory=list,max_length=20)
    enabled: bool = True

class CriterionCreate(BaseModel):
    profile_id: str | None = None
    label: str = Field(min_length=2,max_length=90)
    group_name: str = 'NICE_TO_HAVE'
    weight: int = Field(default=3,ge=1,le=5)
    description: str = Field(default='',max_length=350)
    synonyms: list[str] = Field(default_factory=list,max_length=30)
    match_terms: list[str] = Field(default_factory=list,max_length=20)

class CopyCriteriaBody(BaseModel):
    from_profile_id: str
    to_profile_id: str

class SuggestBody(BaseModel):
    label: str = Field(min_length=2,max_length=90)

class RefreshBody(BaseModel):
    scope: str | dict = 'all'
    reason: str = Field(default='manual',max_length=80)

class ReviewBody(BaseModel):
    profile_id: str | None = None
    criterion_key: str
    status: str
    evidence: str | None = Field(default=None,max_length=400)
    reason: str = Field(default='Handmatige verificatie',max_length=300)

class DescriptionBody(BaseModel):
    text: str = Field(default='',max_length=50000)

class NegotiationBody(BaseModel):
    my_opening: int | None = Field(default=None,ge=1000,le=2_000_000)
    my_target: int | None = Field(default=None,ge=1000,le=2_000_000)
    my_max: int | None = Field(default=None,ge=1000,le=2_000_000)

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

@app.get('/api/v1/system')
def system(_=Depends(require_ui)):
    """Configuration status for the settings screen: booleans and limits only, never secrets."""
    return {'version':VERSION,'live_source':bool(settings.data_source_approved),
            'api_configured':bool(settings.data_source_approved and settings.gaspedaal_api_search_template),
            'ai_enabled':bool(settings.gemini_enabled and settings.gemini_api_key),'ai_model':settings.gemini_model,
            'max_ai_calls_per_run':settings.max_gemini_calls_per_run,
            'detail_hosts':[h.strip() for h in settings.advertiser_detail_hosts.split(',') if h.strip()],
            'max_detail_fetches_per_run':settings.max_detail_fetches_per_run,
            'disappearance_days':settings.disappearance_days}

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

def last_run_for(con, profile_id):
    """Latest finished check that covered this profile, with that profile's own outcome when recorded."""
    for run in con.execute('''SELECT id,state,created_at,finished_at,scope_json,summary_json FROM refresh_runs
                              WHERE finished_at IS NOT NULL ORDER BY created_at DESC,rowid DESC LIMIT 200'''):
        scope=json.loads(run['scope_json'])
        if scope!='all' and profile_id not in (scope.get('profile_ids') or []):continue
        summary=json.loads(run['summary_json'])
        own=(summary.get('per_profile') or {}).get(profile_id)
        if own is None and 'per_profile' in summary:continue  # profile was paused or not part of this check
        return {'run_id':run['id'],'at':run['finished_at'] or run['created_at'],
                'state':(own or {}).get('state',run['state']),'found':(own or {}).get('found')}
    return None


@app.get('/api/v1/profiles')
def profiles(archived:bool=False,_=Depends(require_ui),con=Depends(connection)):
    rows=[dict(x) for x in con.execute(f'''SELECT p.id,p.title,p.search_url,p.provider,p.enabled,p.created_at,p.updated_at,
        p.fixture_payload IS NOT NULL AS has_snapshot,p.budget_eur,p.archived_at,p.scope_changed_at,
        (SELECT COUNT(*) FROM profile_listings pl WHERE pl.profile_id=p.id AND pl.status='ACTIVE') AS listings_active,
        (SELECT COUNT(*) FROM profile_listings pl JOIN listings l ON l.id=pl.listing_id
           WHERE pl.profile_id=p.id AND pl.status='ACTIVE' AND pl.eligibility='MATCH') AS listings_match
        FROM search_profiles p WHERE p.archived_at IS {'NOT ' if archived else ''}NULL ORDER BY p.title''')]
    for row in rows:
        row['last_run']=last_run_for(con,row['id'])
    return {'items':rows, 'gaspedaal_api_configured':bool(settings.data_source_approved and settings.gaspedaal_api_search_template), 'gaspedaal_site_available':settings.data_source_approved}

@app.patch('/api/v1/profiles/{profile_id}')
def update_profile(profile_id:str,body:ProfilePatch,_=Depends(require_csrf),con=Depends(connection)):
    row=con.execute('SELECT * FROM search_profiles WHERE id=? AND archived_at IS NULL',(profile_id,)).fetchone()
    if not row:raise HTTPException(404,'Zoekopdracht niet gevonden')
    changes={}
    given=body.model_fields_set
    if 'title' in given and body.title is not None:changes['title']=body.title.strip()
    if 'search_url' in given and body.search_url is not None:
        try:url=validate_search_url(body.search_url)
        except ValueError as exc:raise HTTPException(422,str(exc))
        if url!=row['search_url']:
            changes['search_url']=url
            # Next complete check marks unseen cars as outside the new filters instead of disappeared.
            changes['scope_changed_at']=now()
    if 'budget_eur' in given:changes['budget_eur']=body.budget_eur
    if 'enabled' in given and body.enabled is not None:changes['enabled']=int(body.enabled)
    if changes:
        changes['updated_at']=now()
        con.execute(f'UPDATE search_profiles SET {",".join(k+"=?" for k in changes)} WHERE id=?',
                    (*changes.values(),profile_id))
    return {'updated':profile_id,'scope_changed':'search_url' in changes}

@app.post('/api/v1/profiles/{profile_id}/archive')
def archive_profile(profile_id:str,_=Depends(require_csrf),con=Depends(connection)):
    """Archive keeps all cars and price history; the search is no longer checked or shown."""
    cur=con.execute('UPDATE search_profiles SET archived_at=?,enabled=0,updated_at=? WHERE id=? AND archived_at IS NULL',
                    (now(),now(),profile_id))
    if not cur.rowcount:raise HTTPException(404,'Zoekopdracht niet gevonden')
    return {'archived':profile_id}

@app.post('/api/v1/profiles',status_code=201)
def create_profile(body:ProfileBody,_=Depends(require_csrf),con=Depends(connection)):
    try:url=validate_search_url(body.search_url)
    except ValueError as exc:raise HTTPException(status_code=422,detail=str(exc))
    pid=uid('sp')
    provider='gaspedaal_site' if settings.data_source_approved else 'fixture'
    con.execute('INSERT INTO search_profiles(id,title,search_url,provider,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                (pid,body.title,url,provider,now(),now()))
    insert_default_criteria(con,pid)
    return {'id':pid,'provider':provider,'source_status':'DIRECT_SEARCH_URL' if provider=='gaspedaal_site' else 'MANUAL_IMPORT'}

@app.put('/api/v1/profiles/{profile_id}/source')
def change_profile_source(profile_id:str,body:SourceBody,_=Depends(require_csrf),con=Depends(connection)):
    if body.provider not in ('fixture','gaspedaal','gaspedaal_site'):
        raise HTTPException(422,'Onbekende gegevensbron')
    if body.provider=='gaspedaal_site' and not settings.data_source_approved:
        raise HTTPException(422,'Directe uitlezing van Gaspedaal staat uit (zie Instellingen)')
    if body.provider=='gaspedaal' and not (settings.data_source_approved and settings.gaspedaal_api_search_template):
        raise HTTPException(422,'De Gaspedaal-koppeling is nog niet ingesteld (zie Instellingen)')
    if not con.execute('SELECT 1 FROM search_profiles WHERE id=?',(profile_id,)).fetchone():
        raise HTTPException(404,'Zoekopdracht niet gevonden')
    con.execute('UPDATE search_profiles SET provider=?,updated_at=? WHERE id=?',(body.provider,now(),profile_id))
    return {'updated':profile_id,'provider':body.provider}

@app.post('/api/v1/profiles/{profile_id}/snapshot')
def import_snapshot(profile_id:str,snapshot:Snapshot,_=Depends(require_csrf),con=Depends(connection)):
    if not con.execute('SELECT 1 FROM search_profiles WHERE id=?',(profile_id,)).fetchone():
        raise HTTPException(404,'Zoekopdracht niet gevonden')
    if len(snapshot.listings)>5000:raise HTTPException(413,'Te veel advertenties')
    ids=[x.external_id for x in snapshot.listings]
    if len(set(ids))!=len(ids):raise HTTPException(422,'Dubbele advertentie-ID')
    con.execute('UPDATE search_profiles SET fixture_payload=?,updated_at=? WHERE id=?',
                (snapshot.model_dump_json(),now(),profile_id))
    return {'imported':len(ids),'complete':snapshot.complete,'message':'Import opgeslagen. Start een controle om de prijzen vast te leggen.'}

def wish_profile(con,profile_id):
    """Wensen horen bij een zoekopdracht; zonder keuze alleen als er precies één is."""
    if profile_id:
        if not con.execute('SELECT 1 FROM search_profiles WHERE id=?',(profile_id,)).fetchone():
            raise HTTPException(404,'Zoekopdracht niet gevonden')
        return profile_id
    rows=con.execute('SELECT id FROM search_profiles WHERE archived_at IS NULL').fetchall()
    if len(rows)!=1:raise HTTPException(422,'Kies een zoekopdracht')
    return rows[0][0]

@app.get('/api/v1/criteria')
def criteria(profile_id:str|None=None,_=Depends(require_ui),con=Depends(connection)):
    pid=wish_profile(con,profile_id)
    return {'profile_id':pid,'items':get_criteria(con,pid)}

def clean_terms(values):
    out=[]
    for v in values:
        v=' '.join(str(v).split())[:80]
        if v and v.lower() not in {x.lower() for x in out}:out.append(v)
    return out


def slug(text):
    import re
    import unicodedata
    ascii_text=unicodedata.normalize('NFKD',text).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+','_',ascii_text).strip('_')[:40] or 'wens'


def profile_pairs(con,profile_id,only_active=False):
    query='SELECT listing_id FROM profile_listings WHERE profile_id=?'+(" AND status='ACTIVE'" if only_active else '')
    return [[profile_id,r[0]] for r in con.execute(query,(profile_id,))]


@app.post('/api/v1/criteria',status_code=201)
def create_criterion(body:CriterionCreate,_=Depends(require_csrf),con=Depends(connection)):
    if body.group_name not in ('MUST_HAVE','NICE_TO_HAVE'):raise HTTPException(422,'Ongeldige groep')
    pid=wish_profile(con,body.profile_id)
    base=slug(body.label);key=base;n=2
    while con.execute('SELECT 1 FROM criteria WHERE profile_id=? AND key=?',(pid,key)).fetchone():
        key=f'{base}_{n}';n+=1
    con.execute('''INSERT INTO criteria(profile_id,key,label,group_name,weight,description,synonyms_json,match_terms_json,
                   enabled,updated_at) VALUES(?,?,?,?,?,?,?,?,1,?)''',
                (pid,key,body.label.strip(),body.group_name,body.weight,body.description.strip(),
                 dumps(clean_terms(body.synonyms)),dumps(clean_terms(body.match_terms)),now()))
    # New wish: recognise it locally right away; the next check asks the AI for the rest.
    apply_local_claims(con,pid,get_criteria(con,pid),{key})
    return {'key':key,'profile_id':pid}

@app.delete('/api/v1/criteria/{key}')
def delete_criterion(key:str,profile_id:str|None=None,_=Depends(require_csrf),con=Depends(connection)):
    """Soft delete: the wish is switched off, its claims (including your own corrections) are kept."""
    pid=wish_profile(con,profile_id)
    cur=con.execute('UPDATE criteria SET enabled=0,updated_at=? WHERE profile_id=? AND key=? AND enabled=1',(now(),pid,key))
    if not cur.rowcount:raise HTTPException(404,'Wens niet gevonden')
    recalculate_all(con,pid,get_criteria(con,pid))
    return {'deleted':key}

@app.put('/api/v1/criteria/{key}')
def update_criterion(key:str,body:CriterionBody,profile_id:str|None=None,_=Depends(require_csrf),con=Depends(connection)):
    if body.group_name not in ('MUST_HAVE','NICE_TO_HAVE'):
        raise HTTPException(422,'Ongeldige groep')
    pid=wish_profile(con,profile_id)
    old=con.execute('SELECT * FROM criteria WHERE profile_id=? AND key=?',(pid,key)).fetchone()
    if not old:raise HTTPException(404,'Wens niet gevonden')
    synonyms,terms=clean_terms(body.synonyms),clean_terms(body.match_terms)
    meaning_changed=(body.description.strip()!=old['description'] or synonyms!=json.loads(old['synonyms_json'])
                     or terms!=json.loads(old['match_terms_json'] or '[]'))
    con.execute('''UPDATE criteria SET label=?,group_name=?,weight=?,description=?,synonyms_json=?,match_terms_json=?,
                   enabled=?,updated_at=? WHERE profile_id=? AND key=?''',
                (body.label.strip(),body.group_name,body.weight,body.description.strip(),dumps(synonyms),dumps(terms),
                 int(body.enabled),now(),pid,key))
    criteria=get_criteria(con,pid)
    if meaning_changed:
        # What counts as present changed: judge again (locally now, with AI at the next check).
        con.execute('UPDATE profile_listings SET analyzed_hash=NULL WHERE profile_id=?',(pid,))
        apply_local_claims(con,pid,criteria,{key})
    # Weight, group or on/off only change the arithmetic: recalculate now, keep every assessment.
    recalculate_all(con,pid,criteria)
    return {'updated':key,'reassess':meaning_changed}

@app.post('/api/v1/criteria/copy')
def copy_criteria(body:CopyCriteriaBody,_=Depends(require_csrf),con=Depends(connection)):
    """Wensen van een andere zoekopdracht overnemen. Bestaande oordelen en eigen correcties blijven bewaard;
    wensen die de bron niet heeft worden uitgezet. Daarna worden de auto's opnieuw beoordeeld."""
    src,dst=wish_profile(con,body.from_profile_id),wish_profile(con,body.to_profile_id)
    if src==dst:raise HTTPException(422,'Kies twee verschillende zoekopdrachten')
    rows=con.execute('SELECT * FROM criteria WHERE profile_id=?',(src,)).fetchall()
    for r in rows:
        con.execute('''INSERT INTO criteria(profile_id,key,label,group_name,weight,description,synonyms_json,
            match_terms_json,enabled,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(profile_id,key) DO UPDATE SET
            label=excluded.label,group_name=excluded.group_name,weight=excluded.weight,description=excluded.description,
            synonyms_json=excluded.synonyms_json,match_terms_json=excluded.match_terms_json,enabled=excluded.enabled,
            updated_at=excluded.updated_at''',(dst,r['key'],r['label'],r['group_name'],r['weight'],r['description'],
            r['synonyms_json'],r['match_terms_json'],r['enabled'],now()))
    keys=[r['key'] for r in rows]
    marks=','.join('?'*len(keys)) or "''"
    con.execute(f'UPDATE criteria SET enabled=0,updated_at=? WHERE profile_id=? AND key NOT IN ({marks})',(now(),dst,*keys))
    criteria=get_criteria(con,dst)
    apply_local_claims(con,dst,criteria,{c['key'] for c in criteria})
    recalculate_all(con,dst,criteria)
    pairs=profile_pairs(con,dst)
    run_id=enqueue_reanalysis(con,pairs) if pairs else None
    return {'copied':len(rows),'run_id':run_id}

@app.post('/api/v1/criteria/suggest')
def suggest_criterion_terms(body:SuggestBody,_=Depends(require_csrf),con=Depends(connection)):
    empty={'description':'','synonyms':[],'match_terms':[],'let_op':[]}
    if not (settings.gemini_enabled and settings.gemini_api_key):
        return {**empty,'ai_beschikbaar':False}
    from app.gemini import suggest_criterion
    sid=uid('cs')
    try:
        result,log=suggest_criterion(body.label)
    except Exception as exc:
        con.execute('INSERT INTO criterion_suggestions(id,label,model_id,error,created_at) VALUES(?,?,?,?,?)',
                    (sid,body.label,settings.gemini_model,f'{type(exc).__name__}: aanroep mislukt',now()))
        return {**empty,'ai_beschikbaar':True,'fout':'Het voorstel kon niet worden opgehaald. Vul zelf zoekwoorden in.'}
    con.execute('''INSERT INTO criterion_suggestions(id,label,model_id,request_json,response_json,parsed_json,tokens_in,
                   tokens_out,duration_ms,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)''',
                (sid,body.label,log['model_id'],dumps(log['request']),log['response'],dumps(log['parsed']),
                 log['tokens_in'],log['tokens_out'],log['duration_ms'],now()))
    return {**result,'ai_beschikbaar':True}

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
            raise HTTPException(400,'Ongeldige keuze van zoekopdrachten')
        if not all(isinstance(x,str) for x in scope['profile_ids']):raise HTTPException(400,'Ongeldige zoekopdracht')
        requested=set(scope['profile_ids'])
        existing={x['id'] for x in con.execute('SELECT id FROM search_profiles WHERE enabled=1')}
        if not requested <= existing:raise HTTPException(403,'Onbekende of gepauzeerde zoekopdracht')
        scope={'profile_ids':sorted(requested)}
    if idempotency_key and len(idempotency_key)>128:
        raise HTTPException(400,'Idempotency-Key te lang')
    payload_hash=hashlib.sha256(dumps({'scope':scope,'reason':body.reason}).encode()).hexdigest()
    con.execute('BEGIN IMMEDIATE')
    try:
        attempt_id=uid('ta')
        prior=con.execute('SELECT * FROM refresh_runs WHERE idempotency_key=? ORDER BY created_at DESC,rowid DESC LIMIT 1',
                          (idempotency_key,)).fetchone() if idempotency_key else None
        if prior:
            con.execute('INSERT INTO trigger_attempts VALUES(?,?,?,?,?,?)',
                        (attempt_id,source,prior['id'],'DUPLICATE',dumps({'scope':scope}),now()))
            con.execute('COMMIT')
            if prior['request_hash']!=payload_hash:
                raise HTTPException(409,detail={'code':'IDEMPOTENCY_KEY_REUSED'})
            return {'run_id':prior['id'],'status':prior['state'],'already_accepted':True}
        active=con.execute('''SELECT * FROM refresh_runs WHERE state IN ('QUEUED','RUNNING')
                                 AND scope_json NOT LIKE '%"analyze%' LIMIT 1''').fetchone()
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

def enqueue_reanalysis(con,items):
    """Herbeoordeling zonder controle: alleen de beoordeling, niets ophalen.

    `items` zijn auto-ID's (alle zoekopdrachten van die auto) of [zoekopdracht, auto]-paren.
    """
    pairs=[]
    for item in items:
        pairs+=[[pid,item] for pid in profiles_of(con,item)] if isinstance(item,str) else [list(item)]
    pairs=sorted({tuple(p) for p in pairs})
    for pid,lid in pairs:
        con.execute('UPDATE profile_listings SET analyzed_hash=NULL WHERE profile_id=? AND listing_id=?',(pid,lid))
    run_id=uid('rr')
    scope={'analyze':[list(p) for p in pairs]}
    con.execute('''INSERT INTO refresh_runs(id,trigger_source,state,scope_json,request_hash,created_at)
                   VALUES(?,?,?,?,?,?)''',(run_id,'REANALYSIS','QUEUED',dumps(scope),'reanalysis',now()))
    return run_id

@app.post('/api/v1/listings/{listing_id}/reanalyze',status_code=202)
def reanalyze_listing(listing_id:str,_=Depends(require_csrf),con=Depends(connection)):
    if not con.execute('SELECT 1 FROM listings WHERE id=?',(listing_id,)).fetchone():
        raise HTTPException(404,'Auto niet gevonden')
    run_id=enqueue_reanalysis(con,[listing_id])
    return {'run_id':run_id,'status_url':f'/api/v1/refresh-runs/{run_id}'}

@app.post('/api/v1/integrations/process-queue',status_code=202)
def process_queue(_=Depends(require_csrf),con=Depends(connection)):
    """Beoordeel auto's die nog wachten, binnen dezelfde AI-limiet per controle."""
    pairs=[list(r) for r in con.execute("""SELECT profile_id,listing_id FROM profile_listings
                                           WHERE analyzed_hash IS NULL AND status='ACTIVE'""")]
    if not pairs:raise HTTPException(409,'Er wacht geen auto op beoordeling')
    run_id=enqueue_reanalysis(con,pairs)
    return {'run_id':run_id,'count':len({p[1] for p in pairs})}

@app.get('/api/v1/integrations/summary')
def integrations_summary(_=Depends(require_ui),con=Depends(connection)):
    month=now()[:7]
    row=con.execute('''SELECT
        (SELECT COUNT(DISTINCT listing_id) FROM profile_listings WHERE analyzed_hash IS NOT NULL) AS assessed,
        (SELECT COUNT(DISTINCT listing_id) FROM profile_listings WHERE analyzed_hash IS NULL AND status='ACTIVE') AS waiting,
        (SELECT COUNT(*) FROM integration_requests WHERE decision='ERROR' AND substr(created_at,1,7)=?) AS failed,
        (SELECT COALESCE(SUM(COALESCE(tokens_in,0)+COALESCE(tokens_out,0)),0) FROM integration_requests
           WHERE substr(created_at,1,7)=?) AS tokens_month''',(month,month)).fetchone()
    return {**dict(row),'max_per_run':settings.max_gemini_calls_per_run,
            'ai_enabled':bool(settings.gemini_enabled and settings.gemini_api_key)}

@app.get('/api/v1/refresh-runs')
def runs(_=Depends(require_ui),con=Depends(connection)):
    items=[dict(r) for r in con.execute('SELECT * FROM refresh_runs ORDER BY created_at DESC,rowid DESC LIMIT 100')]
    for r in items:
        r['summary']=json.loads(r.pop('summary_json'))
        r['scope']=json.loads(r.pop('scope_json'))
    return {'items':items}

@app.get('/api/v1/refresh-runs/{run_id}')
def run_detail(run_id:str,_=Depends(require_ui),con=Depends(connection)):
    row=con.execute('SELECT * FROM refresh_runs WHERE id=?',(run_id,)).fetchone()
    if not row:raise HTTPException(404,'Controle niet gevonden')
    data=dict(row)
    data['summary']=json.loads(data.pop('summary_json'))
    data['scope']=json.loads(data.pop('scope_json'))
    data['events']=[dict(r) for r in con.execute('SELECT * FROM run_events WHERE run_id=? ORDER BY id',(run_id,))]
    titles={r['id']:r['title'] for r in con.execute('SELECT id,title FROM search_profiles')}
    # Completeness per search, from the 'processed' event of each search in this check.
    data['profiles']=[]
    for pid,result in (data['summary'].get('per_profile') or {}).items():
        metrics=next((json.loads(e['metrics_json']) for e in data['events']
                      if e['stage']=='SOURCE' and json.loads(e['metrics_json'] or '{}').get('profile_id')==pid
                      and 'found' in json.loads(e['metrics_json'] or '{}')),{})
        meta=metrics.get('provider_metadata') or {}
        data['profiles'].append({'id':pid,'title':titles.get(pid,'Onbekende zoekopdracht'),'state':result.get('state'),
            'found':metrics.get('found',result.get('found')),'complete':metrics.get('provider_complete'),
            'pages':meta.get('pages_fetched'),'expected':meta.get('expected_listings'),
            'skipped_invalid':metrics.get('skipped_invalid',0),'source':meta.get('source')})
    data['changes']=run_changes.changes(con,None,run_id)['groups']
    data['gemini_requests']=[dict(r) for r in con.execute('''SELECT id,listing_id,decision,model_id,tokens_in,tokens_out,error,created_at
                                                     FROM integration_requests WHERE run_id=? ORDER BY created_at''',(run_id,))]
    return data

@app.get('/api/v1/status')
def check_status(_=Depends(require_ui),con=Depends(connection)):
    """Freshness: last finished check, last successful check and a running one (for the top bar)."""
    return run_changes.status(con)

@app.get('/api/v1/changes')
def check_changes(profile_id:str|None=None,run_id:str|None=None,_=Depends(require_ui),con=Depends(connection)):
    """What changed in one check (default: the last successful one), from the recorded events."""
    if run_id and not con.execute('SELECT 1 FROM refresh_runs WHERE id=?',(run_id,)).fetchone():
        raise HTTPException(404,'Controle niet gevonden')
    return run_changes.changes(con,profile_id,run_id)

@app.get('/api/v1/market')
def market(profile_id:str|None=None,days:int|None=None,_=Depends(require_ui),con=Depends(connection)):
    """Market overview answering the seven questions; every statistic carries n and is null below n = 5."""
    if days is not None and days not in (30,90):raise HTTPException(422,'Kies 30 of 90 dagen, of laat leeg voor alles')
    return market_overview(con,profile_id,days)


LIST_COLUMNS = ('''l.id,l.external_id,l.title,l.url,l.year,l.kilometers,l.trim,l.seller,l.price_eur,l.first_seen,
    l.last_seen,l.updated_at,l.availability,l.favorite,l.photos_json,l.description_source,
    TRIM(l.description)!='' AS has_text''')


@app.get('/api/v1/listings')
def listings(profile_id:str|None=None,_=Depends(require_ui),con=Depends(connection)):
    """List view without the ad text (B5): derived price and time fields, first photo only.

    Scores follow the wishes of the chosen search; with all searches, those of the search the car was first seen in.
    """
    items=scored_listings(con,LIST_COLUMNS,profile_id)
    items.sort(key=lambda i:(i['availability']!='ACTIVE',-(i['score_total'] or 0),i['price_eur']))
    items=items[:1000]
    labels=criteria_labels(con)
    for item in items:
        item['status_reason']=status_reason(item.pop('status_keys_json','{}'),labels,item['score_profile_id'])
        item['photo']=first_photo(item.pop('photos_json'))
    extra=listing_insights(con,items,profile_id)
    market=market_positions(con,items)
    for item in items:
        item.update(extra.get(item['id'],{}))
        position=market.get(item['id']) or {}
        item['market_diff']=position.get('difference')
        item['market_n']=position.get('n')
        item['market_median']=position.get('median')
    return {'items':items}


def status_reason(raw,labels,profile_id):
    """Which must-haves make the status what it is, as labels: {absent, unknown, conflict}."""
    keys=json.loads(raw or '{}')
    return {k:[labels.get((profile_id,x),x) for x in keys.get(k,[])] for k in ('absent','unknown','conflict')}

@app.get('/api/v1/listings/{listing_id}')
def listing_detail(listing_id:str,profile_id:str|None=None,_=Depends(require_ui),con=Depends(connection)):
    row=con.execute('SELECT * FROM listings WHERE id=?',(listing_id,)).fetchone()
    if not row:raise HTTPException(404,'Auto niet gevonden')
    listing=dict(row)
    # Wishes, claims and scores of one search: the requested one if the car is in it, else where it was first seen.
    pid=context_profile(con,listing_id,profile_id)
    titles={r[0]:r[1] for r in con.execute('SELECT id,title FROM search_profiles')}
    listing['score_profile_id']=pid
    listing['score_profile_title']=titles.get(pid)
    listing['profiles']=[{'id':p,'title':titles.get(p)} for p in profiles_of(con,listing_id)]
    score=con.execute(f'''SELECT {",".join(PL_SCORES)} FROM profile_listings WHERE profile_id=? AND listing_id=?''',
                      (pid,listing_id)).fetchone()
    listing.update(dict(score) if score else {})
    listing['sources']=[dict(r) for r in con.execute('''SELECT * FROM listing_sources WHERE listing_id=? ORDER BY site''',(listing_id,))]
    for source in listing['sources']:
        source['history']=[dict(r) for r in con.execute('''SELECT observed_at,price_eur,run_id FROM source_price_observations WHERE listing_id=? AND portal_id=? ORDER BY observed_at''',(listing_id,source['portal_id']))]
    listing['detail_fetches']=[dict(r) for r in con.execute('''SELECT portal_id,source_url,status,text_length,error,created_at FROM source_detail_attempts WHERE listing_id=? ORDER BY created_at DESC LIMIT 15''',(listing_id,))]
    listing['history']=[dict(r) for r in con.execute('SELECT observed_at,price_eur,run_id FROM price_observations WHERE listing_id=? ORDER BY observed_at',(listing_id,))]
    listing['events']=[dict(r) for r in con.execute('SELECT * FROM listing_events WHERE listing_id=? ORDER BY created_at DESC',(listing_id,))]
    # Every active wish, also those without an assessment yet (shown as uncertain).
    listing['claims']=[dict(r) for r in con.execute('''SELECT cr.key AS criterion_key,cr.label,cr.group_name,cr.weight,
        COALESCE(c.status,'UNKNOWN') AS status,c.evidence,c.reason,COALESCE(c.confidence,0) AS confidence,
        c.source,c.updated_at,c.integration_id,c.listing_id IS NULL AS not_assessed
        FROM criteria cr LEFT JOIN claims c ON c.criterion_key=cr.key AND c.profile_id=cr.profile_id AND c.listing_id=?
        WHERE cr.profile_id=? AND cr.enabled=1 ORDER BY cr.group_name,cr.weight DESC,cr.label''',(listing_id,pid))]
    listing['status_reason']=status_reason(listing.pop('status_keys_json','{}'),criteria_labels(con),pid)
    listing['notes']=[dict(r) for r in con.execute('SELECT * FROM negotiation_notes WHERE listing_id=? ORDER BY created_at DESC',(listing_id,))]
    listing.update(listing_insights(con,[listing]).get(listing_id,{}))
    # Exactly the text that is assessed (minimised, personal data removed).
    listing['assessed_text']=cleaned_text(listing['title'],listing['description'],get_criteria(con,pid) if pid else [])
    return listing

@app.get('/api/v1/listings/{listing_id}/valuation')
def listing_valuation(listing_id:str,profile_id:str|None=None,_=Depends(require_ui),con=Depends(connection)):
    """Market band from comparable asking prices, three amounts and the arguments. Never a selling price."""
    if not con.execute('SELECT 1 FROM listings WHERE id=?',(listing_id,)).fetchone():
        raise HTTPException(404,'Auto niet gevonden')
    pid=context_profile(con,listing_id,profile_id)
    return valuation_for(con,listing_id,get_criteria(con,pid) if pid else [],pid)

@app.put('/api/v1/listings/{listing_id}/negotiation')
def set_negotiation(listing_id:str,body:NegotiationBody,_=Depends(require_csrf),con=Depends(connection)):
    """Your own opening bid, target and limit; null returns to the suggestion."""
    cur=con.execute('UPDATE listings SET my_opening=?,my_target=?,my_max=? WHERE id=?',
                    (body.my_opening,body.my_target,body.my_max,listing_id))
    if not cur.rowcount:raise HTTPException(404,'Auto niet gevonden')
    return {'updated':True}

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
    pid=context_profile(con,listing_id,body.profile_id)
    if not pid or not con.execute('SELECT 1 FROM criteria WHERE profile_id=? AND key=?',(pid,body.criterion_key)).fetchone():
        raise HTTPException(404,'Wens onbekend')
    con.execute('''INSERT INTO claims(profile_id,listing_id,criterion_key,status,evidence,reason,confidence,source,updated_at,
       integration_id) VALUES(?,?,?,?,?,?,?,?,?,NULL) ON CONFLICT(profile_id,listing_id,criterion_key) DO UPDATE SET
       status=excluded.status,evidence=excluded.evidence,reason=excluded.reason,confidence=excluded.confidence,
       source=excluded.source,updated_at=excluded.updated_at,integration_id=NULL''',
       (pid,listing_id,body.criterion_key,body.status,body.evidence,body.reason,1,'MANUAL_OVERRIDE',now()))
    score=recalculate_score(con,pid,listing_id,get_criteria(con,pid))
    return {'updated':True,'score':score,'profile_id':pid}

@app.post('/api/v1/listings/{listing_id}/description')
def set_description(listing_id:str,body:DescriptionBody,_=Depends(require_csrf),con=Depends(connection)):
    """Pasted ad text (MANUAL) is never overwritten by a check; an empty text removes it again."""
    row=con.execute('SELECT title FROM listings WHERE id=?',(listing_id,)).fetchone()
    if not row:raise HTTPException(404,'Auto onbekend')
    text=body.text.strip()
    digest=text_hash(cleaned_text(row['title'],text))
    con.execute('''UPDATE listings SET description=?,description_source=?,text_hash=?,updated_at=?
                   WHERE id=?''',(text,'MANUAL' if text else None,digest,now(),listing_id))
    run_id=enqueue_reanalysis(con,[listing_id])
    return {'updated':True,'description_source':'MANUAL' if text else None,'run_id':run_id}

@app.delete('/api/v1/listings/{listing_id}/review/{criterion_key}')
def undo_review(listing_id:str,criterion_key:str,profile_id:str|None=None,_=Depends(require_csrf),
                con=Depends(connection)):
    """Remove your own judgement: the wish is recognised locally again now and reassessed right away."""
    pid=context_profile(con,listing_id,profile_id)
    cur=con.execute("DELETE FROM claims WHERE profile_id=? AND listing_id=? AND criterion_key=? AND source='MANUAL_OVERRIDE'",
                    (pid,listing_id,criterion_key))
    if not cur.rowcount:raise HTTPException(404,'Geen eigen oordeel gevonden')
    criteria=get_criteria(con,pid)
    apply_local_claims(con,pid,criteria,{criterion_key},{listing_id})
    score=recalculate_score(con,pid,listing_id,criteria)
    run_id=enqueue_reanalysis(con,[[pid,listing_id]])
    return {'updated':True,'score':score,'run_id':run_id}

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
    if not row:raise HTTPException(404,'Beoordeling niet gevonden')
    result=dict(row)
    for key in ('request_json','parsed_json'):
        result[key]=json.loads(result[key]) if result[key] else None
    car=con.execute('SELECT title FROM listings WHERE id=?',(row['listing_id'],)).fetchone()
    result['title']=car['title'] if car else None
    # Readable verdicts from this assessment (also for local recognition without an AI call).
    result['claims']=[dict(r) for r in con.execute('''SELECT c.criterion_key,cr.label,cr.group_name,c.status,c.evidence,
        c.reason,c.confidence,c.source FROM claims c JOIN criteria cr ON cr.key=c.criterion_key
        AND cr.profile_id=c.profile_id WHERE c.integration_id=? ORDER BY cr.group_name,cr.weight DESC''',(integration_id,))]
    return result

@app.get('/api/v1/export/observations.csv')
def observations_export(_=Depends(require_ui),con=Depends(connection)):
    output=io.StringIO()
    writer=csv.writer(output)
    writer.writerow(['run_id','profile_id','listing_id','observed_at_utc','asking_price_eur'])
    for r in con.execute('SELECT run_id,profile_id,listing_id,observed_at,price_eur FROM price_observations ORDER BY observed_at'):
        writer.writerow([r['run_id'],r['profile_id'],r['listing_id'],r['observed_at'],r['price_eur']])
    return Response(content=output.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="price-observations.csv"'})
