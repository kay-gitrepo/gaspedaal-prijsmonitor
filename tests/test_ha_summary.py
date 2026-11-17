"""WP-14A: samenvatting voor Home Assistant."""
from fastapi.testclient import TestClient

from app.main import app
from test_profiles import login, new_profile, run

HA = {'Authorization': 'Bearer not-a-real-ha-refresh-token-for-tests'}


def ad(i, price, description='Elektrisch uitklapbare trekhaak'):
    return {'external_id': f'w14-{i}', 'title': f'XC90 w14 {i}', 'price_eur': price, 'description': description}


def test_summary_lists_what_is_worth_a_notification():
    with TestClient(app) as client:
        assert client.get('/api/v1/ha/summary').status_code == 401
        assert client.get('/api/v1/ha/summary', headers={'Authorization': 'Bearer fout'}).status_code == 401
        headers = login(client)
        pid = new_profile(client, headers, 'WP14 HA', 'https://www.gaspedaal.nl/volvo/xc90/w14')
        assert client.patch(f'/api/v1/profiles/{pid}', headers=headers, json={'budget_eur': 70000}).status_code == 200
        run(client, headers, pid, [ad('a', 72000), ad('b', 75000)])
        cars = {x['external_id']: x for x in client.get(f'/api/v1/listings?profile_id={pid}').json()['items']}
        client.post(f"/api/v1/listings/{cars['import:w14-b']['id']}/favorite", headers=headers)
        run(client, headers, pid, [ad('a', 69500), ad('b', 74000), ad('c', 71000)])
        client.cookies.clear()
        data = client.get('/api/v1/ha/summary', headers=HA).json()
        assert data['last_run']['state'] == 'COMPLETE' and data['last_run']['sentence'].startswith('Controle geslaagd')
        assert [i['title'] for i in data['new_matches']] == ['XC90 w14 c']
        assert [(i['previous_price'], i['price_eur']) for i in data['shortlist_price_drops']] == [(75000, 74000)]
        assert [i['title'] for i in data['within_budget']] == ['XC90 w14 a']
        assert data['new_matches'][0]['link'].startswith('/#/auto/')
        assert data['has_news'] is True and 'Binnen budget gekomen: XC90 w14 a (€ 69.500)' in data['message']
        assert data['counts']['new'] == 1 and data['counts']['price_drops'] == 2
