"""Configuration for the Cookidoo Family Voting Bot."""

import os

# ─── Cookidoo ───────────────────────────────────────────────
COOKIDOO_EMAIL = os.environ.get("COOKIDOO_EMAIL", "")
COOKIDOO_PASSWORD = os.environ.get("COOKIDOO_PASSWORD", "")
COOKIDOO_COUNTRY = os.environ.get("COOKIDOO_COUNTRY", "de")      # de, at, ch, ...
COOKIDOO_LANGUAGE = os.environ.get("COOKIDOO_LANGUAGE", "de-DE")  # de-DE, de-AT, de-CH, ...
COOKIDOO_URL = os.environ.get("COOKIDOO_URL", "https://cookidoo.de/foundation/de-DE")

# ─── Telegram ───────────────────────────────────────────────
# Bot token from @BotFather
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
# Chat ID for the family group (use setup_chat_id.py to find it)
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ─── Voting ─────────────────────────────────────────────────
NUM_RECIPE_CANDIDATES = int(os.environ.get("NUM_RECIPE_CANDIDATES", "7"))
# Default voting duration. If VOTING_END_TIME_LOCAL is set, it takes precedence.
VOTING_DURATION_MINUTES = int(os.environ.get("VOTING_DURATION_MINUTES", "120"))

# Optional: set a fixed local end time (HH:MM) for the vote, e.g. "17:00".
# If set, the bot will compute duration "until that time" (same day, or next day if already past).
VOTING_END_TIME_LOCAL = os.environ.get("VOTING_END_TIME_LOCAL", "")

# Allow users to request a different voting end time (local time) via Telegram,
# e.g. "Liste bis 17:00 laufen lassen".
VOTING_DURATION_MAX_MINUTES = int(os.environ.get("VOTING_DURATION_MAX_MINUTES", "720"))

# Max difficulty level to include (easy/medium/difficult)
MAX_DIFFICULTY = os.environ.get("MAX_DIFFICULTY", "medium")

# ─── Recipe History ───────────────────────────────────────────
RECIPE_HISTORY_FILE = os.environ.get(
    "RECIPE_HISTORY_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "recipe_history.json"),
)
RECIPE_HISTORY_DAYS = int(os.environ.get("RECIPE_HISTORY_DAYS", "14"))
