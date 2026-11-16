"""WP-11: marktoverzicht met handgemaakte reeksen."""
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.market import (daily_last, daily_stats, drop_stats, km_classes, price_index, summary, trend_sentence,
                        weekly_flow)


def days(n, start=date(2026, 10, 1)):
    return [(start + timedelta(days=i)).isoformat() for i in range(n)]


def test_composition_change_moves_median_but_not_index():
    # Elke dag dezelfde prijzen; dure auto's verdwijnen en goedkopere komen erbij.
    obs = []
    for i, day in enumerate(days(14)):
        cars = {f'old{k}': 80000 + k * 1000 for k in range(6 - i // 3)}
        cars.update({f'new{k}': 60000 + k * 1000 for k in range(i // 2)})
        obs += [(day, lid, price) for lid, price in cars.items()]
    daily = daily_last(obs)
    index = price_index(daily)
    stats = daily_stats(daily)
    assert all(p['index'] == 100.0 for p in index)
    assert stats[-1]['median'] < stats[0]['median']
    sentence = trend_sentence(stats, index)
    assert sentence.startswith('De mediaan daalde €') and 'vooral de samenstelling' in sentence


def test_all_cars_two_percent_cheaper_gives_index_98():
    first, second = days(2)
    obs = [(first, f'c{k}', 50000 + k * 5000) for k in range(6)]
    obs += [(second, f'c{k}', (50000 + k * 5000) * 0.98) for k in range(6)]
    index = price_index(daily_last(obs))
    assert index[-1]['index'] == 98.0 and index[-1]['pairs'] == 6


def test_repeated_checks_on_one_day_count_once():
    day = '2026-10-01'
    obs = [(day, 'a', 70000), (day, 'a', 69000), (day, 'b', 72000), (day, 'b', 72000)]
    daily = daily_last(obs)
    assert daily == {day: {'a': 69000, 'b': 72000}}  # de laatste waarneming van de dag telt
    assert daily_stats(daily)[0]['n'] == 2


def test_trend_rules():
    short = daily_stats(daily_last([(d, 'a', 1) for d in days(5)]))
    assert trend_sentence(short, price_index({})) == 'Nog te kort gevolgd voor een trend (5 dagen).'
    obs = [(d, f'c{k}', 70000 * (1 - 0.001 * i)) for i, d in enumerate(days(15)) for k in range(5)]
    daily = daily_last(obs)
    assert trend_sentence(daily_stats(daily), price_index(daily)).startswith('Bestaande advertenties werden gemiddeld')
    flat = daily_last([(d, f'c{k}', 70000 + k) for d in days(15) for k in range(5)])
    assert trend_sentence(daily_stats(flat), price_index(flat)) == 'Vraagprijzen zijn in deze periode stabiel.'


def test_true_median_and_small_samples():
    assert summary([1, 2, 3, 4, 5, 6])['median'] == 4  # (3 + 4) / 2 = 3,5, afgerond naar 4 euro
    assert summary([60000, 61000, 62000, 63000, 64000, 65000])['median'] == 62500
    assert summary([1, 2, 3, 4]) == {'n': 4, 'median': None, 'p25': None, 'p75': None}
    rows = km_classes([{'kilometers': 10000 + i * 100, 'price_eur': 70000} for i in range(5)]
                      + [{'kilometers': 30000, 'price_eur': 65000}])
    assert rows[0] == {'label': '0–25 duizend', 'n': 5, 'median': 70000}
    assert rows[1] == {'label': '25–50 duizend', 'n': 1, 'median': None}


def test_weekly_flow_and_drops():
    flow = weekly_flow([('2026-11-03T07:00:00', 'FIRST_SEEN', 'a'), ('2026-11-04T07:00:00', 'MISSING_UNCONFIRMED', 'b'),
                        ('2026-11-12T07:00:00', 'FIRST_SEEN', 'c')], '2026-11-02', '2026-11-15')
    assert flow == [{'week': '2026-11-02', 'new': 1, 'gone': 1}, {'week': '2026-11-09', 'new': 1, 'gone': 0}]
    cars = [{'id': f'c{i}', 'first_seen': '2026-10-01T07:00:00' if i < 3 else '2026-10-10T07:00:00'} for i in range(6)]
    drops = [('c0', '2026-10-05T07:00:00', 70000, 68000), ('c4', '2026-10-20T07:00:00', 60000, 59400),
             ('c4', '2026-10-25T07:00:00', 59400, 59000), ('c5', '2026-10-12T07:00:00', 50000, 51000)]
    out = drop_stats(cars, drops, '2026-10-01T07:00:00')
    assert out['with_drop'] == 2 and out['share'] is None or out['share'] == round(2 / 6 * 100, 1)
    assert out['median_days_to_first'] == {'n': 1, 'value': None}  # alleen c4 verscheen na de start


def test_market_endpoint_validates_period():
    with TestClient(app) as client:
        client.post('/api/v1/login', json={'password': 'not-a-real-password'})
        assert client.get('/api/v1/market?days=7').status_code == 422
        data = client.get('/api/v1/market?days=30').json()
        assert {'asking', 'opportunities', 'scatter', 'km_classes', 'flow', 'in_view', 'drops', 'timeline'} <= set(data)
        assert data['timeline']['sentence']
