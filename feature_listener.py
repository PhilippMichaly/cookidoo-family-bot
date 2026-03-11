#!/usr/bin/env python3
"""
Feature-Request Listener
=========================
Checks Telegram for messages starting with /wunsch or /feature
and stores them. Designed to run as a periodic cron job.

Usage in chat:
  /wunsch Rezepte nach Saison filtern
  /feature Einkaufsliste per WhatsApp teilen
  /wunsch Portionen anpassen können

The bot replies with a confirmation and saves the request to a JSON file.
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

REQUESTS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "feature_requests.json"
)

# Telegram group chat ID
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-5106621509")

# Commands that trigger a feature request
TRIGGER_COMMANDS = ("/wunsch", "/feature", "/idee")


def _call_telegram(tool_name: str, arguments: dict) -> dict | list:
    """Call a Telegram tool via the external-tool CLI."""
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
    """Escape special characters for MarkdownV2."""
    special = r"_*[]()~`>#+-=|{}.!"
    result = ""
    for ch in text:
        if ch in special:
            result += f"\\{ch}"
        else:
            result += ch
    return result


def load_requests() -> list[dict]:
    """Load existing feature requests from file."""
    if os.path.exists(REQUESTS_FILE):
        with open(REQUESTS_FILE) as f:
            return json.load(f)
    return []


def save_requests(requests: list[dict]) -> None:
    """Save feature requests to file."""
    with open(REQUESTS_FILE, "w") as f:
        json.dump(requests, f, ensure_ascii=False, indent=2)


def check_for_requests() -> list[dict]:
    """
    Check Telegram updates for feature request commands.
    Returns list of new requests found.
    """
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

            # Check if message starts with a trigger command
            triggered = False
            for cmd in TRIGGER_COMMANDS:
                if text_lower.startswith(cmd):
                    # Extract the actual request (after the command)
                    request_text = text[len(cmd):].strip()
                    triggered = True
                    break

            if not triggered or not request_text:
                continue

            user = msg.get("from", {})
            chat = msg.get("chat", {})

            request = {
                "text": request_text,
                "from": user.get("first_name", "Unbekannt"),
                "user_id": str(user.get("id", "")),
                "chat_id": str(chat.get("id", "")),
                "date": datetime.fromtimestamp(
                    msg.get("date", 0), tz=timezone.utc
                ).isoformat(),
                "status": "neu",
            }

            new_requests.append(request)
            log.info(
                "Feature request from %s: %s",
                request["from"], request_text,
            )

            # Send confirmation reply
            try:
                reply_text = (
                    f"\u2705 Danke, {_escape_md(request['from'])}\\! "
                    f"Dein Wunsch wurde gespeichert:\n\n"
                    f"\u201E{_escape_md(request_text)}\u201C\n\n"
                    f"Philipp wird benachrichtigt\\."
                )
                _call_telegram(
                    "telegram_bot_api-send-text-message-or-reply",
                    {
                        "chatId": str(chat.get("id", CHAT_ID)),
                        "text": reply_text,
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
    """Main entry point: check for new requests and save them."""
    new_requests = check_for_requests()

    if not new_requests:
        log.info("No new feature requests.")
        # Print empty JSON for cron agent to detect "nothing new"
        print(json.dumps({"new_requests": 0}))
        return

    # Load existing and append new
    all_requests = load_requests()
    all_requests.extend(new_requests)
    save_requests(all_requests)

    log.info("Saved %d new request(s), total: %d", len(new_requests), len(all_requests))

    # Print summary for cron agent to pick up and notify
    print(json.dumps({
        "new_requests": len(new_requests),
        "requests": [
            {"from": r["from"], "text": r["text"]}
            for r in new_requests
        ],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
