"""WP-04: zoekopdrachten bewerken, archiveren, budget en filters wijzigen zonder valse verdwijningen."""
from fastapi.testclient import TestClient

from app.db import connect
from app.main import app
from test_api import wait_run


def login(client):
    return {'X-CSRF-Token': client.post('/api/v1/login', json={'password': 'not-a-real-password'}).json()['csrf']}


def new_profile(client, headers, title, url):
    r = client.post('/api/v1/profiles', headers=headers, json={'title': title, 'search_url': url})
    assert r.status_code == 201, r.text
    return r.json()['id']


def run(client, headers, pid, listings, complete=True):
    payload = {'complete': complete, 'listings': listings}
    assert client.post(f'/api/v1/profiles/{pid}/snapshot', json=payload, headers=headers).status_code == 200
    started = client.post('/api/v1/refresh-runs', json={'scope': {'profile_ids': [pid]}}, headers=headers)
    assert started.status_code == 202, started.text
    return wait_run(client, started.json()['run_id'])


def car(i, price=70000):
    return {'external_id': f'wp04-{i}', 'title': f'XC90 wp04 {i}', 'price_eur': price}


def test_patch_updates_fields_and_budget():
    with TestClient(app) as client:
        headers = login(client)
        pid = new_profile(client, headers, 'WP04 patch', 'https://www.gaspedaal.nl/volvo/xc90/patch')
        r = client.patch(f'/api/v1/profiles/{pid}', headers=headers,
                         json={'title': 'Nieuwe naam', 'budget_eur': 72500, 'enabled': False})
        assert r.status_code == 200 and r.json()['scope_changed'] is False
        item = next(p for p in client.get('/api/v1/profiles').json()['items'] if p['id'] == pid)
        assert (item['title'], item['budget_eur'], item['enabled']) == ('Nieuwe naam', 72500, 0)
        # budget wissen kan met null; ongeldige link wordt geweigerd
        assert client.patch(f'/api/v1/profiles/{pid}', headers=headers, json={'budget_eur': None}).status_code == 200
        item = next(p for p in client.get('/api/v1/profiles').json()['items'] if p['id'] == pid)
        assert item['budget_eur'] is None
        bad = client.patch(f'/api/v1/profiles/{pid}', headers=headers, json={'search_url': 'https://example.com/x'})
        assert bad.status_code == 422
        assert client.patch(f'/api/v1/profiles/{pid}', json={'title': 'Zonder CSRF'}).status_code == 403


def test_archive_hides_profile_and_stops_checks():
    with TestClient(app) as client:
        headers = login(client)
        pid = new_profile(client, headers, 'WP04 archief', 'https://www.gaspedaal.nl/volvo/xc90/archief')
        run(client, headers, pid, [car(1)])
        assert client.post(f'/api/v1/profiles/{pid}/archive', headers=headers).status_code == 200
        assert pid not in [p['id'] for p in client.get('/api/v1/profiles').json()['items']]
        assert pid in [p['id'] for p in client.get('/api/v1/profiles?archived=true').json()['items']]
        refused = client.post('/api/v1/refresh-runs', json={'scope': {'profile_ids': [pid]}}, headers=headers)
        assert refused.status_code == 403
        assert client.post(f'/api/v1/profiles/{pid}/archive', headers=headers).status_code == 404
        con = connect()
        try:
            # archiveren bewaart auto's en prijshistorie
            assert con.execute('SELECT COUNT(*) FROM price_observations WHERE profile_id=?', (pid,)).fetchone()[0] == 1
        finally:
            con.close()


def test_changed_filters_mark_out_of_scope_without_missing_event():
    with TestClient(app) as client:
        headers = login(client)
        pid = new_profile(client, headers, 'WP04 filters', 'https://www.gaspedaal.nl/volvo/xc90/filters')
        run(client, headers, pid, [car(1), car(2), car(3)])
        r = client.patch(f'/api/v1/profiles/{pid}', headers=headers,
                         json={'search_url': 'https://www.gaspedaal.nl/volvo/xc90/filters?kmmax=50000'})
        assert r.json()['scope_changed'] is True
        # Een onvolledige controle wist de wijziging niet en markeert niets.
        run(client, headers, pid, [car(1)], complete=False)
        out = run(client, headers, pid, [car(1)])
        assert out['state'] == 'COMPLETE' and out['summary']['out_of_scope_new'] == 2
        con = connect()
        try:
            rows = dict(con.execute('''SELECT l.external_id,pl.status FROM profile_listings pl JOIN listings l
                                      ON l.id=pl.listing_id WHERE pl.profile_id=?''', (pid,)).fetchall())
            assert rows == {'import:wp04-1': 'ACTIVE', 'import:wp04-2': 'OUT_OF_SCOPE', 'import:wp04-3': 'OUT_OF_SCOPE'}
            events = con.execute('''SELECT COUNT(*) FROM listing_events e JOIN listings l ON l.id=e.listing_id
                WHERE l.external_id IN ('import:wp04-2','import:wp04-3')
                AND e.event_type IN ('MISSING_UNCONFIRMED','OFF_MARKET')''').fetchone()[0]
            assert events == 0
            avail = con.execute("SELECT availability FROM listings WHERE external_id='import:wp04-2'").fetchone()[0]
            assert avail == 'OUT_OF_SCOPE'
            assert con.execute('SELECT scope_changed_at FROM search_profiles WHERE id=?', (pid,)).fetchone()[0] is None
        finally:
            con.close()
        # Daarna gewoon verdwijnen: een auto die nu ontbreekt wordt "niet meer gezien".
        out = run(client, headers, pid, [])
        assert out['state'] == 'FAILED'  # lege controle met eerder aanbod: beschermd, niets gemarkeerd
        listing = next(x for x in client.get(f'/api/v1/listings?profile_id={pid}').json()['items']
                       if x['external_id'] == 'import:wp04-2')
        assert listing['availability'] == 'OUT_OF_SCOPE'
        summary = next(p for p in client.get('/api/v1/profiles').json()['items'] if p['id'] == pid)
        assert summary['listings_active'] == 1 and summary['last_run']['state'] == 'FAILED'
