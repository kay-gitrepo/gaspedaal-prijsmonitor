"""WP-12: herkomst van oordelen en herbeoordeling zonder controle."""
import sqlite3

from fastapi.testclient import TestClient

from app import worker
from app.db import MIGRATIONS, SCHEMA, connect, migrate
from app.main import app
from test_api import wait_run
from test_profiles import login, new_profile, run


def test_migration_sets_claim_source_from_reason():
    con = sqlite3.connect(':memory:', isolation_level=None)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    migrate(con, [m for m in MIGRATIONS if m[0] < 9], backup=False)
    con.execute("INSERT INTO criteria(key,label,group_name,weight,updated_at) VALUES('towbar','Trekhaak','MUST_HAVE',5,'x')")
    con.execute("INSERT INTO listings(id,external_id,title,price_eur,first_seen,last_seen,updated_at) "
                "VALUES('l','import:l','XC90',70000,'x','x','x')")
    rows = [('towbar', 'PRESENT', 'Lokale expliciete advertentievermelding', 'AD_TEXT'),
            ('a', 'UNKNOWN', 'Niet aangetoond in toegestane advertentietekst', 'AD_TEXT'),
            ('b', 'PRESENT', 'Expliciet genoemd', 'AD_TEXT'), ('c', 'ABSENT', 'Dealer belde', 'MANUAL_OVERRIDE')]
    for key, status, reason, source in rows:
        if key != 'towbar':
            con.execute("INSERT INTO criteria(key,label,group_name,weight,updated_at) VALUES(?,?,'NICE_TO_HAVE',1,'x')",
                        (key, key))
        con.execute('INSERT INTO claims(listing_id,criterion_key,status,reason,source,updated_at) VALUES(?,?,?,?,?,?)',
                    ('l', key, status, reason, source, 'x'))
    migrate(con, backup=False)
    sources = dict(con.execute('SELECT criterion_key,source FROM claims').fetchall())
    assert sources == {'towbar': 'LOCAL_RULE', 'a': 'NOT_MENTIONED', 'b': 'GEMINI', 'c': 'MANUAL_OVERRIDE'}
    assert 'integration_id' in {r[1] for r in con.execute('PRAGMA table_info(claims)')}


def test_reanalysis_only_assesses_without_fetching_or_disappearing(monkeypatch):
    with TestClient(app) as client:
        headers = login(client)
        pid = new_profile(client, headers, 'WP12 herbeoordeling', 'https://www.gaspedaal.nl/volvo/xc90/w12')
        run(client, headers, pid, [{'external_id': 'w12-1', 'title': 'XC90 a', 'price_eur': 70000,
                                    'description': 'Met trekhaak'},
                                   {'external_id': 'w12-2', 'title': 'XC90 b', 'price_eur': 71000}])
        con = connect()
        try:
            before_events = con.execute('SELECT COUNT(*) FROM listing_events').fetchone()[0]
            before_obs = con.execute('SELECT COUNT(*) FROM price_observations').fetchone()[0]
        finally:
            con.close()

        def no_source(profile):
            raise AssertionError('Een herbeoordeling mag de bron niet benaderen')
        monkeypatch.setattr(worker, 'provider_for', no_source)
        car = next(x for x in client.get(f'/api/v1/listings?profile_id={pid}').json()['items']
                   if x['external_id'] == 'import:w12-1')
        r = client.post(f"/api/v1/listings/{car['id']}/reanalyze", headers=headers)
        assert r.status_code == 202
        out = wait_run(client, r.json()['run_id'])
        assert out['state'] == 'COMPLETE' and out['trigger_source'] == 'REANALYSIS'
        assert out['summary']['analyzed'] == 1
        con = connect()
        try:
            assert con.execute('SELECT COUNT(*) FROM listing_events').fetchone()[0] == before_events
            assert con.execute('SELECT COUNT(*) FROM price_observations').fetchone()[0] == before_obs
            statuses = {r[0] for r in con.execute('SELECT status FROM profile_listings WHERE profile_id=?', (pid,))}
        finally:
            con.close()
        assert statuses == {'ACTIVE'}
        detail = client.get(f"/api/v1/listings/{car['id']}").json()
        towbar = next(c for c in detail['claims'] if c['criterion_key'] == 'towbar')
        assert towbar['source'] == 'LOCAL_RULE' and towbar['integration_id']
        assert 'Met trekhaak' in detail['assessed_text']
        log = client.get(f"/api/v1/integrations/{towbar['integration_id']}").json()
        assert any(c['criterion_key'] == 'towbar' and c['status'] == 'PRESENT' for c in log['claims'])
        # Herbeoordeling telt niet als controle van het aanbod.
        assert client.get('/api/v1/status').json()['last_run']['trigger_source'] != 'REANALYSIS'
        summary = client.get('/api/v1/integrations/summary').json()
        assert {'assessed', 'waiting', 'failed', 'tokens_month', 'max_per_run'} <= set(summary)
