"""WP-10: rekenmodel marktwaarde met vaste invoer."""
import pytest

from app.valuation import (BELOW_P25, amounts, jaccard, market_band, percentile, round_to, select_comparables,
                           theil_sen, tokens, valuation)

CAR = {'id': 'car', 'title': 'Volvo XC90 T8 Ultra', 'price_eur': 70000, 'year': 2025, 'kilometers': 40000,
       'trim': 'T8 Ultra Bright AWD', 'score_total': 70, 'days_tracked': 30}


def comp(i, price, year=2025, km=40000, trim='T8 Ultra Bright', score=70):
    return {'id': f'c{i}', 'title': f'Auto {i}', 'price_eur': price, 'year': year, 'kilometers': km, 'trim': trim,
            'score_total': score, 'days_tracked': 20}


def test_tokens_and_jaccard_ignore_noise_words():
    assert tokens('T8 AWD Ultra Bright Aut. 7p') == {'t8', 'ultra', 'bright'}
    assert jaccard(tokens('T8 Ultra Bright'), tokens('T8 Ultra Dark')) == 0.5
    assert jaccard(tokens(None), tokens('T8')) is None


def test_level_1_when_eight_strict_matches():
    pool = [comp(i, 68000 + i * 500, km=35000 + i * 1000) for i in range(9)]
    level, comps = select_comparables(CAR, pool + [dict(CAR)])
    assert level == 1 and len(comps) == 9  # de auto zelf telt niet mee


def test_level_2_when_trim_differs():
    pool = [comp(i, 68000, km=40000 + i * 3000, trim='B5 Core') for i in range(8)]
    level, comps = select_comparables(CAR, pool)
    assert level == 2 and len(comps) == 8


def test_level_3_is_used_when_no_level_reaches_eight():
    pool = [comp(i, 68000, year=2023, km=80000) for i in range(3)] + [comp(9, 68000, year=2020)]
    level, comps = select_comparables(CAR, pool)
    assert level == 3 and [c['id'] for c in comps] == ['c0', 'c1', 'c2']


def test_missing_values_do_not_exclude():
    pool = [comp(i, 68000, year=None, km=None, trim=None) for i in range(8)]
    level, comps = select_comparables(CAR, pool)
    assert level == 1 and len(comps) == 8


@pytest.mark.parametrize('n,certainty,corrected', [(4, None, False), (5, 'laag', False), (7, 'laag', False),
                                                   (8, 'redelijk', True)])
def test_sample_size_thresholds(n, certainty, corrected):
    pool = [comp(i, 70000 - i * 400, km=30000 + i * 2500) for i in range(n)]
    result = valuation(CAR, pool)
    assert result['n'] == n and result['certainty'] == certainty and result['corrected'] is corrected
    if n < 5:
        assert result['band'] is None and result['message'] == f"Te weinig vergelijkbare auto's (n = {n}) voor een marktwaarde."
        assert all(a['value'] is None for a in result['amounts'].values())
        assert len(result['comparables']) == n
    else:
        assert result['band']['p25'] <= result['band']['median'] <= result['band']['p75']
        assert (result['slope'] is not None) is (n >= 8)


def test_theil_sen_on_known_series():
    slope = theil_sen([(0, 100), (1, 90), (2, 80), (3, 75)])
    # hellingen: -10, -10, -8,33, -10, -7,5, -5 → mediaan (-10 + -8,33) / 2
    assert slope == pytest.approx((-10 - 25 / 3) / 2)
    assert theil_sen([(0, 100), (10, 110), (20, 130)]) == 0  # positieve helling wordt 0
    assert theil_sen([(5, 100), (5, 120)]) == 0  # geen verschil in km: geen helling


def test_correction_moves_prices_to_the_cars_kilometers():
    pool = [comp(i, 72000 - i * 1000, km=40000 + i * 5000) for i in range(8)]  # elke 5.000 km € 1.000 lager
    band = market_band(CAR, pool)
    assert band['slope'] == pytest.approx(-0.2)
    assert all(round(v) == 72000 for v in band['used'].values())
    assert band['band'] == {'p25': 72000, 'median': 72000, 'p75': 72000}


def test_percentile_is_linear():
    assert percentile([1, 2, 3, 4], 0.25) == 1.75
    assert percentile([10], 0.75) == 10


def test_amounts_without_fixed_discount_and_rounded():
    band = {'p25': 66120, 'median': 68890, 'p75': 71240}
    money, note = amounts(70000, band)
    assert note is None
    assert money['opening'] == {'value': 66000, 'source': 'estimate', 'suggested': 66000}
    assert money['target']['value'] == 69000 and money['limit']['value'] == 71250
    money, _ = amounts(70000, band, budget=70000)
    assert money['limit'] == {'value': 70000, 'source': 'known', 'suggested': 70000}
    money, _ = amounts(70000, band, own={'target': 67500})
    assert money['target'] == {'value': 67500, 'source': 'own', 'suggested': 69000}
    assert round_to(66124) == 66000 and round_to(66126) == 66250


def test_asking_below_p25_gives_no_opening_bid():
    money, note = amounts(64000, {'p25': 66000, 'median': 68000, 'p75': 70000})
    assert money['opening']['value'] is None and note == BELOW_P25
    assert money['target'] == {'value': 64000, 'source': 'known', 'suggested': 64000}


def test_arguments_and_option_premium():
    pool = [comp(i, 72000 - i * 1000, km=40000) for i in range(10)]
    for i, c in enumerate(pool):
        c['claims'] = {'towbar': 'PRESENT' if i < 5 else 'ABSENT'}
    car = dict(CAR, price_drops=[{'amount': 1500, 'at': '2026-11-01T07:00:00+00:00'},
                                 {'amount': 1000, 'at': '2026-11-10T07:00:00+00:00'}], seen_since_start=True)
    from datetime import datetime, timezone
    result = valuation(car, pool, criteria=[{'key': 'towbar', 'label': 'Trekhaak'}],
                       claims=[{'label': 'Luchtvering', 'status': 'ABSENT'}, {'label': 'Trekhaak', 'status': 'UNKNOWN'}],
                       sources=[{'site': 'AutoTrack', 'price_eur': 69500}],
                       now=datetime(2026, 11, 29, 7, tzinfo=timezone.utc))
    texts = [a['text'] for a in result['arguments']]
    assert texts[0] == "€ 2.500 boven de mediaan van 10 vergelijkbare auto's"
    assert 'minstens 30 dagen in beeld; mediaan van vergelijkbare auto\'s 20 dagen' in texts
    assert 'twee keer verlaagd, samen € 2.500; laatste keer 19 dagen geleden' in texts
    assert "7 vergelijkbare auto's zijn goedkoper met een gelijke of betere match" in texts
    assert 'mist: luchtvering · onzeker: trekhaak' in texts
    assert 'bij AutoTrack € 500 lager geadverteerd' in texts
    premium = result['option_premiums'][0]
    assert (premium['n_with'], premium['n_without'], premium['premium']) == (5, 5, 5000)
