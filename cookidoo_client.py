"""Cookidoo client wrapper – fetches recipes, details, and builds shopping lists."""

import asyncio
import random
import logging
from dataclasses import dataclass

import aiohttp
from cookidoo_api import (
    Cookidoo,
    CookidooConfig,
    CookidooLocalizationConfig,
    CookidooCollection,
    CookidooChapterRecipe,
    CookidooShoppingRecipe,
    CookidooShoppingRecipeDetails,
    CookidooIngredientItem,
    CookidooIngredient,
)

from config import (
    COOKIDOO_EMAIL,
    COOKIDOO_PASSWORD,
    COOKIDOO_COUNTRY,
    COOKIDOO_LANGUAGE,
    COOKIDOO_URL,
    MAX_DIFFICULTY,
)

log = logging.getLogger(__name__)

# Difficulty levels ranked for filtering
DIFFICULTY_RANK = {"easy": 1, "medium": 2, "difficult": 3}

# Categories that count as sweets/desserts (will be filtered out)
SWEET_CATEGORY_IDS = {
    "VrkNavCategory-RPF-011",  # Desserts und Süßigkeiten
    "VrkNavCategory-RPF-013",  # Backen, süß
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


async def fetch_candidates(num: int = 7) -> list[RecipeCandidate]:
    """
    Fetch `num` recipe candidates from the user's Cookidoo collections.
    Filters by max difficulty and picks a random subset.
    """
    max_rank = DIFFICULTY_RANK.get(MAX_DIFFICULTY.lower(), 2)

    async with aiohttp.ClientSession() as session:
        api = Cookidoo(session, _make_config())
        await api.login()
        log.info("Logged in to Cookidoo")

        all_recipes = await _get_all_collection_recipe_ids(api)
        log.info("Total recipes in collections: %d", len(all_recipes))

        if not all_recipes:
            log.warning("No recipes found in collections!")
            return []

        # Shuffle and pick up to 3× candidates (we'll filter by difficulty)
        sample_size = min(len(all_recipes), num * 3)
        sample = random.sample(all_recipes, sample_size)

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

                # Build ingredient list from the shopping list API
                # We temporarily add the recipe, read ingredients, then remove it
                ingredient_items = await api.add_ingredient_items_for_recipes([rid])
                shopping_recipes = await api.get_shopping_list_recipes()

                ingredients: list[str] = []
                for sr in shopping_recipes:
                    if sr.id == rid:
                        ingredients = [
                            f"{ing.description} {ing.name}".strip()
                            for ing in sr.ingredients
                        ]
                        break

                # Clean up: remove from shopping list
                await api.remove_ingredient_items_for_recipes([rid])

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
