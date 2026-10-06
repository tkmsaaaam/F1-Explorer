from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from f1_explorer.visualizations import weekend


def _session(name="Practice 1", status="Finished", root=None):
    session = Mock()
    session.name = name
    session.event = SimpleNamespace(year=2026, RoundNumber=13, Location="Baku", EventFormat="conventional")
    session.api_path = "/static/2026/2026-06-12_Canadian_Grand_Prix/2026-06-12_Practice_1/"
    session.session_status = pd.DataFrame({"Status": [status]})
    return session


def _aggregate(complete=True, inputs="inputs"):
    return {
        "drivers": {"AAA": {"Sessions": ["FP1"], "Compounds": ["SOFT"]}},
        "order": ["AAA"], "figure_names": ["AAA"], "sprint": False,
        "event": {"year": 2026, "round": 13, "location": "Baku"},
        "complete": complete, "inputs": inputs,
        "session_signatures": {"FP1": "session"},
    }


class _FakeWeekendSession:
    def __init__(self, name, *, status="Finished", date=None, abbreviations=("AAA",)):
        self.name = name
        self.date = date or weekend.datetime.datetime(2026, 1, 1)
        self.load_count = 0
        self.event = SimpleNamespace(year=2026, RoundNumber=13, Location="Baku",
                                     EventFormat="conventional")
        self.results = SimpleNamespace(Abbreviation=list(abbreviations))
        self.drivers = list(abbreviations)
        self.laps = _FakeLaps(pd.DataFrame({"Driver": list(abbreviations),
                                            "FreshTyre": [True] * len(abbreviations),
                                            "Stint": [1] * len(abbreviations),
                                            "Compound": ["SOFT"] * len(abbreviations)}))
        self.session_status = pd.DataFrame({"Status": [status]})
        self.api_path = f"/static/2026/event/{name}/"

    def load(self, **kwargs):
        self.load_count += 1

    def get_driver(self, abbreviation):
        return SimpleNamespace(Abbreviation=abbreviation)


class _FakeLaps:
    def __init__(self, frame):
        self.frame = frame

    def pick_drivers(self, driver):
        return self.frame[self.frame["Driver"] == driver]


def test_input_signature_uses_fastf1_public_cache_info_and_event_api_path(tmp_path: Path) -> None:
    event_dir = tmp_path / "2026" / "some-event"
    event_dir.mkdir(parents=True)
    (event_dir / "fp1.ff1pkl").write_bytes(b"fp1")
    (event_dir / "q.ff1pkl").write_bytes(b"qualifying")
    (event_dir / "unrelated.sqlite").write_bytes(b"ignore")
    session = _session()
    session.api_path = "/static/2026/some-event/session/"
    with patch.object(weekend.fastf1.Cache, "get_cache_info", return_value=(str(tmp_path), 100)):
        signature = weekend._input_signature(2026, 13, session)
        assert signature is not None
        before = signature
        (event_dir / "q.ff1pkl").write_bytes(b"changed-size")
        assert weekend._input_signature(2026, 13, session) != before
        assert weekend._input_signature(2026, 13, None) is None


def test_cache_hit_reuses_completed_snapshot_without_reload(monkeypatch, tmp_path: Path) -> None:
    session = _session()
    session.name = "Practice 1"
    session.drivers = []
    session.results = SimpleNamespace(Abbreviation=[])
    monkeypatch.setenv("F1_WEEKEND_TYRE_CACHE", str(tmp_path))
    fingerprint = {"fingerprint": "source", "environment": "deps", "settings": "settings", "inputs": "inputs"}
    monkeypatch.setattr(weekend, "_cache_fingerprint", lambda *args: fingerprint)
    monkeypatch.setattr(weekend, "_read_cache", lambda *args: _aggregate())
    monkeypatch.setattr(weekend, "aggregate_tyres", Mock(side_effect=AssertionError("unexpected recompute")))
    monkeypatch.setattr(weekend, "_loaded_session_signature", lambda *args: "session")
    assert weekend._batch_cached_aggregate(2026, 13, Mock(), session) == _aggregate()


def test_cache_miss_writes_only_finished_stable_aggregate(monkeypatch, tmp_path: Path) -> None:
    session = _session()
    monkeypatch.setenv("F1_WEEKEND_TYRE_CACHE", str(tmp_path))
    fingerprint = {"fingerprint": "source", "environment": "deps", "settings": "settings", "inputs": "inputs"}
    monkeypatch.setattr(weekend, "_cache_fingerprint", lambda *args: fingerprint)
    monkeypatch.setattr(weekend, "_read_cache", lambda *args: None)
    monkeypatch.setattr(weekend, "aggregate_tyres", lambda *args, **kwargs: _aggregate())
    write = Mock()
    monkeypatch.setattr(weekend, "_write_cache", write)
    assert weekend._batch_cached_aggregate(2026, 13, Mock(), session) == _aggregate()
    write.assert_called_once()

    write.reset_mock()
    monkeypatch.setattr(weekend, "aggregate_tyres", lambda *args, **kwargs: _aggregate(complete=False))
    weekend._batch_cached_aggregate(2026, 13, Mock(), session)
    write.assert_not_called()


@pytest.mark.parametrize(
    ("initial_files", "final_files", "should_write"),
    [
        ([['old.ff1pkl', 10, 1]], [['old.ff1pkl', 10, 1], ['new.ff1pkl', 20, 2]], True),
        ([['old.ff1pkl', 10, 1]], [['old.ff1pkl', 11, 3]], False),
        ([['old.ff1pkl', 10, 1]], [], False),
    ],
)
def test_cache_write_allows_new_files_but_rejects_changed_or_missing_inputs(
    monkeypatch, tmp_path: Path, initial_files, final_files, should_write
) -> None:
    monkeypatch.setenv("F1_WEEKEND_TYRE_CACHE", str(tmp_path))
    initial = {"fingerprint": "src", "environment": "deps", "settings": "cfg",
               "inputs": "initial", "input_files": initial_files}
    final = {"fingerprint": "src", "environment": "deps", "settings": "cfg",
             "inputs": "final", "input_files": final_files}
    fingerprints = iter([initial, final, final])
    monkeypatch.setattr(weekend, "_cache_fingerprint", lambda *args: next(fingerprints))
    monkeypatch.setattr(weekend, "_read_cache", lambda *args: None)
    aggregate = _aggregate(inputs="final")
    monkeypatch.setattr(weekend, "aggregate_tyres", lambda *args, **kwargs: aggregate)
    write = Mock()
    monkeypatch.setattr(weekend, "_write_cache", write)

    weekend._batch_cached_aggregate(2026, 13, Mock(), _session())

    assert write.called is should_write


def test_cache_hit_recomputes_when_loaded_session_changed(monkeypatch, tmp_path: Path) -> None:
    session = _session()
    session.name = "Practice 1"
    monkeypatch.setenv("F1_WEEKEND_TYRE_CACHE", str(tmp_path))
    fingerprint = {"fingerprint": "source", "environment": "deps", "settings": "settings", "inputs": "inputs"}
    monkeypatch.setattr(weekend, "_cache_fingerprint", lambda *args: fingerprint)
    monkeypatch.setattr(weekend, "_read_cache", lambda *args: _aggregate())
    monkeypatch.setattr(weekend, "_loaded_session_signature", lambda *args: "changed")
    recomputed = _aggregate()
    aggregate = Mock(return_value=recomputed)
    monkeypatch.setattr(weekend, "aggregate_tyres", aggregate)
    monkeypatch.setattr(weekend, "_write_cache", Mock())
    assert weekend._batch_cached_aggregate(2026, 13, Mock(), session) == recomputed
    aggregate.assert_called_once()


def test_figure_reuses_captured_driver_column_order() -> None:
    aggregate = _aggregate()
    aggregate["drivers"]["BBB"] = {"Sessions": ["Q"], "Compounds": ["HARD"]}
    aggregate["figure_names"] = ["AAA", "BBB"]
    figure = weekend.make_tyre_figure(aggregate)
    assert list(figure.data[0].header.values) == ["AAA", "BBB"]


def test_aggregate_reuses_current_session_skips_future_and_requires_completed_race(monkeypatch) -> None:
    current = _FakeWeekendSession("Practice 1")
    future = _FakeWeekendSession("Practice 2", date=weekend.datetime.datetime(2027, 1, 1),
                                 abbreviations=("AAA", "BBB"))
    qualifying = _FakeWeekendSession("Qualifying", abbreviations=("AAA", "BBB"))
    race = _FakeWeekendSession("Race", status="Started", abbreviations=("AAA",))
    lookup = {"FP2": future, "Q": qualifying, "R": race}

    def get_session(year, round_number, name):
        try:
            return lookup[name]
        except KeyError as error:
            raise ValueError("session unavailable") from error

    monkeypatch.setattr(weekend.fastf1, "get_session", get_session)
    monkeypatch.setattr(weekend, "_input_signature", lambda *args: "files")
    aggregate = weekend.aggregate_tyres(2026, 13, Mock(), current_session=current)
    assert aggregate is not None
    assert aggregate["complete"] is False
    assert current.load_count == 0
    assert future.load_count == 0
    assert qualifying.load_count == 1
    assert race.load_count == 1
    assert "BBB" in aggregate["drivers"]


def test_incomplete_real_aggregate_does_not_write_batch_cache(monkeypatch, tmp_path: Path) -> None:
    current = _FakeWeekendSession("Practice 1")
    race = _FakeWeekendSession("Race", status="Started")
    monkeypatch.setattr(weekend.fastf1, "get_session", lambda year, rnd, name:
                        race if name == "R" else (_ for _ in ()).throw(ValueError("absent")))
    monkeypatch.setattr(weekend, "_input_signature", lambda *args: "files")
    monkeypatch.setenv("F1_WEEKEND_TYRE_CACHE", str(tmp_path))
    fingerprint = {"fingerprint": "source", "environment": "deps", "settings": "settings", "inputs": "files"}
    monkeypatch.setattr(weekend, "_cache_fingerprint", lambda *args: fingerprint)
    monkeypatch.setattr(weekend, "_read_cache", lambda *args: None)
    write = Mock()
    monkeypatch.setattr(weekend, "_write_cache", write)
    aggregate = weekend._batch_cached_aggregate(2026, 13, Mock(), current)
    assert aggregate is not None and aggregate["complete"] is False
    write.assert_not_called()


def test_cache_read_rejects_corrupt_and_wrong_version(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    fingerprint = {"x": 1}
    path.write_text("[]", encoding="utf-8")
    assert weekend._read_cache(path, fingerprint) is None
    path.write_text(json.dumps({"schema": 999, "fingerprint": fingerprint, "aggregate": _aggregate()}), encoding="utf-8")
    assert weekend._read_cache(path, fingerprint) is None
    path.write_text(json.dumps({"schema": weekend._CACHE_SCHEMA, "fingerprint": fingerprint,
                                "aggregate": _aggregate()}), encoding="utf-8")
    assert weekend._read_cache(path, fingerprint) == _aggregate()
    malformed = _aggregate()
    malformed["event"] = {"year": "2026", "round": 13, "location": "Baku"}
    path.write_text(json.dumps({"schema": weekend._CACHE_SCHEMA, "fingerprint": fingerprint,
                                "aggregate": malformed}), encoding="utf-8")
    assert weekend._read_cache(path, fingerprint) is None


@pytest.mark.parametrize(
    ("statuses", "complete"),
    [
        (["Finished"], True),
        (["Started", "Finished", "Finalised"], True),
        (["Started", "Finished", "Finalised", "Ends"], True),
        (["Started", "Finished", "Started", "Ends"], False),
        (["Started", "Finished", "Started"], False),
        (["Started", "Ends"], False),
    ],
)
def test_finished_status_requires_latest_terminal_evidence(statuses, complete) -> None:
    session = _session()
    session.session_status = pd.DataFrame({"Status": statuses})
    assert weekend._session_is_complete(session) is complete


def test_cache_write_failure_is_nonfatal(tmp_path: Path) -> None:
    blocked_parent = tmp_path / "file"
    blocked_parent.write_text("not a directory", encoding="utf-8")
    weekend._write_cache(blocked_parent / "cache.json", {"x": 1}, _aggregate())


def test_cache_fingerprint_invalidates_source_dependency_settings_and_inputs(monkeypatch, tmp_path: Path) -> None:
    event_dir = tmp_path / "2026" / "event"
    event_dir.mkdir(parents=True)
    input_file = event_dir / "session.ff1pkl"
    input_file.write_bytes(b"input")
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"Year": 2026, "Round": 13, "Session": "FP1",
                                       "CustomSetting": "a", "separator": [1]}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    session = _session()
    session.api_path = "/static/2026/event/session/"
    monkeypatch.setattr(weekend.fastf1.Cache, "get_cache_info", lambda: (str(tmp_path), 5))
    fingerprint_state = {"source": "source-a", "environment": "deps-a"}
    monkeypatch.setattr(
        "f1_explorer.analysis_state.build_fingerprint",
        lambda *args: SimpleNamespace(source_hash=fingerprint_state["source"],
                                      environment_hash=fingerprint_state["environment"]),
    )
    original = weekend._cache_fingerprint(2026, 13, session)
    assert original is not None
    fingerprint_state["source"] = "source-b"
    assert weekend._cache_fingerprint(2026, 13, session) != original
    fingerprint_state["source"] = "source-a"
    fingerprint_state["environment"] = "deps-b"
    assert weekend._cache_fingerprint(2026, 13, session) != original
    fingerprint_state["environment"] = "deps-a"
    config_path.write_text(json.dumps({"Year": 2026, "Round": 13, "Session": "Q",
                                       "CustomSetting": "b", "separator": [99]}), encoding="utf-8")
    assert weekend._cache_fingerprint(2026, 13, session) != original
    config_path.write_text(json.dumps({"Year": 2026, "Round": 13, "Session": "Q",
                                       "CustomSetting": "a", "separator": [99]}), encoding="utf-8")
    assert weekend._cache_fingerprint(2026, 13, session) == original
    input_file.write_bytes(b"changed input")
    assert weekend._cache_fingerprint(2026, 13, session) != original


def test_each_plot_call_saves_its_own_report_figure(monkeypatch, tmp_path: Path) -> None:
    session = _session()
    aggregate = _aggregate()
    monkeypatch.delenv("F1_WEEKEND_TYRE_CACHE", raising=False)
    aggregate_call = Mock(return_value=aggregate)
    monkeypatch.setattr(weekend, "aggregate_tyres", aggregate_call)
    saved = []
    monkeypatch.setattr(weekend, "save_plotly", lambda figure, path, *args, **kwargs: saved.append((figure, path)))
    weekend.plot_tyre(2026, 13, Mock(), output_dir=tmp_path, current_session=session)
    weekend.plot_tyre(2026, 13, Mock(), output_dir=tmp_path, current_session=session)
    assert len(saved) == 2
    assert [path for _, path in saved] == [tmp_path / "tyres.png"] * 2
    assert saved[0][0].to_json() == saved[1][0].to_json()
