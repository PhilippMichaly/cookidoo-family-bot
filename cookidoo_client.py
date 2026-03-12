"""Cookidoo client — only shopping list operations.

Recipe fetching/filtering is handled by cache.py.
This module only talks to Cookidoo when the winner needs
to be added to the shopping list.
"""

import logging

import aiohttp
from cookidoo_api import Cookidoo, CookidooConfig, CookidooLocalizationConfig

import config as cfg

log = logging.getLogger(__name__)


def _make_config() -> CookidooConfig:
    return CookidooConfig(
        localization=CookidooLocalizationConfig(
            country_code=cfg.COOKIDOO_COUNTRY,
            language=cfg.COOKIDOO_LANGUAGE,
            url=cfg.COOKIDOO_URL,
        ),
        email=cfg.COOKIDOO_EMAIL,
        password=cfg.COOKIDOO_PASSWORD,
    )


async def add_to_shopping_list(recipe_id: str) -> list[str]:
    """Add winner's ingredients to Cookidoo and return ingredient list."""
    async with aiohttp.ClientSession() as session:
        api = Cookidoo(session, _make_config())
        await api.login()

        await api.add_ingredient_items_for_recipes([recipe_id])
        log.info("Added ingredients for %s", recipe_id)

        recipes = await api.get_shopping_list_recipes()
        for sr in recipes:
            if sr.id == recipe_id:
                return [
                    f"{ing.description} {ing.name}".strip()
                    for ing in sr.ingredients
                ]
    return []
