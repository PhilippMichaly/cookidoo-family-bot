#!/usr/bin/env python3
"""
Phase 1: Fetch recipes and send voting message.
Saves state to a JSON file for Phase 2 to pick up.
"""

import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

from config import (
    COOKIDOO_EMAIL,
    TELEGRAM_CHAT_ID,
    TELEGRAM_BOT_TOKEN,
    NUM_RECIPE_CANDIDATES,
    VOTING_DURATION_MINUTES,
)
from cookidoo_client import fetch_candidates
from telegram_client import send_vote, send_error_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("run_vote")

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vote_state.json")


async def main():
    # Validate config
    missing = []
    if not COOKIDOO_EMAIL:
        missing.append("COOKIDOO_EMAIL")
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")
    if missing:
        log.error("Missing environment variables: %s", ", ".join(missing))
        log.error("Copy .env.example to .env and fill in your values.")
        sys.exit(1)

    # Fetch candidates
    log.info("Fetching %d candidates ...", NUM_RECIPE_CANDIDATES)
    try:
        candidates = await fetch_candidates(num=NUM_RECIPE_CANDIDATES)
    except Exception as e:
        log.error("Failed: %s", e)
        send_error_message(TELEGRAM_CHAT_ID, str(e))
        sys.exit(1)

    if not candidates:
        send_error_message(TELEGRAM_CHAT_ID, "Keine Rezepte gefunden.")
        sys.exit(1)

    # Send vote
    msg_id = send_vote(TELEGRAM_CHAT_ID, candidates, VOTING_DURATION_MINUTES)

    # Save state
    state = {
        "message_id": msg_id,
        "candidates": [
            {
                "id": c.id,
                "name": c.name,
                "total_time": c.total_time,
                "difficulty": c.difficulty,
                "serving_size": c.serving_size,
                "url": c.url,
                "ingredients": c.ingredients,
            }
            for c in candidates
        ],
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    log.info("Vote sent. %d candidates. State saved.", len(candidates))
    print(json.dumps({"status": "ok", "candidates": len(candidates), "message_id": msg_id}))


if __name__ == "__main__":
    asyncio.run(main())
