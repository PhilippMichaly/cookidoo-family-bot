"""Cookidoo client wrapper – fetches recipes, details, and builds shopping lists."""

import asyncio
import json
import random
import logging
from dataclasses import dataclass
from datetime import date, timedelta

import aiohttp
from cookidoo_api import (
    Cookidoo,
    CookidooConfig,
    CookidooLocalizationConfig,
)

from config import (
    COOKIDOO_EMAIL,
    COOKIDOO_PASSWORD,
    COOKIDOO_COUNTRY,
    COOKIDOO_LANGUAGE,
    COOKIDOO_URL,
    MAX_DIFFICULTY,
    RECIPE_HISTORY_FILE,
    RECIPE_HISTORY_DAYS,
)

log = logging.getLogger(__name__)

# Difficulty levels ranked for filtering
DIFFICULTY_RANK = {"easy": 1, "medium": 2, "difficult": 3}

# Categories that count as sweets/desserts or drinks (will be filtered out)
SWEET_CATEGORY_IDS = {
    "VrkNavCategory-RPF-011",  # Desserts und Süßigkeiten
    "VrkNavCategory-RPF-013",  # Backen, süß
}

# Drink-related categories (shakes/cocktails/smoothies etc.) to exclude.
# IDs can differ by locale/account; we also use name keywords as fallback.
DRINK_CATEGORY_IDS = {
    "VrkNavCategory-RPF-015",  # Getränke (often)
}

# Sweet keywords in recipe names (fallback if category is missing)
SWEET_NAME_KEYWORDS = [
    "kuchen", "torte", "muffin", "cookie", "keks", "plätzchen",
    "brownie", "tiramisu", "mousse", "pudding", "creme", "crème",
    "eis ", "sorbet", "panna cotta", "tarte", "praline",
    "bonbon", "konfekt", "dessert", "nachtisch", "süß",
    "schokolade", "waffel", "crêpe", "pancake", "pfannkuchen",
    "marmelade", "konfitüre", "gelee", "sirup",
    "cupcake", "donut", "macaron", "baiser", "meringue",
]

# Drink keywords in recipe names (fallback if category is missing)
DRINK_NAME_KEYWORDS = [
    "shake",
    "cocktail",
    "smoothie",
    "lassi",
    "frapp",
    "frappé",
    "milkshake",
    "eistee",
    "limonade",
    "spritz",
    "mojito",
    "caipirinha",
    "daiquiri",
    "sangria",
    "bowle",
]

# Exceptions: these sweet dishes ARE allowed
SWEET_WHITELIST = [
    "kaiserschmarrn",
    "milchreis",
]


@dataclass
class RecipeCandidate:
    """A recipe ready for the vote."""
    id: str
    name: str
    total_time: int          # seconds
    difficulty: str
    serving_size: int
    url: str
    ingredients: list[str]   # ingredient descriptions


def _is_sweet(name: str, details) -> bool:
    """Check if a recipe is a sweet/dessert based on category or name."""
    # Check categories first (most reliable)
    for cat in details.categories:
        if cat.id in SWEET_CATEGORY_IDS:
            return True

    # Fallback: keyword check in recipe name
    name_lower = name.lower()
    for keyword in SWEET_NAME_KEYWORDS:
        if keyword in name_lower:
            return True

    return False


def _is_drink(name: str, details) -> bool:
    """Check if a recipe is a drink (shake/cocktail etc.) based on category or name."""
    for cat in details.categories:
        if cat.id in DRINK_CATEGORY_IDS:
            return True

    name_lower = name.lower()
    for keyword in DRINK_NAME_KEYWORDS:
        if keyword in name_lower:
            return True

    return False


def _is_whitelisted(name: str) -> bool:
    """Check if a sweet recipe is on the whitelist (allowed despite being sweet)."""
    name_lower = name.lower()
    return any(w in name_lower for w in SWEET_WHITELIST)


def _make_config() -> CookidooConfig:
    return CookidooConfig(
        localization=CookidooLocalizationConfig(
            country_code=COOKIDOO_COUNTRY,
            language=COOKIDOO_LANGUAGE,
            url=COOKIDOO_URL,
        ),
        email=COOKIDOO_EMAIL,
        password=COOKIDOO_PASSWORD,
    )


async def _get_all_collection_recipe_ids(api: Cookidoo) -> list[tuple[str, str]]:
    """Return [(recipe_id, recipe_name), ...] from all collections."""
    recipes: list[tuple[str, str]] = []

    # Managed collections (Cookidoo curated)
    try:
        count, pages = await api.count_managed_collections()
        log.info("Managed collections: %d (%d pages)", count, pages)
        for page in range(pages):
            collections = await api.get_managed_collections(page=page)
            for col in collections:
                for chapter in col.chapters:
                    for r in chapter.recipes:
                        recipes.append((r.id, r.name))
    except Exception as e:
        log.warning("Could not load managed collections: %s", e)

    # Custom collections
    try:
        count, pages = await api.count_custom_collections()
        log.info("Custom collections: %d (%d pages)", count, pages)
        for page in range(pages):
            collections = await api.get_custom_collections(page=page)
            for col in collections:
                for chapter in col.chapters:
                    for r in chapter.recipes:
                        recipes.append((r.id, r.name))
    except Exception as e:
        log.warning("Could not load custom collections: %s", e)

    # Deduplicate by id
    seen = set()
    unique = []
    for rid, rname in recipes:
        if rid not in seen:
            seen.add(rid)
            unique.append((rid, rname))

    return unique


def _load_recent_winner_ids() -> set[str]:
    """Load recipe IDs that won within the last RECIPE_HISTORY_DAYS days."""
    try:
        with open(RECIPE_HISTORY_FILE) as f:
            history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

    cutoff = (date.today() - timedelta(days=RECIPE_HISTORY_DAYS)).isoformat()
    return {entry["id"] for entry in history if entry.get("date", "") >= cutoff}


def save_winner_to_history(recipe_id: str, recipe_name: str) -> None:
    """Append today's winner to the history file."""
    try:
        with open(RECIPE_HISTORY_FILE) as f:
            history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        history = []

    history.append({
        "id": recipe_id,
        "name": recipe_name,
        "date": date.today().isoformat(),
    })

    # Prune entries older than RECIPE_HISTORY_DAYS
    cutoff = (date.today() - timedelta(days=RECIPE_HISTORY_DAYS)).isoformat()
    history = [e for e in history if e.get("date", "") >= cutoff]

    with open(RECIPE_HISTORY_FILE, "w") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    log.info("Saved winner '%s' to history (%d entries)", recipe_name, len(history))


async def fetch_candidates(num: int = 7) -> list[RecipeCandidate]:
    """
    Fetch `num` recipe candidates from the user's Cookidoo collections.
    Filters by max difficulty, recent winners, and picks a random subset.
    """
    max_rank = DIFFICULTY_RANK.get(MAX_DIFFICULTY.lower(), 2)
    recent_ids = _load_recent_winner_ids()
    if recent_ids:
        log.info("Excluding %d recent winners from last %d days", len(recent_ids), RECIPE_HISTORY_DAYS)

    async with aiohttp.ClientSession() as session:
        api = Cookidoo(session, _make_config())
        await api.login()
        log.info("Logged in to Cookidoo")

        all_recipes = await _get_all_collection_recipe_ids(api)
        log.info("Total recipes in collections: %d", len(all_recipes))

        if not all_recipes:
            log.warning("No recipes found in collections!")
            return []

        # Remove recent winners from the pool
        pool = [(rid, rname) for rid, rname in all_recipes if rid not in recent_ids]
        if not pool:
            log.warning("All recipes were recent winners — using full pool as fallback")
            pool = all_recipes

        # Shuffle and pick up to 3× candidates (we'll filter by difficulty)
        sample_size = min(len(pool), num * 3)
        sample = random.sample(pool, sample_size)

        candidates: list[RecipeCandidate] = []
        for rid, rname in sample:
            if len(candidates) >= num:
                break
            try:
                details = await api.get_recipe_details(rid)
                diff = details.difficulty.lower() if details.difficulty else "easy"
                diff_rank = DIFFICULTY_RANK.get(diff, 2)
                if diff_rank > max_rank:
                    log.debug("Skipping %s (difficulty=%s)", rname, diff)
                    continue

                # Filter out sweets/desserts (unless whitelisted)
                if _is_sweet(rname, details) and not _is_whitelisted(rname):
                    log.debug("Skipping sweet: %s", rname)
                    continue

                # Filter out drinks (shakes/cocktails etc.)
                if _is_drink(rname, details):
                    log.debug("Skipping drink: %s", rname)
                    continue

                # Ingredients are loaded lazily – only for the winner in
                # add_to_shopping_list(). This avoids 3 extra API calls per
                # candidate (add → read → remove).
                ingredients: list[str] = []

                recipe_url = f"{COOKIDOO_URL}/recipes/recipe/{COOKIDOO_LANGUAGE}/{rid}"

                candidates.append(RecipeCandidate(
                    id=rid,
                    name=rname,
                    total_time=details.total_time,
                    difficulty=diff,
                    serving_size=details.serving_size,
                    url=recipe_url,
                    ingredients=ingredients,
                ))
                log.info("Candidate: %s (%s, %d min)", rname, diff, details.total_time // 60)

            except Exception as e:
                log.warning("Could not fetch details for %s: %s", rname, e)
                continue

    return candidates


async def add_to_shopping_list(recipe_id: str) -> list[str]:
    """
    Add the winning recipe's ingredients to Cookidoo shopping list.
    Returns the list of ingredient descriptions.
    """
    async with aiohttp.ClientSession() as session:
        api = Cookidoo(session, _make_config())
        await api.login()

        # Add ingredients for the winning recipe (without clearing existing items)
        await api.add_ingredient_items_for_recipes([recipe_id])
        log.info("Added ingredients for recipe %s", recipe_id)

        # Fetch the shopping list
        shopping_recipes = await api.get_shopping_list_recipes()
        ingredients: list[str] = []
        for sr in shopping_recipes:
            if sr.id == recipe_id:
                ingredients = [
                    f"{ing.description} {ing.name}".strip()
                    for ing in sr.ingredients
                ]
                break

        return ingredients
