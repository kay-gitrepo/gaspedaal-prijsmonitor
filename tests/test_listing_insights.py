"""WP-08: afgeleide velden in de aanbodlijst, zonder advertentietekst."""
from fastapi.testclient import TestClient

from app.main import app
from test_profiles import login, new_profile, run


def ad(i, price, **extra):
    return {'external_id': f'w8-{i}', 'title': f'XC90 w8 {i}', 'price_eur': price, **extra}


def test_listing_fields_for_price_history_and_tracking():
    with TestClient(app) as client:
        headers = login(client)
        pid = new_profile(client, headers, 'WP08 lijst', 'https://www.gaspedaal.nl/volvo/xc90/lijst')
        photos = ['https://cdn.example.test/a.jpg', 'https://cdn.example.test/b.jpg']
        run(client, headers, pid, [ad('a', 70000, photos=photos, description='Trekhaak'), ad('b', 72000)])
        run(client, headers, pid, [ad('a', 69000, photos=photos, description='Trekhaak'), ad('b', 72000), ad('c', 65000)])
        run(client, headers, pid, [ad('a', 68000, photos=photos, description='Trekhaak'), ad('c', 65000), ad('d', 60000)])
        items = {x['external_id']: x for x in client.get(f'/api/v1/listings?profile_id={pid}').json()['items']}
        a, b, c, d = (items[f'import:w8-{k}'] for k in 'abcd')
        assert 'description' not in a and 'photos_json' not in a
        assert a['photo'] == photos[0] and a['has_text'] == 1
        assert (a['first_price'], a['price_change_total'], a['price_drop_count']) == (70000, -2000, 2)
        assert a['last_price_change_at'] and a['last_drop_at']
        assert a['seen_since_start'] is True and a['is_new'] is False
        assert c['seen_since_start'] is False and c['is_new'] is False
        assert d['is_new'] is True and d['seen_since_start'] is False
        assert b['availability'] == 'MISSING_UNCONFIRMED' and b['price_change_total'] == 0
        assert a['observations'] == 3 and a['days_tracked'] == 0
        assert {'score_potential', 'evidence_coverage', 'must_count', 'provider_count'} <= set(a)
        detail = client.get(f"/api/v1/listings/{a['id']}").json()
        assert detail['first_price'] == 70000 and detail['seen_since_start'] is True
