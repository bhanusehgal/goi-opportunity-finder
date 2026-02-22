"""Daily runner for GoI Opportunity Finder."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from typing import Any

from dotenv import load_dotenv
import yaml

from connectors.eprocure import fetch_opportunities as fetch_eprocure
from connectors.gem import fetch_opportunities as fetch_gem
from connectors.idex import fetch_opportunities as fetch_idex
from core.date_range import filter_by_published_date, parse_iso_date
from core.dedupe import dedupe_opportunities
from core.digest import generate_digest
from core.emailer import send_email
from core.logging_setup import setup_logging
from core.normalize import normalize_records
from core.scoring import hard_filter, score_opportunity
from core.storage import Storage

BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
DB_PATH = DATA_DIR / "db.sqlite"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI flags for run behavior."""
    parser = argparse.ArgumentParser(description="GoI Opportunity Finder daily runner")
    parser.add_argument(
        "--published-from",
        default=None,
        help="Filter and crawl from this e-Published date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--published-to",
        default=None,
        help="Filter and crawl up to this e-Published date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--eprocure-max-pages",
        default=None,
        type=int,
        help="Cap on eProcure pages to fetch when paginating.",
    )
    return parser.parse_args(argv)


def _parse_optional_positive_int(value: str | None) -> int | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        parsed = int(text)
        return parsed if parsed > 0 else None
    except ValueError:
        return None


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"YAML at {path} must be a mapping")
    return loaded


def load_scoring_config() -> dict[str, Any]:
    keywords_cfg = load_yaml(CONFIG_DIR / "keywords.yaml")
    negatives_cfg = load_yaml(CONFIG_DIR / "negatives.yaml")
    buyers_cfg = load_yaml(CONFIG_DIR / "buyers.yaml")

    allow_negative = os.getenv("ALLOW_NEGATIVE_WITH_PENALTY", "false").strip().lower()
    allow_negative_bool = allow_negative in {"1", "true", "yes", "y"}

    config = {
        "keyword_packs": {
            "drones_uav": keywords_cfg.get("drones_uav", []),
            "robotics": keywords_cfg.get("robotics", []),
            "it_cyber_ai": keywords_cfg.get("it_cyber_ai", []),
        },
        "procurement_terms": keywords_cfg.get("procurement_terms", []),
        "scope_terms": keywords_cfg.get("scope_terms", []),
        "service_terms": keywords_cfg.get("service_terms", []),
        "strict_terms": keywords_cfg.get("strict_terms", []),
        "negative_keywords": negatives_cfg.get("negative_keywords", []),
        "buyers": buyers_cfg.get("buyers", []),
        "allow_negative_with_penalty": allow_negative_bool,
    }
    return config


def main(argv: list[str] | None = None) -> int:
    load_dotenv(BASE_DIR / ".env")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    args = parse_args(argv)

    logger = setup_logging(
        level=os.getenv("LOG_LEVEL", "INFO"),
        log_file=DATA_DIR / "finder.log",
    )
    run_ts = datetime.now(timezone.utc)

    logger.info("Run started at %s", run_ts.isoformat())
    config = load_scoring_config()

    env_published_from = os.getenv("PUBLISHED_FROM")
    env_published_to = os.getenv("PUBLISHED_TO")
    try:
        published_from = parse_iso_date(args.published_from or env_published_from)
        published_to = parse_iso_date(args.published_to or env_published_to)
    except ValueError as exc:
        logger.error(str(exc))
        return 2
    if published_from and published_to and published_from > published_to:
        logger.error(
            "Invalid date range: published-from (%s) is later than published-to (%s)",
            published_from.isoformat(),
            published_to.isoformat(),
        )
        return 2

    eprocure_max_pages = args.eprocure_max_pages or _parse_optional_positive_int(
        os.getenv("EPROCURE_MAX_PAGES")
    )
    if published_from or published_to:
        logger.info(
            "Date range enabled | published_from=%s published_to=%s eprocure_max_pages=%s",
            published_from.isoformat() if published_from else None,
            published_to.isoformat() if published_to else None,
            eprocure_max_pages,
        )

    connectors = {
        "eprocure": fetch_eprocure,
        "gem": fetch_gem,
        "idex": fetch_idex,
    }

    fetched_count = 0
    errors: list[str] = []
    raw_records_by_source: dict[str, list[dict[str, Any]]] = {}

    for source, fetch_fn in connectors.items():
        try:
            fetch_kwargs: dict[str, Any] = {
                "cache_dir": CACHE_DIR,
                "logger": logger,
                "published_from": published_from,
                "published_to": published_to,
            }
            if source == "eprocure":
                fetch_kwargs["max_pages"] = eprocure_max_pages
            records = fetch_fn(**fetch_kwargs)
            raw_records_by_source[source] = records
            fetched_count += len(records)
            logger.info("%s fetched=%s", source, len(records))
        except Exception as exc:
            message = f"{source}: {exc}"
            errors.append(message)
            logger.exception("Connector failed for %s", source)

    if fetched_count == 0 and len(errors) == len(connectors):
        logger.error("Fatal: all connectors failed and no records were fetched.")
        with Storage(DB_PATH) as storage:
            storage.record_run(
                run_ts=run_ts,
                fetched_count=0,
                kept_count=0,
                new_count=0,
                emailed_count=0,
                errors=errors,
            )
        return 1

    normalized = []
    for source, records in raw_records_by_source.items():
        normalized.extend(normalize_records(records, source=source, now=run_ts))
    if published_from or published_to:
        before = len(normalized)
        normalized = filter_by_published_date(normalized, published_from, published_to)
        logger.info(
            "published_date_filter kept=%s dropped=%s",
            len(normalized),
            before - len(normalized),
        )
    logger.info("normalized=%s", len(normalized))

    kept = []
    for item in normalized:
        keep, _, _ = hard_filter(item, config)
        if not keep:
            continue
        score_opportunity(item, config, today=run_ts.date())
        if item.score <= 0:
            continue
        kept.append(item)
    logger.info("kept_after_filter_score=%s", len(kept))

    emailed_count = 0
    new_count = 0
    with Storage(DB_PATH) as storage:
        purged_count = storage.purge_placeholder_records()
        if purged_count:
            logger.info("purged_placeholder_records=%s", purged_count)

        existing = storage.load_existing_map()
        deduped, duplicate_map = dedupe_opportunities(kept, existing_by_id=existing)
        new_count, _, new_items = storage.upsert_opportunities(deduped, run_ts=run_ts)
        storage.touch_seen(duplicate_map.values(), run_ts=run_ts)

        digest_text, digest_html = generate_digest(
            opportunities=new_items,
            config=config,
            run_ts=run_ts,
            top_n=10,
        )

        if new_items:
            subject = f"GoI Opportunity Finder Digest - {run_ts.date().isoformat()} ({len(new_items)} new)"
            if send_email(subject=subject, text_body=digest_text, html_body=digest_html):
                emailed_count = len(new_items)
        else:
            logger.info("No new opportunities after dedupe. Email not sent.")

        storage.record_run(
            run_ts=run_ts,
            fetched_count=fetched_count,
            kept_count=len(kept),
            new_count=new_count,
            emailed_count=emailed_count,
            errors=errors,
        )

    logger.info(
        "Run completed | fetched=%s kept=%s new=%s emailed=%s errors=%s",
        fetched_count,
        len(kept),
        new_count,
        emailed_count,
        len(errors),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
