#!/usr/bin/env python3
"""Cookidoo Family Bot — central entrypoint.

Usage:
  python cli.py serve           # Webhook server (recommended)
  python cli.py poll            # Long-polling mode (no public URL needed)
  python cli.py vote            # One-shot: send vote + wait + tally
  python cli.py sync            # Force cache refresh from Cookidoo
  python cli.py tally           # Tally existing vote (from state file)
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("cli")


def _validate():
    """Check required config."""
    import config as cfg
    missing = []
    if not cfg.COOKIDOO_EMAIL:
        missing.append("COOKIDOO_EMAIL")
    if not cfg.TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not cfg.TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")
    if missing:
        log.error("Missing: %s — see .env.example", ", ".join(missing))
        sys.exit(1)


async def cmd_serve():
    """Run webhook server."""
    _validate()
    import config as cfg
    from aiohttp import web
    from webhook_server import create_app

    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, cfg.WEBHOOK_HOST, cfg.WEBHOOK_PORT)
    log.info("Starting webhook server on %s:%d", cfg.WEBHOOK_HOST, cfg.WEBHOOK_PORT)
    await site.start()

    # Run forever
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


async def cmd_poll():
    """Run in long-polling mode."""
    _validate()
    from webhook_server import run_polling
    await run_polling()


async def cmd_vote():
    """One-shot vote cycle."""
    _validate()
    import cache
    import config as cfg
    import telegram_client as tg
    from cookidoo_client import add_to_shopping_list
    from voting import determine_winner

    # Sync cache if needed
    if cache.needs_refresh():
        log.info("Syncing cache...")
        await cache.sync_from_cookidoo()

    candidates = cache.get_candidates()
    if not candidates:
        log.error("No candidates found")
        return

    voting_minutes = cfg.get("voting_minutes") or cfg.VOTING_DURATION_MINUTES
    msg_id = await tg.send_vote(cfg.TELEGRAM_CHAT_ID, candidates, voting_minutes)
    has_photo = bool(candidates[0].image_url)

    log.info("Collecting votes for %d minutes...", voting_minutes)
    votes = await tg.poll_votes(
        cfg.TELEGRAM_CHAT_ID, msg_id, candidates, voting_minutes, has_photo,
    )

    if not votes:
        await tg.send_text(cfg.TELEGRAM_CHAT_ID, "😕 Niemand hat abgestimmt.")
        return

    winner, voters, is_tie, tied = determine_winner(votes, candidates)

    try:
        ingredients = await add_to_shopping_list(winner.id)
    except Exception as e:
        log.error("Shopping list: %s", e)
        ingredients = []

    await tg.send_result(
        cfg.TELEGRAM_CHAT_ID, winner, voters, ingredients,
        is_tie=is_tie, tied_names=tied,
    )
    cache.save_winner(winner.id, winner.name)
    log.info("Done! %s won.", winner.name)


async def cmd_sync():
    """Force cache refresh."""
    _validate()
    import cache
    count = await cache.sync_from_cookidoo()
    log.info("Synced %d recipes", count)


def main():
    parser = argparse.ArgumentParser(description="Cookidoo Family Bot")
    parser.add_argument(
        "command",
        choices=["serve", "poll", "vote", "sync", "tally"],
        help="Bot mode",
    )
    args = parser.parse_args()

    dispatch = {
        "serve": cmd_serve,
        "poll": cmd_poll,
        "vote": cmd_vote,
        "sync": cmd_sync,
    }

    fn = dispatch.get(args.command)
    if fn:
        asyncio.run(fn())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
