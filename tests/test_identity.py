"""WP-02: stabiele voertuigidentiteit, samenvoegen bij migratie, ongeldige prijzen en terugkeer."""
import sqlite3

from fastapi.testclient import TestClient

from app import worker
from app.db import SCHEMA, connect, dumps, init_db, migrate, uid
from app.main import app
from app.provider import Snapshot
from test_api import wait_run

OLD_SCHEMA_STEPS = 2  # migraties vóór de identiteitsmigratie


def memory_db():
    con = sqlite3.connect(':memory:', isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    con.executescript(SCHEMA)
    from app.db import MIGRATIONS
    migrate(con, [m for m in MIGRATIONS if m[0] <= OLD_SCHEMA_STEPS], backup=False)
    return con


def add_profile(con, pid, payload):
    con.execute('''INSERT INTO search_profiles(id,title,search_url,provider,fixture_payload,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?)''', (pid, pid, 'https://www.gaspedaal.nl/volvo', 'fixture', payload,
                                               '2026-01-01', '2026-01-01'))


def add_run(con, rid, when):
    con.execute('''INSERT INTO refresh_runs(id,trigger_source,state,scope_json,request_hash,created_at)
                   VALUES(?,?,?,?,?,?)''', (rid, 'TEST', 'COMPLETE', '"all"', 'x', when))


def add_listing(con, lid, ext, first_seen, last_seen, price, favorite=0, description=''):
    con.execute('''INSERT INTO listings(id,external_id,title,price_eur,description,first_seen,last_seen,updated_at,
                   favorite) VALUES(?,?,?,?,?,?,?,?,?)''',
                (lid, ext, 'Volvo ' + lid, price, description, first_seen, last_seen, last_seen, favorite))


def observe(con, rid, pid, lid, price, when):
    con.execute('INSERT INTO price_observations(run_id,profile_id,listing_id,price_eur,observed_at) VALUES(?,?,?,?,?)',
                (rid, pid, lid, price, when))


def member(con, pid, lid, last_seen, status='ACTIVE'):
    con.execute('INSERT INTO profile_listings(profile_id,listing_id,last_seen,status) VALUES(?,?,?,?)',
                (pid, lid, last_seen, status))


def test_migration_without_collision():
    con = memory_db()
    add_profile(con, 'live', None)
    add_profile(con, 'json', '{}')
    for lid, ext, pid in [('a', 'gaspedaal_site:1', 'live'), ('b', 'fixture:2', 'json'), ('c', 'fixture:3', 'live')]:
        add_listing(con, lid, ext, '2026-01-01', '2026-01-02', 50000)
        member(con, pid, lid, '2026-01-02')
    migrate(con, backup=False)
    ids = dict(con.execute('SELECT id,external_id FROM listings').fetchall())
    assert ids == {'a': 'gaspedaal:1', 'b': 'import:2', 'c': 'gaspedaal:3'}


def test_migration_merges_collision_keeping_all_history():
    con = memory_db()
    add_profile(con, 'live', None)
    add_profile(con, 'site', None)
    for rid, when in [('r1', '2026-01-01T07:00:00'), ('r2', '2026-01-02T07:00:00'), ('r3', '2026-01-03T07:00:00')]:
        add_run(con, rid, when)
    # Oude rij via de terugval (fixture zonder JSON) en nieuwere rij na omschakelen naar de zoeklink.
    add_listing(con, 'old', 'fixture:9', '2026-01-01T07:00:00', '2026-01-02T07:00:00', 60000, description='Trekhaak')
    add_listing(con, 'new', 'gaspedaal_site:9', '2026-01-03T07:00:00', '2026-01-03T07:00:00', 58000, favorite=1)
    observe(con, 'r1', 'live', 'old', 61000, '2026-01-01T07:00:00')
    observe(con, 'r2', 'live', 'old', 60000, '2026-01-02T07:00:00')
    observe(con, 'r3', 'site', 'new', 58000, '2026-01-03T07:00:00')
    member(con, 'live', 'old', '2026-01-02T07:00:00')
    member(con, 'site', 'new', '2026-01-03T07:00:00')
    con.execute("INSERT INTO criteria(key,label,group_name,weight,updated_at) VALUES('towbar','Trekhaak','MUST_HAVE',5,'x')")
    con.execute('''INSERT INTO claims(listing_id,criterion_key,status,source,updated_at)
                   VALUES('old','towbar','PRESENT','MANUAL_OVERRIDE','2026-01-02')''')
    con.execute('''INSERT INTO claims(listing_id,criterion_key,status,source,updated_at)
                   VALUES('new','towbar','UNKNOWN','AD_TEXT','2026-01-03')''')
    con.execute("INSERT INTO listing_events(run_id,listing_id,event_type,new_price,created_at) "
                "VALUES('r1','old','FIRST_SEEN',61000,'2026-01-01T07:00:00')")
    con.execute("INSERT INTO listing_events(run_id,listing_id,event_type,new_price,created_at) "
                "VALUES('r3','new','FIRST_SEEN',58000,'2026-01-03T07:00:00')")
    migrate(con, backup=False)
    rows = con.execute('SELECT * FROM listings').fetchall()
    assert len(rows) == 1
    car = rows[0]
    assert (car['id'], car['external_id']) == ('old', 'gaspedaal:9')
    assert car['first_seen'] == '2026-01-01T07:00:00' and car['last_seen'] == '2026-01-03T07:00:00'
    assert car['price_eur'] == 58000 and car['favorite'] == 1 and car['description'] == 'Trekhaak'
    prices = [r[0] for r in con.execute('SELECT price_eur FROM price_observations WHERE listing_id=? '
                                        'ORDER BY observed_at', ('old',))]
    assert prices == [61000, 60000, 58000]
    assert con.execute("SELECT COUNT(*) FROM listing_events WHERE listing_id='old'").fetchone()[0] == 2
    claim = con.execute("SELECT status,source FROM claims WHERE listing_id='old'").fetchone()
    assert tuple(claim) == ('PRESENT', 'MANUAL_OVERRIDE')
    assert {r[0] for r in con.execute("SELECT profile_id FROM profile_listings WHERE listing_id='old'")} == {
        'live', 'site'}


class FakeProvider:
    def __init__(self, source, ads):
        self.snapshot = Snapshot(complete=True, metadata={'source': source}, listings=ads)

    def fetch(self, profile):
        return self.snapshot


def test_switching_provider_keeps_the_same_vehicle(monkeypatch):
    init_db()
    con = connect()
    try:
        pid = uid('sp')
        con.execute('''INSERT INTO search_profiles(id,title,search_url,provider,created_at,updated_at)
                       VALUES(?,?,?,?,?,?)''', (pid, 'Wissel', 'https://www.gaspedaal.nl/volvo', 'gaspedaal_site',
                                                 'x', 'x'))
        ad = {'external_id': 'switch-1', 'title': 'Volvo XC90', 'price_eur': 70000}
        for source, provider in [('GASPEDAAL_SEARCH_URL', 'gaspedaal_site'), ('GASPEDAAL_DIRECT_API', 'gaspedaal')]:
            con.execute('UPDATE search_profiles SET provider=? WHERE id=?', (provider, pid))
            rid = uid('rr')
            add_run(con, rid, 'x')
            monkeypatch.setattr(worker, 'provider_for', lambda p, s=source: FakeProvider(s, [ad]))
            profile = con.execute('SELECT * FROM search_profiles WHERE id=?', (pid,)).fetchone()
            worker.scan_profile(con, rid, profile, worker.get_criteria(con))
        rows = con.execute('''SELECT l.external_id FROM listings l JOIN profile_listings p ON p.listing_id=l.id
                              WHERE p.profile_id=?''', (pid,)).fetchall()
        assert [r[0] for r in rows] == ['gaspedaal:switch-1']
        assert con.execute('''SELECT COUNT(*) FROM price_observations WHERE profile_id=?''', (pid,)).fetchone()[0] == 2
    finally:
        con.close()


def snapshot(*prices):
    return {'complete': True, 'listings': [
        {'external_id': f'wp02-{i}', 'title': f'XC90 wp02 {i}', 'price_eur': p} for i, p in enumerate(prices) if p]}


def run(client, headers, pid, payload):
    assert client.post(f'/api/v1/profiles/{pid}/snapshot', json=payload, headers=headers).status_code == 200
    started = client.post('/api/v1/refresh-runs', json={'scope': {'profile_ids': [pid]}}, headers=headers)
    assert started.status_code == 202, started.text
    return wait_run(client, started.json()['run_id'])


def statuses(pid):
    con = connect()
    try:
        return dict(con.execute('''SELECT l.external_id,p.status FROM profile_listings p
                                   JOIN listings l ON l.id=p.listing_id WHERE p.profile_id=?''', (pid,)).fetchall())
    finally:
        con.close()


def test_invalid_price_skips_ad_but_keeps_it_seen():
    with TestClient(app) as client:
        headers = {'X-CSRF-Token': client.post('/api/v1/login', json={'password': 'not-a-real-password'}).json()['csrf']}
        pid = client.post('/api/v1/profiles', headers=headers, json={
            'title': 'WP02 prijs', 'search_url': 'https://www.gaspedaal.nl/volvo/xc90/prijs'}).json()['id']
        assert run(client, headers, pid, snapshot(70000, 72000))['state'] == 'COMPLETE'
        out = run(client, headers, pid, snapshot(70000, 500))
        assert out['state'] == 'COMPLETE'
        assert out['summary']['skipped_invalid'] == 1
        assert statuses(pid) == {'import:wp02-0': 'ACTIVE', 'import:wp02-1': 'ACTIVE'}
        con = connect()
        try:
            prices = [r[0] for r in con.execute('''SELECT o.price_eur FROM price_observations o JOIN listings l
                         ON l.id=o.listing_id WHERE l.external_id='import:wp02-1' ''')]
        finally:
            con.close()
        assert prices == [72000]


def test_gone_and_back_records_one_reappearance():
    with TestClient(app) as client:
        headers = {'X-CSRF-Token': client.post('/api/v1/login', json={'password': 'not-a-real-password'}).json()['csrf']}
        pid = client.post('/api/v1/profiles', headers=headers, json={
            'title': 'WP02 terug', 'search_url': 'https://www.gaspedaal.nl/volvo/xc90/terug'}).json()['id']
        run(client, headers, pid, {'complete': True, 'listings': [
            {'external_id': 'back-1', 'title': 'XC90 a', 'price_eur': 70000},
            {'external_id': 'back-2', 'title': 'XC90 b', 'price_eur': 71000}]})
        run(client, headers, pid, {'complete': True, 'listings': [
            {'external_id': 'back-1', 'title': 'XC90 a', 'price_eur': 70000}]})
        assert statuses(pid)['import:back-2'] == 'MISSING_UNCONFIRMED'
        out = run(client, headers, pid, {'complete': True, 'listings': [
            {'external_id': 'back-1', 'title': 'XC90 a', 'price_eur': 70000},
            {'external_id': 'back-2', 'title': 'XC90 b', 'price_eur': 69000}]})
        assert out['summary']['reappeared'] == 1
        assert statuses(pid)['import:back-2'] == 'ACTIVE'
        con = connect()
        try:
            events = [tuple(r) for r in con.execute('''SELECT e.event_type,e.new_price FROM listing_events e
                JOIN listings l ON l.id=e.listing_id WHERE l.external_id='import:back-2' AND e.event_type='REAPPEARED' ''')]
        finally:
            con.close()
        assert events == [('REAPPEARED', 69000)]
        assert dumps(out['summary'])
