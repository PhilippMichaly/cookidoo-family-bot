#!/usr/bin/env python3
"""
Helper: Discover your Telegram Chat ID.

1. Run this script
2. Send a message to your bot in Telegram (in a group or private chat)
3. The script prints the chat_id you need for your .env file

Requires TELEGRAM_BOT_TOKEN to be set (via .env or environment variable).
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from config import TELEGRAM_BOT_TOKEN
from telegram_client import get_updates


def main():
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN ist nicht gesetzt!")
        print("   Setze den Token in deiner .env-Datei oder als Umgebungsvariable.")
        sys.exit(1)

    print("🔍 Warte auf Telegram-Nachrichten ...")
    print("   Sende eine Nachricht an den Bot (in einer Gruppe oder privat).")
    print("   Drücke Ctrl+C zum Beenden.\n")

    seen = set()
    while True:
        try:
            updates = get_updates(limit=100, timeout=5)

            for u in updates:
                uid = u.get("update_id")
                if uid in seen:
                    continue
                seen.add(uid)

                # Extract chat from message or callback_query
                msg = u.get("message", {}) or {}
                chat = msg.get("chat", {})
                if not chat:
                    cb = u.get("callback_query", {}) or {}
                    chat = (cb.get("message", {}) or {}).get("chat", {})

                if chat:
                    chat_id = chat.get("id")
                    chat_type = chat.get("type", "?")
                    title = chat.get("title") or chat.get("first_name", "?")
                    print(f"  ✅ Chat gefunden: '{title}' (Typ: {chat_type})")
                    print(f'     TELEGRAM_CHAT_ID="{chat_id}"')
                    print()

        except Exception as e:
            print(f"  ⚠️ Fehler: {e}", file=sys.stderr)

        time.sleep(3)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBeendet.")
