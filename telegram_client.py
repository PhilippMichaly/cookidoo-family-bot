"""Telegram client — fully async via aiohttp.

Features:
- Vote confirmation via answerCallbackQuery
- Live vote counter (edits message on each vote)
- Vote changing (last click counts)
- No polling in webhook mode
"""

import json
import logging
from typing import Any

import aiohttp

import config as cfg
from cache import Recipe

log = logging.getLogger(__name__)

TG_BASE = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}"


# ─── Low-level API ──────────────────────────────────────

async def tg(method: str, params: dict | None = None, **kw) -> Any:
    """Call Telegram Bot API. Returns result field."""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{TG_BASE}/{method}", json=params or {}, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            data = await resp.json()
            if not data.get("ok"):
                log.error("TG API error %s: %s", method, data)
                raise RuntimeError(f"TG error: {data}")
            return data.get("result", {})


# ─── Formatting ─────────────────────────────────────────

def _esc(text: str) -> str:
    """Escape MarkdownV2 special chars."""
    out = []
    for ch in text:
        if ch in r"_*[]()~`>#+-=|{}.!":
            out.append(f"\\{ch}")
        else:
            out.append(ch)
    return "".join(out)


def _fmt_time(seconds: int) -> str:
    if seconds <= 0:
        return "k.A."
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    if h and m:
        return f"{h} Std. {m} Min."
    if h:
        return f"{h} Std."
    return f"{m} Min."


_DIFF_EMOJI = {"easy": "🟢", "medium": "🟡", "difficult": "🔴"}
_DIFF_DE = {"easy": "einfach", "medium": "mittel", "difficult": "schwer"}


# ─── Vote message building ──────────────────────────────

def _build_vote_text(
    candidates: list[Recipe],
    voting_minutes: int,
    vote_counts: dict[str, int] | None = None,
    total_votes: int = 0,
) -> str:
    """Build the voting message text (MarkdownV2)."""
    lines = [
        "🍽 *Familienabstimmung: Was kochen wir?*\n",
        "Stimmt ab, indem ihr auf euren Favoriten tippt\\!",
        "Ihr könnt eure Stimme jederzeit ändern\\.\n",
    ]

    for i, r in enumerate(candidates, 1):
        emoji = _DIFF_EMOJI.get(r.difficulty, "🟡")
        diff = _DIFF_DE.get(r.difficulty, r.difficulty)
        t = _esc(_fmt_time(r.total_time))
        name = _esc(r.name)
        count_str = ""
        if vote_counts and r.id in vote_counts:
            c = vote_counts[r.id]
            count_str = f" — {c} {'Stimme' if c == 1 else 'Stimmen'}"
        lines.append(
            f"*{i}\\)* {name}{_esc(count_str)}\n"
            f"      ⏱ {t} \\| {emoji} {diff} \\| "
            f"🍽 {r.serving_size} Portionen"
        )

    footer = f"\n⏰ Abstimmung läuft {voting_minutes} Minuten\\."
    if total_votes:
        footer += f"\n📊 Bisher {total_votes} {'Stimme' if total_votes == 1 else 'Stimmen'} abgegeben\\."
    lines.append(footer)

    return "\n".join(lines)


def _build_keyboard(candidates: list[Recipe]) -> str:
    """Build inline keyboard JSON."""
    kb = []
    for i, r in enumerate(candidates, 1):
        short = r.name[:28] + ("…" if len(r.name) > 28 else "")
        kb.append([{"text": f"{i}. {short}", "callback_data": f"vote:{r.id}"}])
    return json.dumps({"inline_keyboard": kb})


# ─── Public API ──────────────────────────────────────────

async def send_vote(
    chat_id: str,
    candidates: list[Recipe],
    voting_minutes: int,
) -> str:
    """Send voting message with inline buttons. Returns message_id."""
    text = _build_vote_text(candidates, voting_minutes)
    kb = _build_keyboard(candidates)

    # Try sending with photo of first candidate
    first_image = candidates[0].image_url if candidates else ""
    msg_id = ""

    if first_image:
        try:
            result = await tg("sendPhoto", {
                "chat_id": chat_id,
                "photo": first_image,
                "caption": text,
                "parse_mode": "MarkdownV2",
                "reply_markup": kb,
            })
            msg_id = str(result.get("message_id", ""))
            log.info("Vote sent with photo, msg_id=%s", msg_id)
            return msg_id
        except Exception as e:
            log.warning("Photo send failed, falling back to text: %s", e)

    result = await tg("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "MarkdownV2",
        "reply_markup": kb,
    })
    msg_id = str(result.get("message_id", ""))
    log.info("Vote sent (text only), msg_id=%s", msg_id)
    return msg_id


async def update_vote_message(
    chat_id: str,
    message_id: str,
    candidates: list[Recipe],
    voting_minutes: int,
    vote_counts: dict[str, int],
    total_votes: int,
    has_photo: bool = False,
) -> None:
    """Edit the vote message to show live vote counts."""
    text = _build_vote_text(candidates, voting_minutes, vote_counts, total_votes)
    kb = _build_keyboard(candidates)

    try:
        method = "editMessageCaption" if has_photo else "editMessageText"
        params = {
            "chat_id": chat_id,
            "message_id": int(message_id),
            "parse_mode": "MarkdownV2",
            "reply_markup": kb,
        }
        if has_photo:
            params["caption"] = text
        else:
            params["text"] = text
        await tg(method, params)
    except Exception as e:
        # "message is not modified" is expected if counts didn't change
        if "not modified" not in str(e).lower():
            log.warning("Could not update vote message: %s", e)


async def answer_callback(callback_id: str, text: str) -> None:
    """Send toast notification to voter."""
    try:
        await tg("answerCallbackQuery", {
            "callback_query_id": callback_id,
            "text": text,
            "show_alert": False,
        })
    except Exception as e:
        log.debug("answerCallbackQuery failed: %s", e)


async def send_result(
    chat_id: str,
    winner: Recipe,
    voters: list[str],
    ingredients: list[str],
    *,
    is_tie: bool = False,
    tied_names: list[str] | None = None,
) -> None:
    """Send voting result + shopping list."""
    voter_text = ", ".join(voters) if voters else "niemand"

    lines = [
        "🏆 *Ergebnis der Abstimmung*\n",
        f"🍽 *{_esc(winner.name)}* hat gewonnen\\!",
    ]
    if is_tie and tied_names:
        lines.append(f"🎲 Gleichstand mit {_esc(', '.join(tied_names))} – das Los hat entschieden\\!")

    lines.extend([
        f"Gewählt von: {_esc(voter_text)}\n",
        f"⏱ Gesamtzeit: {_esc(_fmt_time(winner.total_time))}",
        f"🍽 Portionen: {winner.serving_size}\n",
    ])

    if ingredients:
        lines.append("📋 *Einkaufsliste:*\n")
        for ing in ingredients:
            lines.append(f"  • {_esc(ing)}")

    lines.append(f"\n🔗 [Rezept auf Cookidoo]({_esc(winner.url)})")
    lines.append("\n✅ Die Einkaufsliste wurde auch in Cookidoo gespeichert\\.")

    await tg("sendMessage", {
        "chat_id": chat_id,
        "text": "\n".join(lines),
        "parse_mode": "MarkdownV2",
    })


async def send_text(chat_id: str, text: str, **kw) -> dict:
    """Send plain text message."""
    return await tg("sendMessage", {"chat_id": chat_id, "text": text, **kw})


async def send_md(chat_id: str, text: str) -> dict:
    """Send MarkdownV2 message."""
    return await tg("sendMessage", {
        "chat_id": chat_id,
        "text": _esc(text),
        "parse_mode": "MarkdownV2",
    })


# ─── Polling mode (fallback) ────────────────────────────

async def poll_votes(
    chat_id: str,
    message_id: str,
    candidates: list[Recipe],
    voting_minutes: int,
    has_photo: bool = False,
) -> dict[str, list[str]]:
    """Poll-based vote collection with live updates.

    Returns {recipe_id: [voter_name, ...]}.
    """
    import asyncio
    import time

    user_votes: dict[str, tuple[str, str]] = {}  # user_id -> (recipe_id, name)
    end_time = time.time() + voting_minutes * 60
    offset: int | None = None
    last_counts: dict[str, int] = {}

    while time.time() < end_time:
        try:
            params: dict = {"limit": 100, "timeout": 5}
            if offset is not None:
                params["offset"] = offset

            updates = await tg("getUpdates", params)
            if not isinstance(updates, list):
                updates = []

            changed = False
            for upd in updates:
                uid = upd.get("update_id")
                if uid is not None:
                    offset = uid + 1

                cb = upd.get("callback_query")
                if not cb:
                    continue

                data = cb.get("data", "")
                if not data.startswith("vote:"):
                    continue

                recipe_id = data.split(":", 1)[1]
                user = cb.get("from", {})
                user_id = str(user.get("id", ""))
                first_name = user.get("first_name", "Unbekannt")
                cb_id = cb.get("id", "")

                # Allow vote change
                old = user_votes.get(user_id)
                user_votes[user_id] = (recipe_id, first_name)
                changed = True

                recipe_name = next(
                    (c.name for c in candidates if c.id == recipe_id),
                    recipe_id,
                )

                if old and old[0] != recipe_id:
                    await answer_callback(cb_id, f"↩️ Stimme geändert zu '{recipe_name}'")
                    log.info("Vote changed: %s -> %s", first_name, recipe_name)
                elif old and old[0] == recipe_id:
                    await answer_callback(cb_id, f"✓ Du hast bereits für '{recipe_name}' gestimmt")
                    changed = False
                else:
                    await answer_callback(cb_id, f"✓ Stimme für '{recipe_name}' registriert!")
                    log.info("Vote: %s -> %s", first_name, recipe_name)

            # Update message with live counts if changed
            if changed:
                counts: dict[str, int] = {}
                for rid, _ in user_votes.values():
                    counts[rid] = counts.get(rid, 0) + 1

                if counts != last_counts:
                    await update_vote_message(
                        chat_id, message_id, candidates,
                        voting_minutes, counts, len(user_votes), has_photo,
                    )
                    last_counts = counts.copy()

        except Exception as e:
            log.warning("Poll error: %s", e)

        await asyncio.sleep(3)

    # Aggregate results
    result: dict[str, list[str]] = {}
    for _, (recipe_id, name) in user_votes.items():
        result.setdefault(recipe_id, []).append(name)
    return result
