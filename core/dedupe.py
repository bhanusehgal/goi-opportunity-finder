"""De-duplication logic for opportunities."""

from __future__ import annotations

import re
from typing import Mapping, Sequence

from rapidfuzz import fuzz

from core.schema import Opportunity


def normalize_for_match(value: str | None) -> str:
    """Normalize text for deterministic fuzzy comparisons."""
    if not value:
        return ""
    lowered = value.lower()
    lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def fuzzy_duplicate_of(
    candidate: Opportunity, existing: Sequence[Opportunity], threshold: float = 90.0
) -> Opportunity | None:
    """Find a likely duplicate by fuzzy title/buyer matching."""
    cand_title = normalize_for_match(candidate.title)
    cand_buyer = normalize_for_match(candidate.buyer)

    for item in existing:
        title_score = fuzz.token_set_ratio(cand_title, normalize_for_match(item.title))
        if cand_buyer and item.buyer:
            buyer_score = fuzz.token_set_ratio(cand_buyer, normalize_for_match(item.buyer))
        elif not cand_buyer and not item.buyer:
            buyer_score = 100.0
        else:
            buyer_score = 0.0

        combined_score = 0.8 * title_score + 0.2 * buyer_score
        if combined_score >= threshold:
            return item
    return None


def dedupe_opportunities(
    opportunities: Sequence[Opportunity],
    existing_by_id: Mapping[str, Opportunity] | None = None,
    threshold: float = 90.0,
) -> tuple[list[Opportunity], dict[str, str]]:
    """
    Return de-duplicated opportunities.

    Returns:
    - kept opportunities
    - map of duplicate unique_id -> canonical unique_id
    """
    existing_by_id = existing_by_id or {}
    seen_unique_ids = set(existing_by_id.keys())
    comparison_pool = list(existing_by_id.values())
    kept: list[Opportunity] = []
    duplicate_map: dict[str, str] = {}

    for item in opportunities:
        if item.unique_id in seen_unique_ids:
            duplicate_map[item.unique_id] = item.unique_id
            continue

        fuzzy_match = fuzzy_duplicate_of(item, comparison_pool, threshold=threshold)
        if fuzzy_match:
            duplicate_map[item.unique_id] = fuzzy_match.unique_id
            continue

        seen_unique_ids.add(item.unique_id)
        comparison_pool.append(item)
        kept.append(item)

    return kept, duplicate_map
