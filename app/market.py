"""Marktoverzicht (WP-11): pure rekenfuncties. Elke statistiek geeft n mee; bij n < 5 is de waarde None.

Belangrijk: 'Markt door de tijd' scheidt samenstelling van echte prijsverandering. De mediaan van het aanbod
beweegt ook als er andere auto's te koop komen; de prijsindex beweegt alleen als dezelfde auto's van prijs veranderen.
"""
from datetime import date, timedelta

from app.valuation import percentile

MIN_N = 5
MIN_TREND_DAYS = 14
KM_CLASSES = [(0, 25000, '0–25 duizend'), (25000, 50000, '25–50 duizend'), (50000, 75000, '50–75 duizend'),
              (75000, 100000, '75–100 duizend'), (100000, None, '100 duizend en meer')]


def summary(values):
    """{n, median, p25, p75}; waarden None bij n < 5 (te weinig data)."""
    v = [x for x in values if x is not None]
    if len(v) < MIN_N:
        return {'n': len(v), 'median': None, 'p25': None, 'p75': None}
    return {'n': len(v), 'median': round(percentile(v, 0.5)), 'p25': round(percentile(v, 0.25)),
            'p75': round(percentile(v, 0.75))}


def median_or_none(values):
    v = [x for x in values if x is not None]
    return {'n': len(v), 'value': round(percentile(v, 0.5), 1) if len(v) >= MIN_N else None}


def daily_last(observations):
    """Per kalenderdag per auto de laatste waarneming: herhaalde controles op één dag tellen één keer.

    `observations`: iterable van (datum 'YYYY-MM-DD', listing_id, prijs) in volgorde van waarneming.
    """
    days = {}
    for day, listing_id, price in observations:
        days.setdefault(day, {})[listing_id] = price
    return dict(sorted(days.items()))


def daily_stats(daily):
    """Mediaan en P25–P75 van het aanbod per dag (None bij minder dan 5 auto's die dag)."""
    return [{'date': day, **summary(list(prices.values()))} for day, prices in daily.items()]


def price_index(daily):
    """Prijsindex van dezelfde auto's: gemiddelde relatieve verandering tussen opeenvolgende meetdagen, geketend vanaf 100."""
    out = []
    level = 100.0
    previous = None
    for day, prices in daily.items():
        if previous is not None:
            pairs = [(prices[k], previous[k]) for k in prices.keys() & previous.keys() if previous[k]]
            if pairs:
                level *= 1 + sum(p / q - 1 for p, q in pairs) / len(pairs)
            out.append({'date': day, 'index': round(level, 2), 'pairs': len(pairs)})
        else:
            out.append({'date': day, 'index': 100.0, 'pairs': 0})
        previous = prices
    return out


def _fmt_euro(value):
    return '€ ' + f'{abs(int(round(value))):,}'.replace(',', '.')


def _fmt_pct(value):
    return f'{abs(value):.1f}'.replace('.', ',')


def trend_sentence(stats, index):
    """Eén zin volgens vaste regels; geen advies, alleen feiten."""
    days = len(stats)
    if days < MIN_TREND_DAYS:
        return f'Nog te kort gevolgd voor een trend ({days} {"dag" if days == 1 else "dagen"}).'
    medians = [s['median'] for s in stats if s['median'] is not None]
    if len(medians) < 2 or not index:
        return f'Nog te kort gevolgd voor een trend ({days} dagen).'
    median_change = medians[-1] / medians[0] - 1
    index_change = index[-1]['index'] / 100 - 1
    if abs(median_change) > 0.01 and abs(index_change) < 0.005:
        verb = 'daalde' if median_change < 0 else 'steeg'
        cheaper = 'goedkoper' if median_change < 0 else 'duurder'
        return (f'De mediaan {verb} {_fmt_euro(medians[-1] - medians[0])}, maar dezelfde auto\'s werden nauwelijks '
                f'{cheaper}: vooral de samenstelling van het aanbod veranderde.')
    if median_change < -0.005 and index_change < -0.005:
        return f'Bestaande advertenties werden gemiddeld {_fmt_pct(index_change * 100)} % goedkoper.'
    if median_change > 0.005 and index_change > 0.005:
        return f'Bestaande advertenties werden gemiddeld {_fmt_pct(index_change * 100)} % duurder.'
    return 'Vraagprijzen zijn in deze periode stabiel.'


def km_classes(cars):
    """Mediane vraagprijs per kilometerklasse, met n; None bij n < 5."""
    rows = []
    for lo, hi, label in KM_CLASSES:
        prices = [c['price_eur'] for c in cars if c.get('kilometers') is not None
                  and c['kilometers'] >= lo and (hi is None or c['kilometers'] < hi)]
        s = summary(prices)
        rows.append({'label': label, 'n': s['n'], 'median': s['median']})
    return rows


def week_start(day):
    d = date.fromisoformat(day[:10])
    return (d - timedelta(days=d.weekday())).isoformat()


def weekly_flow(events, start, end):
    """Nieuw en niet meer gezien per week (maandag als begin). `events`: (datum, type, listing_id)."""
    weeks = {}
    cur = date.fromisoformat(week_start(start))
    last = date.fromisoformat(week_start(end))
    while cur <= last:
        weeks[cur.isoformat()] = {'week': cur.isoformat(), 'new': 0, 'gone': 0}
        cur += timedelta(days=7)
    seen = set()
    for day, kind, listing_id in events:
        wk = week_start(day)
        if wk not in weeks:
            continue
        key = 'new' if kind == 'FIRST_SEEN' else 'gone'
        if (wk, key, listing_id) in seen:
            continue
        seen.add((wk, key, listing_id))
        weeks[wk][key] += 1
    return list(weeks.values())


def drop_stats(cars, drops, start_of_tracking):
    """Prijsverlagingen: aandeel auto's met minstens één verlaging, mediane verlaging in € en %,
    mediane dagen tot de eerste verlaging (alleen auto's die na de start van het volgen verschenen).

    cars: [{id, first_seen}]; drops: [(listing_id, datum, oude prijs, nieuwe prijs)] chronologisch.
    """
    ids = {c['id'] for c in cars}
    own = [d for d in drops if d[0] in ids and d[3] < d[2]]
    with_drop = {d[0] for d in own}
    first_drop = {}
    for lid, day, _, _ in own:
        first_drop.setdefault(lid, day)
    later = [c for c in cars if c['first_seen'][:10] > start_of_tracking[:10] and c['id'] in first_drop] \
        if start_of_tracking else []
    days_to_first = [(date.fromisoformat(first_drop[c['id']][:10]) - date.fromisoformat(c['first_seen'][:10])).days
                     for c in later]
    share = round(len(with_drop) / len(cars) * 100, 1) if len(cars) >= MIN_N else None
    return {'n_cars': len(cars), 'with_drop': len(with_drop), 'share': share,
            'median_drop_eur': median_or_none([d[2] - d[3] for d in own]),
            'median_drop_pct': median_or_none([(d[2] - d[3]) / d[2] * 100 for d in own]),
            'median_days_to_first': median_or_none(days_to_first)}
