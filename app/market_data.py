"""Gegevens ophalen voor het marktoverzicht; het rekenwerk staat in app/market.py."""
from datetime import datetime, timedelta, timezone

from app.insights import listing_insights
from app.market import (daily_last, daily_stats, drop_stats, km_classes, median_or_none, price_index, summary,
                        trend_sentence, weekly_flow)
from app.valuation_data import market_positions

CANDIDATE = ('MATCH', 'UNVERIFIED', 'REVIEW')


def _scope(con, profile_id):
    columns = '''l.id,l.title,l.price_eur,l.year,l.kilometers,l.eligibility,l.score_total,l.score_potential,
                 l.first_seen,l.last_seen,l.analyzed_hash,TRIM(l.description)!='' AS has_text'''
    if profile_id:
        rows = con.execute(f'''SELECT {columns},pl.status AS availability FROM listings l
                              JOIN profile_listings pl ON pl.listing_id=l.id WHERE pl.profile_id=?''', (profile_id,))
    else:
        rows = con.execute(f'SELECT {columns},l.availability FROM listings l')
    return [dict(r) for r in rows]


def _budget(con, profile_id):
    if profile_id:
        row = con.execute('SELECT budget_eur FROM search_profiles WHERE id=?', (profile_id,)).fetchone()
        return row[0] if row else None
    budgets = {r[0] for r in con.execute('SELECT budget_eur FROM search_profiles WHERE archived_at IS NULL')}
    return budgets.pop() if len(budgets) == 1 else None


def market_overview(con, profile_id=None, days=None, today=None):
    today = today or datetime.now(timezone.utc).date()
    cutoff = (today - timedelta(days=days - 1)).isoformat() if days else None
    items = _scope(con, profile_id)
    ids = {i['id'] for i in items}
    extra = listing_insights(con, items, profile_id)
    for i in items:
        i.update(extra.get(i['id'], {}))
    active = [i for i in items if i['availability'] == 'ACTIVE']
    gone = [i for i in items if i['availability'] in ('MISSING_UNCONFIRMED', 'OFF_MARKET')]
    budget = _budget(con, profile_id)

    # 1. Gangbare vraagprijs (echte mediaan, B6)
    asking = summary([i['price_eur'] for i in active])
    asking_candidates = summary([i['price_eur'] for i in active if i['eligibility'] in CANDIDATE])

    # 2. Kansen: t.o.v. markt, binnen budget eerst
    positions = market_positions(con, active)
    candidates = []
    for i in active:
        if i['eligibility'] not in CANDIDATE:
            continue
        p = positions.get(i['id']) or {}
        candidates.append({'id': i['id'], 'title': i['title'], 'price_eur': i['price_eur'],
                           'kilometers': i['kilometers'], 'year': i['year'], 'eligibility': i['eligibility'],
                           'score_total': i['score_total'], 'score_potential': i['score_potential'],
                           'has_text': i['has_text'], 'analyzed_hash': i['analyzed_hash'],
                           'market_diff': p.get('difference'), 'market_n': p.get('n'),
                           'within_budget': budget is not None and i['price_eur'] <= budget})
    candidates.sort(key=lambda c: (not c['within_budget'] if budget else 0,
                                   c['market_diff'] if c['market_diff'] is not None else float('inf'), c['price_eur']))

    # 3. Prijs tegen km
    scatter = [{'id': i['id'], 'title': i['title'], 'kilometers': i['kilometers'], 'price_eur': i['price_eur'],
                'eligibility': i['eligibility']} for i in active if i['kilometers'] is not None]

    # 4. Aanbod, in- en uitstroom, tijd in beeld
    marks = ','.join('?' * len(ids)) or "''"
    events = con.execute(f'''SELECT created_at,event_type,listing_id FROM listing_events
        WHERE event_type IN ('FIRST_SEEN','MISSING_UNCONFIRMED') AND listing_id IN ({marks})
        {'AND created_at>=?' if cutoff else ''} ORDER BY created_at,id''',
        [*ids, *([cutoff] if cutoff else [])]).fetchall() if ids else []
    obs_query = 'SELECT substr(observed_at,1,10),listing_id,price_eur FROM price_observations'
    params = []
    conditions = []
    if profile_id:
        conditions.append('profile_id=?')
        params.append(profile_id)
    observations = con.execute(obs_query + (' WHERE ' + ' AND '.join(conditions) if conditions else '')
                               + ' ORDER BY observed_at,id', params).fetchall()
    first_day = observations[0][0] if observations else None
    period_obs = [o for o in observations if not cutoff or o[0] >= cutoff]
    start = cutoff or first_day or today.isoformat()
    flow = weekly_flow([(e[0], e[1], e[2]) for e in events], start, today.isoformat())
    in_view_active = median_or_none([i['days_tracked'] for i in active])
    in_view_gone = median_or_none([i['days_tracked'] for i in gone])

    # 5. Prijsverlagingen in de periode
    drops = con.execute(f'''SELECT listing_id,created_at,previous_price,new_price FROM listing_events
        WHERE event_type='PRICE_CHANGED' AND listing_id IN ({marks}) {'AND created_at>=?' if cutoff else ''}
        ORDER BY created_at,id''', [*ids, *([cutoff] if cutoff else [])]).fetchall() if ids else []
    in_period = [i for i in items if not cutoff or i['last_seen'][:10] >= cutoff]
    drop = drop_stats(in_period, [tuple(d) for d in drops], first_day)

    # 7. Markt door de tijd
    daily = daily_last(period_obs)
    stats = daily_stats(daily)
    index = price_index(daily)
    within = None
    if budget is not None:
        series = [{'date': d, 'count': sum(1 for p in prices.values() if p <= budget), 'n': len(prices)}
                  for d, prices in daily.items()]
        within = {'budget': budget, 'count': sum(1 for i in active if i['price_eur'] <= budget),
                  'match': sum(1 for i in active if i['price_eur'] <= budget and i['eligibility'] == 'MATCH'),
                  'n': len(active), 'series': series}

    return {
        'profile_id': profile_id, 'days': days, 'period_start': start, 'tracking_since': first_day,
        'for_sale': len(active), 'with_text': sum(1 for i in active if i['has_text']),
        'matches': sum(1 for i in active if i['eligibility'] == 'MATCH'),
        'asking': asking, 'asking_candidates': asking_candidates,
        'opportunities': candidates[:5], 'budget': budget, 'within_budget': within,
        'scatter': scatter, 'km_classes': km_classes(active),
        'flow': flow, 'in_view': {'active': in_view_active, 'gone': in_view_gone},
        'drops': drop,
        'timeline': {'days': stats, 'index': index, 'sentence': trend_sentence(stats, index),
                     'measuring_days': len(stats)},
    }
