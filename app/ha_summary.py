"""Samenvatting voor Home Assistant (WP-14A): wat leverde de laatste controle op? De app stuurt zelf niets;
Home Assistant leest dit op en bepaalt of en hoe er een (gebundelde) melding komt."""
from app import changes as run_changes
from app.scope import scored_listings


def _euro(value):
    return '€ ' + f'{int(round(value)):,}'.replace(',', '.') if value is not None else '—'


def _budgets(con):
    """Per auto het laagste budget van de zoekopdrachten waarin hij voorkomt."""
    out = {}
    for lid, budget in con.execute('''SELECT pl.listing_id,p.budget_eur FROM profile_listings pl
                                      JOIN search_profiles p ON p.id=pl.profile_id WHERE p.budget_eur IS NOT NULL'''):
        out[lid] = min(budget, out.get(lid, budget))
    return out


def _item(x, car, previous=None):
    return {'id': x['listing_id'], 'title': x['title'], 'price_eur': x['new_price'] or x['price_eur'],
            'previous_price': previous, 'match': car.get('score_total') if car else None,
            'status': {'MATCH': 'Voldoet', 'REJECTED': 'Valt af'}.get((car or {}).get('eligibility'), 'Nog te controleren'),
            'link': f"/#/auto/{x['listing_id']}"}


def _sentence(run):
    if run is None:
        return 'Nog geen controle uitgevoerd.'
    if run['state'] == 'FAILED':
        return 'Laatste controle mislukt. Er is niets als verdwenen gemarkeerd.'
    s = run['summary']
    parts = [f"{s.get('found', 0)} auto's"]
    if s.get('new'):
        parts.append(f"{s['new']} nieuw")
    if s.get('price_changes'):
        parts.append(f"{s['price_changes']} prijswijziging{'en' if s['price_changes'] != 1 else ''}")
    if s.get('missing_new'):
        parts.append(f"{s['missing_new']} niet meer gezien")
    word = 'geslaagd' if run['state'] == 'COMPLETE' else 'gedeeltelijk gelukt'
    return f"Controle {word}: {', '.join(parts)}."


def summary(con):
    status = run_changes.status(con)
    last = status['last_run']
    base = next((r for r in run_changes.runs_newest_first(con) if r['state'] in ('COMPLETE', 'PARTIAL')), None)
    groups = run_changes.changes(con, None, base['id'])['groups'] if base else {}
    cars = {c['id']: c for c in scored_listings(con, 'l.id,l.title,l.price_eur,l.availability,l.favorite')}
    budgets = _budgets(con)
    new_matches = [_item(x, cars.get(x['listing_id'])) for x in groups.get('new', [])
                   if (cars.get(x['listing_id']) or {}).get('eligibility') == 'MATCH']
    shortlist_drops = [_item(x, cars.get(x['listing_id']), x['previous_price']) for x in groups.get('price_down', [])
                       if (cars.get(x['listing_id']) or {}).get('favorite')]
    within = []
    for x in groups.get('price_down', []):
        b = budgets.get(x['listing_id'])
        if b is not None and x['new_price'] <= b < x['previous_price']:
            within.append(_item(x, cars.get(x['listing_id']), x['previous_price']))
    for x in groups.get('new', []):
        b = budgets.get(x['listing_id'])
        if b is not None and (x['new_price'] or x['price_eur']) <= b:
            within.append(_item(x, cars.get(x['listing_id'])))
    active = [c for c in cars.values() if c['availability'] == 'ACTIVE']
    lines = [_sentence(last)]
    if new_matches:
        lines.append('Nieuw en voldoet: ' + '; '.join(f"{i['title']} ({_euro(i['price_eur'])})" for i in new_matches))
    if shortlist_drops:
        lines.append('Prijsverlaging op je shortlist: ' + '; '.join(
            f"{i['title']} {_euro(i['previous_price'])} → {_euro(i['price_eur'])}" for i in shortlist_drops))
    if within:
        lines.append('Binnen budget gekomen: ' + '; '.join(f"{i['title']} ({_euro(i['price_eur'])})" for i in within))
    return {
        'last_run': {'id': last['id'], 'state': last['state'], 'finished_at': last['finished_at'],
                     'sentence': _sentence(last)} if last else None,
        'based_on_run_id': base['id'] if base else None,
        'counts': {'for_sale': len(active), 'matches': sum(1 for c in active if c.get('eligibility') == 'MATCH'),
                   'shortlist': sum(1 for c in cars.values() if c.get('favorite')),
                   'new': len(groups.get('new', [])), 'price_drops': len(groups.get('price_down', [])),
                   'missing': len(groups.get('missing', []))},
        'new_matches': new_matches, 'shortlist_price_drops': shortlist_drops, 'within_budget': within,
        'has_news': bool(new_matches or shortlist_drops or within or (last and last['state'] == 'FAILED')),
        'message': '\n'.join(lines),
        'note': 'Vraagprijzen, geen verkoopprijzen.',
    }
