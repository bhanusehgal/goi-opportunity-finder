"""SQLite storage layer for opportunities and run metadata."""

from __future__ import annotations

from datetime import date, datetime, timezone
import sqlite3
from pathlib import Path
from typing import Iterable

from core.schema import Opportunity


def _ts(value: datetime) -> str:
    normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return normalized.isoformat()


class Storage:
    """SQLite-backed persistence for opportunities and run history."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.init_schema()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def init_schema(self) -> None:
        """Initialize schema on first run."""
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS opportunities (
                unique_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                source_id TEXT NOT NULL,
                title TEXT NOT NULL,
                buyer TEXT,
                org_path TEXT,
                summary TEXT,
                published_date TEXT,
                deadline TEXT,
                location TEXT,
                estimated_value TEXT,
                url TEXT NOT NULL,
                documents TEXT NOT NULL DEFAULT '[]',
                raw_text TEXT NOT NULL,
                keywords_hit TEXT NOT NULL DEFAULT '[]',
                score INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'new',
                first_seen_ts TEXT NOT NULL,
                last_seen_ts TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_opportunities_source ON opportunities(source);
            CREATE INDEX IF NOT EXISTS idx_opportunities_deadline ON opportunities(deadline);
            CREATE INDEX IF NOT EXISTS idx_opportunities_last_seen ON opportunities(last_seen_ts);

            CREATE TABLE IF NOT EXISTS runs (
                run_ts TEXT PRIMARY KEY,
                fetched_count INTEGER NOT NULL,
                kept_count INTEGER NOT NULL,
                new_count INTEGER NOT NULL,
                emailed_count INTEGER NOT NULL,
                error_count INTEGER NOT NULL,
                errors TEXT
            );

            CREATE TABLE IF NOT EXISTS decisions (
                unique_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                note TEXT,
                follow_up_date TEXT,
                updated_ts TEXT NOT NULL,
                FOREIGN KEY(unique_id) REFERENCES opportunities(unique_id)
            );
            """
        )
        self.conn.commit()

    def load_existing_map(self) -> dict[str, Opportunity]:
        """Load all opportunities as map[unique_id]."""
        rows = self.conn.execute("SELECT * FROM opportunities").fetchall()
        return {row["unique_id"]: Opportunity.from_db_row(dict(row)) for row in rows}

    def purge_placeholder_records(self) -> int:
        """Remove placeholder/mock records that contain synthetic sample markers."""
        cursor = self.conn.execute(
            """
            DELETE FROM opportunities
            WHERE source_id LIKE '%SAMPLE%'
               OR url LIKE '%/sample/%'
            """
        )
        removed = int(cursor.rowcount or 0)
        if removed:
            self.conn.execute(
                """
                DELETE FROM decisions
                WHERE unique_id NOT IN (SELECT unique_id FROM opportunities)
                """
            )
        self.conn.commit()
        return removed

    def _decision_status(self, unique_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT status FROM decisions WHERE unique_id = ?",
            (unique_id,),
        ).fetchone()
        return row["status"] if row else None

    def upsert_opportunities(
        self, opportunities: Iterable[Opportunity], run_ts: datetime
    ) -> tuple[int, int, list[Opportunity]]:
        """Insert/update opportunities and return counts with inserted rows."""
        inserted = 0
        updated = 0
        new_items: list[Opportunity] = []
        run_iso = _ts(run_ts)

        for item in opportunities:
            existing = self.conn.execute(
                "SELECT status, first_seen_ts FROM opportunities WHERE unique_id = ?",
                (item.unique_id,),
            ).fetchone()

            manual_status = self._decision_status(item.unique_id)

            if existing is None:
                item.status = manual_status or "new"
                item.first_seen_ts = run_ts
                item.last_seen_ts = run_ts
                payload = item.to_db_payload()
                self.conn.execute(
                    """
                    INSERT INTO opportunities (
                        unique_id, source, source_id, title, buyer, org_path, summary,
                        published_date, deadline, location, estimated_value, url, documents,
                        raw_text, keywords_hit, score, status, first_seen_ts, last_seen_ts
                    ) VALUES (
                        :unique_id, :source, :source_id, :title, :buyer, :org_path, :summary,
                        :published_date, :deadline, :location, :estimated_value, :url, :documents,
                        :raw_text, :keywords_hit, :score, :status, :first_seen_ts, :last_seen_ts
                    )
                    """,
                    payload,
                )
                inserted += 1
                new_items.append(item)
                continue

            if manual_status:
                resolved_status = manual_status
            elif existing["status"] in {"pursue", "watch", "ignore"}:
                resolved_status = existing["status"]
            else:
                resolved_status = "seen"

            item.status = resolved_status
            item.first_seen_ts = datetime.fromisoformat(existing["first_seen_ts"])
            item.last_seen_ts = run_ts
            payload = item.to_db_payload()
            self.conn.execute(
                """
                UPDATE opportunities
                SET source=:source,
                    source_id=:source_id,
                    title=:title,
                    buyer=:buyer,
                    org_path=:org_path,
                    summary=:summary,
                    published_date=:published_date,
                    deadline=:deadline,
                    location=:location,
                    estimated_value=:estimated_value,
                    url=:url,
                    documents=:documents,
                    raw_text=:raw_text,
                    keywords_hit=:keywords_hit,
                    score=:score,
                    status=:status,
                    first_seen_ts=:first_seen_ts,
                    last_seen_ts=:last_seen_ts
                WHERE unique_id=:unique_id
                """,
                payload,
            )
            updated += 1

        self.conn.commit()
        return inserted, updated, new_items

    def touch_seen(self, unique_ids: Iterable[str], run_ts: datetime) -> None:
        """Mark known duplicates as seen in this run."""
        ids = sorted(set(uid for uid in unique_ids if uid))
        if not ids:
            return
        run_iso = _ts(run_ts)
        for unique_id in ids:
            self.conn.execute(
                """
                UPDATE opportunities
                SET last_seen_ts = ?,
                    status = CASE
                        WHEN status = 'new' THEN 'seen'
                        ELSE status
                    END
                WHERE unique_id = ?
                """,
                (run_iso, unique_id),
            )
        self.conn.commit()

    def record_run(
        self,
        run_ts: datetime,
        fetched_count: int,
        kept_count: int,
        new_count: int,
        emailed_count: int,
        errors: list[str],
    ) -> None:
        """Persist run summary."""
        self.conn.execute(
            """
            INSERT INTO runs (
                run_ts, fetched_count, kept_count, new_count, emailed_count, error_count, errors
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _ts(run_ts),
                fetched_count,
                kept_count,
                new_count,
                emailed_count,
                len(errors),
                "\n".join(errors) if errors else None,
            ),
        )
        self.conn.commit()

    def upsert_decision(
        self,
        unique_id: str,
        status: str,
        note: str | None = None,
        follow_up_date: date | None = None,
    ) -> None:
        """Insert or update manual decision for an opportunity."""
        follow_up = follow_up_date.isoformat() if follow_up_date else None
        now = _ts(datetime.now(timezone.utc))
        self.conn.execute(
            """
            INSERT INTO decisions (unique_id, status, note, follow_up_date, updated_ts)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(unique_id) DO UPDATE SET
                status=excluded.status,
                note=excluded.note,
                follow_up_date=excluded.follow_up_date,
                updated_ts=excluded.updated_ts
            """,
            (unique_id, status, note, follow_up, now),
        )
        self.conn.commit()
