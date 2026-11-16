"""WP-09: actualiteit van de controles en wat er per controle is veranderd."""
from fastapi.testclient import TestClient

from app.db import connect
from app.main import app
from test_profiles import login, new_profile, run


def ad(i, price):
    return {'external_id': f'w9-{i}', 'title': f'XC90 w9 {i}', 'price_eur': price}


def test_changes_groups_events_of_one_check():
    with TestClient(app) as client:
        headers = login(client)
        pid = new_profile(client, headers, 'WP09 wijzigingen', 'https://www.gaspedaal.nl/volvo/xc90/wijzig')
        run(client, headers, pid, [ad('a', 70000), ad('b', 72000), ad('c', 74000)])
        out = run(client, headers, pid, [ad('a', 68000), ad('b', 73000), ad('d', 60000)])
        assert out['state'] == 'COMPLETE'
        data = client.get(f'/api/v1/changes?profile_id={pid}').json()
        assert data['run']['id'] == out['id']
        g = data['groups']
        assert [x['title'] for x in g['new']] == ['XC90 w9 d']
        assert [(x['previous_price'], x['new_price']) for x in g['price_down']] == [(70000, 68000)]
        assert [(x['previous_price'], x['new_price']) for x in g['price_up']] == [(72000, 73000)]
        assert [x['title'] for x in g['missing']] == ['XC90 w9 c']
        assert g['off_market'] == [] and g['reappeared'] == []
        # Een specifieke controle opvragen kan ook; een onbekende geeft 404.
        first = client.get('/api/v1/refresh-runs').json()['items']
        assert client.get('/api/v1/changes?run_id=bestaat-niet').status_code == 404
        assert any(i['id'] == out['id'] for i in first)
        detail = client.get(f"/api/v1/refresh-runs/{out['id']}").json()
        assert detail['changes']['price_down'][0]['new_price'] == 68000
        assert detail['profiles'][0]['title'] == 'WP09 wijzigingen' and detail['profiles'][0]['found'] == 3


def test_status_after_failed_check_keeps_data():
    with TestClient(app) as client:
        headers = login(client)
        pid = new_profile(client, headers, 'WP09 mislukt', 'https://www.gaspedaal.nl/volvo/xc90/mislukt')
        ok = run(client, headers, pid, [ad('x', 70000), ad('y', 71000)])
        st = client.get('/api/v1/status').json()
        assert st['last_run']['id'] == ok['id'] and st['last_success']['id'] == ok['id']
        assert st['running'] is None and st['stale_after_hours'] == 36
        # Lege volledige import terwijl er aanbod was: de controle mislukt bewust.
        failed = run(client, headers, pid, [])
        assert failed['state'] == 'FAILED'
        st = client.get('/api/v1/status').json()
        assert st['last_run']['state'] == 'FAILED' and st['last_success']['id'] == ok['id']
        con = connect()
        try:
            statuses = [r[0] for r in con.execute('SELECT status FROM profile_listings WHERE profile_id=?', (pid,))]
            events = con.execute('''SELECT COUNT(*) FROM listing_events WHERE run_id=?''', (failed['id'],)).fetchone()[0]
        finally:
            con.close()
        assert statuses == ['ACTIVE', 'ACTIVE'] and events == 0
