"""SQLite schema and storage helpers. Database connection is never shared across threads."""
import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4
from app.config import settings


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def uid(prefix):
    return f'{prefix}_{uuid4().hex[:20]}'


def dumps(v):
    return json.dumps(v, ensure_ascii=False, separators=(',', ':'), default=str)


def connect():
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(settings.database_path), timeout=30, isolation_level=None)
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


def init_db():
    con = connect()
    try:
        con.executescript(SCHEMA)
        cols={r[1] for r in con.execute('PRAGMA table_info(listings)')}
        if 'photos_json' not in cols:
            con.execute("ALTER TABLE listings ADD COLUMN photos_json TEXT NOT NULL DEFAULT '[]'")
        if not con.execute('SELECT 1 FROM criteria LIMIT 1').fetchone():
            for key, label, group, weight, description, synonyms in DEFAULT_CRITERIA:
                con.execute('INSERT INTO criteria VALUES (?,?,?,?,?,?,?,?)',
                            (key, label, group, weight, description, dumps(synonyms), 1, now()))
    finally:
        con.close()


def rowdict(row):
    return dict(row) if row is not None else None


def log_event(con, run_id, stage, level, message, metrics=None):
    con.execute('INSERT INTO run_events(run_id,stage,level,message,metrics_json,created_at) VALUES (?,?,?,?,?,?)',
                (run_id, stage, level, message[:1000], dumps(metrics or {}), now()))
