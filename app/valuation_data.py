"""Gegevens ophalen voor app/valuation.py (die zelf alleen pure functies bevat)."""
from app.insights import listing_insights
from app.valuation import market_position, valuation

CAR_COLUMNS = ('id,title,price_eur,year,kilometers,trim,first_seen,last_seen,availability,'
               'my_opening,my_target,my_max')


def memberships(con):
    """(zoekopdrachten per auto, actieve auto's per zoekopdracht)."""
    profiles_of, active_in = {}, {}
    for lid, pid, status in con.execute('SELECT listing_id,profile_id,status FROM profile_listings'):
        profiles_of.setdefault(lid, set()).add(pid)
        if status == 'ACTIVE':
            active_in.setdefault(pid, set()).add(lid)
    return profiles_of, active_in


def _rows(con, ids):
    if not ids:
        return {}
    marks = ','.join('?' * len(ids))
    return {r['id']: dict(r) for r in con.execute(f'SELECT {CAR_COLUMNS} FROM listings WHERE id IN ({marks})', list(ids))}


def pool_ids(listing_id, profiles_of, active_in):
    """Auto's die te koop staan in dezelfde zoekopdracht(en), zonder de auto zelf."""
    ids = set()
    for pid in profiles_of.get(listing_id, ()):
        ids |= active_in.get(pid, set())
    ids.discard(listing_id)
    return ids


def budget_for(con, listing_id):
    """Laagste budget van de zoekopdrachten waarin de auto voorkomt (voorzichtigste grens)."""
    row = con.execute('''SELECT MIN(p.budget_eur) FROM search_profiles p JOIN profile_listings pl ON pl.profile_id=p.id
                         WHERE pl.listing_id=? AND p.budget_eur IS NOT NULL''', (listing_id,)).fetchone()
    return row[0] if row else None


def _scores(con, ids, profile_id):
    """Matchscore per auto volgens de wensen van de zoekopdracht; anders de hoogste score van de auto."""
    out = {}
    for lid, pid, score in con.execute('SELECT listing_id,profile_id,score_total FROM profile_listings'):
        if lid in ids and (pid == profile_id or lid not in out):
            out[lid] = score
    return out


def valuation_for(con, listing_id, criteria, profile_id=None):
    """Waardering volgens de wensen van één zoekopdracht (match, uitrusting en optiepremie)."""
    profiles_of, active_in = memberships(con)
    ids = pool_ids(listing_id, profiles_of, active_in)
    rows = _rows(con, ids | {listing_id})
    scores = _scores(con, ids | {listing_id}, profile_id)
    for lid, row in rows.items():
        row['score_total'] = scores.get(lid)
    car = rows.pop(listing_id)
    extra = listing_insights(con, [car] + list(rows.values()))
    car.update(extra.get(listing_id, {}))
    pool = []
    claims = {}
    if rows:
        marks = ','.join('?' * len(rows))
        for lid, key, status in con.execute(f'''SELECT listing_id,criterion_key,status FROM claims
                                                WHERE profile_id=? AND listing_id IN ({marks})''',
                                             [profile_id, *rows]):
            claims.setdefault(lid, {})[key] = status
    for lid, row in rows.items():
        row.update(extra.get(lid, {}))
        row['claims'] = claims.get(lid, {})
        pool.append(row)
    car['price_drops'] = [{'amount': r['previous_price'] - r['new_price'], 'at': r['created_at']}
                          for r in con.execute('''SELECT previous_price,new_price,created_at FROM listing_events
                              WHERE listing_id=? AND event_type='PRICE_CHANGED' AND new_price<previous_price
                              ORDER BY created_at,id''', (listing_id,))]
    own = {'opening': car.pop('my_opening'), 'target': car.pop('my_target'), 'limit': car.pop('my_max')}
    car_claims = [dict(r) for r in con.execute('''SELECT cr.label,COALESCE(c.status,'UNKNOWN') AS status
        FROM criteria cr LEFT JOIN claims c ON c.criterion_key=cr.key AND c.profile_id=cr.profile_id AND c.listing_id=?
        WHERE cr.profile_id=? AND cr.enabled=1 ORDER BY cr.group_name,cr.weight DESC''', (listing_id, profile_id))]
    sources = [dict(r) for r in con.execute('SELECT site,price_eur FROM listing_sources WHERE listing_id=?',
                                            (listing_id,))]
    return valuation(car, pool, budget=budget_for(con, listing_id), own=own, claims=car_claims, sources=sources,
                     criteria=criteria)


def market_positions(con, items):
    """Verschil met de middenwaarde per auto die te koop staat (voor de aanbodlijst)."""
    profiles_of, active_in = memberships(con)
    wanted = [i for i in items if i.get('availability') == 'ACTIVE']
    all_ids = set().union(*active_in.values()) if active_in else set()
    rows = _rows(con, all_ids | {i['id'] for i in wanted})
    out = {}
    for item in wanted:
        car = rows.get(item['id'])
        if not car:
            continue
        pool = [rows[i] for i in pool_ids(item['id'], profiles_of, active_in) if i in rows]
        out[item['id']] = market_position(car, pool)
    return out
