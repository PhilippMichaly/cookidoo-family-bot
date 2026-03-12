"""Runtime config — /config command handler with JSON persistence.

Supports:
  /config show                 — show current settings
  /config start 07:30          — voting start time
  /config ende 17:00           — voting end time
  /config anzahl 5             — number of candidates
  /config schwierigkeit leicht — max difficulty
  /config filter desserts an   — toggle sweet filter
  /config filter drinks aus    — toggle drink filter
  /config historie 7           — history days
  /config reset                — reset all overrides to env defaults
"""

import json
import logging
import re
from pathlib import Path

import config as cfg

log = logging.getLogger(__name__)

DIFFICULTY_MAP = {
    "leicht": "easy", "einfach": "easy", "easy": "easy",
    "mittel": "medium", "medium": "medium",
    "schwer": "difficult", "schwierig": "difficult", "difficult": "difficult",
}

DIFFICULTY_DISPLAY = {"easy": "leicht", "medium": "mittel", "difficult": "schwer"}


def _load() -> dict:
    return cfg.load_runtime_overrides()


def _save(data: dict) -> None:
    cfg.RUNTIME_CONFIG_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2)
    )


def _show() -> str:
    """Format current effective config for display."""
    rc = _load()
    lines = [
        "⚙️ *Aktuelle Konfiguration*\n",
        f"📊 Vorschläge: {cfg.get('num_candidates')}",
        f"⏱ Abstimmungsdauer: {cfg.get('voting_minutes')} Min.",
        f"🕐 Festes Ende: {cfg.get('voting_end_time') or '—'}",
        f"🎚 Max. Schwierigkeit: {DIFFICULTY_DISPLAY.get(cfg.get('max_difficulty'), cfg.get('max_difficulty'))}",
        f"🍰 Süßspeisen-Filter: {'an' if cfg.get('filter_sweets') else 'aus'}",
        f"🍹 Getränke-Filter: {'an' if cfg.get('filter_drinks') else 'aus'}",
        f"📅 Gewinner-Historie: {cfg.get('history_days')} Tage",
    ]
    if rc:
        lines.append("\n_Überschriebene Werte sind fett markiert._")
    return "\n".join(lines)


def handle_config_command(text: str, user_id: str) -> str:
    """Parse a /config command and return response text.

    Returns plain text (no markdown escaping — caller handles that).
    """
    # Admin check
    if cfg.ADMIN_USER_IDS and user_id not in cfg.ADMIN_USER_IDS:
        return "🔒 Nur Admins können die Konfiguration ändern."

    args = text.strip().lower()

    if not args or args == "show":
        return _show()

    if args == "reset":
        _save({})
        return "✅ Alle Überschreibungen zurückgesetzt. Es gelten wieder die Standardwerte."

    rc = _load()

    # /config anzahl N
    m = re.match(r"anzahl\s+(\d+)", args)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 20:
            rc["num_candidates"] = n
            _save(rc)
            return f"✅ Anzahl Vorschläge: {n}"
        return "❌ Anzahl muss zwischen 1 und 20 liegen."

    # /config ende HH:MM
    m = re.match(r"ende\s+(\d{1,2}):(\d{2})", args)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            rc["voting_end_time"] = f"{hh:02d}:{mm:02d}"
            _save(rc)
            return f"✅ Abstimmung endet um {hh:02d}:{mm:02d}"
        return "❌ Ungültige Uhrzeit."

    # /config start HH:MM (informational — cron must be adjusted separately)
    m = re.match(r"start\s+(\d{1,2}):(\d{2})", args)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            rc["voting_start"] = f"{hh:02d}:{mm:02d}"
            _save(rc)
            return f"✅ Startzeit gespeichert: {hh:02d}:{mm:02d}\nℹ️ Im Webhook-Modus wird der Scheduler automatisch angepasst."
        return "❌ Ungültige Uhrzeit."

    # /config schwierigkeit LEVEL
    m = re.match(r"schwierigkeit\s+(\w+)", args)
    if m:
        raw = m.group(1)
        mapped = DIFFICULTY_MAP.get(raw)
        if mapped:
            rc["max_difficulty"] = mapped
            _save(rc)
            return f"✅ Max. Schwierigkeit: {DIFFICULTY_DISPLAY[mapped]}"
        return f"❌ Unbekannte Schwierigkeit '{raw}'. Erlaubt: leicht, mittel, schwer"

    # /config filter desserts|drinks an|aus
    m = re.match(r"filter\s+(desserts?|sweets?|süß|drinks?|getränke)\s+(an|aus|on|off)", args)
    if m:
        what = m.group(1)
        on = m.group(2) in ("an", "on")
        if what in ("dessert", "desserts", "sweet", "sweets", "süß"):
            rc["filter_sweets"] = on
            _save(rc)
            return f"✅ Süßspeisen-Filter: {'an' if on else 'aus'}"
        else:
            rc["filter_drinks"] = on
            _save(rc)
            return f"✅ Getränke-Filter: {'an' if on else 'aus'}"

    # /config historie N
    m = re.match(r"historie\s+(\d+)", args)
    if m:
        days = int(m.group(1))
        if 0 <= days <= 90:
            rc["history_days"] = days
            _save(rc)
            return f"✅ Gewinner-Historie: {days} Tage"
        return "❌ Historie muss zwischen 0 und 90 Tagen liegen."

    # /config dauer N (voting duration in minutes)
    m = re.match(r"dauer\s+(\d+)", args)
    if m:
        mins = int(m.group(1))
        if 10 <= mins <= cfg.VOTING_DURATION_MAX_MINUTES:
            rc["voting_minutes"] = mins
            _save(rc)
            return f"✅ Abstimmungsdauer: {mins} Minuten"
        return f"❌ Dauer muss zwischen 10 und {cfg.VOTING_DURATION_MAX_MINUTES} Minuten liegen."

    return (
        "❓ Unbekannter Befehl. Versuche:\n"
        "/config show\n"
        "/config anzahl 5\n"
        "/config ende 17:00\n"
        "/config dauer 120\n"
        "/config schwierigkeit mittel\n"
        "/config filter desserts an\n"
        "/config filter drinks aus\n"
        "/config historie 7\n"
        "/config reset"
    )
