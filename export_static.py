"""Export SQLite opportunity data to static JSON for the web UI."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "db.sqlite"
WEB_DIR = BASE_DIR / "web"
OUTPUT_PATH = WEB_DIR / "opportunities.json"


def main() -> int:
    WEB_DIR.mkdir(parents=True, exist_ok=True)
    if not DB_PATH.exists():
        OUTPUT_PATH.write_text(
            json.dumps({"generated_at": None, "runs": [], "opportunities": []}, indent=2),
            encoding="utf-8",
        )
        return 0

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        runs = conn.execute(
            """
            SELECT run_ts, fetched_count, kept_count, new_count, emailed_count, error_count
            FROM runs
            ORDER BY run_ts DESC
            LIMIT 30
            """
        ).fetchall()
        items = conn.execute(
            """
            SELECT
                unique_id,
                source,
                source_id,
                title,
                buyer,
                org_path,
                summary,
                published_date,
                deadline,
                url,
                documents,
                keywords_hit,
                score,
                status,
                first_seen_ts,
                last_seen_ts
            FROM opportunities
            ORDER BY score DESC, last_seen_ts DESC
            LIMIT 300
            """
        ).fetchall()
    finally:
        conn.close()

    payload = {
        "generated_at": runs[0]["run_ts"] if runs else None,
        "runs": [dict(row) for row in runs],
        "opportunities": [],
    }

    for row in items:
        row_dict = dict(row)
        for field in ("documents", "keywords_hit"):
            raw = row_dict.get(field) or "[]"
            try:
                row_dict[field] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                row_dict[field] = []
        payload["opportunities"].append(row_dict)

    OUTPUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
