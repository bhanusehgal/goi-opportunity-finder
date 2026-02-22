from datetime import date

from core.date_range import filter_by_published_date, in_date_range, parse_iso_date
from core.schema import Opportunity


def _opp(source_id: str, published: str | None) -> Opportunity:
    return Opportunity(
        source="eprocure",
        source_id=source_id,
        title=f"RFP {source_id}",
        buyer="Test Buyer",
        org_path=None,
        summary="test",
        published_date=published,
        deadline=None,
        location=None,
        estimated_value=None,
        url=f"https://example.com/{source_id}",
        documents=[],
    )


def test_parse_iso_date_valid_and_empty() -> None:
    assert parse_iso_date("2026-01-01") == date(2026, 1, 1)
    assert parse_iso_date("") is None
    assert parse_iso_date(None) is None


def test_in_date_range_with_bounds() -> None:
    assert in_date_range(date(2026, 1, 15), date(2026, 1, 1), date(2026, 2, 1))
    assert not in_date_range(date(2025, 12, 31), date(2026, 1, 1), date(2026, 2, 1))
    assert not in_date_range(None, date(2026, 1, 1), date(2026, 2, 1))


def test_filter_by_published_date() -> None:
    opportunities = [
        _opp("A", "2026-01-10"),
        _opp("B", "2026-02-20"),
        _opp("C", "2026-03-01"),
        _opp("D", None),
    ]
    filtered = filter_by_published_date(
        opportunities,
        start=date(2026, 1, 1),
        end=date(2026, 2, 28),
    )
    assert [item.source_id for item in filtered] == ["A", "B"]
