#!/usr/bin/env python3
"""
Helper: Discover your Telegram Chat ID.

Run this script, then send a message to your bot in Telegram
(either privately or in your family group). The script will
print the chat_id you need for config.
"""

import json
import subprocess
import time
import sys


def call_telegram(tool_name, arguments):
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
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout)


def main():
    print("🔍 Listening for Telegram messages ...")
    print("   Send any message to the bot (in a group or private chat).")
    print("   Press Ctrl+C to stop.\n")

    seen = set()
    while True:
        try:
            updates = call_telegram("telegram_bot_api-list-updates", {"limit": 100})
            if not isinstance(updates, list):
                updates = []

            for u in updates:
                uid = u.get("update_id")
                if uid in seen:
                    continue
                seen.add(uid)

                chat = u.get("chat", {}) or u.get("message", {}).get("chat", {})
                if chat:
                    chat_id = chat.get("id")
                    chat_type = chat.get("type", "?")
                    title = chat.get("title") or chat.get("first_name", "?")
                    print(f"  ✅ Chat gefunden: '{title}' (Typ: {chat_type})")
                    print(f"     TELEGRAM_CHAT_ID = \"{chat_id}\"")
                    print()

        except Exception as e:
            print(f"  ⚠️ Fehler: {e}", file=sys.stderr)

        time.sleep(3)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBeendet.")
