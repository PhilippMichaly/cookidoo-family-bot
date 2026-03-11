#!/usr/bin/env python3
"""
Phase 2: Tally votes, announce winner, build shopping list.
Reads state from vote_state.json (created by Phase 1).
Does a single pass through Telegram updates to collect all votes.
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

from config import TELEGRAM_CHAT_ID
from cookidoo_client import RecipeCandidate, add_to_shopping_list
from telegram_client import (
    collect_all_votes_once,
    resolve_number_votes,
    send_result,
    send_no_votes_message,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("tally_votes")

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vote_state.json")


def load_state() -> tuple[list[RecipeCandidate], str, int | None]:
    """Load candidates, message_id and min_update_id from state file."""
    with open(STATE_FILE) as f:
        state = json.load(f)

    candidates = [RecipeCandidate(**c) for c in state["candidates"]]
    message_id = state.get("message_id", "")
    min_update_id = state.get("last_update_id_before_vote")
    return candidates, message_id, min_update_id


async def main():
    if not os.path.exists(STATE_FILE):
        log.error("No vote_state.json found. Phase 1 hasn't run yet.")
        sys.exit(1)

    candidates, message_id, min_update_id = load_state()
    log.info("Loaded %d candidates from state (min_update_id=%s)",
             len(candidates), min_update_id)

    # Collect all votes (single pass), ignoring updates before the vote was sent
    votes = collect_all_votes_once(min_update_id=min_update_id)

    if not votes or all(len(v) == 0 for v in votes.values()):
        log.info("No votes received.")
        send_no_votes_message(TELEGRAM_CHAT_ID)
        # Clean up
        os.remove(STATE_FILE)
        return

    # Resolve number-based votes
    votes = resolve_number_votes(votes, candidates)

    if not votes:
        send_no_votes_message(TELEGRAM_CHAT_ID)
        os.remove(STATE_FILE)
        return

    # Determine winner
    from voting import determine_winner
    try:
        winner, winner_voters, is_tie, tied_names = determine_winner(votes, candidates)
    except ValueError as e:
        log.error(str(e))
        os.remove(STATE_FILE)
        return

    # Add to Cookidoo shopping list
    try:
        ingredients = await add_to_shopping_list(winner.id)
    except Exception as e:
        log.error("Shopping list error: %s", e)
        ingredients = winner.ingredients

    # Send result
    send_result(TELEGRAM_CHAT_ID, winner, winner_voters, ingredients,
                is_tie=is_tie, tied_names=tied_names)

    from cookidoo_client import save_winner_to_history
    save_winner_to_history(winner.id, winner.name)
    log.info("Done! Guten Appetit!")

    # Print result as JSON
    print(json.dumps({
        "status": "ok",
        "winner": winner.name,
        "winner_id": winner.id,
        "voters": winner_voters,
        "ingredients": ingredients,
        "is_tie": is_tie,
    }, ensure_ascii=False))

    # Clean up
    os.remove(STATE_FILE)


if __name__ == "__main__":
    asyncio.run(main())
