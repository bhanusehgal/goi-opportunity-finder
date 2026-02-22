"""Digest rendering (plaintext + HTML)."""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any, Mapping, Sequence

from core.schema import Opportunity

CATEGORY_LABELS = {
    "drones_uav": "Drones/UAV",
    "robotics": "Robotics",
    "it_cyber_ai": "IT",
}


def _pack_terms(config: Mapping[str, Any], key: str) -> list[str]:
    packs = config.get("keyword_packs", {})
    return [str(item).strip().lower() for item in packs.get(key, []) if str(item).strip()]


def categorize_opportunity(opportunity: Opportunity, config: Mapping[str, Any]) -> str:
    """Assign one primary category for digest grouping."""
    text = " ".join(
        [
            opportunity.title,
            opportunity.summary or "",
            " ".join(opportunity.keywords_hit),
            opportunity.raw_text,
        ]
    ).lower()

    best_key = "it_cyber_ai"
    best_score = -1
    for key in ("drones_uav", "robotics", "it_cyber_ai"):
        terms = _pack_terms(config, key)
        score = sum(1 for term in terms if term and term in text)
        if score > best_score:
            best_key = key
            best_score = score
    return CATEGORY_LABELS[best_key]


def next_step(opportunity: Opportunity, config: Mapping[str, Any]) -> str:
    """Rules-based follow-up suggestion."""
    text = " ".join(
        [opportunity.title, opportunity.summary or "", opportunity.raw_text]
    ).lower()
    service_terms = [
        str(item).strip().lower() for item in config.get("service_terms", []) if str(item).strip()
    ]
    strict_terms = [
        str(item).strip().lower() for item in config.get("strict_terms", []) if str(item).strip()
    ]

    if opportunity.source == "idex" or "challenge" in text:
        return "Draft challenge response + demo plan"
    if any(term in text for term in service_terms):
        return "Check eligibility + pre-bid queries + capability note"
    if any(term in text for term in strict_terms):
        return "Consider consortium/prime partner"
    return "Download documents, map compliance, and assign bid owner"


def _format_plain_item(index: int, opportunity: Opportunity, config: Mapping[str, Any]) -> str:
    why = ", ".join(opportunity.keywords_hit[:6]) if opportunity.keywords_hit else "keyword match"
    deadline = opportunity.deadline.isoformat() if opportunity.deadline else "N/A"
    buyer = opportunity.buyer or opportunity.org_path or "N/A"
    return (
        f"{index}. {opportunity.title}\n"
        f"   Buyer: {buyer}\n"
        f"   Source: {opportunity.source}\n"
        f"   Deadline: {deadline}\n"
        f"   Score: {opportunity.score}\n"
        f"   Why matched: {why}\n"
        f"   Link: {opportunity.url}\n"
        f"   Next step: {next_step(opportunity, config)}\n"
    )


def _format_html_item(opportunity: Opportunity, config: Mapping[str, Any]) -> str:
    why = ", ".join(opportunity.keywords_hit[:6]) if opportunity.keywords_hit else "keyword match"
    deadline = opportunity.deadline.isoformat() if opportunity.deadline else "N/A"
    buyer = opportunity.buyer or opportunity.org_path or "N/A"
    return (
        "<li>"
        f"<strong>{escape(opportunity.title)}</strong><br/>"
        f"Buyer: {escape(buyer)}<br/>"
        f"Source: {escape(opportunity.source)}<br/>"
        f"Deadline: {escape(deadline)}<br/>"
        f"Score: {opportunity.score}<br/>"
        f"Why matched: {escape(why)}<br/>"
        f"Link: <a href=\"{escape(opportunity.url)}\">Open</a><br/>"
        f"Next step: {escape(next_step(opportunity, config))}"
        "</li>"
    )


def generate_digest(
    opportunities: Sequence[Opportunity],
    config: Mapping[str, Any],
    run_ts: datetime,
    top_n: int = 10,
) -> tuple[str, str]:
    """Generate plaintext and HTML digest."""
    sorted_items = sorted(opportunities, key=lambda item: item.score, reverse=True)

    if not sorted_items:
        date_label = run_ts.date().isoformat()
        text = f"GoI Opportunity Finder Digest ({date_label})\n\nNo new relevant opportunities today."
        html = (
            f"<h2>GoI Opportunity Finder Digest ({escape(date_label)})</h2>"
            "<p>No new relevant opportunities today.</p>"
        )
        return text, html

    grouped: dict[str, list[Opportunity]] = {"Drones/UAV": [], "Robotics": [], "IT": []}
    for item in sorted_items:
        grouped[categorize_opportunity(item, config)].append(item)

    date_label = run_ts.date().isoformat()
    header = f"GoI Opportunity Finder Digest ({date_label})"

    plain_lines = [header, "", f"Total new opportunities: {len(sorted_items)}", ""]
    plain_lines.append(f"Top {min(top_n, len(sorted_items))} Overall")
    plain_lines.append("-" * 40)
    for idx, item in enumerate(sorted_items[:top_n], start=1):
        plain_lines.append(_format_plain_item(idx, item, config))

    for group_name in ("Drones/UAV", "Robotics", "IT"):
        items = grouped[group_name]
        plain_lines.append("")
        plain_lines.append(f"{group_name} ({len(items)})")
        plain_lines.append("-" * 40)
        for idx, item in enumerate(items, start=1):
            plain_lines.append(_format_plain_item(idx, item, config))

    html_parts = [
        f"<h2>{escape(header)}</h2>",
        f"<p>Total new opportunities: <strong>{len(sorted_items)}</strong></p>",
        f"<h3>Top {min(top_n, len(sorted_items))} Overall</h3>",
        "<ol>",
    ]
    html_parts.extend(_format_html_item(item, config) for item in sorted_items[:top_n])
    html_parts.append("</ol>")

    for group_name in ("Drones/UAV", "Robotics", "IT"):
        items = grouped[group_name]
        html_parts.append(f"<h3>{escape(group_name)} ({len(items)})</h3>")
        html_parts.append("<ul>")
        html_parts.extend(_format_html_item(item, config) for item in items)
        html_parts.append("</ul>")

    return "\n".join(plain_lines), "".join(html_parts)
