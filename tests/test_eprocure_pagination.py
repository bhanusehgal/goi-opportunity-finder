from datetime import date

from connectors.eprocure import (
    _build_page_url,
    _filter_records_by_date,
    _parse_eprocure_date,
    _parse_listing_page,
)


def test_build_page_url() -> None:
    base = "https://eprocure.gov.in/cppp/latestactivetendersnew/cpppdata"
    assert _build_page_url(base, 1) == base
    assert _build_page_url(base, 2).endswith("cpppdata?page=2")


def test_parse_eprocure_date_with_time() -> None:
    assert _parse_eprocure_date("21-Feb-2026 09:18 PM") == date(2026, 2, 21)
    assert _parse_eprocure_date("03-Mar-2026 10:30 AM") == date(2026, 3, 3)


def test_parse_listing_page_and_date_filter() -> None:
    html = """
    <html><body>
      <table>
        <tr>
          <th>S.No</th><th>e-Published Date</th><th>Bid Submission Closing Date</th>
          <th>Bid Opening Date</th><th>Title/Ref.No./Tender Id</th><th>Organisation Chain</th><th>Location</th>
        </tr>
        <tr>
          <td>1.</td>
          <td>21-Feb-2026 09:18 PM</td>
          <td>03-Mar-2026 10:30 AM</td>
          <td>03-Mar-2026 11:00 AM</td>
          <td><a href="https://eprocure.gov.in/cppp/tendersfullview/ABC123">RFP for Drone Survey</a>/ABC123</td>
          <td>Survey of India</td>
          <td>New Delhi</td>
        </tr>
        <tr>
          <td>2.</td>
          <td>31-Dec-2025 05:00 PM</td>
          <td>10-Jan-2026 10:00 AM</td>
          <td>10-Jan-2026 10:30 AM</td>
          <td><a href="https://eprocure.gov.in/cppp/tendersfullview/XYZ999">Tender for Robotics</a>/XYZ999</td>
          <td>CPWD</td>
          <td>Lucknow</td>
        </tr>
      </table>
      <div class='pagination'>
        <a href="https://eprocure.gov.in/cppp/latestactivetendersnew/cpppdata?page=2">2</a>
        <a href="https://eprocure.gov.in/cppp/latestactivetendersnew/cpppdata?page=3314">3314</a>
      </div>
    </body></html>
    """
    records, oldest, newest, max_page = _parse_listing_page(
        html,
        base_url="https://eprocure.gov.in/cppp/latestactivetendersnew/cpppdata",
    )
    assert len(records) == 2
    assert oldest is not None and oldest.isoformat() == "2025-12-31"
    assert newest is not None and newest.isoformat() == "2026-02-21"
    assert max_page == 3314

    filtered = _filter_records_by_date(
        records,
        published_from=date(2026, 1, 1),
        published_to=date(2026, 2, 28),
    )
    assert len(filtered) == 1
    assert filtered[0]["title"] == "RFP for Drone Survey"
