"""SQLite recipe cache — sync once, serve locally.

Stores recipe metadata + details so daily votes need zero Cookidoo API
calls until the winner's shopping list is built.
"""

import json
import logging
import random
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import config as cfg

log = logging.getLogger(__name__)

DIFFICULTY_RANK = {"easy": 1, "medium": 2, "difficult": 3}


@dataclass
class Recipe:
    """Cached recipe ready for voting."""
    id: str
    name: str
    total_time: int
    difficulty: str
    serving_size: int
    url: str
    categories: str  # JSON list of category IDs
    image_url: str = ""


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(cfg.CACHE_DB_FILE))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recipes (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            total_time INTEGER DEFAULT 0,
            difficulty TEXT DEFAULT 'easy',
            serving_size INTEGER DEFAULT 4,
            url TEXT DEFAULT '',
            categories TEXT DEFAULT '[]',
            image_url TEXT DEFAULT '',
            updated_at REAL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id TEXT,
            name TEXT,
            date TEXT,
            PRIMARY KEY (id, date)
        )
    """)
    conn.commit()
    return conn


def needs_refresh() -> bool:
    """Check if cache is stale and needs a Cookidoo sync."""
    conn = _db()
    row = conn.execute(
        "SELECT value FROM meta WHERE key='last_sync'"
    ).fetchone()
    conn.close()
    if not row:
        return True
    try:
        last = float(row["value"])
        return (time.time() - last) > cfg.CACHE_REFRESH_HOURS * 3600
    except (ValueError, TypeError):
        return True


async def sync_from_cookidoo() -> int:
    """Pull all recipes from Cookidoo collections into cache.

    Returns number of recipes cached.
    """
    import aiohttp
    from cookidoo_api import Cookidoo, CookidooConfig, CookidooLocalizationConfig

    api_cfg = CookidooConfig(
        localization=CookidooLocalizationConfig(
            country_code=cfg.COOKIDOO_COUNTRY,
            language=cfg.COOKIDOO_LANGUAGE,
            url=cfg.COOKIDOO_URL,
        ),
        email=cfg.COOKIDOO_EMAIL,
        password=cfg.COOKIDOO_PASSWORD,
    )

    conn = _db()
    count = 0

    async with aiohttp.ClientSession() as session:
        api = Cookidoo(session, api_cfg)
        await api.login()
        log.info("Logged in to Cookidoo for cache sync")

        # Gather all recipe IDs from collections
        all_ids: dict[str, str] = {}  # id -> name

        for count_fn, get_fn in [
            (api.count_managed_collections, api.get_managed_collections),
            (api.count_custom_collections, api.get_custom_collections),
        ]:
            try:
                total, pages = await count_fn()
                for page in range(pages):
                    collections = await get_fn(page=page)
                    for col in collections:
                        for chapter in col.chapters:
                            for r in chapter.recipes:
                                all_ids[r.id] = r.name
            except Exception as e:
                log.warning("Collection fetch error: %s", e)

        log.info("Found %d unique recipes in collections", len(all_ids))

        # Fetch details for each (with rate limiting)
        for rid, rname in all_ids.items():
            try:
                details = await api.get_recipe_details(rid)
                diff = (details.difficulty or "easy").lower()
                cats = json.dumps([c.id for c in details.categories])

                # Try to get image URL
                image_url = ""
                if hasattr(details, "image") and details.image:
                    image_url = str(details.image)
                elif hasattr(details, "images") and details.images:
                    image_url = str(details.images[0]) if details.images else ""

                recipe_url = f"{cfg.COOKIDOO_URL}/recipes/recipe/{cfg.COOKIDOO_LANGUAGE}/{rid}"

                conn.execute("""
                    INSERT OR REPLACE INTO recipes
                    (id, name, total_time, difficulty, serving_size, url, categories, image_url, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    rid, rname, details.total_time, diff,
                    details.serving_size, recipe_url, cats, image_url,
                    time.time(),
                ))
                count += 1

                if count % 50 == 0:
                    conn.commit()
                    log.info("Cached %d/%d recipes...", count, len(all_ids))

            except Exception as e:
                log.warning("Detail fetch failed for %s: %s", rname, e)

    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_sync', ?)",
        (str(time.time()),)
    )
    conn.commit()
    conn.close()
    log.info("Cache sync complete: %d recipes", count)
    return count


def _load_filters() -> dict:
    """Load filter keywords from filters.json."""
    try:
        return json.loads(cfg.FILTERS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _load_recent_winner_ids() -> set[str]:
    """Get recipe IDs that won recently."""
    days = cfg.get("history_days") or cfg.RECIPE_HISTORY_DAYS
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    conn = _db()
    rows = conn.execute(
        "SELECT id FROM history WHERE date >= ?", (cutoff,)
    ).fetchall()
    conn.close()
    return {r["id"] for r in rows}


def save_winner(recipe_id: str, recipe_name: str) -> None:
    """Record today's winner and prune old entries."""
    days = cfg.get("history_days") or cfg.RECIPE_HISTORY_DAYS
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    conn = _db()
    conn.execute(
        "INSERT OR REPLACE INTO history (id, name, date) VALUES (?, ?, ?)",
        (recipe_id, recipe_name, date.today().isoformat()),
    )
    conn.execute("DELETE FROM history WHERE date < ?", (cutoff,))
    conn.commit()
    conn.close()


def get_candidates(num: int | None = None) -> list[Recipe]:
    """Pick random candidates from cache, applying all filters.

    Zero API calls — everything comes from SQLite.
    """
    if num is None:
        num = cfg.get("num_candidates") or cfg.NUM_RECIPE_CANDIDATES

    max_diff = cfg.get("max_difficulty") or cfg.MAX_DIFFICULTY
    max_rank = DIFFICULTY_RANK.get(max_diff.lower(), 2)
    recent_ids = _load_recent_winner_ids()
    filters = _load_filters()
    filter_sweets = cfg.get("filter_sweets") is not False
    filter_drinks = cfg.get("filter_drinks") is not False

    sweet_cat_ids = set(filters.get("sweet_category_ids", []))
    drink_cat_ids = set(filters.get("drink_category_ids", []))
    sweet_kw = filters.get("sweet_keywords", [])
    drink_kw = filters.get("drink_keywords", [])
    whitelist = filters.get("sweet_whitelist", [])

    conn = _db()
    rows = conn.execute("SELECT * FROM recipes").fetchall()
    conn.close()

    pool: list[Recipe] = []
    for r in rows:
        rid = r["id"]
        if rid in recent_ids:
            continue

        diff_rank = DIFFICULTY_RANK.get(r["difficulty"], 2)
        if diff_rank > max_rank:
            continue

        name_lower = r["name"].lower()
        cats = set(json.loads(r["categories"]))

        # Sweet filter
        if filter_sweets:
            is_sweet = bool(cats & sweet_cat_ids) or any(k in name_lower for k in sweet_kw)
            is_wl = any(w in name_lower for w in whitelist)
            if is_sweet and not is_wl:
                continue

        # Drink filter
        if filter_drinks:
            is_drink = bool(cats & drink_cat_ids) or any(k in name_lower for k in drink_kw)
            if is_drink:
                continue

        pool.append(Recipe(
            id=rid,
            name=r["name"],
            total_time=r["total_time"],
            difficulty=r["difficulty"],
            serving_size=r["serving_size"],
            url=r["url"],
            categories=r["categories"],
            image_url=r["image_url"] or "",
        ))

    if not pool:
        log.warning("No recipes match filters — returning empty")
        return []

    return random.sample(pool, min(num, len(pool)))


def get_recipe_by_id(recipe_id: str) -> Recipe | None:
    """Lookup single recipe from cache."""
    conn = _db()
    row = conn.execute(
        "SELECT * FROM recipes WHERE id=?", (recipe_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return Recipe(
        id=row["id"], name=row["name"], total_time=row["total_time"],
        difficulty=row["difficulty"], serving_size=row["serving_size"],
        url=row["url"], categories=row["categories"],
        image_url=row["image_url"] or "",
    )
