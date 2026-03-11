#!/usr/bin/env python3
"""
Feature-Request Listener
=========================
Checks Telegram for messages starting with /wunsch, /feature or /idee.
Confirms receipt in the chat and prints the request as JSON so the
cron agent can pick it up and implement the change.

Usage in chat:
  /wunsch Rezepte nach Saison filtern
  /feature Einkaufsliste per WhatsApp teilen
  /idee Portionen anpassen können
"""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("feature_listener")

CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-5106621509")
TRIGGER_COMMANDS = ("/wunsch", "/feature", "/idee")


def _call_telegram(tool_name: str, arguments: dict) -> dict | list:
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


def _escape_md(text: str) -> str:
    special = r"_*[]()~`>#+-=|{}.!"
    result = ""
    for ch in text:
        if ch in special:
            result += f"\\{ch}"
        else:
            result += ch
    return result


def check_for_requests() -> list[dict]:
    """Check Telegram for feature request commands. Returns new requests."""
    new_requests = []

    try:
        updates = _call_telegram("telegram_bot_api-list-updates", {
            "limit": 100,
            "autoPaging": True,
        })
        if not isinstance(updates, list):
            updates = []

        for update in updates:
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
                    f"\U0001f6e0 Wird jetzt umgesetzt\\.\\.\\."
                )
                _call_telegram(
                    "telegram_bot_api-send-text-message-or-reply",
                    {
                        "chatId": str(chat.get("id", CHAT_ID)),
                        "text": reply,
                        "parse_mode": "MarkdownV2",
                        "reply_to_message_id": str(msg.get("message_id", "")),
                    },
                )
            except Exception as e:
                log.warning("Could not send confirmation: %s", e)

    except Exception as e:
        log.error("Error checking updates: %s", e)

    return new_requests


def main():
    new_requests = check_for_requests()
    # Output as JSON for the cron agent to process
    print(json.dumps({
        "new_requests": len(new_requests),
        "requests": new_requests,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
