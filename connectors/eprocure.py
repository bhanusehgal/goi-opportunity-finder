"""Connector for CPPP/eProcure."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

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
    published_from: date | None = None,
    published_to: date | None = None,
    max_pages: int | None = None,
) -> list[dict[str, Any]]:
    """Fetch latest eProcure opportunities."""
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Backfill mode: crawl paginated results until e-Published dates cross the range boundary.
    if published_from or published_to:
        paginated = _fetch_paginated_records(
            base_url=URLS[0],
            cache_dir=cache_dir,
            logger=logger,
            timeout=timeout,
            max_items=max_items,
            published_from=published_from,
            published_to=published_to,
            max_pages=max_pages,
        )
        if paginated:
            logger.info(
                "eProcure paginated fetch parsed %s records (range mode)",
                len(paginated),
            )
            return paginated

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
        parsed = _filter_records_by_date(parsed, published_from=published_from, published_to=published_to)
        if parsed:
            logger.info("eProcure parsed %s records from %s", len(parsed), url)
            return parsed

    logger.warning("eProcure parsing failed, using fallback sample records.")
    return _sample_records()


def _build_page_url(base_url: str, page_number: int) -> str:
    if page_number <= 1:
        return base_url
    parsed = urlparse(base_url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["page"] = [str(page_number)]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def _parse_eprocure_date(value: str | None) -> date | None:
    text = _normalize_text(value)
    if not text:
        return None

    # e-Published and deadline cells usually include time; strip it for date-only filtering.
    date_token = text.split(" ")[0]
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_token, fmt).date()
        except ValueError:
            continue
    return None


def _extract_max_page_hint(soup: BeautifulSoup) -> int | None:
    max_page: int | None = None
    for anchor in soup.select("a[href*='page=']"):
        href = anchor.get("href", "")
        match = re.search(r"[?&]page=(\d+)", href)
        if not match:
            continue
        number = int(match.group(1))
        max_page = number if max_page is None else max(max_page, number)
    return max_page


def _filter_records_by_date(
    records: list[dict[str, Any]],
    published_from: date | None,
    published_to: date | None,
) -> list[dict[str, Any]]:
    if not published_from and not published_to:
        return records
    kept: list[dict[str, Any]] = []
    for record in records:
        record_date = _parse_eprocure_date(record.get("published_date"))
        if record_date is None:
            continue
        if published_from and record_date < published_from:
            continue
        if published_to and record_date > published_to:
            continue
        kept.append(record)
    return kept


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
        r"\b\d{2}-(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*-\d{4}\b",
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
    records, _, _, _ = _parse_listing_page(html, base_url=base_url)
    return records[:max_items]


def _parse_listing_page(
    html: str, base_url: str
) -> tuple[list[dict[str, Any]], date | None, date | None, int | None]:
    """Parse one eProcure listing page and return records plus page metadata."""
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("#tenderscpppdata_short-div table tr")
    if not rows:
        rows = soup.select("table tr")

    records: list[dict[str, Any]] = []
    published_dates: list[date] = []

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 6:
            continue

        published_raw = _normalize_text(cells[1].get_text(" ", strip=True))
        deadline_raw = _normalize_text(cells[2].get_text(" ", strip=True))
        title_cell = cells[4]
        link_tag = title_cell.find("a", href=True)
        if not link_tag:
            continue

        href = urljoin(base_url, link_tag.get("href", ""))
        title = _normalize_text(link_tag.get_text(" ", strip=True))
        if not title or not href:
            continue

        title_ref_text = _normalize_text(title_cell.get_text(" ", strip=True))
        row_text = _normalize_text(" ".join(cell.get_text(" ", strip=True) for cell in cells))
        source_id = _extract_source_id(title_ref_text, href)
        if not source_id:
            source_id = hashlib.sha256(f"{title}|{href}".encode("utf-8")).hexdigest()[:16]

        buyer = _normalize_text(cells[5].get_text(" ", strip=True)) or None
        location = (
            _normalize_text(cells[6].get_text(" ", strip=True)) if len(cells) > 6 else None
        )

        parsed_pub = _parse_eprocure_date(published_raw)
        if parsed_pub:
            published_dates.append(parsed_pub)

        records.append(
            {
                "source_id": source_id,
                "title": title,
                "buyer": buyer,
                "org_path": buyer,
                "summary": row_text,
                "published_date": published_raw,
                "deadline": deadline_raw,
                "location": location,
                "url": href,
                "documents": [],
                "source_status": "open",
            }
        )

    oldest = min(published_dates) if published_dates else None
    newest = max(published_dates) if published_dates else None
    max_page_hint = _extract_max_page_hint(soup)
    return records, oldest, newest, max_page_hint


def _fetch_paginated_records(
    base_url: str,
    cache_dir: Path,
    logger: logging.Logger,
    timeout: int,
    max_items: int,
    published_from: date | None,
    published_to: date | None,
    max_pages: int | None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    page_number = 1
    discovered_max_page: int | None = None

    while True:
        page_url = _build_page_url(base_url, page_number)
        html = _fetch_html_with_cache(
            url=page_url,
            cache_dir=cache_dir,
            logger=logger,
            timeout=timeout,
        )
        if not html:
            logger.warning("eProcure pagination stopped: failed to load page=%s", page_number)
            break

        page_records, oldest_page_date, _, page_hint = _parse_listing_page(
            html=html,
            base_url=page_url,
        )
        if page_hint:
            discovered_max_page = (
                page_hint if discovered_max_page is None else max(discovered_max_page, page_hint)
            )

        if not page_records:
            logger.info("eProcure pagination stopped: no rows on page=%s", page_number)
            break

        kept_records = _filter_records_by_date(
            page_records,
            published_from=published_from,
            published_to=published_to,
        )
        records.extend(kept_records)
        logger.info(
            "eProcure page=%s parsed=%s kept=%s total_kept=%s",
            page_number,
            len(page_records),
            len(kept_records),
            len(records),
        )

        if published_from and oldest_page_date and oldest_page_date < published_from:
            logger.info(
                "eProcure pagination stop at page=%s: oldest e-Published date %s is older than start %s",
                page_number,
                oldest_page_date.isoformat(),
                published_from.isoformat(),
            )
            break

        if max_pages and page_number >= max_pages:
            logger.info("eProcure pagination stop at configured max_pages=%s", max_pages)
            break

        if discovered_max_page and page_number >= discovered_max_page:
            break

        # In non-range mode, respect max_items cap.
        if not (published_from or published_to) and len(records) >= max_items:
            return records[:max_items]

        page_number += 1

    if not (published_from or published_to):
        return records[:max_items]
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
            "url": "https://eprocure.gov.in/eprocure/app",
            "documents": [],
            "source_status": "inactive_mock",
        },
        {
            "source_id": "EPR-SAMPLE-002",
            "title": "Tender for Integrated SIEM and SOC Modernization",
            "buyer": "National Informatics Centre",
            "org_path": "Ministry of Electronics and IT",
            "summary": "Bid for SOC operations, SIEM deployment, and cyber monitoring.",
            "published_date": now.isoformat(),
            "deadline": (now + timedelta(days=12)).isoformat(),
            "url": "https://eprocure.gov.in/eprocure/app",
            "documents": [],
            "source_status": "inactive_mock",
        },
    ]
