"""Common data schema for opportunities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import hashlib
import json
from typing import Any

VALID_STATUSES = {"new", "seen", "pursue", "watch", "ignore"}


def utc_now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return utc_now()


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        for fmt in (
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%Y/%m/%d",
            "%d %b %Y",
            "%d %B %Y",
            "%b %d, %Y",
            "%B %d, %Y",
        ):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
    return None


def _parse_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            loaded = json.loads(text)
            if isinstance(loaded, list):
                return [str(item).strip() for item in loaded if str(item).strip()]
        except json.JSONDecodeError:
            pass
        separator = "|" if "|" in text else ","
        return [part.strip() for part in text.split(separator) if part.strip()]
    parsed = str(value).strip()
    return [parsed] if parsed else []


@dataclass(slots=True)
class Opportunity:
    """Normalized opportunity representation."""

    source: str
    source_id: str
    title: str
    buyer: str | None
    org_path: str | None
    summary: str | None
    published_date: date | None
    deadline: date | None
    location: str | None
    estimated_value: str | None
    url: str
    documents: list[str] = field(default_factory=list)
    raw_text: str = ""
    keywords_hit: list[str] = field(default_factory=list)
    score: int = 0
    status: str = "new"
    first_seen_ts: datetime = field(default_factory=utc_now)
    last_seen_ts: datetime = field(default_factory=utc_now)
    unique_id: str = ""

    def __post_init__(self) -> None:
        self.source = self.source.strip().lower()
        self.source_id = self.source_id.strip()
        self.title = self.title.strip()
        self.buyer = self.buyer.strip() if self.buyer else None
        self.org_path = self.org_path.strip() if self.org_path else None
        self.summary = self.summary.strip() if self.summary else None
        self.location = self.location.strip() if self.location else None
        self.estimated_value = (
            self.estimated_value.strip() if self.estimated_value else None
        )
        self.url = self.url.strip()
        self.documents = _parse_list(self.documents)
        self.keywords_hit = _parse_list(self.keywords_hit)
        self.first_seen_ts = _parse_datetime(self.first_seen_ts)
        self.last_seen_ts = _parse_datetime(self.last_seen_ts)
        self.published_date = _parse_date(self.published_date)
        self.deadline = _parse_date(self.deadline)

        if not self.raw_text:
            parts = [self.title, self.summary or "", self.buyer or "", self.org_path or ""]
            self.raw_text = " ".join(part for part in parts if part).strip()

        if self.status not in VALID_STATUSES:
            self.status = "new"

        if not self.unique_id:
            self.unique_id = self.compute_unique_id(
                source=self.source,
                source_id=self.source_id,
                title=self.title,
                buyer=self.buyer,
            )

    @staticmethod
    def compute_unique_id(
        source: str, source_id: str, title: str, buyer: str | None
    ) -> str:
        """Create a stable hash for de-duplication."""
        normalized = "|".join(
            [
                source.strip().lower(),
                source_id.strip().lower(),
                title.strip().lower(),
                (buyer or "").strip().lower(),
            ]
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def to_db_payload(self) -> dict[str, Any]:
        """Return a dict payload for SQLite operations."""
        return {
            "source": self.source,
            "source_id": self.source_id,
            "title": self.title,
            "buyer": self.buyer,
            "org_path": self.org_path,
            "summary": self.summary,
            "published_date": self.published_date.isoformat() if self.published_date else None,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "location": self.location,
            "estimated_value": self.estimated_value,
            "url": self.url,
            "documents": json.dumps(self.documents, ensure_ascii=True),
            "raw_text": self.raw_text,
            "keywords_hit": json.dumps(self.keywords_hit, ensure_ascii=True),
            "score": self.score,
            "status": self.status,
            "first_seen_ts": self.first_seen_ts.isoformat(),
            "last_seen_ts": self.last_seen_ts.isoformat(),
            "unique_id": self.unique_id,
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "Opportunity":
        """Build an opportunity from a SQLite row/dict."""
        return cls(
            source=row["source"],
            source_id=row["source_id"],
            title=row["title"],
            buyer=row.get("buyer"),
            org_path=row.get("org_path"),
            summary=row.get("summary"),
            published_date=row.get("published_date"),
            deadline=row.get("deadline"),
            location=row.get("location"),
            estimated_value=row.get("estimated_value"),
            url=row["url"],
            documents=_parse_list(row.get("documents")),
            raw_text=row.get("raw_text", ""),
            keywords_hit=_parse_list(row.get("keywords_hit")),
            score=int(row.get("score", 0)),
            status=row.get("status", "new"),
            first_seen_ts=row.get("first_seen_ts"),
            last_seen_ts=row.get("last_seen_ts"),
            unique_id=row.get("unique_id", ""),
        )
