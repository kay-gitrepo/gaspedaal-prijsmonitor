"""WP-07: bevestigde en mogelijke score, bewijsdekking en terugzetten van een eigen oordeel."""
from fastapi.testclient import TestClient

from app.main import app
from app.scoring import calculate
from test_api import wait_run
from test_profiles import login, new_profile, run

CRITERIA = [
    {'key': 'towbar', 'group_name': 'MUST_HAVE', 'weight': 5, 'enabled': 1},
    {'key': 'air', 'group_name': 'MUST_HAVE', 'weight': 5, 'enabled': 1},
    {'key': 'roof', 'group_name': 'NICE_TO_HAVE', 'weight': 3, 'enabled': 1},
    {'key': 'hud', 'group_name': 'NICE_TO_HAVE', 'weight': 1, 'enabled': 1},
]


def test_all_unknown_is_zero_confirmed_but_fully_possible():
    out = calculate(CRITERIA, {})
    assert out['score_total'] == 0 and out['score_potential'] == 100
    assert out['evidence_coverage'] == 0
    assert (out['must_present'], out['must_count'], out['must_unknown'], out['must_absent']) == (0, 2, 2, 0)
    assert out['eligibility'] == 'UNVERIFIED' and out['status_keys']['unknown'] == ['towbar', 'air']


def test_absent_must_lowers_potential_and_rejects():
    out = calculate(CRITERIA, {'towbar': 'ABSENT', 'air': 'PRESENT', 'roof': 'PRESENT'})
    assert out['eligibility'] == 'REJECTED' and out['status_keys']['absent'] == ['towbar']
    assert out['score_potential'] < 100
    # must: 50 % bevestigd, 50 % mogelijk; nice: 75 % bevestigd, 100 % mogelijk (hud onbekend)
    assert out['score_total'] == round(0.7 * 50 + 0.3 * 75, 1)
    assert out['score_potential'] == round(0.7 * 50 + 0.3 * 100, 1)
    # bekend: towbar (5) + air (5) + roof (3) van 14
    assert out['evidence_coverage'] == round(13 / 14 * 100, 1)


def test_conflict_counts_as_possible_and_uncertain():
    out = calculate(CRITERIA, {'towbar': 'PRESENT', 'air': 'CONFLICT', 'roof': 'ABSENT', 'hud': 'PRESENT'})
    assert out['score_potential'] > out['score_total']
    assert out['must_unknown'] == 1 and out['status_keys']['conflict'] == ['air']
    assert out['eligibility'] == 'UNVERIFIED'


def test_undo_manual_review_returns_to_automatic():
    with TestClient(app) as client:
        headers = login(client)
        pid = new_profile(client, headers, 'WP07 terug', 'https://www.gaspedaal.nl/volvo/xc90/terug07')
        run(client, headers, pid, [{'external_id': 'w7-1', 'title': 'XC90', 'price_eur': 70000,
                                    'description': 'Met trekhaak'}])
        car = next(x for x in client.get(f'/api/v1/listings?profile_id={pid}').json()['items'])
        r = client.post(f"/api/v1/listings/{car['id']}/review", headers=headers,
                        json={'criterion_key': 'towbar', 'status': 'ABSENT', 'evidence': 'Dealer: is verwijderd'})
        assert r.json()['score']['eligibility'] == 'REJECTED'
        detail = client.get(f"/api/v1/listings/{car['id']}").json()
        towbar = next(c for c in detail['claims'] if c['criterion_key'] == 'towbar')
        assert (towbar['status'], towbar['source']) == ('ABSENT', 'MANUAL_OVERRIDE')
        assert detail['status_reason']['absent'] == ['Trekhaak']
        back = client.delete(f"/api/v1/listings/{car['id']}/review/towbar", headers=headers)
        assert back.status_code == 200 and back.json()['score']['eligibility'] != 'REJECTED'
        assert wait_run(client, back.json()['run_id'])['state'] == 'COMPLETE'
        detail = client.get(f"/api/v1/listings/{car['id']}").json()
        towbar = next(c for c in detail['claims'] if c['criterion_key'] == 'towbar')
        assert towbar['status'] == 'PRESENT' and towbar['source'] == 'LOCAL_RULE' and towbar['integration_id']
        assert detail['analyzed_hash']
        assert client.delete(f"/api/v1/listings/{car['id']}/review/towbar", headers=headers).status_code == 404
