"""Normalization utilities for raw connector records."""

from __future__ import annotations

from datetime import date, datetime
import hashlib
import re
from typing import Any, Mapping, Sequence

from core.schema import Opportunity, utc_now

DATE_FORMATS = (
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%Y/%m/%d",
    "%d.%m.%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
)

ACTIVE_STATUS_TERMS = ("open", "active", "published", "live")
INACTIVE_STATUS_TERMS = ("closed", "cancelled", "awarded", "expired", "inactive")


def clean_text(value: Any) -> str:
    """Normalize whitespace and cast values to text."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def parse_date(value: Any) -> date | None:
    """Convert raw string/date to date when possible."""
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()

    text = clean_text(value)
    if not text:
        return None

    # Keep deterministic parsing by trimming common datetime suffixes first.
    text = text.replace("T", " ").split(" ")[0]

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _first_string(record: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        if key in record and record[key] is not None:
            text = clean_text(record[key])
            if text:
                return text
    return None


def _parse_documents(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [clean_text(item) for item in value if clean_text(item)]
    text = clean_text(value)
    if not text:
        return []
    separator = ";" if ";" in text else ","
    return [part.strip() for part in text.split(separator) if part.strip()]


def status_is_active(source_status: str | None) -> bool:
    """Return whether source-provided status suggests item is open."""
    if not source_status:
        return True
    lowered = source_status.strip().lower()
    if any(token in lowered for token in INACTIVE_STATUS_TERMS):
        return False
    if any(token in lowered for token in ACTIVE_STATUS_TERMS):
        return True
    return True


def normalize_record(
    record: Mapping[str, Any], source: str, now: datetime | None = None
) -> Opportunity | None:
    """Normalize one raw connector record into an Opportunity."""
    normalized_now = now or utc_now()

    source_id = _first_string(
        record,
        [
            "source_id",
            "id",
            "tender_id",
            "tenderId",
            "bid_number",
            "bid_no",
            "challenge_id",
            "reference_no",
            "number",
        ],
    )
    title = _first_string(record, ["title", "name", "subject", "headline"])
    url = _first_string(record, ["url", "link", "details_url"])

    if not title or not url:
        return None

    if not source_id:
        digest = hashlib.sha256(f"{source}|{title}|{url}".encode("utf-8")).hexdigest()
        source_id = digest[:16]

    buyer = _first_string(record, ["buyer", "department", "dept", "organization", "org"])
    org_path = _first_string(record, ["org_path", "ministry", "agency"])
    summary = _first_string(record, ["summary", "description", "desc", "snippet"])
    published_date = parse_date(
        _first_string(record, ["published_date", "published", "publish_date", "date"])
    )
    deadline = parse_date(
        _first_string(record, ["deadline", "closing_date", "end_date", "due_date"])
    )
    location = _first_string(record, ["location", "city", "state"])
    estimated_value = _first_string(
        record, ["estimated_value", "value", "emd", "tender_value"]
    )
    documents = _parse_documents(record.get("documents"))
    source_status = _first_string(record, ["source_status", "status", "bid_status"])

    raw_parts = [
        title,
        summary or "",
        buyer or "",
        org_path or "",
        " ".join(documents),
        source_status or "",
    ]
    raw_text = clean_text(" ".join(raw_parts))

    status = "new" if status_is_active(source_status) else "ignore"

    return Opportunity(
        source=source,
        source_id=source_id,
        title=title,
        buyer=buyer,
        org_path=org_path,
        summary=summary,
        published_date=published_date,
        deadline=deadline,
        location=location,
        estimated_value=estimated_value,
        url=url,
        documents=documents,
        raw_text=raw_text,
        status=status,
        first_seen_ts=normalized_now,
        last_seen_ts=normalized_now,
    )


def normalize_records(
    records: Sequence[Mapping[str, Any]], source: str, now: datetime | None = None
) -> list[Opportunity]:
    """Normalize many records while dropping invalid rows."""
    normalized: list[Opportunity] = []
    for record in records:
        item = normalize_record(record, source=source, now=now)
        if item:
            normalized.append(item)
    return normalized
