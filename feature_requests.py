"""Helpers for interpreting feature requests sent to the Telegram chat.

This module is intentionally small and conservative: it only implements
well-understood shortcuts and keeps any more complex requests out of
scope.

Currently supported:
- "Zähler herunter" / "reset counter": resets the Telegram update offset
  so the bot can see existing callback_query updates again.
- "bis HH:MM": interprets a requested local end time and converts it into
  a voting duration in minutes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class FeatureRequestActions:
    reset_update_offset: bool = False
    requested_end_time_local: str | None = None  # "HH:MM"


_RESET_PATTERNS = [
    r"\bz(ae|ä)hler\s+herunter\b",
    r"\breset\s+(den\s+)?z(ae|ä)hler\b",
    r"\bupdate\s+offset\s+reset\b",
]

_ENDTIME_RE = re.compile(r"\bbis\s+(\d{1,2}):(\d{2})\b")


def parse_feature_request(text: str) -> FeatureRequestActions:
    t = (text or "").strip().lower()

    reset = any(re.search(p, t) for p in _RESET_PATTERNS)

    end_time = None
    m = _ENDTIME_RE.search(t)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            end_time = f"{hh:02d}:{mm:02d}"

    return FeatureRequestActions(
        reset_update_offset=reset,
        requested_end_time_local=end_time,
    )


def compute_voting_minutes_until(
    end_time_hhmm: str,
    *,
    tz: str = "Europe/Berlin",
    now_utc: datetime | None = None,
) -> int:
    """Return minutes from now until the next occurrence of end_time_hhmm.

    If the requested end time is earlier than 'now' in the same day, it will
    be interpreted as tomorrow.
    """
    if now_utc is None:
        now_utc = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))

    local_tz = ZoneInfo(tz)
    now_local = now_utc.astimezone(local_tz)

    hh, mm = map(int, end_time_hhmm.split(":"))
    target_local = now_local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if target_local <= now_local:
        target_local = target_local + timedelta(days=1)

    delta = target_local - now_local
    minutes = int(delta.total_seconds() // 60)
    return max(0, minutes)
