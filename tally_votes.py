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

from config import TELEGRAM_CHAT_ID
from cookidoo_client import RecipeCandidate, add_to_shopping_list
from telegram_client import (
    resolve_number_votes,
    send_result,
    send_no_votes_message,
    _call_telegram,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("tally_votes")

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vote_state.json")


def load_state() -> tuple[list[RecipeCandidate], str]:
    """Load candidates and message_id from state file."""
    with open(STATE_FILE) as f:
        state = json.load(f)

    candidates = [RecipeCandidate(**c) for c in state["candidates"]]
    message_id = state.get("message_id", "")
    return candidates, message_id


def collect_all_votes_once() -> dict[str, list[str]]:
    """
    Do a single pass through all pending Telegram updates.
    Returns {recipe_id: [voter_first_name, ...]}.
    """
    user_votes: dict[str, tuple[str, str]] = {}  # user_id -> (recipe_id, name)

    try:
        # Fetch all pending updates with autoPaging to get everything
        updates = _call_telegram("telegram_bot_api-list-updates", {
            "limit": 100,
            "autoPaging": True,
        })
        if not isinstance(updates, list):
            updates = []

        log.info("Found %d updates", len(updates))

        for update in updates:
            # Handle callback_query (inline button press)
            cb = update.get("callback_query")
            if cb:
                data = cb.get("data", "")
                if data.startswith("vote:"):
                    recipe_id = data.split(":", 1)[1]
                    user = cb.get("from", {})
                    user_id = str(user.get("id", ""))
                    first_name = user.get("first_name", "Unbekannt")
                    if user_id not in user_votes:
                        user_votes[user_id] = (recipe_id, first_name)
                        log.info("Vote: %s -> %s", first_name, recipe_id)
                    else:
                        log.info("Duplicate vote from %s ignored", first_name)

            # Handle text replies like "3"
            msg = update.get("message", {})
            if msg:
                text = (msg.get("text") or "").strip()
                if text.isdigit():
                    user = msg.get("from", {})
                    user_id = str(user.get("id", ""))
                    first_name = user.get("first_name", "Unbekannt")
                    if user_id not in user_votes:
                        user_votes[user_id] = (f"number:{text}", first_name)
                        log.info("Text vote: %s -> %s", first_name, text)
                    else:
                        log.info("Duplicate text vote from %s ignored", first_name)

    except Exception as e:
        log.warning("Error fetching updates: %s", e)

    # Aggregate
    result: dict[str, list[str]] = {}
    for uid, (recipe_id, name) in user_votes.items():
        result.setdefault(recipe_id, [])
        result[recipe_id].append(name)

    return result


async def main():
    if not os.path.exists(STATE_FILE):
        log.error("No vote_state.json found. Phase 1 hasn't run yet.")
        sys.exit(1)

    candidates, message_id = load_state()
    log.info("Loaded %d candidates from state", len(candidates))

    # Collect all votes (single pass)
    votes = collect_all_votes_once()

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
    winner_id = max(votes, key=lambda rid: len(votes[rid]))
    winner_voters = votes[winner_id]
    winner = next((c for c in candidates if c.id == winner_id), None)

    if not winner:
        log.error("Winner %s not in candidates!", winner_id)
        os.remove(STATE_FILE)
        return

    log.info("Winner: %s (%d votes from: %s)",
             winner.name, len(winner_voters), ", ".join(winner_voters))

    # Add to Cookidoo shopping list
    try:
        ingredients = await add_to_shopping_list(winner.id)
    except Exception as e:
        log.error("Shopping list error: %s", e)
        ingredients = winner.ingredients

    # Send result
    send_result(TELEGRAM_CHAT_ID, winner, winner_voters, ingredients)
    log.info("Done! Guten Appetit!")

    # Clean up
    os.remove(STATE_FILE)


if __name__ == "__main__":
    asyncio.run(main())
