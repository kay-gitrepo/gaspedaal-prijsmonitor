"""Vul de dev-database met de demo-snapshot en 45 dagen gesimuleerde historie.

Gebruik: python scripts/seed_demo.py [--reset]

Schrijft rechtstreeks via app.db (geen HTTP). Resultaat is reproduceerbaar (random.seed(1)):
- per auto een eerste waarneming op een gespreide datum (een deel stond er al bij de start);
- bij ongeveer een derde één of twee prijsverlagingen;
- twee auto's die verdwenen zijn, één die even weg was en terugkwam;
- één auto die pas bij de laatste controle voor het eerst is gezien;
- twee zoekopdrachten die elkaar deels overlappen (alle auto's, en alleen auto's vanaf 45.000 km).
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
from app.db import connect, dumps, init_db, insert_default_criteria, uid  # noqa: E402
from app.extraction import cleaned_text, sha256  # noqa: E402
from app.worker import analyze_listing, external_key, get_criteria  # noqa: E402

DAYS = 45
SNAPSHOT = ROOT / 'sample_data' / 'xc90_demo_snapshot.json'
PROFILES = [
    {'id': 'sp_demo_xc90', 'title': 'Volvo XC90 (demo)', 'budget': 72500,
     'url': 'https://www.gaspedaal.nl/volvo/xc90?bmin=2025', 'accepts': lambda ad: True},
    {'id': 'sp_demo_xc90_km', 'title': 'Volvo XC90 vanaf 45.000 km (demo)', 'budget': None,
     'url': 'https://www.gaspedaal.nl/volvo/xc90?bmin=2025&kmmin=45000',
     'accepts': lambda ad: (ad.get('kilometers') or 0) >= 45000},
]
TABLES = ['claims', 'criterion_suggestions', 'integration_requests', 'negotiation_notes', 'listing_events', 'source_detail_attempts',
          'source_price_observations', 'listing_sources', 'price_observations', 'profile_listings', 'run_events',
          'trigger_attempts', 'listings', 'refresh_runs', 'search_profiles']


def iso(moment):
    return moment.isoformat(timespec='seconds')


def plan_cars(ads):
    """Bepaal per auto: eerste dag, prijsverlagingen en afwezige dagen."""
    random.seed(1)
    plans = []
    for ad in ads:
        # Vaste spreiding rond de lineaire demoprijs, zodat marktband en onderhandelen iets laten zien.
        ad['price_eur'] += random.choice(range(-2500, 2501, 250))
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
    con.execute('DELETE FROM criteria')


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


def empty_stats():
    return {'profiles': len(PROFILES), 'profiles_ok': len(PROFILES), 'profiles_partial': 0, 'profiles_failed': 0,
            'found': 0, 'new': 0, 'price_changes': 0, 'missing_new': 0, 'off_market_new': 0, 'reappeared': 0,
            'skipped_invalid': 0, 'out_of_scope_new': 0, 'observations': 0, 'gemini_calls': 0, 'gemini_errors': 0,
            'cache_hits': 0, 'portals': 0, 'portal_price_changes': 0}


def seed(con):
    snapshot = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
    for i in (2, 5, 10):  # zoals bij Gaspedaal: geen advertentietekst
        snapshot['listings'][i]['description'] = ''
    plans = plan_cars(snapshot['listings'])
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=DAYS - 1)
    created = iso(datetime.combine(start, time(6, 0), timezone.utc) - timedelta(days=1))
    for p in PROFILES:
        con.execute('''INSERT INTO search_profiles(id,title,search_url,provider,fixture_payload,enabled,created_at,
                       updated_at,budget_eur) VALUES(?,?,?,?,?,1,?,?,?)''',
                    (p['id'], p['title'], p['url'], 'fixture', '{}', created, created, p['budget']))
        insert_default_criteria(con, p['id'])
    # Wensen per zoekopdracht: in de tweede zoekopdracht is een trekhaak mooi meegenomen, geen eis.
    con.execute('''UPDATE criteria SET group_name='NICE_TO_HAVE',weight=3 WHERE profile_id=? AND key='towbar' ''',
                (PROFILES[1]['id'],))
    ids = {}
    price_now = {}
    status = {}          # (profiel, auto) -> status in die zoekopdracht
    missing_since = {}
    run_id = None
    for day in range(DAYS):
        moment = datetime.combine(start + timedelta(days=day), time(7, 0), timezone.utc)
        ts = iso(moment)
        run_id = uid('rr')
        con.execute('BEGIN')
        con.execute('''INSERT INTO refresh_runs(id,trigger_source,state,scope_json,request_hash,created_at,started_at,
                       finished_at,summary_json) VALUES(?,?,?,?,?,?,?,?,?)''',
                    (run_id, 'HOME_ASSISTANT', 'RUNNING', '"all"', 'seed', ts, ts, None, '{}'))
        stats = empty_stats()
        per_profile = {p['id']: {'state': 'COMPLETE', 'found': 0, 'new': 0} for p in PROFILES}
        for plan in plans:
            ad = plan['ad']
            key = ad['external_id']
            visible = day >= plan['first'] and day not in plan['gone']
            price = price_on(plan, day)
            if visible:
                if key not in ids:
                    ids[key] = uid('car')
                    text = cleaned_text(ad['title'], ad.get('description', ''))
                    con.execute('''INSERT INTO listings(id,external_id,title,url,year,kilometers,trim,seller,price_eur,
                        description,text_hash,first_seen,last_seen,updated_at,photos_json)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (ids[key], external_key({}, {'source': 'IMPORT'}, key), ad['title'], ad.get('url'),
                         ad.get('year'), ad.get('kilometers'), ad.get('trim'), ad.get('seller'), price,
                         ad.get('description', ''), sha256(text), ts, ts, ts, '[]'))
                    con.execute('''INSERT INTO listing_events(run_id,listing_id,event_type,new_price,created_at)
                                   VALUES(?,?,?,?,?)''', (run_id, ids[key], 'FIRST_SEEN', price, ts))
                    stats['new'] += 1
                else:
                    if price != price_now[key]:
                        stats['price_changes'] += 1
                        con.execute('''INSERT INTO listing_events(run_id,listing_id,event_type,previous_price,new_price,
                                       created_at) VALUES(?,?,?,?,?,?)''',
                                    (run_id, ids[key], 'PRICE_CHANGED', price_now[key], price, ts))
                    con.execute('UPDATE listings SET price_eur=?,last_seen=?,updated_at=? WHERE id=?',
                                (price, ts, ts, ids[key]))
                price_now[key] = price
                stats['found'] += 1
            events_done = False
            for p in PROFILES:
                if not p['accepts'](ad) or key not in ids:
                    continue
                pk = (p['id'], key)
                if visible:
                    per_profile[p['id']]['found'] += 1
                    if pk not in status:
                        per_profile[p['id']]['new'] += 1
                        con.execute('''INSERT INTO profile_listings(profile_id,listing_id,last_seen,status)
                                       VALUES(?,?,?,'ACTIVE')''', (p['id'], ids[key], ts))
                    else:
                        if status[pk] != 'ACTIVE' and not events_done:
                            stats['reappeared'] += 1
                            con.execute('''INSERT INTO listing_events(run_id,listing_id,event_type,new_price,created_at)
                                           VALUES(?,?,?,?,?)''', (run_id, ids[key], 'REAPPEARED', price, ts))
                            events_done = True
                        con.execute('''UPDATE profile_listings SET last_seen=?,missing_since=NULL,missing_checks=0,
                                       status='ACTIVE' WHERE profile_id=? AND listing_id=?''', (ts, p['id'], ids[key]))
                    status[pk] = 'ACTIVE'
                    con.execute('''INSERT INTO price_observations(run_id,profile_id,listing_id,price_eur,observed_at)
                                   VALUES(?,?,?,?,?)''', (run_id, p['id'], ids[key], price, ts))
                    stats['observations'] += 1
                elif pk in status and status[pk] != 'OFF_MARKET':
                    if status[pk] == 'ACTIVE':
                        status[pk] = 'MISSING_UNCONFIRMED'
                        missing_since[pk] = moment
                        con.execute('''UPDATE profile_listings SET status='MISSING_UNCONFIRMED',missing_since=?,
                                       missing_checks=1 WHERE profile_id=? AND listing_id=?''', (ts, p['id'], ids[key]))
                        if not events_done:
                            stats['missing_new'] += 1
                            con.execute('''INSERT INTO listing_events(run_id,listing_id,event_type,created_at)
                                           VALUES(?,?,?,?)''', (run_id, ids[key], 'MISSING_UNCONFIRMED', ts))
                            events_done = True
                    elif (moment - missing_since[pk]).days >= settings.disappearance_days:
                        status[pk] = 'OFF_MARKET'
                        con.execute('''UPDATE profile_listings SET status='OFF_MARKET',missing_checks=missing_checks+1
                                       WHERE profile_id=? AND listing_id=?''', (p['id'], ids[key]))
                        if not events_done:
                            stats['off_market_new'] += 1
                            con.execute('''INSERT INTO listing_events(run_id,listing_id,event_type,created_at)
                                           VALUES(?,?,?,?)''', (run_id, ids[key], 'OFF_MARKET', ts))
                            events_done = True
                    else:
                        con.execute('''UPDATE profile_listings SET missing_checks=missing_checks+1
                                       WHERE profile_id=? AND listing_id=?''', (p['id'], ids[key]))
        stats['per_profile'] = per_profile
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
    # De JSON-import van elk profiel weerspiegelt de huidige stand, zodat "Nu controleren" daarop doorgaat.
    for p in PROFILES:
        current = [{**plan['ad'], 'price_eur': price_on(plan, DAYS - 1)} for plan in plans
                   if status.get((p['id'], plan['ad']['external_id'])) == 'ACTIVE']
        con.execute('UPDATE search_profiles SET fixture_payload=? WHERE id=?',
                    (dumps({'complete': True, 'metadata': {}, 'listings': current}), p['id']))
    for p in PROFILES:
        criteria = get_criteria(con, p['id'])
        for (listing_id,) in con.execute('SELECT listing_id FROM profile_listings WHERE profile_id=?',
                                         (p['id'],)).fetchall():
            analyze_listing(con, p['id'], listing_id, run_id, criteria)


if __name__ == '__main__':
    main()
