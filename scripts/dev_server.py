"""Start OccasionIQ lokaal voor ontwikkeling op http://127.0.0.1:8099.

Zet alleen ontbrekende omgevingsvariabelen op duidelijke dev-waarden. Nooit in productie gebruiken.
Inloggen met het wachtwoord `dev`. Vul de database met `python scripts/seed_demo.py`.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEV_DEFAULTS = {
    'UI_PASSWORD': 'dev',
    'SESSION_SECRET': 'dev-session-secret-alleen-voor-lokaal-gebruik',
    'HA_REFRESH_TOKEN': 'dev-ha-refresh-token-alleen-voor-lokaal-gebruik',
    'DATABASE_PATH': str(ROOT / 'data' / 'dev.sqlite3'),
    'GEMINI_ENABLED': 'false',
}


def apply_dev_env():
    for key, value in DEV_DEFAULTS.items():
        os.environ.setdefault(key, value)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


if __name__ == '__main__':
    apply_dev_env()
    os.chdir(ROOT)
    import uvicorn
    print('OccasionIQ dev-server op http://127.0.0.1:8099 (wachtwoord: %s)' % os.environ['UI_PASSWORD'])
    uvicorn.run('app.main:app', host='127.0.0.1', port=8099, workers=1)
