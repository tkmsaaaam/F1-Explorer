"""Session failures must reach the CLI and the batch runner without live data."""

import datetime
import importlib
from pathlib import Path
import runpy
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from f1_explorer.config import Config


SESSIONS = [
    ("practice", "FP1", "Practice 1"),
    ("practice", "FP2", "Practice 2"),
    ("practice", "FP3", "Practice 3"),
    ("qualifying", "Q", "Qualifying"),
    ("qualifying", "SQ", "Sprint Qualifying"),
    ("race", "R", "Race"),
    ("race", "S", "Sprint"),
]


@pytest.fixture(params=SESSIONS, ids=[code for _, code, _ in SESSIONS])
def analysis(request, monkeypatch, tmp_path):
    category, code, name = request.param
    module = importlib.import_module(f"analyze_{category}")
    config = Config(2026, 1, code, {}, [], [])
    past = datetime.datetime(2000, 1, 1, tzinfo=datetime.timezone.utc)
    event = MagicMock(year=2026, RoundNumber=1, EventName="Test GP", Location="Test")
    event.__getitem__.side_effect = lambda key: getattr(event, key)
    for index in range(1, 6):
        setattr(event, f"Session{index}Date", past)
    session = MagicMock(name="session")
    session.name = name
    session.event = event
    session.laps.pick_fastest.return_value = None
    monkeypatch.setattr(module.config_module, "load_config", MagicMock(return_value=config))
    monkeypatch.setattr(module.config_module, "fast_f1", MagicMock())
    log = MagicMock()
    monkeypatch.setattr(module.config_module, "log", lambda: log)
    monkeypatch.setattr(module.fastf1, "get_session", MagicMock(return_value=session))
    monkeypatch.setattr(module, "session_output_dir", lambda session: tmp_path / "images")
    monkeypatch.setattr(module, "session_report_dir", lambda session: tmp_path / "report")
    monkeypatch.setattr(module, "build_fingerprint", MagicMock())
    monkeypatch.setattr(module, "should_skip", MagicMock(return_value=False))
    manifest = MagicMock()
    monkeypatch.setattr(module, "write_success_manifest", manifest)
    report = MagicMock()
    monkeypatch.setattr(module, "SessionReport", MagicMock(return_value=report))
    for function in ("plot_lap_number_by_timing", "plot_laptime", "plot_laptime_by_timing",
                     "plot_laptime_by_lap_number", "plot_pit_time"):
        monkeypatch.setattr(module.run_volume, function, MagicMock())
    monkeypatch.setattr(module.weekend, "plot_tyre", MagicMock())
    monkeypatch.setattr(module.weather, "execute", MagicMock())
    if category == "race":
        monkeypatch.setattr(module.race, "execute", MagicMock())
    else:
        monkeypatch.setattr(module, "resolve_separators", MagicMock(return_value=SimpleNamespace(
            separators=[], boundaries=[], pending_save=False, source="saved")))
        monkeypatch.setattr(module, "persist_resolution", MagicMock())
        monkeypatch.setattr(module, "_circuit_info_or_none", MagicMock(return_value=None))
        monkeypatch.setattr(module, "save_plotly", MagicMock())
        for function in ("plot_flat_out", "plot_ideal_best", "plot_ideal_best_diff",
                         "plot_speed_and_laptime", "plot_tyre_age_and_laptime"):
            monkeypatch.setattr(module.short_runs, function, MagicMock())
        if category == "practice":
            monkeypatch.setattr(module.long_runs, "plot_by_tyre_age_and_tyre", MagicMock())
            functions = ("make_practice_best", "make_practice_speed", "make_telemetry_comparison",
                         "make_track_map_comparison")
        else:
            functions = ("make_qualifying_best", "make_qualifying_speed",
                         "make_qualifying_telemetry", "make_qualifying_track_map")
        for function in functions:
            monkeypatch.setattr(module, function, MagicMock())
    return SimpleNamespace(module=module, config=config, session=session, report=report,
                           manifest=manifest, log=log)


def test_setup_failure_returns_nonzero_without_success_record(analysis):
    analysis.module.config_module.load_config.side_effect = ValueError("invalid config")
    assert analysis.module.main() == 1
    analysis.module.fastf1.get_session.assert_not_called()
    analysis.manifest.assert_not_called()
    analysis.log.warning.assert_called_once()


def test_wrong_category_returns_nonzero(analysis):
    analysis.config.session_category = None
    assert analysis.module.main() == 1
    analysis.module.fastf1.get_session.assert_not_called()
    analysis.manifest.assert_not_called()


def test_session_lookup_failure_returns_nonzero(analysis):
    analysis.module.fastf1.get_session.side_effect = ValueError("session unavailable")
    assert analysis.module.main() == 1
    analysis.manifest.assert_not_called()


def test_unknown_session_name_is_failure(analysis):
    analysis.session.name = "Unknown"
    assert analysis.module.main() == 1
    analysis.session.load.assert_not_called()
    analysis.manifest.assert_not_called()


def test_future_session_skips_before_loading_even_with_force(analysis):
    future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
    for index in range(1, 6):
        setattr(analysis.session.event, f"Session{index}Date", future)
    assert analysis.module.main(force=True) == 0
    analysis.session.load.assert_not_called()
    analysis.module.should_skip.assert_not_called()
    analysis.module.SessionReport.assert_not_called()
    analysis.manifest.assert_not_called()


def test_unchanged_session_is_normal_skip(analysis):
    analysis.module.should_skip.return_value = True
    assert analysis.module.main() == 0
    analysis.module.SessionReport.assert_not_called()
    analysis.manifest.assert_not_called()


@pytest.mark.parametrize("stage", ["load", "analysis", "report", "manifest"])
def test_unhandled_failure_propagates_without_new_success_record(analysis, stage):
    failing_call = {
        "load": analysis.session.load,
        "analysis": analysis.module.run_volume.plot_laptime,
        "report": analysis.report.write,
        "manifest": analysis.manifest,
    }[stage]
    failing_call.side_effect = RuntimeError(f"{stage} failed")
    with pytest.raises(RuntimeError, match=f"{stage} failed"):
        analysis.module.main()
    if stage != "manifest":
        analysis.manifest.assert_not_called()


def test_success_returns_zero_after_report_and_manifest(analysis):
    assert analysis.module.main() == 0
    analysis.report.write.assert_called_once_with(scan_existing=False)
    analysis.manifest.assert_called_once()


@pytest.mark.parametrize("future", [False, True], ids=["setup-error", "future-skip"])
def test_cli_exits_with_main_status(analysis, monkeypatch, future):
    # Execute the actual __main__ block with shared dependencies mocked.
    if future:
        for index in range(1, 6):
            setattr(analysis.session.event, f"Session{index}Date",
                    datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1))
    else:
        analysis.module.config_module.load_config.side_effect = ValueError("invalid config")
    monkeypatch.setattr("sys.argv", [analysis.module.__file__])
    with pytest.raises(SystemExit) as error:
        runpy.run_path(analysis.module.__file__, run_name="__main__")
    assert error.value.code == (0 if future else 1)
    analysis.session.load.assert_not_called()


@pytest.mark.parametrize("category", ["practice", "qualifying", "race"])
def test_process_with_missing_config_exits_one(category, tmp_path):
    script = Path(__file__).resolve().parents[1] / f"analyze_{category}.py"
    result = subprocess.run(
        [sys.executable, str(script)], cwd=tmp_path, capture_output=True, text=True,
        check=False, timeout=60,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "setup is failed" in result.stdout + result.stderr
    assert list(tmp_path.iterdir()) == []
