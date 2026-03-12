"""Winner determination with tie-breaking."""

import random
import logging
from cache import Recipe

log = logging.getLogger(__name__)


def determine_winner(
    votes: dict[str, list[str]],
    candidates: list[Recipe],
) -> tuple[Recipe, list[str], bool, list[str]]:
    """Pick winner from votes. Random tie-break.

    Returns (winner, voter_names, is_tie, tied_recipe_names).
    """
    if not votes:
        raise ValueError("No votes to evaluate")

    max_count = max(len(v) for v in votes.values())
    tied_ids = [rid for rid, v in votes.items() if len(v) == max_count]
    winner_id = random.choice(tied_ids) if len(tied_ids) > 1 else tied_ids[0]
    is_tie = len(tied_ids) > 1
    tied_names = [c.name for c in candidates if c.id in tied_ids] if is_tie else []

    winner = next((c for c in candidates if c.id == winner_id), None)
    if not winner:
        raise ValueError(f"Winner ID {winner_id} not in candidates")

    return winner, votes[winner_id], is_tie, tied_names
