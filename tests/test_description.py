"""WP-05: zelf geplakte advertentietekst blijft behouden en telt mee voor de beoordeling."""
from fastapi.testclient import TestClient

from app.db import connect
from app.main import app
from test_profiles import login, new_profile, run


def listing(external_id):
    con = connect()
    try:
        return dict(con.execute('SELECT * FROM listings WHERE external_id=?', (external_id,)).fetchone())
    finally:
        con.close()


def test_manual_text_survives_later_checks():
    with TestClient(app) as client:
        headers = login(client)
        pid = new_profile(client, headers, 'WP05 tekst', 'https://www.gaspedaal.nl/volvo/xc90/tekst')
        run(client, headers, pid, [{'external_id': 'txt-1', 'title': 'XC90 tekst', 'price_eur': 70000}])
        car = listing('import:txt-1')
        assert car['description'] == '' and car['description_source'] is None
        items = client.get(f'/api/v1/listings?profile_id={pid}').json()['items']
        assert items[0]['has_text'] == 0
        r = client.post(f'/api/v1/listings/{car["id"]}/description', headers=headers,
                        json={'text': 'Elektrisch uitklapbare trekhaak en 22 inch velgen.'})
        assert r.status_code == 200 and r.json()['description_source'] == 'MANUAL'
        assert listing('import:txt-1')['analyzed_hash'] is None
        # Een latere controle met (andere) brontekst overschrijft de handmatige tekst niet,
        # en de herbeoordeling gebruikt die tekst.
        run(client, headers, pid, [{'external_id': 'txt-1', 'title': 'XC90 tekst', 'price_eur': 69000,
                                    'description': 'Geen trekhaak'}])
        car = listing('import:txt-1')
        assert car['description_source'] == 'MANUAL'
        assert car['description'].startswith('Elektrisch uitklapbare trekhaak')
        detail = client.get(f'/api/v1/listings/{car["id"]}').json()
        towbar = next(c for c in detail['claims'] if c['criterion_key'] == 'towbar')
        assert towbar['status'] == 'PRESENT'
        # Leeg maken haalt de handmatige tekst weg; daarna mag de bron weer tekst leveren.
        client.post(f'/api/v1/listings/{car["id"]}/description', headers=headers, json={'text': ''})
        run(client, headers, pid, [{'external_id': 'txt-1', 'title': 'XC90 tekst', 'price_eur': 69000,
                                    'description': 'Geen trekhaak'}])
        car = listing('import:txt-1')
        assert (car['description'], car['description_source']) == ('Geen trekhaak', 'SOURCE')


def test_dashboard_reports_text_coverage():
    with TestClient(app) as client:
        headers = login(client)
        pid = new_profile(client, headers, 'WP05 dekking', 'https://www.gaspedaal.nl/volvo/xc90/dekking')
        run(client, headers, pid, [
            {'external_id': 'cov-1', 'title': 'XC90 a', 'price_eur': 70000, 'description': 'Met trekhaak'},
            {'external_id': 'cov-2', 'title': 'XC90 b', 'price_eur': 71000}])
        d = client.get(f'/api/v1/dashboard?profile_id={pid}').json()
        assert d['active_listings'] == 2 and d['with_text'] == 1
