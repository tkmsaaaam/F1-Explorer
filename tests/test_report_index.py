"""Offline report navigation and template integration."""

import json
import re
from types import SimpleNamespace
from unittest.mock import patch

from visualizations.report import SessionReport
from visualizations.report_index import build_index


def _entries(html: str) -> list[dict[str, str]]:
    payload = re.search(r'<script type="application/json" id="reports">(.*?)</script>', html)
    assert payload is not None
    return json.loads(payload.group(1))


def test_index_lists_only_existing_reports_in_round_order(tmp_path):
    for relative in (
        "2026/12_Zandvoort/Race/report.html",
        "2026/2_Suzuka/Qualifying/report.html",
        "2025/1_Melbourne/Practice1/report.html",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True)
        path.write_text("report")
    (tmp_path / "2026/3_Missing/Race").mkdir(parents=True)

    html = build_index(tmp_path).read_text()
    assert [(entry["year"], entry["gp"], entry["session"]) for entry in _entries(html)] == [
        ("2026", "2_Suzuka", "Qualifying"),
        ("2026", "12_Zandvoort", "Race"),
        ("2025", "1_Melbourne", "Practice1"),
    ]


def test_session_write_updates_index_and_uses_template(tmp_path):
    report_root = tmp_path / "reports"
    report_dir = report_root / "2026" / "7_Test GP" / "Qualifying"
    session = SimpleNamespace(
        name="Qualifying",
        event=SimpleNamespace(year=2026, RoundNumber=7, Location="Test GP", EventName="Test GP"),
    )
    with patch("visualizations.report._plotly_js", return_value=""):
        html = SessionReport(session, tmp_path / "images", report_dir=report_dir).write().read_text()

    assert "@@EVENT_NAME@@" not in html
    assert "F1 Explorer — Test GP / Qualifying" in html
    entries = _entries((report_root / "index.html").read_text())
    assert entries == [{
        "year": "2026", "gp": "7_Test GP", "session": "Qualifying",
        "url": "2026/7_Test%20GP/Qualifying/report.html",
    }]
