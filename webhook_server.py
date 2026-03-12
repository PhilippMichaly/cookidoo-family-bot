"""Webhook server — persistent bot with scheduled votes.

Runs an aiohttp web server that:
1. Receives Telegram webhook updates (votes, commands)
2. Schedules daily vote start/tally via asyncio
3. Handles /config, /status, /wunsch commands

No polling needed — Telegram pushes updates to us.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiohttp import web

import cache
import config as cfg
import telegram_client as tg
from cookidoo_client import add_to_shopping_list
from runtime_config import handle_config_command
from voting import determine_winner

log = logging.getLogger(__name__)

# ─── In-memory vote state ───────────────────────────────

_vote_state: dict = {}  # active vote session


def _is_voting_active() -> bool:
    return bool(_vote_state.get("candidates"))


# ─── Webhook handler ────────────────────────────────────

async def handle_webhook(request: web.Request) -> web.Response:
    """Process incoming Telegram update."""
    try:
        update = await request.json()
    except Exception:
        return web.Response(status=400)

    asyncio.create_task(_process_update(update))
    return web.Response(text="ok")


async def _process_update(update: dict) -> None:
    """Route update to appropriate handler."""
    # Callback query (vote button)
    cb = update.get("callback_query")
    if cb:
        await _handle_vote(cb)
        return

    # Text message (commands)
    msg = update.get("message", {})
    text = (msg.get("text") or "").strip()
    if not text:
        return

    chat_id = str(msg.get("chat", {}).get("id", ""))
    user_id = str(msg.get("from", {}).get("id", ""))

    # /config command
    if text.lower().startswith("/config"):
        args = text[7:].strip()
        response = handle_config_command(args, user_id)
        await tg.send_text(chat_id, response)
        return

    # /status command
    if text.lower().startswith("/status"):
        await _handle_status(chat_id)
        return

    # /wunsch /feature /idee
    for cmd in ("/wunsch", "/feature", "/idee"):
        if text.lower().startswith(cmd):
            wish = text[len(cmd):].strip()
            if wish:
                name = msg.get("from", {}).get("first_name", "Unbekannt")
                await tg.send_text(
                    chat_id,
                    f"✅ Danke, {name}! Dein Wunsch wurde notiert:\n\"{wish}\""
                )
                log.info("Feature request from %s: %s", name, wish)
            return

    # /sync command (force cache refresh)
    if text.lower().startswith("/sync"):
        if cfg.ADMIN_USER_IDS and user_id not in cfg.ADMIN_USER_IDS:
            await tg.send_text(chat_id, "🔒 Nur Admins können den Cache aktualisieren.")
            return
        await tg.send_text(chat_id, "🔄 Cache-Sync gestartet...")
        count = await cache.sync_from_cookidoo()
        await tg.send_text(chat_id, f"✅ {count} Rezepte synchronisiert.")
        return

    # /vote command (manual vote trigger)
    if text.lower().startswith("/vote"):
        if cfg.ADMIN_USER_IDS and user_id not in cfg.ADMIN_USER_IDS:
            await tg.send_text(chat_id, "🔒 Nur Admins können eine Abstimmung starten.")
            return
        if _is_voting_active():
            await tg.send_text(chat_id, "⚠️ Es läuft bereits eine Abstimmung.")
            return
        asyncio.create_task(_run_vote_cycle())
        return


async def _handle_vote(cb: dict) -> None:
    """Process a vote callback."""
    if not _is_voting_active():
        await tg.answer_callback(cb.get("id", ""), "⏰ Keine aktive Abstimmung.")
        return

    data = cb.get("data", "")
    if not data.startswith("vote:"):
        return

    recipe_id = data.split(":", 1)[1]
    user = cb.get("from", {})
    user_id = str(user.get("id", ""))
    first_name = user.get("first_name", "Unbekannt")
    cb_id = cb.get("id", "")

    candidates = _vote_state.get("candidates", [])
    user_votes = _vote_state.setdefault("user_votes", {})

    recipe_name = next(
        (c.name for c in candidates if c.id == recipe_id), recipe_id
    )

    old = user_votes.get(user_id)

    if old and old[0] == recipe_id:
        await tg.answer_callback(cb_id, f"✓ Du hast bereits für '{recipe_name}' gestimmt")
        return

    user_votes[user_id] = (recipe_id, first_name)

    if old and old[0] != recipe_id:
        old_name = next((c.name for c in candidates if c.id == old[0]), "?")
        await tg.answer_callback(cb_id, f"↩️ Stimme geändert: '{old_name}' → '{recipe_name}'")
        log.info("Vote changed: %s %s -> %s", first_name, old_name, recipe_name)
    else:
        await tg.answer_callback(cb_id, f"✓ Stimme für '{recipe_name}' registriert!")
        log.info("Vote: %s -> %s", first_name, recipe_name)

    # Update live counter
    counts: dict[str, int] = {}
    for rid, _ in user_votes.values():
        counts[rid] = counts.get(rid, 0) + 1

    await tg.update_vote_message(
        cfg.TELEGRAM_CHAT_ID,
        _vote_state.get("message_id", ""),
        candidates,
        _vote_state.get("voting_minutes", 120),
        counts,
        len(user_votes),
        _vote_state.get("has_photo", False),
    )


async def _handle_status(chat_id: str) -> None:
    """Show bot status."""
    lines = ["📊 *Bot Status*\n"]

    if _is_voting_active():
        n = len(_vote_state.get("user_votes", {}))
        lines.append(f"🗳 Abstimmung aktiv — {n} Stimmen bisher")
    else:
        lines.append("😴 Keine aktive Abstimmung")

    if cache.needs_refresh():
        lines.append("⚠️ Rezept-Cache veraltet")
    else:
        lines.append("✅ Rezept-Cache aktuell")

    await tg.send_text(chat_id, "\n".join(lines))


# ─── Vote cycle ─────────────────────────────────────────

async def _run_vote_cycle() -> None:
    """Full vote cycle: cache check → send vote → wait → tally."""
    global _vote_state

    log.info("Starting vote cycle")

    # Refresh cache if needed
    if cache.needs_refresh():
        log.info("Cache stale, syncing...")
        try:
            await cache.sync_from_cookidoo()
        except Exception as e:
            log.error("Cache sync failed: %s", e)
            await tg.send_text(cfg.TELEGRAM_CHAT_ID, f"⚠️ Cache-Sync fehlgeschlagen: {e}")
            return

    # Get candidates
    candidates = cache.get_candidates()
    if not candidates:
        await tg.send_text(cfg.TELEGRAM_CHAT_ID, "😕 Keine passenden Rezepte gefunden.")
        return

    # Determine voting duration
    voting_minutes = cfg.get("voting_minutes") or cfg.VOTING_DURATION_MINUTES
    end_time = cfg.get("voting_end_time")
    if end_time:
        try:
            tz = ZoneInfo("Europe/Berlin")
            now = datetime.now(tz)
            hh, mm = map(int, end_time.split(":"))
            target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            computed = int((target - now).total_seconds() // 60)
            if 1 <= computed <= cfg.VOTING_DURATION_MAX_MINUTES:
                voting_minutes = computed
        except Exception as e:
            log.warning("End time parse error: %s", e)

    # Send vote
    msg_id = await tg.send_vote(cfg.TELEGRAM_CHAT_ID, candidates, voting_minutes)
    has_photo = bool(candidates[0].image_url) if candidates else False

    _vote_state = {
        "candidates": candidates,
        "message_id": msg_id,
        "voting_minutes": voting_minutes,
        "user_votes": {},
        "has_photo": has_photo,
        "start_time": time.time(),
    }

    log.info("Vote sent, waiting %d minutes", voting_minutes)

    # Wait for voting period
    await asyncio.sleep(voting_minutes * 60)

    # Tally
    await _tally_votes()


async def _tally_votes() -> None:
    """Evaluate votes and announce winner."""
    global _vote_state

    if not _is_voting_active():
        return

    candidates = _vote_state["candidates"]
    user_votes = _vote_state.get("user_votes", {})

    # Aggregate
    votes: dict[str, list[str]] = {}
    for _, (recipe_id, name) in user_votes.items():
        votes.setdefault(recipe_id, []).append(name)

    if not votes:
        await tg.send_text(
            cfg.TELEGRAM_CHAT_ID,
            "😕 Leider hat niemand abgestimmt. Nächstes Mal vielleicht!"
        )
        _vote_state = {}
        return

    # Determine winner
    try:
        winner, voter_names, is_tie, tied_names = determine_winner(votes, candidates)
    except ValueError as e:
        log.error("Winner determination failed: %s", e)
        _vote_state = {}
        return

    # Add to shopping list
    ingredients: list[str] = []
    try:
        ingredients = await add_to_shopping_list(winner.id)
    except Exception as e:
        log.error("Shopping list error: %s", e)

    # Send result
    await tg.send_result(
        cfg.TELEGRAM_CHAT_ID, winner, voter_names, ingredients,
        is_tie=is_tie, tied_names=tied_names,
    )

    cache.save_winner(winner.id, winner.name)
    log.info("Vote cycle complete: %s won!", winner.name)

    _vote_state = {}


# ─── Scheduler ──────────────────────────────────────────

async def _scheduler() -> None:
    """Schedule daily vote at configured time."""
    tz = ZoneInfo("Europe/Berlin")

    while True:
        now = datetime.now(tz)

        # Get start time from runtime config or env
        rc = cfg.load_runtime_overrides()
        start_str = rc.get("voting_start", "07:00")
        try:
            hh, mm = map(int, start_str.split(":"))
        except (ValueError, AttributeError):
            hh, mm = 7, 0

        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)

        wait_seconds = (target - now).total_seconds()
        log.info(
            "Next vote scheduled at %s (%d seconds from now)",
            target.strftime("%Y-%m-%d %H:%M"), wait_seconds,
        )

        await asyncio.sleep(wait_seconds)

        if not _is_voting_active():
            await _run_vote_cycle()
        else:
            log.info("Vote already active, skipping scheduled trigger")


# ─── Server setup ───────────────────────────────────────

async def setup_webhook() -> None:
    """Register webhook URL with Telegram."""
    if not cfg.WEBHOOK_URL:
        log.warning("WEBHOOK_URL not set, skipping webhook registration")
        return

    url = f"{cfg.WEBHOOK_URL}/webhook"
    await tg.tg("setWebhook", {"url": url})
    log.info("Webhook registered: %s", url)


async def remove_webhook() -> None:
    """Remove webhook (for switching to polling mode)."""
    await tg.tg("deleteWebhook")
    log.info("Webhook removed")


def create_app() -> web.Application:
    """Create aiohttp web application."""
    app = web.Application()
    app.router.add_post("/webhook", handle_webhook)
    app.router.add_get("/health", lambda _: web.Response(text="ok"))

    async def on_startup(_app: web.Application) -> None:
        if cfg.WEBHOOK_URL:
            await setup_webhook()
        asyncio.create_task(_scheduler())
        log.info("Bot started in webhook mode")

    app.on_startup.append(on_startup)
    return app


async def run_polling() -> None:
    """Run in polling mode (no webhook server needed)."""
    log.info("Starting in polling mode")
    await remove_webhook()

    # Start scheduler in background
    scheduler_task = asyncio.create_task(_scheduler())

    offset: int | None = None
    try:
        while True:
            try:
                params: dict = {"limit": 100, "timeout": 30}
                if offset is not None:
                    params["offset"] = offset

                updates = await tg.tg("getUpdates", params)
                if not isinstance(updates, list):
                    updates = []

                for upd in updates:
                    uid = upd.get("update_id")
                    if uid is not None:
                        offset = uid + 1
                    await _process_update(upd)

            except Exception as e:
                log.warning("Polling error: %s", e)
                await asyncio.sleep(5)

    except asyncio.CancelledError:
        scheduler_task.cancel()
