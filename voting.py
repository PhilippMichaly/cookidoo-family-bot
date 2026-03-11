"""Shared voting logic – winner determination with tie-breaking."""

import random
import logging

from cookidoo_client import RecipeCandidate

log = logging.getLogger(__name__)


def determine_winner(
    votes: dict[str, list[str]],
    candidates: list[RecipeCandidate],
) -> tuple[RecipeCandidate, list[str], bool, list[str]]:
    """
    Determine the winner of a vote.

    If there's a tie, the winner is chosen randomly among tied recipes.

    Returns:
        (winner, voter_names, is_tie, tied_recipe_names)
    """
    max_votes = max(len(v) for v in votes.values())
    tied_ids = [rid for rid, v in votes.items() if len(v) == max_votes]

    winner_id = random.choice(tied_ids) if len(tied_ids) > 1 else tied_ids[0]
    is_tie = len(tied_ids) > 1
    tied_names = [c.name for c in candidates if c.id in tied_ids] if is_tie else []

    winner = next((c for c in candidates if c.id == winner_id), None)
    if not winner:
        raise ValueError(f"Winner ID {winner_id} not found in candidates")

    voter_names = votes[winner_id]
    log.info("Winner: %s (%d votes%s)", winner.name, len(voter_names),
             f", tie with {tied_names}" if is_tie else "")
    return winner, voter_names, is_tie, tied_names
