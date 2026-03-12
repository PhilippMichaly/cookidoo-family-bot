"""Configuration — env vars with runtime JSON overrides."""

import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ─── Cookidoo ────────────────────────────────────────────
COOKIDOO_EMAIL = os.environ.get("COOKIDOO_EMAIL", "")
COOKIDOO_PASSWORD = os.environ.get("COOKIDOO_PASSWORD", "")
COOKIDOO_COUNTRY = os.environ.get("COOKIDOO_COUNTRY", "de")
COOKIDOO_LANGUAGE = os.environ.get("COOKIDOO_LANGUAGE", "de-DE")
COOKIDOO_URL = os.environ.get(
    "COOKIDOO_URL", "https://cookidoo.de/foundation/de-DE"
)

# ─── Telegram ────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
WEBHOOK_HOST = os.environ.get("WEBHOOK_HOST", "0.0.0.0")
WEBHOOK_PORT = int(os.environ.get("WEBHOOK_PORT", "8443"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")  # public URL for TG webhook

# ─── Defaults (overridable via /config in TG) ────────────
NUM_RECIPE_CANDIDATES = int(os.environ.get("NUM_RECIPE_CANDIDATES", "7"))
VOTING_DURATION_MINUTES = int(os.environ.get("VOTING_DURATION_MINUTES", "120"))
VOTING_DURATION_MAX_MINUTES = int(os.environ.get("VOTING_DURATION_MAX_MINUTES", "720"))
VOTING_START_CRON = os.environ.get("VOTING_START_CRON", "0 7 * * *")
VOTING_END_TIME_LOCAL = os.environ.get("VOTING_END_TIME_LOCAL", "")
MAX_DIFFICULTY = os.environ.get("MAX_DIFFICULTY", "medium")
RECIPE_HISTORY_DAYS = int(os.environ.get("RECIPE_HISTORY_DAYS", "14"))
CACHE_REFRESH_HOURS = int(os.environ.get("CACHE_REFRESH_HOURS", "24"))

# ─── Paths ───────────────────────────────────────────────
RUNTIME_CONFIG_FILE = DATA_DIR / "runtime_config.json"
RECIPE_HISTORY_FILE = DATA_DIR / "recipe_history.json"
VOTE_STATE_FILE = DATA_DIR / "vote_state.json"
CACHE_DB_FILE = DATA_DIR / "recipe_cache.db"
FILTERS_FILE = BASE_DIR / "filters.json"

# ─── Admin user IDs (can use /config) ────────────────────
_admin_raw = os.environ.get("ADMIN_USER_IDS", "")
ADMIN_USER_IDS: set[str] = {
    uid.strip() for uid in _admin_raw.split(",") if uid.strip()
}


def load_runtime_overrides() -> dict:
    """Load runtime config JSON (set via /config in TG)."""
    try:
        return json.loads(RUNTIME_CONFIG_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get(key: str):
    """Get config value: runtime override > env default."""
    overrides = load_runtime_overrides()
    env_defaults = {
        "num_candidates": NUM_RECIPE_CANDIDATES,
        "voting_minutes": VOTING_DURATION_MINUTES,
        "voting_end_time": VOTING_END_TIME_LOCAL,
        "max_difficulty": MAX_DIFFICULTY,
        "history_days": RECIPE_HISTORY_DAYS,
        "filter_sweets": True,
        "filter_drinks": True,
    }
    if key in overrides:
        return overrides[key]
    return env_defaults.get(key)
