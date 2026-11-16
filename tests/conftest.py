import os
import tempfile
from pathlib import Path

# These values are for local, isolated tests only, never production.
_testdir = tempfile.TemporaryDirectory()
os.environ['DATABASE_PATH'] = str(Path(_testdir.name)/'tests.sqlite3')
os.environ['UI_PASSWORD'] = 'not-a-real-password'
os.environ['SESSION_SECRET'] = 'not-a-real-secret-for-tests-only-not-a-real-secret'
os.environ['HA_REFRESH_TOKEN'] = 'not-a-real-ha-refresh-token-for-tests'
os.environ['GEMINI_ENABLED'] = 'false'
