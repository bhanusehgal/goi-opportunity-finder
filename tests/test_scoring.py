from datetime import date, timedelta

from core.schema import Opportunity
from core.scoring import hard_filter, score_opportunity


def _config(allow_negative: bool = False) -> dict:
    return {
        "keyword_packs": {
            "drones_uav": ["drone", "uav"],
            "robotics": ["robotics", "amr"],
            "it_cyber_ai": ["siem", "soc", "cybersecurity"],
        },
        "procurement_terms": ["rfp", "tender", "eoi", "proposal"],
        "scope_terms": ["scope of work", "technical specification", "sow"],
        "service_terms": ["managed service", "operation and maintenance"],
        "strict_terms": ["turnover", "past performance"],
        "negative_keywords": ["internship", "recruitment"],
        "buyers": [{"name": "Survey of India", "weight": 15}],
        "allow_negative_with_penalty": allow_negative,
    }


def test_score_high_for_relevant_procurement() -> None:
    opp = Opportunity(
        source="eprocure",
        source_id="1",
        title="RFP for Drone Mapping Platform",
        buyer="Survey of India",
        org_path="Ministry of Science and Technology",
        summary="Tender for drone analytics and managed service platform",
        published_date=date.today(),
        deadline=date.today() + timedelta(days=14),
        location=None,
        estimated_value=None,
        url="https://example.com/1",
        documents=["scope_of_work.pdf"],
    )
    keep, _, _ = hard_filter(opp, _config())
    assert keep

    score = score_opportunity(opp, _config(), today=date.today())
    assert score >= 80
    assert "drone" in " ".join(opp.keywords_hit)


def test_negative_filtered_when_disallowed() -> None:
    opp = Opportunity(
        source="gem",
        source_id="2",
        title="Tender for Drone Internship Program",
        buyer="Survey of India",
        org_path=None,
        summary="Recruitment and internship related notice",
        published_date=None,
        deadline=date.today() + timedelta(days=10),
        location=None,
        estimated_value=None,
        url="https://example.com/2",
        documents=[],
    )
    keep, _, negative_hits = hard_filter(opp, _config(allow_negative=False))
    assert not keep
    assert "internship" in negative_hits or "recruitment" in negative_hits


def test_negative_penalized_when_allowed() -> None:
    opp = Opportunity(
        source="gem",
        source_id="3",
        title="RFP for Drone Operations and Internship Support",
        buyer="Survey of India",
        org_path=None,
        summary="Managed service with internship component",
        published_date=None,
        deadline=date.today() + timedelta(days=8),
        location=None,
        estimated_value=None,
        url="https://example.com/3",
        documents=["scope_of_work.pdf"],
    )
    keep, _, _ = hard_filter(opp, _config(allow_negative=True))
    assert keep

    score = score_opportunity(opp, _config(allow_negative=True), today=date.today())
    assert score < 100
