"""Connector for CPPP/eProcure."""

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

SOURCE = "eprocure"
URLS = [
    "https://eprocure.gov.in/cppp/latestactivetendersnew/cpppdata",
    "https://eprocure.gov.in/eprocure/app",
]
DEFAULT_USER_AGENT = "GoIOpportunityFinder/1.0 (+ops@example.com)"
MAX_CACHE_AGE_HOURS = 6


def fetch_opportunities(
    cache_dir: Path,
    logger: logging.Logger,
    timeout: int = 25,
    max_items: int = 80,
) -> list[dict[str, Any]]:
    """Fetch latest eProcure opportunities."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    for url in URLS:
        html = _fetch_html_with_cache(
            url=url,
            cache_dir=cache_dir,
            logger=logger,
            timeout=timeout,
        )
        if not html:
            continue
        parsed = _parse_listing(html, base_url=url, max_items=max_items)
        if parsed:
            logger.info("eProcure parsed %s records from %s", len(parsed), url)
            return parsed

    logger.warning("eProcure parsing failed, using fallback sample records.")
    return _sample_records()


def _cache_paths(cache_dir: Path, url: str) -> tuple[Path, Path]:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
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


def _load_stale_cache(html_path: Path) -> str | None:
    if html_path.exists():
        return html_path.read_text(encoding="utf-8", errors="ignore")
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
    html_path, meta_path = _cache_paths(cache_dir, url)
    cached = _load_fresh_cache(html_path, meta_path)
    if cached:
        logger.info("eProcure cache hit: %s", url)
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
                "eProcure request non-200/empty (attempt=%s, status=%s)",
                attempt,
                response.status_code,
            )
        except requests.RequestException as exc:
            logger.warning("eProcure request failed (attempt=%s): %s", attempt, exc)

    stale = _load_stale_cache(html_path)
    if stale:
        logger.info("eProcure using stale cache for %s", url)
    return stale


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


def _extract_source_id(text: str, href: str) -> str | None:
    patterns = [
        r"(?:Tender|Bid|RFP|EOI)\s*(?:ID|No\.?|Number)?[:\s-]+([A-Za-z0-9/_-]{5,})",
        r"\b([A-Z]{2,}\d{3,}[A-Z0-9/-]*)\b",
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
    # TODO: tighten selectors against stable CPPP markup if/when official structure is confirmed.
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table tr")
    records: list[dict[str, Any]] = []

    for row in rows:
        text = " ".join(row.stripped_strings)
        if len(text) < 16:
            continue
        if not re.search(r"\b(tender|rfp|eoi|bid|proposal)\b", text, flags=re.IGNORECASE):
            continue

        link_tag = row.find("a", href=True)
        if link_tag:
            href = urljoin(base_url, link_tag["href"])
            title = link_tag.get_text(" ", strip=True) or text
        else:
            href = base_url
            title = text

        source_id = _extract_source_id(text, href)
        if not source_id:
            source_id = hashlib.sha256(f"{title}|{href}".encode("utf-8")).hexdigest()[:16]

        dates = _extract_dates(text)
        published_date = dates[0] if dates else None
        deadline = dates[-1] if len(dates) > 1 else None
        buyer = None
        cols = [cell.get_text(" ", strip=True) for cell in row.find_all("td")]
        if len(cols) >= 2:
            buyer = cols[1]

        docs = [
            urljoin(base_url, a["href"])
            for a in row.find_all("a", href=True)
            if any(ext in a["href"].lower() for ext in [".pdf", ".doc", ".docx", ".zip"])
        ]

        records.append(
            {
                "source_id": source_id,
                "title": title,
                "buyer": buyer,
                "org_path": buyer,
                "summary": text,
                "published_date": published_date,
                "deadline": deadline,
                "url": href,
                "documents": docs,
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
            "source_id": "EPR-SAMPLE-001",
            "title": "RFP for Drone Based Aerial Survey and GIS Mapping Services",
            "buyer": "Survey of India",
            "org_path": "Ministry of Science and Technology",
            "summary": "Expression of Interest for UAV mapping and analytics platform.",
            "published_date": now.isoformat(),
            "deadline": (now + timedelta(days=18)).isoformat(),
            "url": "https://eprocure.gov.in/sample/drone-survey-rfp",
            "documents": ["https://eprocure.gov.in/sample/drone-survey-rfp/spec.pdf"],
            "source_status": "open",
        },
        {
            "source_id": "EPR-SAMPLE-002",
            "title": "Tender for Integrated SIEM and SOC Modernization",
            "buyer": "National Informatics Centre",
            "org_path": "Ministry of Electronics and IT",
            "summary": "Bid for SOC operations, SIEM deployment, and cyber monitoring.",
            "published_date": now.isoformat(),
            "deadline": (now + timedelta(days=12)).isoformat(),
            "url": "https://eprocure.gov.in/sample/siem-soc-tender",
            "documents": ["https://eprocure.gov.in/sample/siem-soc-tender/terms.pdf"],
            "source_status": "open",
        },
    ]
