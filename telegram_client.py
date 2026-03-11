"""Telegram client – sends votes with inline buttons, collects results.

Supports two modes:
1. Direct Telegram Bot API (recommended for self-hosting)
   → Set TELEGRAM_BOT_TOKEN in your .env file
2. External tool connector (for managed platforms like Pipedream)
   → Automatically used if TELEGRAM_BOT_TOKEN is not set but
     the external-tool CLI is available

For self-hosting, only mode 1 is needed. Mode 2 is a fallback for
environments with a pre-configured Telegram connector.
"""

import json
import logging
import os
import subprocess
import time

import requests as http

from config import TELEGRAM_BOT_TOKEN
from cookidoo_client import RecipeCandidate

log = logging.getLogger(__name__)

# ─── Transport layer ────────────────────────────────────────
# Detects which mode to use based on TELEGRAM_BOT_TOKEN availability.

_USE_DIRECT_API = bool(TELEGRAM_BOT_TOKEN)


def _call_telegram_direct(method: str, params: dict | None = None) -> dict | list:
    """Call Telegram Bot API directly via HTTPS."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    r = http.post(url, json=params or {}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")
    return data.get("result", {})


def _call_telegram_external(tool_name: str, arguments: dict) -> dict | list:
    """Call Telegram via external-tool CLI (Pipedream connector)."""
    payload = json.dumps({
        "source_id": "telegram_bot_api__pipedream",
        "tool_name": tool_name,
        "arguments": arguments,
    })
    result = subprocess.run(
        ["external-tool", "call", payload],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Telegram API error: {result.stderr}")
    return json.loads(result.stdout)


def _call_telegram(method: str, params: dict | None = None) -> dict | list:
    """
    Call Telegram API using the best available transport.
    - If TELEGRAM_BOT_TOKEN is set → direct HTTPS
    - Otherwise → external-tool CLI (Pipedream connector)
    """
    if _USE_DIRECT_API:
        return _call_telegram_direct(method, params)

    # Map Bot API method names to Pipedream tool names
    method_map = {
        "sendMessage": "telegram_bot_api-send-text-message-or-reply",
        "getUpdates": "telegram_bot_api-list-updates",
        "answerCallbackQuery": None,  # Not available in connector
    }

    tool_name = method_map.get(method)
    if tool_name is None:
        log.debug("Method %s not available via external connector, skipping", method)
        return {}

    # Translate parameter names for the connector
    args = dict(params or {})
    if "chat_id" in args:
        args["chatId"] = str(args.pop("chat_id"))
    if "reply_markup" in args and isinstance(args["reply_markup"], dict):
        args["reply_markup"] = json.dumps(args["reply_markup"])
    if "offset" in args:
        args["offset"] = str(args["offset"])

    return _call_telegram_external(tool_name, args)


# ─── Helpers ────────────────────────────────────────────────

def _format_time(seconds: int) -> str:
    """Format seconds to a human-readable German time string."""
    if seconds <= 0:
        return "k.A."
    hours = seconds // 3600
    mins = (seconds % 3600) // 60
    if hours > 0 and mins > 0:
        return f"{hours} Std. {mins} Min."
    if hours > 0:
        return f"{hours} Std."
    return f"{mins} Min."


def _difficulty_emoji(diff: str) -> str:
    d = diff.lower()
    if d == "easy":
        return "\U0001f7e2"   # green circle
    if d == "medium":
        return "\U0001f7e1"   # yellow circle
    return "\U0001f534"       # red circle


def _difficulty_de(diff: str) -> str:
    d = diff.lower()
    if d == "easy":
        return "einfach"
    if d == "medium":
        return "mittel"
    return "schwer"


def _escape_md(text: str) -> str:
    """Escape special characters for MarkdownV2."""
    special = r"_*[]()~`>#+-=|{}.!"
    result = ""
    for ch in text:
        if ch in special:
            result += f"\\{ch}"
        else:
            result += ch
    return result


# ─── Voting ─────────────────────────────────────────────────

def send_vote(chat_id: str, candidates: list[RecipeCandidate],
              voting_minutes: int) -> str:
    """
    Send a voting message with inline keyboard buttons to the Telegram chat.
    Returns the message_id of the sent message.
    """
    # Build message text (MarkdownV2 escaped)
    lines = [
        "\U0001f37d *Familienabstimmung: Was kochen wir?*\n",
        "Stimmt ab, indem ihr auf euren Favoriten tippt\\!\n",
    ]

    for i, r in enumerate(candidates, 1):
        emoji = _difficulty_emoji(r.difficulty)
        diff_text = _difficulty_de(r.difficulty)
        time_text = _escape_md(_format_time(r.total_time))
        name_esc = _escape_md(r.name)
        lines.append(
            f"*{i}\\)* {name_esc}\n"
            f"      \u23F1 {time_text} \\| {emoji} {diff_text} \\| "
            f"\U0001f37d {r.serving_size} Portionen"
        )

    lines.append(f"\n\u23F0 Abstimmung endet in {voting_minutes} Minuten\\.")

    text = "\n".join(lines)

    # Build inline keyboard – one button per recipe
    keyboard = []
    for i, r in enumerate(candidates, 1):
        short_name = r.name[:28] + ("..." if len(r.name) > 28 else "")
        keyboard.append([{
            "text": f"{i}. {short_name}",
            "callback_data": f"vote:{r.id}",
        }])

    reply_markup = json.dumps({"inline_keyboard": keyboard})

    result = _call_telegram("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "MarkdownV2",
        "reply_markup": reply_markup,
    })

    msg_id = _extract_message_id(result)
    log.info("Vote message sent, message_id=%s", msg_id)
    return msg_id


def collect_votes(voting_minutes: int) -> dict[str, list[str]]:
    """
    Poll Telegram for callback_query updates over the voting period.

    Uses offset-based pagination so we don't re-process old updates.
    Each user gets exactly one vote – the first click counts,
    subsequent clicks are ignored.

    Returns {recipe_id: [voter_first_name, ...]}.
    """
    # Track votes as {user_id: (recipe_id, first_name)}
    user_votes: dict[str, tuple[str, str]] = {}
    end_time = time.time() + voting_minutes * 60
    poll_interval = 10  # seconds
    last_offset: int | None = None

    log.info("Collecting votes for %d minutes ...", voting_minutes)

    while time.time() < end_time:
        try:
            params: dict = {"limit": 100, "timeout": 5}
            if last_offset is not None:
                params["offset"] = last_offset

            updates = _call_telegram("getUpdates", params)
            if not isinstance(updates, list):
                updates = []

            for update in updates:
                update_id = update.get("update_id")
                if update_id is not None:
                    # Advance offset past this update
                    last_offset = update_id + 1

                # Handle callback_query (inline button press)
                cb = update.get("callback_query")
                if cb:
                    data = cb.get("data", "")
                    if data.startswith("vote:"):
                        recipe_id = data.split(":", 1)[1]
                        user = cb.get("from", {})
                        user_id = str(user.get("id", ""))
                        first_name = user.get("first_name", "Unbekannt")

                        if user_id in user_votes:
                            log.info(
                                "%s tried to vote again – ignored (already voted for %s)",
                                first_name, user_votes[user_id][0],
                            )
                        else:
                            user_votes[user_id] = (recipe_id, first_name)
                            log.info("Vote from %s for %s", first_name, recipe_id)

                        # Answer callback to remove loading indicator
                        try:
                            _call_telegram("answerCallbackQuery", {
                                "callback_query_id": cb.get("id"),
                            })
                        except Exception:
                            pass

                # Also handle text replies like "3" as fallback
                msg = update.get("message", {})
                if msg:
                    text = (msg.get("text") or "").strip()
                    if text.isdigit():
                        user = msg.get("from", {})
                        user_id = str(user.get("id", ""))
                        first_name = user.get("first_name", "Unbekannt")
                        if user_id in user_votes:
                            log.info("%s tried text vote – ignored", first_name)
                        else:
                            user_votes[user_id] = (f"number:{text}", first_name)
                            log.info("Text vote from %s: %s", first_name, text)

        except Exception as e:
            log.warning("Error polling updates: %s", e)

        time.sleep(poll_interval)

    # Aggregate: {recipe_id: [first_name, ...]}
    result: dict[str, list[str]] = {}
    for user_id, (recipe_id, name) in user_votes.items():
        result.setdefault(recipe_id, [])
        result[recipe_id].append(name)

    return result


def collect_all_votes_once(
    min_update_id: int | None = None,
) -> dict[str, list[str]]:
    """
    Do a single pass through all pending Telegram updates.
    Used by Phase 2 (tally) to collect votes after the voting window.

    If min_update_id is given, updates with update_id <= min_update_id
    are ignored (they predate the current vote).

    Returns {recipe_id: [voter_first_name, ...]}.
    """
    user_votes: dict[str, tuple[str, str]] = {}  # user_id -> (recipe_id, name)

    try:
        if _USE_DIRECT_API:
            # Direct API: paginate with offset
            last_offset: int | None = None
            while True:
                params: dict = {"limit": 100, "timeout": 0}
                if last_offset is not None:
                    params["offset"] = last_offset

                updates = _call_telegram("getUpdates", params)
                if not isinstance(updates, list) or not updates:
                    break

                for update in updates:
                    update_id = update.get("update_id")
                    if update_id is not None:
                        last_offset = update_id + 1
                    if min_update_id is not None and update_id is not None:
                        if update_id <= min_update_id:
                            continue
                    _process_update(update, user_votes)
        else:
            # External connector: use autoPaging
            updates = _call_telegram_external(
                "telegram_bot_api-list-updates",
                {"limit": 100, "autoPaging": True},
            )
            if not isinstance(updates, list):
                updates = []
            for update in updates:
                update_id = update.get("update_id")
                if min_update_id is not None and update_id is not None:
                    if update_id <= min_update_id:
                        continue
                _process_update(update, user_votes)

    except Exception as e:
        log.warning("Error fetching updates: %s", e)

    # Aggregate
    result: dict[str, list[str]] = {}
    for uid, (recipe_id, name) in user_votes.items():
        result.setdefault(recipe_id, [])
        result[recipe_id].append(name)

    return result


def _process_update(update: dict, user_votes: dict) -> None:
    """Process a single Telegram update for votes."""
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


def resolve_number_votes(
    votes: dict[str, list[str]],
    candidates: list[RecipeCandidate],
) -> dict[str, list[str]]:
    """Convert 'number:N' vote keys to actual recipe IDs."""
    resolved: dict[str, list[str]] = {}
    for key, names in votes.items():
        if key.startswith("number:"):
            idx = int(key.split(":")[1]) - 1
            if 0 <= idx < len(candidates):
                real_id = candidates[idx].id
                resolved.setdefault(real_id, [])
                resolved[real_id].extend(names)
            else:
                log.warning("Invalid vote number: %s", key)
        else:
            resolved.setdefault(key, [])
            resolved[key].extend(names)
    return resolved


# ─── Result messages ────────────────────────────────────────

def send_result(chat_id: str, winner: RecipeCandidate, voters: list[str],
                ingredients: list[str], *,
                is_tie: bool = False,
                tied_names: list[str] | None = None) -> None:
    """Send the voting result and shopping list to the chat."""
    voter_text = ", ".join(voters) if voters else "niemand"

    lines = [
        "\U0001f3c6 *Ergebnis der Abstimmung*\n",
        f"\U0001f37d *{_escape_md(winner.name)}* hat gewonnen\\!",
    ]

    if is_tie and tied_names:
        names_text = _escape_md(", ".join(tied_names))
        lines.append(f"\U0001f3b2 Gleichstand mit {names_text} \u2013 das Los hat entschieden\\!")

    lines.extend([
        f"Gew\u00e4hlt von: {_escape_md(voter_text)}\n",
        f"\u23F1 Gesamtzeit: {_escape_md(_format_time(winner.total_time))}",
        f"\U0001f37d Portionen: {winner.serving_size}\n",
        "\U0001f4cb *Einkaufsliste:*\n",
    ]

    for ing in ingredients:
        lines.append(f"  \u2022 {_escape_md(ing)}")

    lines.append(f"\n\U0001f517 [Rezept auf Cookidoo]({_escape_md(winner.url)})")
    lines.append(
        "\n\u2705 Die Einkaufsliste wurde auch in Cookidoo gespeichert\\."
    )

    text = "\n".join(lines)

    _call_telegram("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "MarkdownV2",
    })
    log.info("Result message sent for %s", winner.name)


def send_no_votes_message(chat_id: str) -> None:
    """Send a message when nobody voted."""
    _call_telegram("sendMessage", {
        "chat_id": chat_id,
        "text": (
            "\U0001f615 Leider hat niemand abgestimmt\\. "
            "N\u00e4chstes Mal vielleicht\\!"
        ),
        "parse_mode": "MarkdownV2",
    })


def send_error_message(chat_id: str, error: str) -> None:
    """Send an error message to the chat."""
    _call_telegram("sendMessage", {
        "chat_id": chat_id,
        "text": f"\u26A0\uFE0F Fehler beim Rezept\\-Bot: {_escape_md(error)}",
        "parse_mode": "MarkdownV2",
    })


def send_message(chat_id: str, text: str, **kwargs) -> dict:
    """Send a plain text message (convenience wrapper)."""
    return _call_telegram("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        **kwargs,
    })


def get_updates(offset: int | None = None, limit: int = 100,
                timeout: int = 0) -> list:
    """Get pending updates from the Telegram Bot API."""
    params = {"limit": limit, "timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    result = _call_telegram("getUpdates", params)
    return result if isinstance(result, list) else []


def reset_updates_offset(chat_id: str | None = None) -> None:
    """Best-effort reset of the update offset.

    Telegram doesn't provide a true 'reset' API. The practical meaning here is:
    consume nothing and allow the next caller to re-read older pending updates.

    We implement this by *not* advancing offset state on our side. For the
    direct Bot API, each polling loop already starts without a stored offset.

    This function exists so feature requests can be implemented explicitly and
    logged/audited.
    """
    # No persistent offset is stored; so a reset is a no-op.
    # Keeping the function to support the feature request intent.
    log.info("Reset update offset requested (no persistent offset to reset)")


def get_last_feature_request(chat_id: str, limit: int = 50) -> str:
    """Return the most recent plain-text message that looks like a feature request.

    This is used to implement small runtime overrides (e.g., end time) without
    changing the scheduler/config.

    We scan a limited number of updates and pick the newest message text.
    """
    try:
        updates = get_updates(offset=None, limit=limit, timeout=0)
    except Exception as e:
        log.info("Could not read updates for feature request: %s", e)
        return ""

    last_text = ""
    last_update_id = -1
    for upd in updates or []:
        uid = upd.get("update_id", -1)
        msg = upd.get("message") or {}
        text = (msg.get("text") or "").strip()
        if text and uid >= last_update_id:
            last_text = text
            last_update_id = uid

    return last_text


def _extract_message_id(result) -> str:
    """Extract message_id from Telegram API response."""
    if isinstance(result, dict):
        if "message_id" in result:
            return str(result["message_id"])
        if "result" in result and isinstance(result["result"], dict):
            return str(result["result"].get("message_id", ""))
        rv = result.get("$return_value", {})
        if isinstance(rv, dict):
            return str(rv.get("message_id", ""))
    return ""
