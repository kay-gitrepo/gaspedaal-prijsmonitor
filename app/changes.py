"""Actualiteit van de controles en 'wat is er veranderd' per controle (alleen lezen)."""
import json

FINISHED = ('COMPLETE', 'PARTIAL', 'FAILED')
EVENT_GROUP = {'FIRST_SEEN': 'new', 'MISSING_UNCONFIRMED': 'missing', 'OFF_MARKET': 'off_market',
               'REAPPEARED': 'reappeared'}


def is_check(scope_json):
    """Een herbeoordeling zonder ophalen telt niet als controle van het aanbod."""
    scope = json.loads(scope_json or '"all"')
    return not (isinstance(scope, dict) and ('analyze_listing_ids' in scope or 'analyze' in scope))


def covers(scope_json, profile_id):
    scope = json.loads(scope_json or '"all"')
    return scope == 'all' or profile_id in (scope.get('profile_ids') or [])


def run_brief(row):
    if row is None:
        return None
    return {'id': row['id'], 'state': row['state'], 'trigger_source': row['trigger_source'],
            'created_at': row['created_at'], 'started_at': row['started_at'], 'finished_at': row['finished_at'],
            'summary': json.loads(row['summary_json'] or '{}')}


def runs_newest_first(con, profile_id=None, limit=500):
    rows = con.execute('SELECT * FROM refresh_runs ORDER BY rowid DESC LIMIT ?', (limit,)).fetchall()
    return [r for r in rows if is_check(r['scope_json']) and (not profile_id or covers(r['scope_json'], profile_id))]


def status(con):
    """Laatste afgeronde controle, laatste geslaagde controle en een eventueel lopende controle."""
    runs = runs_newest_first(con)
    last = next((r for r in runs if r['state'] in FINISHED), None)
    success = next((r for r in runs if r['state'] == 'COMPLETE'), None)
    running = next((r for r in runs if r['state'] in ('QUEUED', 'RUNNING')), None)
    return {'last_run': run_brief(last), 'last_success': run_brief(success), 'running': run_brief(running),
            'stale_after_hours': 36}


def changes(con, profile_id=None, run_id=None):
    """Gebeurtenissen van één controle, gegroepeerd: nieuw, prijs omlaag/omhoog, niet meer gezien, weg, terug."""
    if run_id:
        run = con.execute('SELECT * FROM refresh_runs WHERE id=?', (run_id,)).fetchone()
    else:
        run = next((r for r in runs_newest_first(con, profile_id) if r['state'] == 'COMPLETE'), None)
    groups = {k: [] for k in ('new', 'price_down', 'price_up', 'missing', 'off_market', 'reappeared')}
    if run is None:
        return {'run': None, 'groups': groups}
    params = [run['id']]
    member = ''
    if profile_id:
        member = 'AND EXISTS (SELECT 1 FROM profile_listings pl WHERE pl.listing_id=e.listing_id AND pl.profile_id=?)'
        params.append(profile_id)
    rows = con.execute(f'''SELECT e.event_type,e.previous_price,e.new_price,e.created_at,l.id,l.title,l.price_eur,
        l.year,l.kilometers FROM listing_events e JOIN listings l ON l.id=e.listing_id
        WHERE e.run_id=? {member} ORDER BY e.id''', params).fetchall()
    seen = set()
    for r in rows:
        if r['event_type'] == 'PRICE_CHANGED':
            group = 'price_down' if r['new_price'] < r['previous_price'] else 'price_up'
        else:
            group = EVENT_GROUP.get(r['event_type'])
        # The same car can be reported once per search; show it once per group.
        if not group or (group, r['id']) in seen:
            continue
        seen.add((group, r['id']))
        groups[group].append({'listing_id': r['id'], 'title': r['title'], 'year': r['year'],
                              'kilometers': r['kilometers'], 'price_eur': r['price_eur'],
                              'previous_price': r['previous_price'], 'new_price': r['new_price'],
                              'at': r['created_at']})
    return {'run': run_brief(run), 'groups': groups}
