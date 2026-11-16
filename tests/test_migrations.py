import sqlite3

from app.db import MIGRATIONS, SCHEMA, migrate, schema_version


def fresh_connection():
    con = sqlite3.connect(':memory:', isolation_level=None)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def test_migrations_run_exactly_once():
    calls = []

    def first(con):
        calls.append(1)
        con.execute('CREATE TABLE extra(x INTEGER)')

    def second(con):
        calls.append(2)
        con.execute('INSERT INTO extra VALUES (42)')

    con = fresh_connection()
    assert migrate(con, [(1, first), (2, second)], backup=False) == [1, 2]
    assert migrate(con, [(1, first), (2, second)], backup=False) == []
    assert calls == [1, 2]
    assert con.execute('SELECT COUNT(*) FROM extra').fetchone()[0] == 1
    assert schema_version(con) == 2


def test_failed_migration_rolls_back_and_retries_later():
    def broken(con):
        con.execute('CREATE TABLE half(x INTEGER)')
        raise RuntimeError('stop')

    con = fresh_connection()
    try:
        migrate(con, [(1, broken)], backup=False)
    except RuntimeError:
        pass
    assert schema_version(con) == 0
    assert not con.execute("SELECT 1 FROM sqlite_master WHERE name='half'").fetchone()


def test_real_migrations_are_idempotent_on_existing_columns():
    con = fresh_connection()
    con.execute("ALTER TABLE listings ADD COLUMN photos_json TEXT NOT NULL DEFAULT '[]'")
    applied = migrate(con, backup=False)
    assert applied == [v for v, _ in MIGRATIONS]
    assert migrate(con, backup=False) == []
