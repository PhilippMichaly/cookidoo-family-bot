#!/usr/bin/env python3
"""
Feature-Request Listener
=========================
Checks Telegram for messages starting with /wunsch, /feature or /idee.
Confirms receipt in the chat and prints the request as JSON for
further processing (e.g. by a cron job or CI pipeline).

Usage in chat:
  /wunsch Rezepte nach Saison filtern
  /feature Einkaufsliste per WhatsApp teilen
  /idee Portionen anpassen können
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

from config import TELEGRAM_CHAT_ID
from telegram_client import get_updates, send_message, _escape_md

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("feature_listener")

TRIGGER_COMMANDS = ("/wunsch", "/feature", "/idee")

# Persistent offset file so we don't re-process old messages
_OFFSET_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "feature_listener_offset.json"
)


def _load_offset() -> int | None:
    """Load the last processed update_id from disk."""
    try:
        with open(_OFFSET_FILE) as f:
            data = json.load(f)
        return data.get("next_offset")
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None


def _save_offset(next_offset: int) -> None:
    """Persist the next offset so future runs skip already-seen updates."""
    with open(_OFFSET_FILE, "w") as f:
        json.dump({"next_offset": next_offset}, f)
    log.info("Saved feature listener offset: %d", next_offset)


def check_for_requests() -> list[dict]:
    """Check Telegram for feature request commands. Returns new requests."""
    new_requests = []
    offset = _load_offset()
    max_update_id: int | None = None

    try:
        updates = get_updates(offset=offset, limit=100)

        for update in updates:
            # Track highest update_id for offset persistence
            update_id = update.get("update_id")
            if update_id is not None:
                if max_update_id is None or update_id > max_update_id:
                    max_update_id = update_id

            msg = update.get("message", {})
            if not msg:
                continue

            text = (msg.get("text") or "").strip()
            text_lower = text.lower()

            request_text = None
            for cmd in TRIGGER_COMMANDS:
                if text_lower.startswith(cmd):
                    request_text = text[len(cmd):].strip()
                    break

            if not request_text:
                continue

            user = msg.get("from", {})
            chat = msg.get("chat", {})

            request = {
                "text": request_text,
                "from": user.get("first_name", "Unbekannt"),
                "user_id": str(user.get("id", "")),
                "chat_id": str(chat.get("id", "")),
                "message_id": str(msg.get("message_id", "")),
                "date": datetime.fromtimestamp(
                    msg.get("date", 0), tz=timezone.utc
                ).isoformat(),
            }
            new_requests.append(request)
            log.info("Feature request from %s: %s", request["from"], request_text)

            # Confirm in chat
            try:
                reply = (
                    f"\u2705 Danke, {_escape_md(request['from'])}\\!\n\n"
                    f"Dein Wunsch:\n"
                    f"\u201E{_escape_md(request_text)}\u201C\n\n"
                    f"\U0001f551 Wird innerhalb der n\u00e4chsten Stunde umgesetzt\\."
                )
                send_message(
                    str(chat.get("id", TELEGRAM_CHAT_ID)),
                    reply,
                    parse_mode="MarkdownV2",
                    reply_to_message_id=str(msg.get("message_id", "")),
                )
            except Exception as e:
                log.warning("Could not send confirmation: %s", e)

    except Exception as e:
        log.error("Error checking updates: %s", e)

    # Persist offset so next run skips everything we've already seen
    if max_update_id is not None:
        _save_offset(max_update_id + 1)

    return new_requests


def main():
    new_requests = check_for_requests()
    # Output as JSON for further processing
    print(json.dumps({
        "new_requests": len(new_requests),
        "requests": new_requests,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
