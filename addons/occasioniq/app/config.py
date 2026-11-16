"""Environment configuration. Never persist secrets to the database or logs."""
from dataclasses import dataclass
import os
from pathlib import Path

@dataclass(frozen=True)
class Settings:
    database_path: Path = Path(os.getenv('DATABASE_PATH', './data/monitor.sqlite3'))
    ui_password: str = os.getenv('UI_PASSWORD', '')
    session_secret: str = os.getenv('SESSION_SECRET', '')
    ha_refresh_token: str = os.getenv('HA_REFRESH_TOKEN', '')
    secure_cookies: bool = os.getenv('SECURE_COOKIES', 'false').lower() == 'true'
    gemini_api_key: str = os.getenv('GEMINI_API_KEY', '')
    gemini_model: str = os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')
    gemini_enabled: bool = os.getenv('GEMINI_ENABLED', 'true').lower() == 'true'
    max_gemini_calls_per_run: int = int(os.getenv('MAX_GEMINI_CALLS_PER_RUN', '20'))
    min_price: int = int(os.getenv('MIN_VALID_PRICE_EUR', '1000'))
    max_price: int = int(os.getenv('MAX_VALID_PRICE_EUR', '500000'))
    disappearance_days: int = int(os.getenv('DISAPPEARANCE_DAYS', '7'))
    retention_days: int = int(os.getenv('INTEGRATION_LOG_RETENTION_DAYS', '90'))
    data_source_approved: bool = os.getenv('DATA_SOURCE_APPROVED', 'false').lower() == 'true'
    gaspedaal_api_search_template: str = os.getenv('GASPEDAAL_API_SEARCH_TEMPLATE', '')
    gaspedaal_api_items_path: str = os.getenv('GASPEDAAL_API_ITEMS_PATH', 'data.results')
    gaspedaal_api_fields_json: str = os.getenv('GASPEDAAL_API_FIELDS_JSON', '{}')
    gaspedaal_api_max_pages: int = min(max(int(os.getenv('GASPEDAAL_API_MAX_PAGES', '10')), 1), 50)

settings = Settings()
