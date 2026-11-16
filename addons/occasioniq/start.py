"""Home Assistant Supervisor app launcher (options are supplied in /data/options.json)."""
import json
import os
import sys
from pathlib import Path

optpath=Path('/data/options.json')
if not optpath.is_file():
    print('Supervisor options.json ontbreekt. Start deze image alleen als Home Assistant app.', file=sys.stderr)
    sys.exit(1)
options=json.loads(optpath.read_text())
mapping={'ui_password':'UI_PASSWORD', 'session_secret':'SESSION_SECRET',
         'ha_refresh_token':'HA_REFRESH_TOKEN','gemini_api_key':'GEMINI_API_KEY',
         'gemini_model':'GEMINI_MODEL',
         'data_source_approved':'DATA_SOURCE_APPROVED',
         'gaspedaal_api_search_template':'GASPEDAAL_API_SEARCH_TEMPLATE',
         'gaspedaal_api_items_path':'GASPEDAAL_API_ITEMS_PATH',
         'gaspedaal_api_fields_json':'GASPEDAAL_API_FIELDS_JSON',
         'gaspedaal_api_max_pages':'GASPEDAAL_API_MAX_PAGES',
         'advertiser_detail_hosts':'ADVERTISER_DETAIL_HOSTS',
         'max_detail_fetches_per_run':'MAX_DETAIL_FETCHES_PER_RUN'}
for source,target in mapping.items():
    os.environ[target]=str(options.get(source) or '')
os.environ['DATABASE_PATH']='/data/prices.sqlite3'
os.environ['SECURE_COOKIES']='false'  # Direct access is LAN HTTP; use a trusted HTTPS proxy when remote.
os.execvp('uvicorn',['uvicorn','app.main:app','--host','0.0.0.0','--port','8099','--workers','1'])
