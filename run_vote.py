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
    VOTING_DURATION_MAX_MINUTES,
)
from cookidoo_client import fetch_candidates
from telegram_client import send_vote, send_error_message, get_updates

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

    # Determine voting duration:
    # - default from env
    # - optionally overridden by a Telegram feature request like "bis 17:00"
    voting_minutes = VOTING_DURATION_MINUTES

    try:
        # Keep this optional and robust; if anything fails we fall back
        # to the configured default.
        from feature_requests import parse_feature_request, compute_voting_minutes_until
        from telegram_client import get_last_feature_request

        fr_text = get_last_feature_request(TELEGRAM_CHAT_ID)
        actions = parse_feature_request(fr_text)
        if actions.requested_end_time_local:
            requested = compute_voting_minutes_until(actions.requested_end_time_local)
            if 1 <= requested <= VOTING_DURATION_MAX_MINUTES:
                voting_minutes = requested
                log.info("Voting duration overridden by request '%s' -> %d minutes",
                         actions.requested_end_time_local, voting_minutes)
    except Exception as e:
        log.info("No voting duration override applied: %s", e)

    # Snapshot the current update_id before sending the vote.
    # Phase 2 uses this to ignore any older/stale updates.
    snapshot = get_updates(limit=1, timeout=0)
    last_update_id_before_vote = snapshot[-1]["update_id"] if snapshot else None

    # Send vote
    msg_id = send_vote(TELEGRAM_CHAT_ID, candidates, voting_minutes)

    # Save state
    state = {
        "message_id": msg_id,
        "last_update_id_before_vote": last_update_id_before_vote,
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
