"""Connector for iDEX open challenges."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import requests

SOURCE = "idex"
URL = "https://idex.gov.in/challenges"
DEFAULT_USER_AGENT = "GoIOpportunityFinder/1.0 (+ops@example.com)"
MAX_CACHE_AGE_HOURS = 8


def fetch_opportunities(
    cache_dir: Path,
    logger: logging.Logger,
    timeout: int = 25,
    max_items: int = 50,
) -> list[dict[str, Any]]:
    """Fetch current iDEX challenges."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    html = _fetch_html_with_cache(URL, cache_dir=cache_dir, logger=logger, timeout=timeout)
    if html:
        parsed = _parse_listing(html, base_url=URL, max_items=max_items)
        if parsed:
            logger.info("iDEX parsed %s records", len(parsed))
            return parsed

    logger.warning("iDEX parsing failed, using fallback sample records.")
    return _sample_records()


def _cache_paths(cache_dir: Path) -> tuple[Path, Path]:
    digest = hashlib.sha256(URL.encode("utf-8")).hexdigest()[:16]
    return (
        cache_dir / f"{SOURCE}_{digest}.html",
        cache_dir / f"{SOURCE}_{digest}.meta.json",
    )


def _load_fresh_cache(html_path: Path, meta_path: Path) -> str | None:
    if not html_path.exists() or not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        fetched_at = datetime.fromisoformat(meta["fetched_at"])
        if datetime.now(timezone.utc) - fetched_at <= timedelta(hours=MAX_CACHE_AGE_HOURS):
            return html_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    return None


def _save_cache(html_path: Path, meta_path: Path, html: str) -> None:
    html_path.write_text(html, encoding="utf-8")
    meta_path.write_text(
        json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat()}, ensure_ascii=True),
        encoding="utf-8",
    )


def _fetch_html_with_cache(
    url: str,
    cache_dir: Path,
    logger: logging.Logger,
    timeout: int,
) -> str | None:
    html_path, meta_path = _cache_paths(cache_dir)
    cached = _load_fresh_cache(html_path, meta_path)
    if cached:
        logger.info("iDEX cache hit")
        return cached

    headers = {"User-Agent": os.getenv("GOI_FINDER_USER_AGENT", DEFAULT_USER_AGENT)}
    delay = float(os.getenv("REQUEST_DELAY_SECONDS", "1.5"))
    for attempt in range(1, 4):
        try:
            time.sleep(delay)
            response = requests.get(url, headers=headers, timeout=timeout)
            if response.status_code == 200 and response.text.strip():
                _save_cache(html_path, meta_path, response.text)
                return response.text
            logger.warning(
                "iDEX request non-200/empty (attempt=%s status=%s)",
                attempt,
                response.status_code,
            )
        except requests.RequestException as exc:
            logger.warning("iDEX request failed (attempt=%s): %s", attempt, exc)

    if html_path.exists():
        logger.info("iDEX using stale cache")
        return html_path.read_text(encoding="utf-8", errors="ignore")
    return None


def _extract_dates(text: str) -> list[str]:
    patterns = [
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b\d{2}-\d{2}-\d{4}\b",
        r"\b\d{2}/\d{2}/\d{4}\b",
        r"\b\d{1,2}\s(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s\d{4}\b",
    ]
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(re.findall(pattern, text, flags=re.IGNORECASE))
    return matches


def _extract_challenge_id(text: str, href: str) -> str | None:
    patterns = [
        r"\b(?:iDEX|IDEX|Challenge)\s*(?:ID|No\.?|Number)?[:\s-]+([A-Za-z0-9/_-]{4,})",
        r"\b([A-Z]{2,}-\d{3,}[A-Z0-9/-]*)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    href_match = re.search(r"([A-Za-z0-9_-]{8,})", href)
    if href_match:
        return href_match.group(1)
    return None


def _parse_listing(html: str, base_url: str, max_items: int) -> list[dict[str, Any]]:
    # TODO: replace heuristic parsing with stable challenge-card selectors for future site revisions.
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("a[href]")
    records: list[dict[str, Any]] = []

    for card in cards:
        href = card.get("href", "").strip()
        if not href:
            continue
        text = card.get_text(" ", strip=True)
        if len(text) < 10:
            continue
        if not re.search(r"\b(challenge|innovation|idex|defence)\b", text, flags=re.IGNORECASE):
            continue
        if "javascript:" in href.lower():
            continue

        full_link = urljoin(base_url, href)
        parent_text = card.parent.get_text(" ", strip=True) if card.parent else text
        combined = f"{text} {parent_text}"
        source_id = _extract_challenge_id(combined, full_link)
        if not source_id:
            source_id = hashlib.sha256(f"{text}|{full_link}".encode("utf-8")).hexdigest()[:16]

        dates = _extract_dates(combined)
        published_date = dates[0] if dates else None
        deadline = dates[-1] if len(dates) > 1 else None

        records.append(
            {
                "source_id": source_id,
                "title": text,
                "buyer": "iDEX / Defence Innovation Organisation",
                "org_path": "Ministry of Defence",
                "summary": combined,
                "published_date": published_date,
                "deadline": deadline,
                "url": full_link,
                "documents": [],
                "source_status": "open",
            }
        )
        if len(records) >= max_items:
            break

    return records


def _sample_records() -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).date()
    return [
        {
            "source_id": "IDEX-SAMPLE-001",
            "title": "iDEX Open Challenge: Swarm UAV for Tactical Reconnaissance",
            "buyer": "iDEX / Defence Innovation Organisation",
            "org_path": "Ministry of Defence",
            "summary": "Challenge seeks autonomous UAV swarm, onboard AI, and secure control link.",
            "published_date": now.isoformat(),
            "deadline": (now + timedelta(days=24)).isoformat(),
            "url": "https://idex.gov.in/sample/swarm-uav-challenge",
            "documents": ["https://idex.gov.in/sample/swarm-uav-challenge/brief.pdf"],
            "source_status": "open",
        },
        {
            "source_id": "IDEX-SAMPLE-002",
            "title": "iDEX Challenge: Autonomous Ground Robotics for Logistics",
            "buyer": "iDEX / Defence Innovation Organisation",
            "org_path": "Ministry of Defence",
            "summary": "Defence innovation challenge for autonomous mobile robotics and mission planning.",
            "published_date": now.isoformat(),
            "deadline": (now + timedelta(days=28)).isoformat(),
            "url": "https://idex.gov.in/sample/autonomous-robotics-logistics",
            "documents": ["https://idex.gov.in/sample/autonomous-robotics-logistics/spec.pdf"],
            "source_status": "open",
        },
    ]
