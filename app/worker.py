"""Persistent, single-consumer refresh engine. Home Assistant owns scheduling."""
import json
import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone
from hashlib import sha256
from app.config import settings
from app.db import connect, dumps, log_event, now, uid
from app.extraction import cleaned_text, local_claims, sha256 as text_hash
from app.gemini import classify, build_payload, PROMPT_VERSION
from app.provider import provider_for
from app.source_details import fetch_advertiser_text
from app.scoring import calculate

logger = logging.getLogger(__name__)
_stop = threading.Event()
_thread = None


def get_criteria(con):
    result = []
    for row in con.execute('SELECT * FROM criteria WHERE enabled=1 ORDER BY group_name,weight DESC').fetchall():
        item = dict(row)
        item['synonyms'] = json.loads(item.pop('synonyms_json'))
        result.append(item)
    return result


def recalculate_score(con, listing_id, criteria):
    claims = {r['criterion_key']: r['status'] for r in con.execute('SELECT criterion_key,status FROM claims WHERE listing_id=?',(listing_id,))}
    score = calculate(criteria, claims)
    con.execute('UPDATE listings SET score_total=?,score_must=?,score_nice=?,eligibility=? WHERE id=?',
                (score['score_total'],score['score_must'],score['score_nice'],score['eligibility'],listing_id))
    return score


def analyze_listing(con, listing_id, run_id, criteria):
    row = con.execute('SELECT * FROM listings WHERE id=?',(listing_id,)).fetchone()
    if row is None: return 'MISSING'
    text = cleaned_text(row['title'], row['description'], criteria)
    fingerprint = text_hash(text + dumps([{'key':c['key'],'group':c['group_name'],'weight':c['weight'],
                  'description':c['description'],'synonyms':c['synonyms']} for c in criteria]) + settings.gemini_model + PROMPT_VERSION + ('gemini' if settings.gemini_api_key and settings.gemini_enabled else 'local'))
    if row['analyzed_hash'] == fingerprint:
        return 'CACHE_HIT'
    local = local_claims(text)
    outstanding = [c for c in criteria if local.get(c['key'],{}).get('status') not in ('PRESENT','ABSENT')]
    all_claims = {c['key']:{'criterion_key':c['key'],'status':'UNKNOWN','confidence':0,
                  'evidence_quote':None,'reason_short':'Niet aangetoond in toegestane advertentietekst'} for c in criteria}
    all_claims.update(local)
    decision = 'LOCAL_ONLY' if not outstanding else 'SKIPPED_NO_KEY'
    outgoing, incoming, parsed, duration, ti, to, error = None,None,None,None,None,None,None
    if outstanding and settings.gemini_enabled and settings.gemini_api_key:
        count = con.execute('SELECT COUNT(*) FROM integration_requests WHERE run_id=? AND decision=?', (run_id,'SUCCESS')).fetchone()[0]
        if count < settings.max_gemini_calls_per_run:
            decision = 'SUCCESS'
            # Never call Gemini with the entire dealer page: text is already minimized, personal data redacted.
            outgoing = {'model':settings.gemini_model, 'contents':build_payload(text,outstanding)}
            try:
                remote, call = classify(text,outstanding)
                incoming, parsed, duration, ti, to = call['response'], call['parsed'],call['duration_ms'],call['tokens_in'],call['tokens_out']
                # Deterministic PRESENT/ABSENT claims are not demoted by uncertain model output.
                all_claims.update({x['criterion_key']:x for x in remote})
            except Exception as exc:
                decision = 'ERROR'
                error = f'{type(exc).__name__}: modelaanroep mislukt (details achterwege om sleutels/gegevens te beschermen)' 
                # Provider errors are visible in Gemini log but do not lose the scan.
                log_event(con,run_id,'GEMINI','WARN',f'Gemini-analyse voor advertentie mislukt: {type(exc).__name__}',
                          {'listing_id':listing_id})
        else:
            decision='SKIPPED_BUDGET'
    elif not outstanding:
        decision='LOCAL_ONLY'
    else:
        decision='SKIPPED_NO_KEY'
    # Log the exact sanitized payload sent, parsed response, errors and use; skipped requests do not pretend to be API calls.
    con.execute('''INSERT INTO integration_requests(id,run_id,listing_id,decision,model_id,request_json,response_json,parsed_json,
        tokens_in,tokens_out,duration_ms,error,text_hash,criteria_hash,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (uid('gi'),run_id,listing_id,decision,settings.gemini_model,dumps(outgoing) if outgoing else None,
         incoming,dumps(parsed) if parsed else None,ti,to,duration,error,row['text_hash'],fingerprint,now()))
    for key,c in all_claims.items():
        original=con.execute('SELECT source FROM claims WHERE listing_id=? AND criterion_key=?',(listing_id,key)).fetchone()
        if original and original['source']=='MANUAL_OVERRIDE':
            continue  # Manual evidence is deliberately sticky across refreshes.
        con.execute('''INSERT INTO claims(listing_id,criterion_key,status,evidence,reason,confidence,source,updated_at)
           VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(listing_id,criterion_key) DO UPDATE SET
           status=excluded.status,evidence=excluded.evidence,reason=excluded.reason,confidence=excluded.confidence,
           source=excluded.source,updated_at=excluded.updated_at''',
           (listing_id,key,c['status'],c.get('evidence_quote'),c.get('reason_short'),c.get('confidence',0),
            'AD_TEXT',now()))
    # Failed/budgeted analyses must be eligible for retry later.
    if decision not in ('ERROR','SKIPPED_BUDGET'):
        con.execute('UPDATE listings SET analyzed_hash=? WHERE id=?',(fingerprint,listing_id))
    recalculate_score(con, listing_id, criteria)
    return decision


def scan_profile(con,run_id,profile,criteria):
    snapshot = provider_for(profile).fetch(dict(profile))
    count=len(snapshot.listings)
    if count == 0 and snapshot.complete:
        # Empty complete scan could be legitimate; use defensive protection to avoid mass disappearance.
        prev=con.execute('SELECT COUNT(*) FROM profile_listings WHERE profile_id=? AND status=?',
                         (profile['id'],'ACTIVE')).fetchone()[0]
        if prev > 0:
            raise RuntimeError('Lege scan terwijl eerder actief aanbod bestond: geen verdwijningen toegepast')
    for ad in snapshot.listings:
        if not (settings.min_price <= ad.price_eur <= settings.max_price):
            raise ValueError(f'Ongeldige/onwaarschijnlijke vraagprijs: {ad.external_id}')
    stats={'found':count,'new':0,'price_changes':0,'missing_new':0,'off_market_new':0,'observations':0,
           'gemini_calls':0,'gemini_errors':0,'cache_hits':0, 'portals':0,'portal_price_changes':0,'provider_complete':snapshot.complete,
           'provider_metadata':snapshot.metadata}
    # A bounded optional detail pass, outside the database write transaction.
    details={}
    if settings.advertiser_detail_hosts.strip():
        used=con.execute('SELECT COUNT(*) FROM source_detail_attempts WHERE run_id=?',(run_id,)).fetchone()[0]
        remaining=max(0,settings.max_detail_fetches_per_run-used)
        for ad in snapshot.listings:
            if not remaining:break
            if ad.description.strip() or not ad.portals:continue
            old=con.execute('SELECT description FROM listings WHERE external_id=?',
                           (f'{profile["provider"]}:{ad.external_id}',)).fetchone()
            if old and old['description'].strip():continue
            try:detail=fetch_advertiser_text(ad.portals)
            except Exception as exc:
                logger.warning('Bronadvertentie niet leesbaar: %s',type(exc).__name__)
                continue
            if detail.status=='NO_ALLOWED_SOURCE':continue
            details[ad.external_id]=detail
            if detail.status=='SUCCESS':ad.description=detail.text
            remaining-=1
    seen=set()
    candidate_ids=set()
    # All observations and missing transitions are committed together for each profile.
    con.execute('BEGIN IMMEDIATE')
    try:
        for ad in snapshot.listings:
            ext_id=f'{profile["provider"]}:{ad.external_id}'
            previous=con.execute('SELECT * FROM listings WHERE external_id=?',(ext_id,)).fetchone()
            listing_id=previous['id'] if previous else uid('car')
            clean=cleaned_text(ad.title,ad.description,criteria)
            content_hash=text_hash(clean)
            if previous:
                if ad.price_eur != previous['price_eur']:
                    stats['price_changes']+=1
                    con.execute('INSERT INTO listing_events(run_id,listing_id,event_type,previous_price,new_price,created_at) VALUES(?,?,?,?,?,?)',
                                (run_id,listing_id,'PRICE_CHANGED',previous['price_eur'],ad.price_eur,now()))
                # analyze_listing checks a content+criteria+model fingerprint and skips cache hits.
                candidate_ids.add(listing_id)
                con.execute('''UPDATE listings SET title=?,url=?,year=?,kilometers=?,trim=?,seller=?,price_eur=?,
                   description=?,text_hash=?,last_seen=?,updated_at=?,availability='ACTIVE' WHERE id=?''',
                   (ad.title,ad.url,ad.year,ad.kilometers,ad.trim,ad.seller,ad.price_eur,
                    ad.description or previous['description'],content_hash if ad.description or not previous['description'] else previous['text_hash'],now(),now(),listing_id))
            else:
                stats['new']+=1
                candidate_ids.add(listing_id)
                con.execute('''INSERT INTO listings(id,external_id,title,url,year,kilometers,trim,seller,price_eur,
                  description,text_hash,first_seen,last_seen,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (listing_id,ext_id,ad.title,ad.url,ad.year,ad.kilometers,ad.trim,ad.seller,ad.price_eur,
                   ad.description,content_hash,now(),now(),now()))
                con.execute('INSERT INTO listing_events(run_id,listing_id,event_type,new_price,created_at) VALUES(?,?,?,?,?)',
                            (run_id,listing_id,'FIRST_SEEN',ad.price_eur,now()))
            # One car, multiple advertisers; retain per-portal price measurements.
            for offer in ad.portals:
                old_price=con.execute('SELECT price_eur FROM listing_sources WHERE listing_id=? AND portal_id=?',
                                      (listing_id,offer.portal_id)).fetchone()
                if old_price and old_price['price_eur'] is not None and offer.price_eur is not None and old_price['price_eur']!=offer.price_eur:
                    stats['portal_price_changes']+=1
                    log_event(con,run_id,'PORTAL','INFO','Prijs bij aanbieder gewijzigd',{
                        'listing_id':listing_id,'site':offer.site,'from':old_price['price_eur'],'to':offer.price_eur})
                con.execute('''INSERT INTO listing_sources(listing_id,portal_id,site,kind,click_url,source_url,price_eur,first_seen,last_seen)
                    VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(listing_id,portal_id) DO UPDATE SET
                    site=excluded.site,kind=excluded.kind,
                    click_url=COALESCE(excluded.click_url,listing_sources.click_url),
                    source_url=COALESCE(excluded.source_url,listing_sources.source_url),
                    price_eur=COALESCE(excluded.price_eur,listing_sources.price_eur),
                    last_seen=excluded.last_seen''',
                    (listing_id,offer.portal_id,offer.site,offer.kind,offer.click_url,
                     offer.source_url,offer.price_eur,now(),now()))
                if offer.price_eur is not None:
                    con.execute('''INSERT OR IGNORE INTO source_price_observations
                        (run_id,listing_id,portal_id,site,price_eur,observed_at)
                        VALUES(?,?,?,?,?,?)''',
                        (run_id,listing_id,offer.portal_id,offer.site,offer.price_eur,now()))
                stats['portals']+=1
            detail=details.get(ad.external_id)
            if detail:
                con.execute('''INSERT INTO source_detail_attempts
                    (id,run_id,listing_id,portal_id,source_url,status,text_length,error,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?)''',
                    (uid('sd'),run_id,listing_id,detail.portal_id,detail.source_url,detail.status,
                     len(detail.text),detail.error,now()))
                log_event(con,run_id,'SOURCE_DETAIL','INFO' if detail.status=='SUCCESS' else 'WARN',
                    'Advertentietekst opgehaald' if detail.status=='SUCCESS' else 'Advertentietekst niet opgehaald',
                    {'listing_id':listing_id,'status':detail.status,'portal_id':detail.portal_id})
            con.execute('''INSERT INTO profile_listings(profile_id,listing_id,last_seen,missing_since,missing_checks,status)
             VALUES(?,?,?,NULL,0,'ACTIVE') ON CONFLICT(profile_id,listing_id) DO UPDATE SET
             last_seen=excluded.last_seen,missing_since=NULL,missing_checks=0,status='ACTIVE' ''',
             (profile['id'],listing_id,now()))
            con.execute('''INSERT OR IGNORE INTO price_observations(run_id,profile_id,listing_id,price_eur,observed_at)
             VALUES(?,?,?,?,?)''',(run_id,profile['id'],listing_id,ad.price_eur,now()))
            stats['observations']+=1
            seen.add(listing_id)
        if snapshot.complete:
            members=con.execute('SELECT * FROM profile_listings WHERE profile_id=?',(profile['id'],)).fetchall()
            for entry in members:
                if entry['listing_id'] in seen or entry['status']=='OFF_MARKET':
                    continue
                if not entry['missing_since']:
                    stats['missing_new']+=1
                    con.execute('''UPDATE profile_listings SET status='MISSING_UNCONFIRMED',missing_since=?,missing_checks=1
                       WHERE profile_id=? AND listing_id=?''',(now(),profile['id'],entry['listing_id']))
                    con.execute('INSERT INTO listing_events(run_id,listing_id,event_type,created_at) VALUES(?,?,?,?)',
                                (run_id,entry['listing_id'],'MISSING_UNCONFIRMED',now()))
                else:
                    elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(entry['missing_since'])).total_seconds()/86400
                    if elapsed >= settings.disappearance_days and entry['missing_checks'] >= 1:
                        stats['off_market_new']+=1
                        con.execute('UPDATE profile_listings SET status=?,missing_checks=missing_checks+1 WHERE profile_id=? AND listing_id=?',
                                    ('OFF_MARKET',profile['id'],entry['listing_id']))
                        con.execute('INSERT INTO listing_events(run_id,listing_id,event_type,created_at) VALUES(?,?,?,?)',
                                    (run_id,entry['listing_id'],'OFF_MARKET',now()))
                    else:
                        con.execute('UPDATE profile_listings SET missing_checks=missing_checks+1 WHERE profile_id=? AND listing_id=?',
                                    (profile['id'],entry['listing_id']))
        # Global listing availability should be active if active anywhere, avoiding false sales across search profiles.
        con.execute('''UPDATE listings SET availability=CASE
            WHEN EXISTS (SELECT 1 FROM profile_listings p WHERE p.listing_id=listings.id AND p.status='ACTIVE') THEN 'ACTIVE'
            WHEN EXISTS (SELECT 1 FROM profile_listings p WHERE p.listing_id=listings.id AND p.status='MISSING_UNCONFIRMED') THEN 'MISSING_UNCONFIRMED'
            ELSE 'OFF_MARKET' END WHERE id IN (SELECT listing_id FROM profile_listings WHERE profile_id=?)''',(profile['id'],))
        log_event(con,run_id,'SOURCE','INFO','Zoekprofiel verwerkt',{'profile_id':profile['id'],**stats})
        con.execute('COMMIT')
    except Exception:
        con.execute('ROLLBACK')
        raise
    for listing_id in sorted(candidate_ids):
        state=analyze_listing(con,listing_id,run_id,criteria)
        if state=='SUCCESS':stats['gemini_calls']+=1
        if state=='ERROR':stats['gemini_errors']+=1
        if state=='CACHE_HIT':stats['cache_hits']+=1
    return stats


def execute_run(run_id):
    con=connect()
    try:
        # Minimize long-term retention of full LLM payloads while keeping metadata/audit trail.
        con.execute("UPDATE integration_requests SET request_json=NULL,response_json=NULL,parsed_json=NULL WHERE created_at < datetime('now', ?)",
                    (f'-{settings.retention_days} days',))
        con.execute('UPDATE refresh_runs SET state=?,started_at=? WHERE id=? AND state=?',('RUNNING',now(),run_id,'QUEUED'))
        run=con.execute('SELECT * FROM refresh_runs WHERE id=?',(run_id,)).fetchone()
        if run is None or run['state']!='RUNNING': return
        log_event(con,run_id,'RUN','INFO','Refresh gestart')
        scope=json.loads(run['scope_json'])
        profiles=con.execute('SELECT * FROM search_profiles WHERE enabled=1 ORDER BY title').fetchall()
        if scope!='all':
            allowed=set(scope.get('profile_ids',[]))
            profiles=[p for p in profiles if p['id'] in allowed]
        if not profiles:
            raise RuntimeError('Geen actieve zoekprofielen voor deze run')
        criteria=get_criteria(con)
        totals={'profiles':len(profiles),'profiles_ok':0,'profiles_partial':0,'profiles_failed':0,
                'found':0,'new':0,'price_changes':0,'missing_new':0,'off_market_new':0,
                'observations':0,'gemini_calls':0,'gemini_errors':0,'cache_hits':0,'portals':0,'portal_price_changes':0}
        errors=[]
        for profile in profiles:
            log_event(con,run_id,'PROFILE','INFO',f'Scan gestart: {profile["title"]}')
            try:
                result=scan_profile(con,run_id,profile,criteria)
                for key in totals.keys() & result.keys():
                    totals[key]+=result[key] if isinstance(result[key],int) else 0
                if result['provider_complete']:totals['profiles_ok']+=1
                else:totals['profiles_partial']+=1
            except Exception as exc:
                totals['profiles_failed']+=1
                message=f'{profile["title"]}: {type(exc).__name__}: {str(exc)[:250]}'
                errors.append(message)
                log_event(con,run_id,'PROFILE','ERROR',message)
                logger.warning('Profile scan failed run=%s profile=%s type=%s',run_id,profile['id'],type(exc).__name__)
        if totals['profiles_ok']==totals['profiles'] and not totals['gemini_errors']:
            state='COMPLETE'
        elif totals['profiles_ok'] or totals['profiles_partial']:
            state='PARTIAL'
        else:
            state='FAILED'
        con.execute('UPDATE refresh_runs SET state=?,finished_at=?,summary_json=?,error=? WHERE id=?',
                    (state,now(),dumps(totals),'\n'.join(errors)[:2000] if errors else None,run_id))
        log_event(con,run_id,'RUN','INFO' if state=='COMPLETE' else 'WARN',f'Refresh afgerond: {state}',totals)
    except Exception as exc:
        error=f'{type(exc).__name__}: {str(exc)[:500]}'
        con.execute('UPDATE refresh_runs SET state=?,finished_at=?,error=? WHERE id=?',('FAILED',now(),error,run_id))
        log_event(con,run_id,'RUN','ERROR',error)
        logger.exception('Unexpected refresh failure (run=%s)',run_id)
    finally:
        con.close()


def _loop():
    while not _stop.is_set():
        con=connect()
        try:
            item=con.execute("SELECT id FROM refresh_runs WHERE state='QUEUED' ORDER BY created_at LIMIT 1").fetchone()
        finally:
            con.close()
        if item:
            execute_run(item['id'])
        else:
            _stop.wait(0.5)


def start_worker():
    global _thread
    _stop.clear()
    con=connect()
    try:
        # Recover accepted work after server restart; UNIQUE observations avoid double counting.
        con.execute("UPDATE refresh_runs SET state='QUEUED',started_at=NULL WHERE state='RUNNING'")
    finally:
        con.close()
    _thread=threading.Thread(target=_loop,daemon=True,name='refresh-worker')
    _thread.start()


def stop_worker():
    _stop.set()
    if _thread: _thread.join(timeout=5)
