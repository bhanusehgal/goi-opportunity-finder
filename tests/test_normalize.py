from datetime import datetime, timezone

from core.normalize import normalize_record


def test_normalize_record_happy_path() -> None:
    now = datetime(2026, 2, 21, 12, 0, tzinfo=timezone.utc)
    raw = {
        "tender_id": "GOV-1234",
        "title": "RFP for UAV Mapping Services",
        "department": "Survey of India",
        "description": "Drone survey and analytics",
        "published_date": "2026-02-20",
        "deadline": "15-03-2026",
        "url": "https://example.com/opportunity",
        "documents": "https://example.com/spec.pdf",
        "status": "Open",
    }

    opp = normalize_record(raw, source="eprocure", now=now)
    assert opp is not None
    assert opp.source == "eprocure"
    assert opp.source_id == "GOV-1234"
    assert opp.title == "RFP for UAV Mapping Services"
    assert opp.deadline is not None
    assert opp.status == "new"
    assert opp.unique_id


def test_normalize_record_requires_title_and_url() -> None:
    raw = {"tender_id": "MISSING"}
    opp = normalize_record(raw, source="eprocure")
    assert opp is None


def test_normalize_closed_status_marked_ignore() -> None:
    raw = {
        "id": "X-1",
        "title": "Closed bid for robotics",
        "url": "https://example.com/x1",
        "status": "Closed",
    }
    opp = normalize_record(raw, source="gem")
    assert opp is not None
    assert opp.status == "ignore"
