"""WP-06: wensen toevoegen, lokale herkenning en direct herrekenen zonder nieuwe AI-beoordeling."""
from fastapi.testclient import TestClient

from app.db import connect
from app.extraction import local_claims
from app.main import app
from app.worker import get_criteria
from test_profiles import login, new_profile, run


def claims_for(external_id):
    con = connect()
    try:
        return dict(con.execute('''SELECT c.criterion_key,c.status FROM claims c JOIN listings l ON l.id=c.listing_id
                                   WHERE l.external_id=?''', (external_id,)).fetchall())
    finally:
        con.close()


def criterion(client, key):
    return next(c for c in client.get('/api/v1/criteria').json()['items'] if c['key'] == key)


def put(client, headers, c, **changes):
    body = {k: c[k] for k in ('label', 'group_name', 'weight', 'description', 'synonyms', 'match_terms')}
    body['enabled'] = bool(c['enabled'])
    body.update(changes)
    r = client.put(f"/api/v1/criteria/{c['key']}", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_weight_change_recalculates_without_reassessment():
    with TestClient(app) as client:
        headers = login(client)
        pid = new_profile(client, headers, 'WP06 gewicht', 'https://www.gaspedaal.nl/volvo/xc90/gewicht')
        cars = [{'external_id': 'w6-1', 'title': 'XC90 a', 'price_eur': 70000,
                 'description': 'Trekhaak. Panoramadak.'}]
        run(client, headers, pid, cars)
        con = connect()
        try:
            before = dict(con.execute('''SELECT analyzed_hash,score_total,eligibility FROM listings
                                         WHERE external_id='import:w6-1' ''').fetchone())
            calls = con.execute('SELECT COUNT(*) FROM integration_requests').fetchone()[0]
        finally:
            con.close()
        roof = criterion(client, 'panoramic_roof')
        out = put(client, headers, roof, weight=5, group_name='MUST_HAVE')
        assert out['reassess'] is False
        con = connect()
        try:
            after = dict(con.execute('''SELECT analyzed_hash,score_total,eligibility FROM listings
                                        WHERE external_id='import:w6-1' ''').fetchone())
            assert con.execute('SELECT COUNT(*) FROM integration_requests').fetchone()[0] == calls
        finally:
            con.close()
        assert after['analyzed_hash'] == before['analyzed_hash'] is not None
        assert after['score_total'] != before['score_total']
        # De volgende controle hergebruikt de beoordeling: gewicht zit niet in de vingerafdruk.
        out = run(client, headers, pid, cars)
        assert out['summary']['cache_hits'] == 1
        put(client, headers, criterion(client, 'panoramic_roof'), weight=roof['weight'], group_name=roof['group_name'])


def test_new_wish_is_recognised_locally_with_negation_and_hedge():
    with TestClient(app) as client:
        headers = login(client)
        pid = new_profile(client, headers, 'WP06 nieuw', 'https://www.gaspedaal.nl/volvo/xc90/nieuw')
        run(client, headers, pid, [
            {'external_id': 'w6-a', 'title': 'XC90 a', 'price_eur': 70000, 'description': 'Met elektrische achterklep.'},
            {'external_id': 'w6-b', 'title': 'XC90 b', 'price_eur': 70000, 'description': 'Geen elektrische achterklep, wel trekhaak.'},
            {'external_id': 'w6-c', 'title': 'XC90 c', 'price_eur': 70000,
             'description': 'Elektrische achterklep tegen meerprijs.'},
        ])
        r = client.post('/api/v1/criteria', headers=headers, json={
            'label': 'Elektrische achterklep', 'group_name': 'MUST_HAVE', 'weight': 4,
            'match_terms': ['elektrische achterklep', 'elektrisch bedienbare achterklep']})
        assert r.status_code == 201
        key = r.json()['key']
        assert key == 'elektrische_achterklep'
        assert claims_for('import:w6-a')[key] == 'PRESENT'
        assert claims_for('import:w6-b')[key] == 'ABSENT'
        assert claims_for('import:w6-b')['towbar'] == 'PRESENT'  # ontkenning geldt alleen voor het eigen zinsdeel
        assert claims_for('import:w6-c')[key] == 'UNKNOWN'
        # Tweede wens met hetzelfde label krijgt een uniek volgnummer; verwijderen bewaart de beoordelingen.
        again = client.post('/api/v1/criteria', headers=headers, json={'label': 'Elektrische achterklep'})
        assert again.json()['key'] == 'elektrische_achterklep_2'
        for k in (key, 'elektrische_achterklep_2'):
            assert client.delete(f'/api/v1/criteria/{k}', headers=headers).status_code == 200
        assert key not in [c['key'] for c in client.get('/api/v1/criteria').json()['items']]
        assert claims_for('import:w6-a')[key] == 'PRESENT'


def test_19_inch_wheels_are_not_22_inch():
    con = connect()
    try:
        criteria = get_criteria(con)
    finally:
        con.close()
    assert 'wheels_22' not in local_claims('Mooie 19 inch velgen en nieuwe wielen', criteria)
    assert local_claims('22 inch velgen', criteria)['wheels_22']['status'] == 'PRESENT'
    assert all('velgen' not in c['match_terms'] and 'wielen' not in c['match_terms'] for c in criteria)


def test_suggestion_without_ai_returns_empty_lists():
    with TestClient(app) as client:
        headers = login(client)
        r = client.post('/api/v1/criteria/suggest', headers=headers, json={'label': 'Stoelverwarming'})
        assert r.status_code == 200
        assert r.json() == {'description': '', 'synonyms': [], 'match_terms': [], 'let_op': [], 'ai_beschikbaar': False}
