"""Scoring and filtering rules for opportunities."""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Sequence

from core.schema import Opportunity

DEFAULT_PROCUREMENT_TERMS = [
    "eoi",
    "rfp",
    "tender",
    "bid",
    "proposal",
    "expression of interest",
]


def _as_terms(values: Sequence[Any] | None) -> list[str]:
    if not values:
        return []
    return [str(value).strip().lower() for value in values if str(value).strip()]


def _text_blob(opportunity: Opportunity) -> str:
    parts = [
        opportunity.title,
        opportunity.summary or "",
        opportunity.buyer or "",
        opportunity.org_path or "",
        opportunity.raw_text,
        " ".join(opportunity.documents),
    ]
    return " ".join(part for part in parts if part).lower()


def _find_hits(text: str, terms: Sequence[str]) -> list[str]:
    lowered = text.lower()
    hits = [term for term in terms if term and term in lowered]
    return sorted(set(hits))


def _collect_positive_terms(config: Mapping[str, Any]) -> list[str]:
    keyword_packs = config.get("keyword_packs", {})
    positives: list[str] = []
    for key in ("drones_uav", "robotics", "it_cyber_ai"):
        positives.extend(_as_terms(keyword_packs.get(key, [])))
    return sorted(set(positives))


def _buyer_bonus(opportunity: Opportunity, config: Mapping[str, Any]) -> tuple[int, list[str]]:
    buyer_blob = " ".join(
        part for part in [opportunity.buyer or "", opportunity.org_path or ""] if part
    ).lower()
    if not buyer_blob:
        return 0, []

    best_bonus = 0
    hits: list[str] = []
    for buyer_cfg in config.get("buyers", []):
        name = str(buyer_cfg.get("name", "")).strip()
        if not name:
            continue
        name_lower = name.lower()
        if name_lower in buyer_blob:
            weight = int(buyer_cfg.get("weight", 0))
            best_bonus = max(best_bonus, max(0, min(15, weight)))
            hits.append(f"buyer:{name}")
    return best_bonus, sorted(set(hits))


def hard_filter(opportunity: Opportunity, config: Mapping[str, Any]) -> tuple[bool, list[str], list[str]]:
    """Apply non-negotiable filters before scoring."""
    if opportunity.status == "ignore":
        return False, [], ["inactive_status"]

    text = _text_blob(opportunity)
    positive_terms = _collect_positive_terms(config)
    positive_hits = _find_hits(text, positive_terms)
    if not positive_hits:
        return False, [], []

    negative_terms = _as_terms(config.get("negative_keywords", []))
    negative_hits = _find_hits(text, negative_terms)
    allow_negative = bool(config.get("allow_negative_with_penalty", False))
    if negative_hits and not allow_negative:
        return False, positive_hits, negative_hits

    return True, positive_hits, negative_hits


def score_opportunity(
    opportunity: Opportunity, config: Mapping[str, Any], today: date | None = None
) -> int:
    """
    Score one opportunity and update its `score` and `keywords_hit`.

    Rules:
    - +30 procurement intent
    - +25 core domain in title
    - +15 high-priority buyer match (weighted)
    - +10 deadline in [7, 30] days
    - +10 document signal
    - -20 negative keyword signal
    """
    today = today or date.today()
    score = 0
    hits: list[str] = []

    text_blob = _text_blob(opportunity)
    title_and_summary = f"{opportunity.title} {opportunity.summary or ''}".lower()
    title_only = opportunity.title.lower()

    procurement_terms = _as_terms(
        config.get("procurement_terms", DEFAULT_PROCUREMENT_TERMS)
    ) or DEFAULT_PROCUREMENT_TERMS
    procurement_hits = _find_hits(title_and_summary, procurement_terms)
    if procurement_hits:
        score += 30
        hits.extend(procurement_hits)

    core_domain_terms = _collect_positive_terms(config)
    title_domain_hits = _find_hits(title_only, core_domain_terms)
    if title_domain_hits:
        score += 25
        hits.extend(title_domain_hits)

    buyer_bonus, buyer_hits = _buyer_bonus(opportunity, config)
    if buyer_bonus:
        score += buyer_bonus
        hits.extend(buyer_hits)

    if opportunity.deadline:
        days_to_deadline = (opportunity.deadline - today).days
        if 7 <= days_to_deadline <= 30:
            score += 10
            hits.append("deadline_window")

    scope_terms = _as_terms(config.get("scope_terms", []))
    documents_blob = " ".join(opportunity.documents).lower()
    docs_have_scope_signal = bool(_find_hits(documents_blob, scope_terms))
    if opportunity.documents or docs_have_scope_signal:
        score += 10
        if docs_have_scope_signal:
            hits.extend(_find_hits(documents_blob, scope_terms))
        else:
            hits.append("documents_available")

    negative_terms = _as_terms(config.get("negative_keywords", []))
    negative_hits = _find_hits(text_blob, negative_terms)
    if negative_hits:
        score -= 20
        hits.extend([f"negative:{term}" for term in negative_hits])

    clamped = max(0, min(100, score))
    opportunity.score = clamped
    opportunity.keywords_hit = sorted(set(hits))
    return clamped
