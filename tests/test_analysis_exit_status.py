"""Session failures must reach the CLI and the batch runner without live data."""

import datetime
import importlib
from pathlib import Path
import runpy
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from f1_explorer import session_pipeline
from f1_explorer.config import Config
from f1_explorer.visualizations.report import current_report
from f1_explorer.visualizations import report as report_module
from f1_explorer.visualizations import run_volume
from f1_explorer.analysis_state import manifest_path


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
    monkeypatch.setattr(session_pipeline, "session_output_dir", lambda session: tmp_path / "images")
    monkeypatch.setattr(session_pipeline, "session_report_dir", lambda session: tmp_path / "report")
    monkeypatch.setattr(session_pipeline, "build_fingerprint", MagicMock())
    monkeypatch.setattr(session_pipeline, "session_input_fingerprint", MagicMock(return_value={"algorithm": "test", "hash": "x"}))
    monkeypatch.setattr(session_pipeline, "session_is_finished", MagicMock(return_value=True))
    monkeypatch.setattr(session_pipeline, "should_skip", MagicMock(return_value=False))
    manifest = MagicMock()
    monkeypatch.setattr(session_pipeline, "write_success_manifest", manifest)
    report_dir = tmp_path / "report"
    manifest_path(report_dir).parent.mkdir(parents=True, exist_ok=True)
    manifest_path(report_dir).write_text('{"previous":"success"}', encoding="utf-8")
    report = report_module.SessionReport(session, tmp_path / "images", report_dir=report_dir)
    for method in ("write", "register_plotly", "written_output_paths", "required_png_paths"):
        monkeypatch.setattr(report, method, MagicMock())
    monkeypatch.setattr(session_pipeline, "SessionReport", MagicMock(return_value=report))
    for function in ("plot_lap_number_by_timing", "plot_laptime", "plot_laptime_by_timing",
                     "plot_laptime_by_lap_number", "plot_pit_time"):
        monkeypatch.setattr(module.run_volume, function, MagicMock())
    monkeypatch.setattr(module.weekend, "plot_tyre", MagicMock())
    monkeypatch.setattr(module.weather, "execute", MagicMock())
    if category == "race":
        monkeypatch.setattr(module.race, "execute", MagicMock())
    else:
        monkeypatch.setattr(session_pipeline, "resolve_separators", MagicMock(return_value=SimpleNamespace(
            separators=[], boundaries=[], pending_save=False, source="saved")))
        monkeypatch.setattr(session_pipeline, "persist_resolution", MagicMock())
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
    return SimpleNamespace(module=module, category=category, config=config, session=session,
                           report=report, manifest=manifest, log=log, report_dir=report_dir)


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
    session_pipeline.should_skip.assert_not_called()
    session_pipeline.SessionReport.assert_not_called()
    analysis.manifest.assert_not_called()


def test_unchanged_session_is_normal_skip(analysis):
    session_pipeline.should_skip.return_value = True
    assert analysis.module.main() == 0
    session_pipeline.SessionReport.assert_not_called()
    analysis.manifest.assert_not_called()
    analysis.session.load.assert_called_once()


def test_loaded_input_change_regenerates_then_identical_input_skips(analysis):
    first = {"algorithm": "test", "hash": "first"}
    changed = {"algorithm": "test", "hash": "changed"}
    session_pipeline.session_input_fingerprint.side_effect = [first, changed, changed]
    previous = None

    def compare_loaded_input(*args, **kwargs):
        nonlocal previous
        current = kwargs["session_input"]
        should_reuse = previous == current
        previous = current
        return should_reuse

    session_pipeline.should_skip.side_effect = compare_loaded_input
    assert analysis.module.main() == 0
    assert analysis.module.main() == 0
    assert analysis.module.main() == 0
    assert analysis.report.write.call_count == 2
    assert analysis.session.load.call_count == 3
    assert analysis.manifest.call_count == 2


@pytest.mark.parametrize("unusable", ["unfinished", "hash-failure"])
def test_unfinished_or_unhashable_input_writes_report_without_success_manifest(analysis, unusable):
    if unusable == "unfinished":
        session_pipeline.session_is_finished.return_value = False
    else:
        session_pipeline.session_input_fingerprint.return_value = None
    assert analysis.module.main() == 0
    assert analysis.report.write.call_count == 1
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
    if stage == "load":
        assert not manifest_path(analysis.report_dir).exists()
    if stage != "manifest":
        analysis.manifest.assert_not_called()
    assert current_report() is None


@pytest.mark.parametrize("analysis", [
    ("practice", "FP1", "Practice 1"),
    ("qualifying", "Q", "Qualifying"),
], indirect=True, ids=["FP", "Q"])
@pytest.mark.parametrize("telemetry", [
    None,
    pd.DataFrame(),
    pd.DataFrame({"Time": [0, 1]}),
    pd.DataFrame({"Distance": [float("nan"), float("inf")]}),
    pd.DataFrame({"Distance": [0, 0]}),
])
def test_missing_fastest_distance_skips_circuit_charts_and_writes_report(analysis, telemetry, monkeypatch):
    module = analysis.module
    mini_segment = MagicMock()
    segment_tables = MagicMock()
    monkeypatch.setattr(module.segment_analysis, "plot_mini_segment_on_circuit", mini_segment)
    monkeypatch.setattr(module.segment_analysis, "compute_and_save_segment_tables_plotly", segment_tables)
    fastest = MagicMock()
    analysis.session.laps.pick_fastest.return_value = fastest
    module._circuit_info_or_none.return_value = SimpleNamespace(
        corners=pd.DataFrame({"Distance": [100.0]}),
    )
    module.lap_telemetry_without_driver_ahead.return_value = telemetry

    assert module.main() == 0

    mini_segment.assert_not_called()
    segment_tables.assert_not_called()
    analysis.report.write.assert_called_once()
    analysis.log.warning.assert_any_call("Skipping circuit-dependent analysis without valid fastest-lap distances")


def test_success_returns_zero_after_report_and_manifest(analysis):
    assert analysis.module.main() == 0
    analysis.report.write.assert_called_once_with(scan_existing=False)
    analysis.manifest.assert_called_once()


@pytest.mark.parametrize("stage", ["analysis", "registration", "report"])
def test_report_context_is_restored_after_analysis_failures(analysis, monkeypatch, stage):
    category = analysis.module.__name__.removeprefix("analyze_")
    initial = MagicMock(name="previous report")
    token = report_module._CURRENT_REPORT.set(initial)
    try:
        if stage == "analysis":
            analysis.module.run_volume.plot_laptime.side_effect = RuntimeError("injected analysis failure")
        elif stage == "registration":
            analysis.report.register_plotly.side_effect = RuntimeError("injected registration failure")
            if category == "race":
                monkeypatch.setattr(analysis.module.race, "execute", lambda *args: analysis.report.register_plotly(None, "x"))
            else:
                monkeypatch.setattr(analysis.module, "save_plotly", lambda *args, **kwargs: analysis.report.register_plotly(None, "x"))
        else:
            analysis.report.write.side_effect = RuntimeError("injected report failure")
        before = set(plt.get_fignums())
        with pytest.raises(RuntimeError):
            analysis.module.main(force=True)
        assert current_report() is initial
        assert set(plt.get_fignums()) == before
        assert not manifest_path(analysis.report_dir).exists()
        analysis.manifest.assert_not_called()
    finally:
        report_module._CURRENT_REPORT.reset(token)


@pytest.mark.parametrize("stage", ["analysis", "report", "manifest"])
def test_forced_regeneration_invalidates_old_manifest(analysis, stage):
    manifest = manifest_path(analysis.report_dir)
    assert manifest.is_file()
    if stage == "analysis":
        analysis.module.run_volume.plot_laptime.side_effect = RuntimeError("forced analysis failure")
    elif stage == "report":
        analysis.report.write.side_effect = RuntimeError("forced HTML failure")
    else:
        analysis.manifest.side_effect = RuntimeError("manifest write failure")
    with pytest.raises(RuntimeError):
        analysis.module.main(force=True)
    assert not manifest.exists()
    assert analysis.manifest.call_count == (1 if stage == "manifest" else 0)


@pytest.mark.parametrize("stage", ["analysis", "report", "manifest"])
def test_normal_run_retries_after_failed_forced_regeneration(analysis, stage):
    if stage == "analysis":
        analysis.module.run_volume.plot_laptime.side_effect = [RuntimeError("figure failed"), None]
    elif stage == "report":
        analysis.report.write.side_effect = [RuntimeError("HTML failed"), None]
    else:
        analysis.manifest.side_effect = [RuntimeError("manifest failed"), None]
    with pytest.raises(RuntimeError):
        analysis.module.main(force=True)
    assert not manifest_path(analysis.report_dir).exists()

    assert analysis.module.main(force=False) == 0
    assert analysis.report.write.call_count == (1 if stage == "analysis" else 2)
    assert analysis.manifest.call_count == (2 if stage == "manifest" else 1)


def test_figure_construction_failure_closes_only_owned_figure(monkeypatch, tmp_path):
    laps = pd.DataFrame({
        "Stint": [1], "DriverNumber": ["1"], "Team": ["Ferrari"], "LapNumber": [1],
        "LapStartDate": [datetime.datetime(2026, 1, 1)], "Driver": ["Driver"],
    })
    session = MagicMock()
    session.laps = laps
    session.event.year = 2026
    unrelated = plt.figure()
    before = set(plt.get_fignums())
    monkeypatch.setattr(run_volume, "driver_linestyle", lambda *args: "solid")
    monkeypatch.setattr("fastf1.plotting.get_team_color", lambda *args: "red")
    monkeypatch.setattr(run_volume, "save_matplotlib", lambda *args, **kwargs: None)
    with pytest.raises(RuntimeError, match="plot failed"):
        with monkeypatch.context() as patcher:
            patcher.setattr(run_volume.plt.Axes, "plot", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("plot failed")))
            run_volume.plot_lap_number_by_timing(session, MagicMock(), output_dir=tmp_path)
    assert set(plt.get_fignums()) == before
    assert unrelated.number in plt.get_fignums()
    plt.close(unrelated)


def test_report_context_does_not_leak_figures_to_next_session(analysis):
    analysis.module.run_volume.plot_laptime.side_effect = RuntimeError("injected failure")
    with pytest.raises(RuntimeError):
        analysis.module.main(force=True)
    second = report_module.SessionReport(analysis.session, Path("second"))
    with second:
        assert current_report() is second
        assert second._ordered_items() == []
    assert current_report() is None


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


def test_load_options_and_manifest_outputs_keep_session_contract(analysis):
    png = analysis.report.output_dir / "current.png"
    analysis.report.written_output_paths.return_value = (png,)
    analysis.report.required_png_paths.return_value = (png,)
    assert analysis.module.main() == 0
    is_race = analysis.category == "race"
    analysis.session.load.assert_called_once_with(**({} if is_race else {"messages": False}))
    session_pipeline.session_input_fingerprint.assert_called_once_with(
        analysis.session, include_messages=is_race)
    # Race fingerprints once before load and never rebuilds; other
    # categories fingerprint before the reuse check and again after persist.
    assert session_pipeline.build_fingerprint.call_count == (1 if is_race else 2)
    args, kwargs = analysis.manifest.call_args
    assert args[2] == {
        "year": 2026, "round": 1, "session": analysis.session.name,
        "entrypoint": Path(analysis.module.__file__).name,
    }
    logs = ()
    if is_race:
        # The race manifest pins the three FastF1 log files next to the
        # session's output directory, exactly where _figures returned them.
        logs = tuple(analysis.report.output_dir / name
                     for name in ("timestamp.txt", "race_control.txt", "track_status.txt"))
    assert kwargs["extra_output_paths"] == (png, *logs)
    assert kwargs["required_output_paths"] == (analysis.report.report_dir / "report.html", png, *logs)
    assert kwargs["session_input"] == {"algorithm": "test", "hash": "x"}


@pytest.mark.parametrize("force", [False, True])
def test_reuse_is_checked_after_loading_and_force_is_forwarded(analysis, force):
    def check(*args, **kwargs):
        analysis.session.load.assert_called_once()
        assert kwargs["force"] is force
        assert kwargs["complete"] is True
        return not force

    session_pipeline.should_skip.side_effect = check
    assert analysis.module.main(force=force) == 0
    assert analysis.report.write.call_count == int(force)
    assert manifest_path(analysis.report_dir).exists() is (not force)


@pytest.mark.parametrize("analysis", SESSIONS[:5], indirect=True)
@pytest.mark.parametrize("mode", ["force", "refresh", "pending", "save-failure"])
def test_separator_resolution_persistence_and_post_save_fingerprint(analysis, mode):
    resolution = session_pipeline.resolve_separators.return_value
    resolution.pending_save = mode == "pending"
    before, after = object(), object()
    session_pipeline.build_fingerprint.side_effect = [before, after]
    if mode == "pending":
        session_pipeline.should_skip.return_value = True
    if mode == "save-failure":
        session_pipeline.persist_resolution.side_effect = OSError("read only")
    assert analysis.module.main(force=mode == "force", refresh_separators=mode == "refresh") == 0
    assert session_pipeline.resolve_separators.call_args.kwargs["refresh"] is (mode == "refresh")
    session_pipeline.persist_resolution.assert_called_once_with(
        resolution, Path("config.json"), analysis.session, refresh=mode == "refresh")
    if mode == "pending":
        session_pipeline.should_skip.assert_not_called()
    else:
        assert session_pipeline.should_skip.call_args.kwargs["force"] is (mode in {"force", "refresh"})
    assert analysis.manifest.call_args.args[1] is after
    if mode == "save-failure":
        analysis.log.warning.assert_any_call("automatic separators were not saved", error="read only")


def test_cli_options_remain_category_specific(analysis):
    assert analysis.module.parse_args([]).force is False
    assert analysis.module.parse_args(["--force"]).force is True
    if analysis.category == "race":
        with pytest.raises(SystemExit) as error:
            analysis.module.parse_args(["--refresh-separators"])
        assert error.value.code == 2
    else:
        assert analysis.module.parse_args([]).refresh_separators is False
        assert analysis.module.parse_args(["--refresh-separators"]).refresh_separators is True
