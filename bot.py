#!/usr/bin/env python3
"""
Cookidoo Family Voting Bot
===========================
1. Fetches recipe candidates from your Cookidoo collections
2. Sends a Telegram vote with inline buttons
3. Collects votes for a configurable period
4. Announces the winner with a shopping list
5. Saves the shopping list to Cookidoo
"""

import asyncio
import logging
import sys

from config import (
    COOKIDOO_EMAIL,
    TELEGRAM_CHAT_ID,
    NUM_RECIPE_CANDIDATES,
    VOTING_DURATION_MINUTES,
)
from cookidoo_client import fetch_candidates, add_to_shopping_list
from telegram_client import (
    send_vote,
    collect_votes,
    resolve_number_votes,
    send_result,
    send_no_votes_message,
    send_error_message,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("bot")


def validate_config():
    """Check that all required config is set."""
    missing = []
    if not COOKIDOO_EMAIL:
        missing.append("COOKIDOO_EMAIL")
    if not TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")
    if missing:
        log.error("Missing environment variables: %s", ", ".join(missing))
        sys.exit(1)


async def run():
    """Main bot flow."""
    validate_config()

    # ── Step 1: Fetch recipe candidates ──────────────────────
    log.info("Fetching %d recipe candidates from Cookidoo ...", NUM_RECIPE_CANDIDATES)
    try:
        candidates = await fetch_candidates(num=NUM_RECIPE_CANDIDATES)
    except Exception as e:
        log.error("Failed to fetch recipes: %s", e)
        send_error_message(TELEGRAM_CHAT_ID, f"Konnte keine Rezepte laden: {e}")
        return

    if not candidates:
        log.warning("No recipe candidates found!")
        send_error_message(TELEGRAM_CHAT_ID, "Keine Rezepte in deinen Sammlungen gefunden.")
        return

    log.info("Got %d candidates", len(candidates))

    # ── Step 2: Send vote to Telegram ────────────────────────
    log.info("Sending vote to Telegram chat %s ...", TELEGRAM_CHAT_ID)
    try:
        msg_id = send_vote(TELEGRAM_CHAT_ID, candidates, VOTING_DURATION_MINUTES)
    except Exception as e:
        log.error("Failed to send vote: %s", e)
        return

    # ── Step 3: Collect votes ────────────────────────────────
    log.info("Collecting votes for %d minutes ...", VOTING_DURATION_MINUTES)
    votes = collect_votes(VOTING_DURATION_MINUTES)

    if not votes or all(len(v) == 0 for v in votes.values()):
        log.info("No votes received.")
        send_no_votes_message(TELEGRAM_CHAT_ID)
        return

    # Resolve any text-number votes to real recipe IDs
    votes = resolve_number_votes(votes, candidates)

    if not votes or all(len(v) == 0 for v in votes.values()):
        log.info("No valid votes after resolution.")
        send_no_votes_message(TELEGRAM_CHAT_ID)
        return

    # ── Step 4: Determine winner ─────────────────────────────
    winner_id = max(votes, key=lambda rid: len(votes[rid]))
    winner_voters = votes[winner_id]
    winner = next((c for c in candidates if c.id == winner_id), None)

    if not winner:
        log.error("Winner recipe %s not found in candidates?!", winner_id)
        return

    log.info("Winner: %s with %d votes", winner.name, len(winner_voters))

    # ── Step 5: Build shopping list ──────────────────────────
    log.info("Adding ingredients to Cookidoo shopping list ...")
    try:
        ingredients = await add_to_shopping_list(winner.id)
    except Exception as e:
        log.error("Failed to update shopping list: %s", e)
        ingredients = winner.ingredients  # Fallback to cached ingredients

    # ── Step 6: Send result ──────────────────────────────────
    send_result(TELEGRAM_CHAT_ID, winner, winner_voters, ingredients)
    log.info("Done! Bon appétit!")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
