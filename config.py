"""Configuration for the Cookidoo Family Voting Bot."""

import os

# ─── Cookidoo ───────────────────────────────────────────────
COOKIDOO_EMAIL = os.environ.get("COOKIDOO_EMAIL", "")
COOKIDOO_PASSWORD = os.environ.get("COOKIDOO_PASSWORD", "")
COOKIDOO_COUNTRY = os.environ.get("COOKIDOO_COUNTRY", "de")      # de, at, ch, ...
COOKIDOO_LANGUAGE = os.environ.get("COOKIDOO_LANGUAGE", "de-DE")  # de-DE, de-AT, de-CH, ...
COOKIDOO_URL = os.environ.get("COOKIDOO_URL", "https://cookidoo.de/foundation/de-DE")

# ─── Telegram ───────────────────────────────────────────────
# Chat ID for the family group (or private chat for testing).
# Use /chatid command with the bot or check get_updates.
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ─── Voting ─────────────────────────────────────────────────
NUM_RECIPE_CANDIDATES = int(os.environ.get("NUM_RECIPE_CANDIDATES", "7"))
VOTING_DURATION_MINUTES = int(os.environ.get("VOTING_DURATION_MINUTES", "120"))

# Max difficulty level to include (easy/medium/difficult)
MAX_DIFFICULTY = os.environ.get("MAX_DIFFICULTY", "medium")
