from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from analyze_batch import AnalysisJob, command_for, parse_plan, run_jobs


def test_parse_plan_expands_order_and_deduplicates() -> None:
    jobs = parse_plan([
        {"year": 2026, "gp": [
            {"number": 13, "sessions": ["fp1", "Q", "Q"]},
            {"round": 14, "sessions": ["S", "R"]},
        ]},
    ])
    assert jobs == [
        AnalysisJob(2026, 13, "FP1"),
        AnalysisJob(2026, 13, "Q"),
        AnalysisJob(2026, 14, "S"),
        AnalysisJob(2026, 14, "R"),
    ]


def test_parse_plan_rejects_unknown_session() -> None:
    with pytest.raises(ValueError, match="unsupported session"):
        parse_plan([{"year": 2026, "gp": [{"number": 1, "sessions": ["X"]}]}])


def test_command_routes_sessions_and_only_refreshes_supported_analyzers() -> None:
    assert command_for(
        AnalysisJob(2026, 1, "FP2"), python="python", force=True, refresh_separators=True
    ) == ["python", "analyze_practice.py", "--force", "--refresh-separators"]
    assert command_for(
        AnalysisJob(2026, 1, "R"), python="python", refresh_separators=True
    ) == ["python", "analyze_race.py"]


def test_run_jobs_updates_sequentially_and_restores_only_selection(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "Year": 2025,
        "Round": 1,
        "Session": "FP1",
        "separator": [500],
        "separators": {},
        "custom": {"keep": True},
    }), encoding="utf-8")
    observed = []

    def run(command, cwd, check):
        current = json.loads(config_path.read_text())
        observed.append((current["Year"], current["Round"], current["Session"], command))
        current["separators"].setdefault(str(current["Year"]), {})[current["Session"]] = [123.4]
        config_path.write_text(json.dumps(current), encoding="utf-8")
        return SimpleNamespace(returncode=0)

    jobs = [AnalysisJob(2026, 13, "FP1"), AnalysisJob(2026, 13, "Q")]
    with patch("analyze_batch.subprocess.run", side_effect=run):
        assert run_jobs(
            jobs,
            config_path=config_path,
            repo_root=tmp_path,
            python="python",
        ) == 0

    assert [(year, rnd, session) for year, rnd, session, _ in observed] == [
        (2026, 13, "FP1"),
        (2026, 13, "Q"),
    ]
    restored = json.loads(config_path.read_text())
    assert (restored["Year"], restored["Round"], restored["Session"]) == (2025, 1, "FP1")
    assert restored["custom"] == {"keep": True}
    assert restored["separators"]["2026"] == {"FP1": [123.4], "Q": [123.4]}


def test_failed_job_returns_one_and_fail_fast_stops(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    original = {"Year": 2025, "Round": 1, "Session": "R"}
    config_path.write_text(json.dumps(original), encoding="utf-8")
    with patch(
        "analyze_batch.subprocess.run",
        return_value=SimpleNamespace(returncode=7),
    ) as run:
        result = run_jobs(
            [AnalysisJob(2026, 1, "FP1"), AnalysisJob(2026, 1, "Q")],
            config_path=config_path,
            repo_root=tmp_path,
            fail_fast=True,
        )
    assert result == 1
    assert run.call_count == 1
    assert json.loads(config_path.read_text()) == original
