"""Afgeleide gegevens per auto: prijsverloop, tijd in beeld, nieuw en 'al te koop bij de start'.

Alles is afgeleid uit prijsobservaties en gebeurtenissen; er wordt niets opgeslagen of gewijzigd.
"""
import json
from datetime import datetime, timezone


def _parse(ts):
    moment = datetime.fromisoformat(ts)
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def days_between(start, end):
    return max(0, int((_parse(end) - _parse(start)).total_seconds() // 86400))


def profile_run_bounds(con, profile_id=None):
    """Per zoekopdracht de eerste en de laatste controle waarin prijzen zijn vastgelegd (mislukte controles niet)."""
    # Ordered by the first observation id of each check: timestamps have whole seconds and may tie.
    query = '''SELECT profile_id, run_id, MIN(id) AS seq FROM price_observations
               {} GROUP BY profile_id, run_id'''.format('WHERE profile_id=?' if profile_id else '')
    first, last = {}, {}
    for pid, rid, seq in con.execute(query, (profile_id,) if profile_id else ()):
        if pid not in first or seq < first[pid][1]:
            first[pid] = (rid, seq)
        if pid not in last or seq > last[pid][1]:
            last[pid] = (rid, seq)
    return {p: v[0] for p, v in first.items()}, {p: v[0] for p, v in last.items()}


def listing_insights(con, listing_rows, profile_id=None, now=None):
    """Extra velden per auto (dict per id). `listing_rows` heeft id, price_eur, first_seen, last_seen, availability."""
    now = now or datetime.now(timezone.utc).isoformat(timespec='seconds')
    ids = {r['id'] for r in listing_rows}
    if not ids:
        return {}
    first_run, last_run = profile_run_bounds(con, profile_id)
    observations = {}
    for lid, pid, rid, price, at in con.execute('''SELECT listing_id, profile_id, run_id, price_eur, observed_at
                                                   FROM price_observations ORDER BY observed_at, id'''):
        if lid in ids:
            observations.setdefault(lid, []).append((pid, rid, price, at))
    events = {}
    for lid, kind, prev, new, at in con.execute('''SELECT listing_id, event_type, previous_price, new_price, created_at
            FROM listing_events WHERE event_type IN ('PRICE_CHANGED','REAPPEARED') ORDER BY created_at, id'''):
        if lid in ids:
            events.setdefault(lid, []).append((kind, prev, new, at))
    providers = dict(con.execute('SELECT listing_id, COUNT(*) FROM listing_sources GROUP BY listing_id').fetchall())
    result = {}
    for row in listing_rows:
        lid = row['id']
        obs = observations.get(lid, [])
        scoped = [o for o in obs if not profile_id or o[0] == profile_id]
        first_price = obs[0][2] if obs else row['price_eur']
        changes = [e for e in events.get(lid, []) if e[0] == 'PRICE_CHANGED']
        drops = [e for e in changes if e[1] is not None and e[2] is not None and e[2] < e[1]]
        reappeared = [e for e in events.get(lid, []) if e[0] == 'REAPPEARED']
        gone = row['availability'] != 'ACTIVE'
        seen_since_start = is_new = False
        if scoped:
            pid, rid = scoped[0][0], scoped[0][1]
            seen_since_start = first_run.get(pid) == rid
            is_new = last_run.get(pid) == rid and first_run.get(pid) != rid
        result[lid] = {
            'first_price': first_price,
            'price_change_total': row['price_eur'] - first_price,
            'price_drop_count': len(drops),
            'last_price_change_at': changes[-1][3] if changes else None,
            'last_drop_at': drops[-1][3] if drops else None,
            'reappeared_at': reappeared[-1][3] if reappeared else None,
            'days_tracked': days_between(row['first_seen'], row['last_seen'] if gone else now),
            'seen_since_start': seen_since_start,
            'is_new': is_new,
            'provider_count': providers.get(lid, 0),
            'observations': len(obs),
        }
    return result


def first_photo(photos_json):
    try:
        photos = json.loads(photos_json or '[]')
    except ValueError:
        return None
    return photos[0] if photos else None
