"""Marktwaarde en onderhandelingspositie (WP-10). Alleen pure functies: invoer zijn dicts, geen database.

Uitgangspunten
- Vergelijkingspool: auto's die te koop staan in dezelfde zoekopdracht(en) als de gekozen auto, zonder de auto zelf.
- Drie niveaus van streng naar ruim; het eerste niveau met n >= 8 wordt gebruikt, anders het ruimste.
- Kilometercorrectie (Theil–Sen) alleen bij n >= 8; een positieve helling wordt 0.
- n >= 8: band P25–P75 van gecorrigeerde prijzen, zekerheid "redelijk"; 5 <= n < 8: zonder correctie, "laag";
  n < 5: geen marktwaarde.
- Uitrusting wordt niet in euro's gecorrigeerd. Alles is gebaseerd op vraagprijzen, niet op verkoopprijzen.
"""
import re
from datetime import datetime, timezone
from math import ceil, floor

NOISE = {'aut', 'automaat', 'awd', '4wd', '7p', '5p', 'pk', 'kw'}
LEVELS = [
    (1, {'years': 1, 'km': 20000, 'trim': 0.5}),
    (2, {'years': 1, 'km': 30000, 'trim': None}),
    (3, {'years': 2, 'km': 50000, 'trim': None}),
]
MIN_BAND = 5
MIN_CORRECTED = 8
ROUND_TO = 250
NUMBER_WORDS = {1: 'één', 2: 'twee', 3: 'drie', 4: 'vier', 5: 'vijf', 6: 'zes', 7: 'zeven', 8: 'acht', 9: 'negen',
                10: 'tien'}
BELOW_P25 = ('De vraagprijs ligt al onder het onderste kwart van vergelijkbare auto\'s; onderhandelingsruimte is niet '
             'uit de data af te leiden.')


# ---------- Bouwstenen ----------
def tokens(trim):
    """Uitvoering als set woorden: kleine letters, alleen letters en cijfers, zonder ruiswoorden."""
    return {t for t in re.findall(r'[a-z0-9]+', (trim or '').lower()) if t not in NOISE}


def jaccard(a, b):
    """Overlap van twee woordensets; None als één van beide onbekend (leeg) is."""
    if not a or not b:
        return None
    return len(a & b) / len(a | b)


def percentile(values, q):
    """Lineair geïnterpoleerd percentiel (zelfde als numpy 'linear' / Excel PERCENTILE.INC)."""
    v = sorted(values)
    if not v:
        return None
    pos = (len(v) - 1) * q
    lo, hi = floor(pos), ceil(pos)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def median(values):
    return percentile(values, 0.5)


def theil_sen(points):
    """Mediaan van alle paarsgewijze hellingen (prijs per km). Positieve helling wordt 0; te weinig punten: 0."""
    pts = [(k, p) for k, p in points if k is not None]
    slopes = [(p2 - p1) / (k2 - k1) for i, (k1, p1) in enumerate(pts) for k2, p2 in pts[i + 1:] if k2 != k1]
    if not slopes:
        return 0.0
    return min(0.0, median(slopes))


def round_to(value, step=ROUND_TO):
    return None if value is None else int(round(value / step) * step)


def number_word(n):
    return NUMBER_WORDS.get(n, str(n))


def euro(value):
    return '€ ' + f'{abs(int(round(value))):,}'.replace(',', '.')


# ---------- Vergelijkbare auto's ----------
def _passes(car, other, rule):
    if car.get('year') and other.get('year') and abs(car['year'] - other['year']) > rule['years']:
        return False
    if car.get('kilometers') is not None and other.get('kilometers') is not None \
            and abs(car['kilometers'] - other['kilometers']) > rule['km']:
        return False
    if rule['trim'] is not None:
        overlap = jaccard(tokens(car.get('trim')), tokens(other.get('trim')))
        if overlap is not None and overlap < rule['trim']:
            return False
    return True


def select_comparables(car, pool):
    """(niveau, vergelijkbare auto's): eerste niveau met n >= 8, anders het ruimste niveau."""
    others = [p for p in pool if p['id'] != car['id']]
    chosen = (LEVELS[-1][0], [])
    for level, rule in LEVELS:
        comps = [p for p in others if _passes(car, p, rule)]
        chosen = (level, comps)
        if len(comps) >= MIN_CORRECTED:
            return chosen
    return chosen


def differences(car, other):
    """Verschillen in woorden; ontbrekende waarden worden als verschil genoemd, niet uitgesloten."""
    out = []
    if not other.get('year') or not car.get('year'):
        out.append('bouwjaar onbekend')
    elif other['year'] != car['year']:
        d = other['year'] - car['year']
        out.append(f'{abs(d)} jaar {"nieuwer" if d > 0 else "ouder"}')
    if other.get('kilometers') is None or car.get('kilometers') is None:
        out.append('km onbekend')
    elif other['kilometers'] != car['kilometers']:
        d = other['kilometers'] - car['kilometers']
        out.append(f'{abs(d):,} km {"meer" if d > 0 else "minder"}'.replace(',', '.'))
    overlap = jaccard(tokens(car.get('trim')), tokens(other.get('trim')))
    if overlap is None:
        out.append('uitvoering onbekend')
    elif overlap < 1:
        out.append('andere uitvoering' if overlap < 0.5 else 'vergelijkbare uitvoering')
    return out


def level_reason(level):
    rule = dict(LEVELS)[level]
    km = f'{rule["km"]:,}'.replace(',', '.')
    text = f'bouwjaar ±{rule["years"]}, km ±{km}'
    return text + (', uitvoering grotendeels gelijk' if rule['trim'] else '')


# ---------- Waardering ----------
def market_band(car, comps):
    """Band, middenwaarde en helling volgens de steekproefregels. Geeft ook de gebruikte prijs per auto."""
    n = len(comps)
    slope = None
    used = {c['id']: c['price_eur'] for c in comps}
    if n >= MIN_CORRECTED:
        slope = theil_sen([(c.get('kilometers'), c['price_eur']) for c in comps])
        if car.get('kilometers') is not None:
            for c in comps:
                if c.get('kilometers') is not None:
                    used[c['id']] = c['price_eur'] + slope * (car['kilometers'] - c['kilometers'])
    if n < MIN_BAND:
        return {'n': n, 'certainty': None, 'band': None, 'slope': slope, 'corrected': False, 'used': used}
    prices = list(used.values())
    band = {'p25': round(percentile(prices, 0.25)), 'median': round(median(prices)), 'p75': round(percentile(prices, 0.75))}
    corrected = n >= MIN_CORRECTED and car.get('kilometers') is not None and bool(slope)
    return {'n': n, 'certainty': 'redelijk' if n >= MIN_CORRECTED else 'laag', 'band': band, 'slope': slope,
            'corrected': corrected, 'used': used}


def amounts(asking, band, budget=None, own=None):
    """Openingsbod, streefprijs en grens; elk met herkomst: known, estimate of own (eigen keuze)."""
    own = own or {}
    out = {}
    def item(key, suggested, source):
        mine = own.get(key)
        if mine is not None:
            return {'value': mine, 'source': 'own', 'suggested': suggested}
        return {'value': suggested, 'source': source if suggested is not None else None, 'suggested': suggested}
    note = None
    if band:
        if asking < band['p25']:
            opening, note = None, BELOW_P25
        else:
            opening = round_to(min(asking, band['p25']))
        target = round_to(min(asking, band['median']))
        out['opening'] = item('opening', opening, 'estimate')
        out['target'] = item('target', target, 'known' if target == round_to(asking) else 'estimate')
        limit = band['p75'] if budget is None else min(budget, band['p75'])
        out['limit'] = item('limit', round_to(limit), 'known' if budget is not None and budget <= band['p75'] else 'estimate')
    else:
        out['opening'] = item('opening', None, None)
        out['target'] = item('target', None, None)
        out['limit'] = item('limit', round_to(budget) if budget else None, 'known' if budget else None)
    return out, note


def option_premiums(comps, used, criteria):
    """Mediaanverschil per wens tussen auto's mét (aanwezig) en zónder (afwezig); alleen bij minstens 5 en 5."""
    out = []
    for c in criteria:
        with_ = [used[x['id']] for x in comps if (x.get('claims') or {}).get(c['key']) == 'PRESENT']
        without = [used[x['id']] for x in comps if (x.get('claims') or {}).get(c['key']) == 'ABSENT']
        enough = len(with_) >= 5 and len(without) >= 5
        out.append({'key': c['key'], 'label': c['label'], 'n_with': len(with_), 'n_without': len(without),
                    'premium': round(median(with_) - median(without)) if enough else None})
    return out


def _days_ago(ts, now):
    then = datetime.fromisoformat(ts)
    then = then if then.tzinfo else then.replace(tzinfo=timezone.utc)
    return max(0, (now - then).days)


def arguments(car, result, comps, claims, sources, now=None):
    """Feiten met herkomst, alleen als ze van toepassing zijn."""
    now = now or datetime.now(timezone.utc)
    out = []
    band = result['band']
    if band:
        diff = round_to(car['price_eur'] - band['median'], 50)
        if diff:
            out.append({'text': f'{euro(diff)} {"boven" if diff > 0 else "onder"} de mediaan van {result["n"]} '
                                f'vergelijkbare auto\'s', 'source': 'Vergelijkbare auto\'s (schatting)'})
        else:
            out.append({'text': f'Gelijk aan de mediaan van {result["n"]} vergelijkbare auto\'s',
                        'source': 'Vergelijkbare auto\'s (schatting)'})
    days = car.get('days_tracked')
    if days is not None:
        comp_days = [c['days_tracked'] for c in comps if c.get('days_tracked') is not None]
        text = f'{"minstens " if car.get("seen_since_start") else ""}{days} dagen in beeld'
        if len(comp_days) >= MIN_BAND:
            text += f'; mediaan van vergelijkbare auto\'s {round(median(comp_days))} dagen'
        out.append({'text': text, 'source': 'Eigen waarnemingen'})
    drops = car.get('price_drops') or []
    if drops:
        total = sum(d['amount'] for d in drops)
        last = _days_ago(drops[-1]['at'], now)
        when = 'vandaag' if last == 0 else f'{last} {"dag" if last == 1 else "dagen"} geleden'
        out.append({'text': f'{number_word(len(drops))} keer verlaagd, samen {euro(total)}; laatste keer {when}',
                    'source': 'Eigen waarnemingen'})
    else:
        out.append({'text': 'nog niet verlaagd', 'source': 'Eigen waarnemingen'})
    cheaper = [c for c in comps if c['price_eur'] < car['price_eur']
               and (c.get('score_total') or 0) >= (car.get('score_total') or 0)]
    if cheaper:
        n = len(cheaper)
        noun = "vergelijkbare auto's zijn" if n != 1 else 'vergelijkbare auto is'
        out.append({'text': f'{n} {noun} goedkoper met een gelijke of betere match', 'source': "Vergelijkbare auto's",
                    'links': [{'id': c['id'], 'title': c['title'], 'price_eur': c['price_eur']}
                              for c in sorted(cheaper, key=lambda c: c['price_eur'])[:5]]})
    missing = [c['label'] for c in claims if c['status'] == 'ABSENT']
    unsure = [c['label'] for c in claims if c['status'] not in ('PRESENT', 'ABSENT')]
    if missing or unsure:
        parts = []
        if missing:
            parts.append('mist: ' + ', '.join(m.lower() if not re.search('[A-Z]', m[1:]) else m for m in missing))
        if unsure:
            parts.append('onzeker: ' + ', '.join(m.lower() if not re.search('[A-Z]', m[1:]) else m for m in unsure))
        out.append({'text': ' · '.join(parts), 'source': 'Jouw wensen en de advertentie'})
    priced = [s for s in sources if s.get('price_eur') is not None]
    if priced:
        low = min(priced, key=lambda s: s['price_eur'])
        if low['price_eur'] < car['price_eur']:
            out.append({'text': f'bij {low["site"]} {euro(car["price_eur"] - low["price_eur"])} lager geadverteerd',
                        'source': 'Aanbieders'})
    return out


def valuation(car, pool, *, budget=None, own=None, claims=(), sources=(), criteria=(), now=None):
    """Volledige waardering van één auto. `pool` bevat auto's uit dezelfde zoekopdracht(en) die te koop staan."""
    level, comps = select_comparables(car, pool)
    result = market_band(car, comps)
    used = result.pop('used')
    asking = car['price_eur']
    money, note = amounts(asking, result['band'], budget, own)
    result.update({'level': level, 'level_reason': level_reason(level), 'amounts': money, 'note': note,
                   'asking': asking, 'budget': budget})
    if result['n'] < MIN_BAND:
        result['message'] = f'Te weinig vergelijkbare auto\'s (n = {result["n"]}) voor een marktwaarde.'
    result['comparables'] = sorted([{
        'id': c['id'], 'title': c['title'], 'price_eur': c['price_eur'],
        'corrected_price': round(used[c['id']]) if result['corrected'] else None,
        'kilometers': c.get('kilometers'), 'year': c.get('year'), 'trim': c.get('trim'),
        'score_total': c.get('score_total'), 'days_tracked': c.get('days_tracked'),
        'differences': differences(car, c)} for c in comps], key=lambda c: c['corrected_price'] or c['price_eur'])
    result['option_premiums'] = option_premiums(comps, used, criteria)
    result['arguments'] = arguments(car, result, comps, list(claims), list(sources), now)
    if result['band']:
        result['difference'] = asking - result['band']['median']
    return result


def market_position(car, pool):
    """Kort: verschil met de middenwaarde voor de aanbodlijst, of None bij n < 5."""
    level, comps = select_comparables(car, pool)
    result = market_band(car, comps)
    if not result['band']:
        return {'n': result['n'], 'difference': None, 'median': None, 'certainty': None}
    return {'n': result['n'], 'difference': car['price_eur'] - result['band']['median'],
            'median': result['band']['median'], 'certainty': result['certainty']}
