"""Vul de dev-database met de demo-snapshot en 45 dagen gesimuleerde historie.

Gebruik: python scripts/seed_demo.py [--reset]

Schrijft rechtstreeks via app.db (geen HTTP). Resultaat is reproduceerbaar (random.seed(1)):
- per auto een eerste waarneming op een gespreide datum (een deel stond er al bij de start);
- bij ongeveer een derde één of twee prijsverlagingen;
- twee auto's die verdwenen zijn, één die even weg was en terugkwam;
- één auto die pas bij de laatste controle voor het eerst is gezien.
Alle auto's zijn fictief (DEMO).
"""
import argparse
import json
import random
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dev_server import ROOT, apply_dev_env  # noqa: E402

apply_dev_env()

from app.config import settings  # noqa: E402
from app.db import connect, dumps, init_db, uid  # noqa: E402
from app.extraction import cleaned_text, sha256  # noqa: E402
from app.worker import analyze_listing, external_key, get_criteria  # noqa: E402

DAYS = 45
PROFILE_ID = 'sp_demo_xc90'
SNAPSHOT = ROOT / 'sample_data' / 'xc90_demo_snapshot.json'
TABLES = ['claims', 'integration_requests', 'negotiation_notes', 'listing_events', 'source_detail_attempts',
          'source_price_observations', 'listing_sources', 'price_observations', 'profile_listings', 'run_events',
          'trigger_attempts', 'listings', 'refresh_runs', 'search_profiles']


def iso(moment):
    return moment.isoformat(timespec='seconds')


def plan_cars(ads):
    """Bepaal per auto: eerste dag, prijsverlagingen en afwezige dagen."""
    random.seed(1)
    plans = []
    for ad in ads:
        first = 0 if random.random() < 0.4 else random.randint(1, 35)
        drops = []
        if random.random() < 0.34:
            for _ in range(random.choice((1, 2))):
                day = random.randint(first + 3, DAYS - 1) if first + 3 < DAYS else DAYS - 1
                drops.append((day, random.choice((500, 750, 1000, 1500, 2000, 2500))))
        plans.append({'ad': ad, 'first': first, 'drops': sorted(drops), 'gone': set()})
    # Vaste kenmerken zodat elk scenario in de demo zichtbaar is.
    plans[-1].update(first=DAYS - 1, drops=[])                      # nieuw bij de laatste controle
    plans[1]['drops'] = [(12, 1500), (DAYS - 3, 1000)]               # recent nog verlaagd
    plans[1]['first'] = 0
    plans[4]['gone'] = set(range(24, DAYS))                         # al lang weg: uit het aanbod
    plans[7]['gone'] = set(range(DAYS - 2, DAYS))                   # net weg: niet meer gezien
    plans[9]['gone'] = set(range(18, 23))                           # even weg, daarna terug
    plans[9]['first'] = min(plans[9]['first'], 5)
    for p in plans:
        p['drops'] = [(d, a) for d, a in p['drops'] if d > p['first']]
        p['start_price'] = p['ad']['price_eur'] + sum(a for _, a in p['drops'])
    return plans


def price_on(plan, day):
    return plan['start_price'] - sum(a for d, a in plan['drops'] if d <= day)


def reset(con):
    for table in TABLES:
        con.execute(f'DELETE FROM {table}')


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--reset', action='store_true', help='bestaande gegevens eerst wissen')
    args = parser.parse_args()
    init_db()
    con = connect()
    try:
        if con.execute('SELECT 1 FROM listings LIMIT 1').fetchone():
            if not args.reset:
                sys.exit('De database bevat al auto\'s. Gebruik --reset om opnieuw te beginnen.')
            reset(con)
        seed(con)
    finally:
        con.close()
    print(f'Demo-data geladen in {settings.database_path}')


def seed(con):
    snapshot = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
    plans = plan_cars(snapshot['listings'])
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=DAYS - 1)
    created = iso(datetime.combine(start, time(6, 0), timezone.utc) - timedelta(days=1))
    profile = {'id': PROFILE_ID, 'provider': 'fixture', 'fixture_payload': '{}'}
    con.execute('''INSERT INTO search_profiles(id,title,search_url,provider,fixture_payload,enabled,created_at,updated_at)
                   VALUES(?,?,?,?,?,1,?,?)''',
                (PROFILE_ID, 'Volvo XC90 (demo)', 'https://www.gaspedaal.nl/volvo/xc90?bmin=2025', 'fixture',
                 '{}', created, created))
    ids = {}
    state = {}
    run_id = None
    for day in range(DAYS):
        moment = datetime.combine(start + timedelta(days=day), time(7, 0), timezone.utc)
        ts = iso(moment)
        run_id = uid('rr')
        con.execute('BEGIN')
        con.execute('''INSERT INTO refresh_runs(id,trigger_source,state,scope_json,request_hash,created_at,started_at,
                       finished_at,summary_json) VALUES(?,?,?,?,?,?,?,?,?)''',
                    (run_id, 'HOME_ASSISTANT', 'RUNNING', '"all"', 'seed', ts, ts, None, '{}'))
        stats = {'profiles': 1, 'profiles_ok': 1, 'profiles_partial': 0, 'profiles_failed': 0, 'found': 0, 'new': 0,
                 'price_changes': 0, 'missing_new': 0, 'off_market_new': 0, 'reappeared': 0, 'observations': 0,
                 'gemini_calls': 0, 'gemini_errors': 0, 'cache_hits': 0, 'portals': 0, 'portal_price_changes': 0}
        for plan in plans:
            ad = plan['ad']
            visible = day >= plan['first'] and day not in plan['gone']
            key = ad['external_id']
            if visible:
                stats['found'] += 1
                price = price_on(plan, day)
                if key not in ids:
                    ids[key] = uid('car')
                    text = cleaned_text(ad['title'], ad.get('description', ''))
                    con.execute('''INSERT INTO listings(id,external_id,title,url,year,kilometers,trim,seller,price_eur,
                        description,text_hash,first_seen,last_seen,updated_at,photos_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (ids[key], external_key(profile, {'source': 'IMPORT'}, key), ad['title'], ad.get('url'),
                         ad.get('year'), ad.get('kilometers'), ad.get('trim'), ad.get('seller'), price,
                         ad.get('description', ''), sha256(text), ts, ts, ts, '[]'))
                    con.execute('''INSERT INTO listing_events(run_id,listing_id,event_type,new_price,created_at)
                                   VALUES(?,?,?,?,?)''', (run_id, ids[key], 'FIRST_SEEN', price, ts))
                    con.execute('''INSERT INTO profile_listings(profile_id,listing_id,last_seen,status)
                                   VALUES(?,?,?,'ACTIVE')''', (PROFILE_ID, ids[key], ts))
                    stats['new'] += 1
                    state[key] = {'price': price, 'status': 'ACTIVE'}
                else:
                    old = state[key]
                    if old['status'] != 'ACTIVE':
                        stats['reappeared'] += 1
                        con.execute('''INSERT INTO listing_events(run_id,listing_id,event_type,new_price,created_at)
                                       VALUES(?,?,?,?,?)''', (run_id, ids[key], 'REAPPEARED', price, ts))
                    if price != old['price']:
                        stats['price_changes'] += 1
                        con.execute('''INSERT INTO listing_events(run_id,listing_id,event_type,previous_price,new_price,
                                       created_at) VALUES(?,?,?,?,?,?)''',
                                    (run_id, ids[key], 'PRICE_CHANGED', old['price'], price, ts))
                    con.execute('UPDATE listings SET price_eur=?,last_seen=?,updated_at=? WHERE id=?',
                                (price, ts, ts, ids[key]))
                    con.execute('''UPDATE profile_listings SET last_seen=?,missing_since=NULL,missing_checks=0,
                                   status='ACTIVE' WHERE profile_id=? AND listing_id=?''', (ts, PROFILE_ID, ids[key]))
                    state[key] = {'price': price, 'status': 'ACTIVE'}
                con.execute('''INSERT INTO price_observations(run_id,profile_id,listing_id,price_eur,observed_at)
                               VALUES(?,?,?,?,?)''', (run_id, PROFILE_ID, ids[key], price, ts))
                stats['observations'] += 1
            elif key in state and state[key]['status'] != 'OFF_MARKET':
                entry = con.execute('SELECT * FROM profile_listings WHERE profile_id=? AND listing_id=?',
                                    (PROFILE_ID, ids[key])).fetchone()
                if state[key]['status'] == 'ACTIVE':
                    stats['missing_new'] += 1
                    state[key]['status'] = 'MISSING_UNCONFIRMED'
                    con.execute('''UPDATE profile_listings SET status='MISSING_UNCONFIRMED',missing_since=?,
                                   missing_checks=1 WHERE profile_id=? AND listing_id=?''', (ts, PROFILE_ID, ids[key]))
                    con.execute('''INSERT INTO listing_events(run_id,listing_id,event_type,created_at)
                                   VALUES(?,?,?,?)''', (run_id, ids[key], 'MISSING_UNCONFIRMED', ts))
                else:
                    since = datetime.fromisoformat(entry['missing_since'])
                    if (moment - since).days >= settings.disappearance_days:
                        stats['off_market_new'] += 1
                        state[key]['status'] = 'OFF_MARKET'
                        con.execute('''UPDATE profile_listings SET status='OFF_MARKET',missing_checks=missing_checks+1
                                       WHERE profile_id=? AND listing_id=?''', (PROFILE_ID, ids[key]))
                        con.execute('''INSERT INTO listing_events(run_id,listing_id,event_type,created_at)
                                       VALUES(?,?,?,?)''', (run_id, ids[key], 'OFF_MARKET', ts))
                    else:
                        con.execute('''UPDATE profile_listings SET missing_checks=missing_checks+1
                                       WHERE profile_id=? AND listing_id=?''', (PROFILE_ID, ids[key]))
        done = iso(moment + timedelta(seconds=40))
        con.execute("UPDATE refresh_runs SET state='COMPLETE',finished_at=?,summary_json=? WHERE id=?",
                    (done, dumps(stats), run_id))
        con.execute('''INSERT INTO run_events(run_id,stage,level,message,metrics_json,created_at)
                       VALUES(?,?,?,?,?,?)''', (run_id, 'RUN', 'INFO', 'Controle afgerond: geslaagd', dumps(stats), done))
        con.execute('COMMIT')
    con.execute('''UPDATE listings SET availability=COALESCE((SELECT CASE
        WHEN SUM(p.status='ACTIVE')>0 THEN 'ACTIVE'
        WHEN SUM(p.status='MISSING_UNCONFIRMED')>0 THEN 'MISSING_UNCONFIRMED'
        ELSE 'OFF_MARKET' END FROM profile_listings p WHERE p.listing_id=listings.id),'ACTIVE')''')
    # De JSON-import van het profiel weerspiegelt de huidige stand, zodat "Nu controleren" daarop doorgaat.
    current = []
    for plan in plans:
        if state.get(plan['ad']['external_id'], {}).get('status') == 'ACTIVE':
            current.append({**plan['ad'], 'price_eur': price_on(plan, DAYS - 1)})
    con.execute('UPDATE search_profiles SET fixture_payload=? WHERE id=?',
                (dumps({'complete': True, 'metadata': {}, 'listings': current}), PROFILE_ID))
    criteria = get_criteria(con)
    for listing_id in ids.values():
        analyze_listing(con, listing_id, run_id, criteria)


if __name__ == '__main__':
    main()
