"""Date-range helpers for opportunity filtering."""

from __future__ import annotations

from datetime import date
from typing import Sequence

from core.schema import Opportunity


def parse_iso_date(value: str | None) -> date | None:
    """Parse YYYY-MM-DD date, returning None for empty values."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"Invalid date '{value}'. Expected YYYY-MM-DD.") from exc


def in_date_range(
    value: date | None,
    start: date | None,
    end: date | None,
    *,
    require_value_when_bounded: bool = True,
) -> bool:
    """
    Check if `value` is within [start, end].

    If any bound is provided and value is missing, returns False by default.
    """
    if start is None and end is None:
        return True
    if value is None:
        return not require_value_when_bounded
    if start is not None and value < start:
        return False
    if end is not None and value > end:
        return False
    return True


def filter_by_published_date(
    opportunities: Sequence[Opportunity],
    start: date | None,
    end: date | None,
) -> list[Opportunity]:
    """Return only opportunities whose published date fits the window."""
    return [
        item
        for item in opportunities
        if in_date_range(item.published_date, start, end, require_value_when_bounded=True)
    ]
