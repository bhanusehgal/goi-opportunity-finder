from datetime import date

from core.dedupe import dedupe_opportunities
from core.schema import Opportunity


def _opportunity(source_id: str, title: str, buyer: str) -> Opportunity:
    return Opportunity(
        source="eprocure",
        source_id=source_id,
        title=title,
        buyer=buyer,
        org_path=buyer,
        summary=title,
        published_date=date.today(),
        deadline=None,
        location=None,
        estimated_value=None,
        url=f"https://example.com/{source_id}",
        documents=[],
    )


def test_unique_id_dedupe() -> None:
    first = _opportunity("A-1", "RFP for Drone Mapping", "Survey of India")
    second = _opportunity("A-1", "RFP for Drone Mapping", "Survey of India")
    kept, duplicate_map = dedupe_opportunities([first, second], existing_by_id={})
    assert len(kept) == 1
    assert second.unique_id in duplicate_map


def test_fuzzy_dedupe_against_existing() -> None:
    existing = _opportunity(
        "X-100",
        "Tender for Integrated Drone Surveillance and Analytics",
        "Delhi Smart City Limited",
    )
    candidate = _opportunity(
        "Y-200",
        "Tender for Drone Surveillance & Analytics Integration",
        "Delhi Smart City Ltd",
    )
    kept, duplicate_map = dedupe_opportunities(
        [candidate],
        existing_by_id={existing.unique_id: existing},
        threshold=88.0,
    )
    assert len(kept) == 0
    assert candidate.unique_id in duplicate_map
