"""WP-13: wensen per zoekopdracht."""
import sqlite3

from fastapi.testclient import TestClient

from app.config import settings
from app.db import MIGRATIONS, SCHEMA, migrate
from app.main import app
from test_api import wait_run
from test_profiles import login, new_profile, run


def old_database():
    con = sqlite3.connect(':memory:', isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    con.executescript(SCHEMA)
    migrate(con, [m for m in MIGRATIONS if m[0] <= 9], backup=False)
    return con


def test_migration_copies_wishes_and_keeps_manual_corrections():
    con = old_database()
    for pid in ('A', 'B'):
        con.execute('''INSERT INTO search_profiles(id,title,search_url,created_at,updated_at)
                       VALUES(?,?,?,?,?)''', (pid, pid, 'https://www.gaspedaal.nl/x', 'x', 'x'))
    con.execute("INSERT INTO criteria(key,label,group_name,weight,updated_at) VALUES('towbar','Trekhaak','MUST_HAVE',5,'x')")
    con.execute("INSERT INTO criteria(key,label,group_name,weight,updated_at) VALUES('roof','Dak','NICE_TO_HAVE',3,'x')")
    for lid, profiles in [('both', ('A', 'B')), ('only_a', ('A',))]:
        con.execute('''INSERT INTO listings(id,external_id,title,price_eur,first_seen,last_seen,updated_at,score_total,
                       eligibility,analyzed_hash) VALUES(?,?,?,?,?,?,?,?,?,?)''',
                    (lid, 'import:' + lid, lid, 70000, 'x', 'x', 'x', 75.0, 'MATCH', 'hash-' + lid))
        for pid in profiles:
            con.execute("INSERT INTO profile_listings(profile_id,listing_id,last_seen) VALUES(?,?,'x')", (pid, lid))
        con.execute('''INSERT INTO claims(listing_id,criterion_key,status,evidence,source,updated_at)
                       VALUES(?,'towbar','PRESENT','Dealer bevestigd','MANUAL_OVERRIDE','x')''', (lid,))
        con.execute('''INSERT INTO claims(listing_id,criterion_key,status,source,updated_at)
                       VALUES(?,'roof','UNKNOWN','NOT_MENTIONED','x')''', (lid,))
    target = settings.database_path.with_name(f'{settings.database_path.name}.bak-v9')
    if target.exists():
        target.unlink()
    assert migrate(con) == [10]
    assert target.exists()  # back-up vóór de migratie
    wishes = sorted(tuple(r) for r in con.execute('SELECT profile_id,key FROM criteria'))
    assert wishes == [('A', 'roof'), ('A', 'towbar'), ('B', 'roof'), ('B', 'towbar')]
    manual = sorted(tuple(r) for r in con.execute('''SELECT profile_id,listing_id,evidence FROM claims
                                                     WHERE source='MANUAL_OVERRIDE' '''))
    assert manual == [('A', 'both', 'Dealer bevestigd'), ('A', 'only_a', 'Dealer bevestigd'),
                      ('B', 'both', 'Dealer bevestigd')]
    scores = {(r[0], r[1]): (r[2], r[3]) for r in con.execute(
        'SELECT profile_id,listing_id,score_total,analyzed_hash FROM profile_listings')}
    assert scores[('B', 'both')] == (75.0, 'hash-both')
    assert 'score_total' not in {r[1] for r in con.execute('PRAGMA table_info(listings)')}
    assert not con.execute('PRAGMA foreign_key_check').fetchall()


def test_two_searches_with_different_wishes_give_different_scores():
    with TestClient(app) as client:
        headers = login(client)
        a = new_profile(client, headers, 'WP13 A', 'https://www.gaspedaal.nl/volvo/xc90/w13a')
        b = new_profile(client, headers, 'WP13 B', 'https://www.gaspedaal.nl/volvo/xc90/w13b')
        car = {'external_id': 'w13-1', 'title': 'XC90 w13', 'price_eur': 70000, 'description': 'Geen trekhaak. Panoramadak.'}
        run(client, headers, a, [car])
        run(client, headers, b, [car])
        # In B is de trekhaak geen eis: een nice-to-have.
        towbar = next(c for c in client.get(f'/api/v1/criteria?profile_id={b}').json()['items'] if c['key'] == 'towbar')
        body = {k: towbar[k] for k in ('label', 'weight', 'description', 'synonyms', 'match_terms')}
        assert client.put(f'/api/v1/criteria/towbar?profile_id={b}', headers=headers,
                          json={**body, 'group_name': 'NICE_TO_HAVE', 'enabled': True}).status_code == 200
        in_a = client.get(f'/api/v1/listings?profile_id={a}').json()['items'][0]
        in_b = client.get(f'/api/v1/listings?profile_id={b}').json()['items'][0]
        assert in_a['id'] == in_b['id']
        assert in_a['eligibility'] == 'REJECTED' and in_b['eligibility'] != 'REJECTED'
        assert in_a['score_total'] != in_b['score_total']
        assert (in_a['score_profile_title'], in_b['score_profile_title']) == ('WP13 A', 'WP13 B')
        detail_b = client.get(f"/api/v1/listings/{in_a['id']}?profile_id={b}").json()
        assert detail_b['score_profile_id'] == b and {p['id'] for p in detail_b['profiles']} == {a, b}
        # Een eigen correctie geldt voor de zoekopdracht waarin hij is gemaakt.
        client.post(f"/api/v1/listings/{in_a['id']}/review", headers=headers,
                    json={'profile_id': b, 'criterion_key': 'panoramic_roof', 'status': 'ABSENT'})
        roof_a = next(c for c in client.get(f"/api/v1/listings/{in_a['id']}?profile_id={a}").json()['claims']
                      if c['criterion_key'] == 'panoramic_roof')
        assert roof_a['status'] == 'PRESENT' and roof_a['source'] != 'MANUAL_OVERRIDE'
        # Zonder keuze is een zoekopdracht verplicht voor wensen.
        assert client.get('/api/v1/criteria').status_code == 422


def test_copy_wishes_from_another_search():
    with TestClient(app) as client:
        headers = login(client)
        src = new_profile(client, headers, 'WP13 bron', 'https://www.gaspedaal.nl/volvo/xc90/w13src')
        dst = new_profile(client, headers, 'WP13 doel', 'https://www.gaspedaal.nl/volvo/xc90/w13dst')
        run(client, headers, dst, [{'external_id': 'w13-c', 'title': 'XC90 c', 'price_eur': 70000,
                                    'description': 'Elektrische achterklep'}])
        client.post('/api/v1/criteria', headers=headers, json={'profile_id': src, 'label': 'Elektrische achterklep',
                                                                'group_name': 'MUST_HAVE',
                                                                'match_terms': ['elektrische achterklep']})
        client.delete(f'/api/v1/criteria/hud?profile_id={src}', headers=headers)
        r = client.post('/api/v1/criteria/copy', headers=headers, json={'from_profile_id': src, 'to_profile_id': dst})
        assert r.status_code == 200 and r.json()['run_id']
        wait_run(client, r.json()['run_id'])
        keys = {c['key'] for c in client.get(f'/api/v1/criteria?profile_id={dst}').json()['items']}
        assert 'elektrische_achterklep' in keys and 'hud' not in keys
        car = client.get(f'/api/v1/listings?profile_id={dst}').json()['items'][0]
        claim = next(c for c in client.get(f"/api/v1/listings/{car['id']}?profile_id={dst}").json()['claims']
                     if c['criterion_key'] == 'elektrische_achterklep')
        assert claim['status'] == 'PRESENT'
        bad = client.post('/api/v1/criteria/copy', headers=headers, json={'from_profile_id': dst, 'to_profile_id': dst})
        assert bad.status_code == 422
