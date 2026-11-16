"""WP-10: waardering via de API; zoekopdrachten mengen niet en eigen bedragen heten 'Jouw keuze'."""
from fastapi.testclient import TestClient

from app.main import app
from test_profiles import login, new_profile, run


def ad(prefix, i, price, km=40000):
    return {'external_id': f'{prefix}-{i}', 'title': f'XC90 {prefix} {i}', 'price_eur': price, 'year': 2025,
            'kilometers': km, 'trim': 'T8 Ultra'}


def test_searches_do_not_mix_and_own_amounts_are_kept():
    with TestClient(app) as client:
        headers = login(client)
        a = new_profile(client, headers, 'WP10 A', 'https://www.gaspedaal.nl/volvo/xc90/w10a')
        b = new_profile(client, headers, 'WP10 B', 'https://www.gaspedaal.nl/volvo/xc90/w10b')
        run(client, headers, a, [ad('w10a', i, 70000 + i * 500) for i in range(4)])
        run(client, headers, b, [ad('w10b', i, 60000 + i * 500) for i in range(9)])
        items = client.get(f'/api/v1/listings?profile_id={a}').json()['items']
        car = next(x for x in items if x['external_id'] == 'import:w10a-0')
        v = client.get(f"/api/v1/listings/{car['id']}/valuation").json()
        assert v['n'] == 3 and v['band'] is None and v['certainty'] is None
        assert {c['title'] for c in v['comparables']} == {'XC90 w10a 1', 'XC90 w10a 2', 'XC90 w10a 3'}
        assert v['message'] == "Te weinig vergelijkbare auto's (n = 3) voor een marktwaarde."
        assert car['market_diff'] is None and car['market_n'] == 3
        # Zoekopdracht B heeft genoeg auto's: band met gecorrigeerde prijzen en een verschil in de lijst.
        b_items = client.get(f'/api/v1/listings?profile_id={b}').json()['items']
        assert all(x['market_n'] == 8 and x['market_diff'] is not None for x in b_items)
        b_car = b_items[0]
        v = client.get(f"/api/v1/listings/{b_car['id']}/valuation").json()
        assert v['certainty'] == 'redelijk' and v['level'] == 1
        r = client.put(f"/api/v1/listings/{b_car['id']}/negotiation", headers=headers,
                       json={'my_opening': 59000, 'my_target': None, 'my_max': 62000})
        assert r.status_code == 200
        v = client.get(f"/api/v1/listings/{b_car['id']}/valuation").json()
        assert v['amounts']['opening']['source'] == 'own' and v['amounts']['opening']['value'] == 59000
        assert v['amounts']['target']['source'] in ('known', 'estimate')
        assert v['amounts']['limit'] == {'value': 62000, 'source': 'own', 'suggested': v['amounts']['limit']['suggested']}
        assert client.get('/api/v1/listings/bestaat-niet/valuation').status_code == 404
