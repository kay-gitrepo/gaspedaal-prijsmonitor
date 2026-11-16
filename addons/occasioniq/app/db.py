"""SQLite schema and storage helpers. Database connection is never shared across threads."""
import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4
from app.config import settings
from app.extraction import DEFAULT_MATCH_TERMS


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def uid(prefix):
    return f'{prefix}_{uuid4().hex[:20]}'


def dumps(v):
    return json.dumps(v, ensure_ascii=False, separators=(',', ':'), default=str)


def connect():
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    # FastAPI may open a request's connection in one worker thread and use it in another (never concurrently),
    # so the same-thread check is disabled; each request and the worker still get their own connection.
    con = sqlite3.connect(str(settings.database_path), timeout=30, isolation_level=None, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA busy_timeout=30000')
    return con

SCHEMA = '''
CREATE TABLE IF NOT EXISTS search_profiles (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, search_url TEXT NOT NULL, provider TEXT NOT NULL DEFAULT 'fixture',
 fixture_payload TEXT, enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS criteria (
 key TEXT PRIMARY KEY, label TEXT NOT NULL, group_name TEXT NOT NULL CHECK(group_name IN ('MUST_HAVE','NICE_TO_HAVE')),
 weight INTEGER NOT NULL CHECK(weight BETWEEN 1 AND 5), description TEXT NOT NULL DEFAULT '',
 synonyms_json TEXT NOT NULL DEFAULT '[]', enabled INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS listings (
 id TEXT PRIMARY KEY, external_id TEXT NOT NULL UNIQUE, title TEXT NOT NULL, url TEXT, year INTEGER, kilometers INTEGER,
 trim TEXT, seller TEXT, price_eur INTEGER NOT NULL, description TEXT NOT NULL DEFAULT '', text_hash TEXT NOT NULL DEFAULT '',
 first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, updated_at TEXT NOT NULL, availability TEXT NOT NULL DEFAULT 'ACTIVE',
 favorite INTEGER NOT NULL DEFAULT 0, analyzed_hash TEXT, score_total REAL NOT NULL DEFAULT 0,
 score_must REAL NOT NULL DEFAULT 0, score_nice REAL NOT NULL DEFAULT 0, eligibility TEXT NOT NULL DEFAULT 'UNVERIFIED'
);
CREATE TABLE IF NOT EXISTS profile_listings (
 profile_id TEXT NOT NULL REFERENCES search_profiles(id) ON DELETE CASCADE,
 listing_id TEXT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
 last_seen TEXT NOT NULL, missing_since TEXT, missing_checks INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'ACTIVE', PRIMARY KEY(profile_id,listing_id)
);
CREATE TABLE IF NOT EXISTS refresh_runs (
 id TEXT PRIMARY KEY, trigger_source TEXT NOT NULL, state TEXT NOT NULL, scope_json TEXT NOT NULL,
 request_hash TEXT NOT NULL, idempotency_key TEXT, created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
 summary_json TEXT NOT NULL DEFAULT '{}', error TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_created ON refresh_runs(created_at DESC);
CREATE TABLE IF NOT EXISTS trigger_attempts (
 id TEXT PRIMARY KEY, source TEXT NOT NULL, run_id TEXT, outcome TEXT NOT NULL, details_json TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES refresh_runs(id),
 stage TEXT NOT NULL, level TEXT NOT NULL, message TEXT NOT NULL, metrics_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS price_observations (
 id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES refresh_runs(id),
 profile_id TEXT NOT NULL REFERENCES search_profiles(id), listing_id TEXT NOT NULL REFERENCES listings(id),
 price_eur INTEGER NOT NULL, observed_at TEXT NOT NULL,
 UNIQUE(run_id,profile_id,listing_id)
);
CREATE INDEX IF NOT EXISTS idx_observations_listing ON price_observations(listing_id,observed_at);
CREATE TABLE IF NOT EXISTS listing_sources (
 listing_id TEXT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
 portal_id TEXT NOT NULL, site TEXT NOT NULL, kind TEXT,
 click_url TEXT, source_url TEXT, price_eur INTEGER,
 first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
 PRIMARY KEY(listing_id,portal_id)
);
CREATE TABLE IF NOT EXISTS source_price_observations (
 run_id TEXT NOT NULL REFERENCES refresh_runs(id),
 listing_id TEXT NOT NULL REFERENCES listings(id),
 portal_id TEXT NOT NULL, site TEXT NOT NULL,
 price_eur INTEGER NOT NULL, observed_at TEXT NOT NULL,
 PRIMARY KEY(run_id,listing_id,portal_id)
);
CREATE TABLE IF NOT EXISTS source_detail_attempts (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES refresh_runs(id),
 listing_id TEXT NOT NULL REFERENCES listings(id), portal_id TEXT,
 source_url TEXT, status TEXT NOT NULL, text_length INTEGER,
 error TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS listing_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES refresh_runs(id),
 listing_id TEXT NOT NULL REFERENCES listings(id), event_type TEXT NOT NULL,
 previous_price INTEGER, new_price INTEGER, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS claims (
 listing_id TEXT NOT NULL REFERENCES listings(id) ON DELETE CASCADE, criterion_key TEXT NOT NULL REFERENCES criteria(key),
 status TEXT NOT NULL, evidence TEXT, reason TEXT, confidence REAL NOT NULL DEFAULT 0,
 source TEXT NOT NULL DEFAULT 'AD_TEXT', updated_at TEXT NOT NULL,
 PRIMARY KEY(listing_id,criterion_key)
);
CREATE TABLE IF NOT EXISTS integration_requests (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES refresh_runs(id), listing_id TEXT NOT NULL REFERENCES listings(id),
 kind TEXT NOT NULL DEFAULT 'GEMINI', decision TEXT NOT NULL, model_id TEXT, request_json TEXT, response_json TEXT,
 parsed_json TEXT, tokens_in INTEGER, tokens_out INTEGER, duration_ms INTEGER, error TEXT,
 text_hash TEXT, criteria_hash TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_integration_date ON integration_requests(created_at DESC);
CREATE TABLE IF NOT EXISTS negotiation_notes (
 id TEXT PRIMARY KEY, listing_id TEXT NOT NULL REFERENCES listings(id), offer_eur INTEGER,
 actual_purchase_price INTEGER, note TEXT NOT NULL, created_at TEXT NOT NULL
);
'''

DEFAULT_CRITERIA = [
 ('towbar','Trekhaak','MUST_HAVE',5,'Aanwezige trekhaak, niet slechts voorbereiding',['trekhaak','towbar','anhängerkupplung']),
 ('wheels_22','22-inch velgen','NICE_TO_HAVE',5,'Gemonteerde 22 inch velgen of wielen',['22 inch','22-inch','22"',"22''",'22”','velgen','wielen']),
 ('air_suspension','Luchtvering','NICE_TO_HAVE',4,'Luchtvering aanwezig',['luchtvering','air suspension','four-c']),
 ('pilot_assist','Pilot Assist','NICE_TO_HAVE',4,'Pilot Assist, niet alleen adaptieve cruisecontrol',['pilot assist','stuurassistent']),
 ('hud','Head-updisplay','NICE_TO_HAVE',3,'Projectie van rijinformatie op de voorruit',['head-up','hud','head up display']),
 ('camera_360','360°-camera','NICE_TO_HAVE',3,'360-graden surround camera',['360 camera','360°','surround view']),
 ('panoramic_roof','Panoramadak','NICE_TO_HAVE',3,'Panoramisch glazen dak',['panoramadak','panoramic roof']),
 ('premium_audio','Premium audio','NICE_TO_HAVE',3,'Bowers & Wilkins of andere expliciet gespecificeerde premium audio',['bowers','wilkins','harman kardon']),
 ('ventilated_seats','Geventileerde stoelen','NICE_TO_HAVE',2,'Actieve ventilatie van voorstoelen',['stoelventilatie','geventileerde stoelen','ventilated seats']),
 ('massage_seats','Massagestoelen','NICE_TO_HAVE',2,'Massagefunctie in stoelen',['massagefunctie','massagestoelen','massage seats']),
]


def columns(con, table):
    return {r[1] for r in con.execute(f'PRAGMA table_info({table})')}


def add_column(con, table, name, definition):
    """Idempotent ALTER TABLE: databases from before the migration mechanism may already have the column."""
    if name not in columns(con, table):
        con.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')


def _m1_photos(con):
    add_column(con, 'listings', 'photos_json', "TEXT NOT NULL DEFAULT '[]'")


def _m2_license_plate(con):
    add_column(con, 'listings', 'license_plate', 'TEXT')


def merge_listings(con, keep, drop):
    """Fold vehicle row `drop` into `keep` without losing history; `drop` is deleted afterwards.

    Price observations are never changed except for their vehicle reference. Manual evidence wins over
    automatic claims; the most recently seen row supplies the current listing fields.
    """
    k = con.execute('SELECT * FROM listings WHERE id=?', (keep,)).fetchone()
    d = con.execute('SELECT * FROM listings WHERE id=?', (drop,)).fetchone()
    for table in ('listing_events', 'integration_requests', 'negotiation_notes', 'source_detail_attempts'):
        con.execute(f'UPDATE {table} SET listing_id=? WHERE listing_id=?', (keep, drop))
    con.execute('UPDATE OR IGNORE price_observations SET listing_id=? WHERE listing_id=?', (keep, drop))
    if con.execute('SELECT 1 FROM price_observations WHERE listing_id=?', (drop,)).fetchone():
        raise RuntimeError(f'Samenvoegen {drop} → {keep}: dubbele prijsobservatie in dezelfde controle')
    con.execute('''INSERT OR IGNORE INTO source_price_observations(run_id,listing_id,portal_id,site,price_eur,observed_at)
                   SELECT run_id,?,portal_id,site,price_eur,observed_at FROM source_price_observations
                   WHERE listing_id=?''', (keep, drop))
    con.execute('DELETE FROM source_price_observations WHERE listing_id=?', (drop,))
    con.execute('''INSERT OR IGNORE INTO listing_sources(listing_id,portal_id,site,kind,click_url,source_url,price_eur,
                   first_seen,last_seen) SELECT ?,portal_id,site,kind,click_url,source_url,price_eur,first_seen,last_seen
                   FROM listing_sources WHERE listing_id=?''', (keep, drop))
    con.execute('DELETE FROM listing_sources WHERE listing_id=?', (drop,))
    for claim in con.execute('SELECT * FROM claims WHERE listing_id=?', (drop,)).fetchall():
        own = con.execute('SELECT * FROM claims WHERE listing_id=? AND criterion_key=?',
                          (keep, claim['criterion_key'])).fetchone()
        manual = claim['source'] == 'MANUAL_OVERRIDE'
        own_manual = own is not None and own['source'] == 'MANUAL_OVERRIDE'
        if own is None or (manual and (not own_manual or claim['updated_at'] > own['updated_at'])):
            con.execute('''INSERT OR REPLACE INTO claims(listing_id,criterion_key,status,evidence,reason,confidence,
                           source,updated_at) VALUES(?,?,?,?,?,?,?,?)''',
                        (keep, claim['criterion_key'], claim['status'], claim['evidence'], claim['reason'],
                         claim['confidence'], claim['source'], claim['updated_at']))
    con.execute('DELETE FROM claims WHERE listing_id=?', (drop,))
    for entry in con.execute('SELECT * FROM profile_listings WHERE listing_id=?', (drop,)).fetchall():
        own = con.execute('SELECT * FROM profile_listings WHERE profile_id=? AND listing_id=?',
                          (entry['profile_id'], keep)).fetchone()
        if own is None:
            con.execute('UPDATE profile_listings SET listing_id=? WHERE profile_id=? AND listing_id=?',
                        (keep, entry['profile_id'], drop))
            continue
        if entry['last_seen'] > own['last_seen']:
            con.execute('''UPDATE profile_listings SET last_seen=?,missing_since=?,missing_checks=?,status=?
                           WHERE profile_id=? AND listing_id=?''',
                        (entry['last_seen'], entry['missing_since'], entry['missing_checks'], entry['status'],
                         entry['profile_id'], keep))
        con.execute('DELETE FROM profile_listings WHERE profile_id=? AND listing_id=?', (entry['profile_id'], drop))
    newest = d if d['last_seen'] > k['last_seen'] else k
    description = newest['description'] if newest['description'].strip() else (
        k['description'] if k['description'].strip() else d['description'])
    text_hash = newest['text_hash'] if newest['description'].strip() else (
        k['text_hash'] if k['description'].strip() else d['text_hash'])
    con.execute('''UPDATE listings SET title=?,url=?,year=?,kilometers=?,trim=?,seller=?,price_eur=?,photos_json=?,
                   description=?,text_hash=?,first_seen=?,last_seen=?,updated_at=?,favorite=?,
                   license_plate=COALESCE(license_plate,?),analyzed_hash=NULL WHERE id=?''',
                (newest['title'], newest['url'], newest['year'], newest['kilometers'], newest['trim'],
                 newest['seller'], newest['price_eur'], newest['photos_json'], description, text_hash,
                 min(k['first_seen'], d['first_seen']), max(k['last_seen'], d['last_seen']), now(),
                 max(k['favorite'], d['favorite']), d['license_plate'], keep))
    con.execute('DELETE FROM listings WHERE id=?', (drop,))
    refresh_availability(con, [keep])


# Active anywhere wins; then 'not seen recently'; then off market. OUT_OF_SCOPE (outside a changed search)
# counts neither as active nor as disappeared. Rows without any membership keep their value.
AVAILABILITY_CASE = '''CASE
    WHEN EXISTS (SELECT 1 FROM profile_listings p WHERE p.listing_id=listings.id AND p.status='ACTIVE') THEN 'ACTIVE'
    WHEN EXISTS (SELECT 1 FROM profile_listings p WHERE p.listing_id=listings.id AND p.status='MISSING_UNCONFIRMED')
      THEN 'MISSING_UNCONFIRMED'
    WHEN EXISTS (SELECT 1 FROM profile_listings p WHERE p.listing_id=listings.id AND p.status='OFF_MARKET') THEN 'OFF_MARKET'
    WHEN EXISTS (SELECT 1 FROM profile_listings p WHERE p.listing_id=listings.id AND p.status='OUT_OF_SCOPE')
      THEN 'OUT_OF_SCOPE'
    ELSE availability END'''


def refresh_availability(con, listing_ids):
    for listing_id in listing_ids:
        con.execute(f'UPDATE listings SET availability={AVAILABILITY_CASE} WHERE id=?', (listing_id,))


def identity_target(con, row):
    """New vehicle key per source namespace (WP-02): `gaspedaal:<id>` or `import:<id>`."""
    prefix, sep, rest = row['external_id'].partition(':')
    if not sep or prefix in ('gaspedaal', 'import'):
        return row['external_id']
    if prefix == 'gaspedaal_site':
        return f'gaspedaal:{rest}'
    if prefix == 'fixture':
        # A JSON-import profile without payload was read live from the search URL (fallback in provider_for).
        live = [r[0] for r in con.execute('''SELECT sp.fixture_payload IS NULL FROM profile_listings pl
                    JOIN search_profiles sp ON sp.id=pl.profile_id WHERE pl.listing_id=?''', (row['id'],))]
        return f'gaspedaal:{rest}' if live and all(live) else f'import:{rest}'
    return row['external_id']


def _m3_vehicle_identity(con):
    rows = con.execute('SELECT id,external_id,first_seen FROM listings').fetchall()
    groups = {}
    for row in rows:
        groups.setdefault(identity_target(con, row), []).append(row)
    for target, members in groups.items():
        members.sort(key=lambda r: (r['first_seen'], r['id']))
        keeper = members[0]
        for other in members[1:]:
            merge_listings(con, keeper['id'], other['id'])
        if keeper['external_id'] != target:
            con.execute('UPDATE listings SET external_id=? WHERE id=?', (target, keeper['id']))


_m3_vehicle_identity.changes_data = True


def _m4_profile_management(con):
    add_column(con, 'search_profiles', 'budget_eur', 'INTEGER')
    add_column(con, 'search_profiles', 'archived_at', 'TEXT')
    add_column(con, 'search_profiles', 'scope_changed_at', 'TEXT')


def _m5_description_source(con):
    """Where the ad text came from: SOURCE (search result), DETAIL_PAGE (advertiser page) or MANUAL (pasted)."""
    add_column(con, 'listings', 'description_source', 'TEXT')
    con.execute("""UPDATE listings SET description_source=CASE
        WHEN EXISTS (SELECT 1 FROM source_detail_attempts a WHERE a.listing_id=listings.id AND a.status='SUCCESS')
          THEN 'DETAIL_PAGE' ELSE 'SOURCE' END
        WHERE description_source IS NULL AND TRIM(description)!=''""")


_m5_description_source.changes_data = True


def _m6_criteria_terms(con):
    """Safe local match terms per wish, and a log of AI suggestions for new wishes."""
    add_column(con, 'criteria', 'match_terms_json', "TEXT NOT NULL DEFAULT '[]'")
    for key, terms in DEFAULT_MATCH_TERMS.items():
        con.execute("UPDATE criteria SET match_terms_json=? WHERE key=? AND match_terms_json='[]'", (dumps(terms), key))
    con.execute('''CREATE TABLE IF NOT EXISTS criterion_suggestions (
        id TEXT PRIMARY KEY, label TEXT NOT NULL, model_id TEXT, request_json TEXT, response_json TEXT,
        parsed_json TEXT, tokens_in INTEGER, tokens_out INTEGER, duration_ms INTEGER, error TEXT, created_at TEXT NOT NULL)''')


SCORE_COLUMNS = ('score_total', 'score_must', 'score_nice', 'eligibility', 'score_potential', 'evidence_coverage',
                 'must_present', 'must_count', 'must_unknown', 'must_absent', 'status_keys_json')


def score_values(score):
    """Column values for SCORE_COLUMNS from a scoring.calculate() result."""
    return (score['score_total'], score['score_must'], score['score_nice'], score['eligibility'],
            score['score_potential'], score['evidence_coverage'], score['must_present'], score['must_count'],
            score['must_unknown'], score['must_absent'], dumps(score['status_keys']))


def _m7_score_uncertainty(con):
    """Confirmed vs. possible score, evidence coverage and must-have counts per car (WP-07)."""
    from app.scoring import calculate
    for name, definition in [('score_potential', 'REAL NOT NULL DEFAULT 0'), ('evidence_coverage', 'REAL NOT NULL DEFAULT 0'),
                             ('must_present', 'INTEGER NOT NULL DEFAULT 0'), ('must_count', 'INTEGER NOT NULL DEFAULT 0'),
                             ('must_unknown', 'INTEGER NOT NULL DEFAULT 0'), ('must_absent', 'INTEGER NOT NULL DEFAULT 0'),
                             ('status_keys_json', "TEXT NOT NULL DEFAULT '{}'")]:
        add_column(con, 'listings', name, definition)
    criteria = [dict(r) for r in con.execute('SELECT key,group_name,weight,enabled FROM criteria WHERE enabled=1')]
    for (listing_id,) in con.execute('SELECT id FROM listings').fetchall():
        claims = {r[0]: r[1] for r in con.execute('SELECT criterion_key,status FROM claims WHERE listing_id=?',
                                                   (listing_id,))}
        score = calculate(criteria, claims)
        con.execute(f'UPDATE listings SET {",".join(c + "=?" for c in SCORE_COLUMNS)} WHERE id=?',
                    (*score_values(score), listing_id))


_m7_score_uncertainty.changes_data = True


def _m8_own_amounts(con):
    """Eigen openingsbod, streefprijs en grens per auto (WP-10); leeg = het voorstel geldt."""
    for name in ('my_opening', 'my_target', 'my_max'):
        add_column(con, 'listings', name, 'INTEGER')


def _m9_claim_provenance(con):
    """Herkomst per oordeel (WP-12): LOCAL_RULE, GEMINI, NOT_MENTIONED of MANUAL_OVERRIDE, met verwijzing naar het log."""
    add_column(con, 'claims', 'integration_id', 'TEXT')
    con.execute("""UPDATE claims SET source=CASE
        WHEN reason='Lokale expliciete advertentievermelding' THEN 'LOCAL_RULE'
        WHEN reason='Niet aangetoond in toegestane advertentietekst' THEN 'NOT_MENTIONED'
        ELSE 'GEMINI' END WHERE source='AD_TEXT'""")


_m9_claim_provenance.changes_data = True


PROFILE_SCORE_COLUMNS = SCORE_COLUMNS + ('analyzed_hash',)


def _m10_wishes_per_profile(con):
    """Wensen per zoekopdracht (WP-13).

    - criteria krijgt sleutel (profile_id, key); claims krijgt profile_id in de sleutel. Elke bestaande zoekopdracht
      krijgt een kopie van de huidige wensen en van de oordelen over de auto's in die zoekopdracht (ook eigen correcties).
    - Scorevelden en analyzed_hash verhuizen van listings naar profile_listings: één auto kan in twee zoekopdrachten
      vallen met verschillende wensen.
    """
    profiles = [r[0] for r in con.execute('SELECT id FROM search_profiles')]
    con.execute('''CREATE TABLE criteria_new (
        profile_id TEXT NOT NULL REFERENCES search_profiles(id) ON DELETE CASCADE, key TEXT NOT NULL,
        label TEXT NOT NULL, group_name TEXT NOT NULL CHECK(group_name IN ('MUST_HAVE','NICE_TO_HAVE')),
        weight INTEGER NOT NULL CHECK(weight BETWEEN 1 AND 5), description TEXT NOT NULL DEFAULT '',
        synonyms_json TEXT NOT NULL DEFAULT '[]', match_terms_json TEXT NOT NULL DEFAULT '[]',
        enabled INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL, PRIMARY KEY(profile_id, key))''')
    for pid in profiles:
        con.execute('''INSERT INTO criteria_new(profile_id,key,label,group_name,weight,description,synonyms_json,
                       match_terms_json,enabled,updated_at) SELECT ?,key,label,group_name,weight,description,
                       synonyms_json,match_terms_json,enabled,updated_at FROM criteria''', (pid,))
    con.execute('''CREATE TABLE claims_new (
        profile_id TEXT NOT NULL, listing_id TEXT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
        criterion_key TEXT NOT NULL, status TEXT NOT NULL, evidence TEXT, reason TEXT,
        confidence REAL NOT NULL DEFAULT 0, source TEXT NOT NULL DEFAULT 'AD_TEXT', updated_at TEXT NOT NULL,
        integration_id TEXT, PRIMARY KEY(profile_id, listing_id, criterion_key),
        FOREIGN KEY(profile_id, criterion_key) REFERENCES criteria(profile_id, key) ON DELETE CASCADE)''')
    columns = 'listing_id,criterion_key,status,evidence,reason,confidence,source,updated_at,integration_id'
    con.execute(f'''INSERT INTO claims_new(profile_id,{columns}) SELECT pl.profile_id,{",".join("c." + x for x in
                columns.split(","))} FROM claims c JOIN profile_listings pl ON pl.listing_id=c.listing_id''')
    # Oordelen over auto's zonder zoekopdracht gaan niet verloren: die krijgt elke zoekopdracht.
    for pid in profiles:
        con.execute(f'''INSERT OR IGNORE INTO claims_new(profile_id,{columns}) SELECT ?,{columns} FROM claims c
                        WHERE NOT EXISTS (SELECT 1 FROM profile_listings pl WHERE pl.listing_id=c.listing_id)''', (pid,))
    con.execute('DROP TABLE claims')
    con.execute('DROP TABLE criteria')
    con.execute('ALTER TABLE criteria_new RENAME TO criteria')
    con.execute('ALTER TABLE claims_new RENAME TO claims')
    con.execute('CREATE INDEX IF NOT EXISTS idx_claims_listing ON claims(listing_id)')
    for name, definition in [('score_total', 'REAL NOT NULL DEFAULT 0'), ('score_must', 'REAL NOT NULL DEFAULT 0'),
                             ('score_nice', 'REAL NOT NULL DEFAULT 0'),
                             ('eligibility', "TEXT NOT NULL DEFAULT 'UNVERIFIED'"),
                             ('score_potential', 'REAL NOT NULL DEFAULT 0'), ('evidence_coverage', 'REAL NOT NULL DEFAULT 0'),
                             ('must_present', 'INTEGER NOT NULL DEFAULT 0'), ('must_count', 'INTEGER NOT NULL DEFAULT 0'),
                             ('must_unknown', 'INTEGER NOT NULL DEFAULT 0'), ('must_absent', 'INTEGER NOT NULL DEFAULT 0'),
                             ('status_keys_json', "TEXT NOT NULL DEFAULT '{}'"), ('analyzed_hash', 'TEXT')]:
        add_column(con, 'profile_listings', name, definition)
    assignments = ','.join(f'{c}=(SELECT l.{c} FROM listings l WHERE l.id=profile_listings.listing_id)'
                           for c in PROFILE_SCORE_COLUMNS)
    con.execute(f'UPDATE profile_listings SET {assignments}')
    for c in PROFILE_SCORE_COLUMNS:
        if c in columns_of(con, 'listings'):
            con.execute(f'ALTER TABLE listings DROP COLUMN {c}')
    add_column(con, 'integration_requests', 'profile_id', 'TEXT')
    con.execute('''UPDATE integration_requests SET profile_id=(SELECT MIN(pl.profile_id) FROM profile_listings pl
                   WHERE pl.listing_id=integration_requests.listing_id)
                   WHERE (SELECT COUNT(*) FROM profile_listings pl WHERE pl.listing_id=integration_requests.listing_id)=1''')
    broken = con.execute('PRAGMA foreign_key_check').fetchall()
    if broken:
        raise RuntimeError(f'Migratie 10: {len(broken)} verwijzingen kloppen niet; niets gewijzigd')


def columns_of(con, table):
    return columns(con, table)


_m10_wishes_per_profile.changes_data = True
_m10_wishes_per_profile.foreign_keys_off = True


# (versie, functie). Functies met attribuut `changes_data = True` wijzigen bestaande rijen;
# vóór de eerste daarvan wordt een back-up van het databasebestand gemaakt.
MIGRATIONS = [
    (1, _m1_photos),
    (2, _m2_license_plate),
    (3, _m3_vehicle_identity),
    (4, _m4_profile_management),
    (5, _m5_description_source),
    (6, _m6_criteria_terms),
    (7, _m7_score_uncertainty),
    (8, _m8_own_amounts),
    (9, _m9_claim_provenance),
    (10, _m10_wishes_per_profile),
]


def schema_version(con):
    con.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
    return con.execute('SELECT COALESCE(MAX(version),0) FROM schema_migrations').fetchone()[0]


def backup_database(con, version):
    """Consistent copy via the SQLite backup API (safe with WAL), to `<pad>.bak-v<schemaversie>`."""
    target = settings.database_path.with_name(f'{settings.database_path.name}.bak-v{version}')
    dest = sqlite3.connect(str(target))
    try:
        con.backup(dest)
    finally:
        dest.close()
    return target


def migrate(con, migrations=None, backup=True):
    """Run missing migrations in order, each in its own transaction. Returns applied versions."""
    migrations = MIGRATIONS if migrations is None else migrations
    current = schema_version(con)
    done = {r[0] for r in con.execute('SELECT version FROM schema_migrations')}
    pending = [(v, fn) for v, fn in sorted(migrations, key=lambda m: m[0]) if v not in done]
    has_data = con.execute('SELECT EXISTS(SELECT 1 FROM listings) OR EXISTS(SELECT 1 FROM refresh_runs)').fetchone()[0]
    backed_up = False
    applied = []
    for version, fn in pending:
        if backup and has_data and not backed_up and getattr(fn, 'changes_data', False):
            backup_database(con, current)
            backed_up = True
        foreign_keys_off = getattr(fn, 'foreign_keys_off', False)
        if foreign_keys_off:
            con.execute('PRAGMA foreign_keys=OFF')
        con.execute('BEGIN IMMEDIATE')
        try:
            fn(con)
            con.execute('INSERT INTO schema_migrations(version,applied_at) VALUES(?,?)', (version, now()))
            con.execute('COMMIT')
        except Exception:
            con.execute('ROLLBACK')
            raise
        finally:
            if foreign_keys_off:
                con.execute('PRAGMA foreign_keys=ON')
        applied.append(version)
        current = version
    return applied


def insert_default_criteria(con, profile_id):
    """Standaardwensen voor een nieuwe zoekopdracht (aan te passen of te kopiëren van een andere)."""
    for key, label, group, weight, description, synonyms in DEFAULT_CRITERIA:
        con.execute('''INSERT OR IGNORE INTO criteria(profile_id,key,label,group_name,weight,description,synonyms_json,
                       enabled,updated_at,match_terms_json) VALUES (?,?,?,?,?,?,?,?,?,?)''',
                    (profile_id, key, label, group, weight, description, dumps(synonyms), 1, now(),
                     dumps(DEFAULT_MATCH_TERMS.get(key, []))))


def init_db():
    con = connect()
    try:
        con.executescript(SCHEMA)
        migrate(con)
    finally:
        con.close()


def rowdict(row):
    return dict(row) if row is not None else None


def log_event(con, run_id, stage, level, message, metrics=None):
    con.execute('INSERT INTO run_events(run_id,stage,level,message,metrics_json,created_at) VALUES (?,?,?,?,?,?)',
                (run_id, stage, level, message[:1000], dumps(metrics or {}), now()))
