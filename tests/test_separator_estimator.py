from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import pandas as pd

from separator_estimator import (
    SeparatorEstimationError,
    SeparatorBoundary,
    SeparatorResolution,
    StaticArchiveClient,
    build_distance_lookup,
    build_live_timing_lap_windows,
    estimate_separator_distances,
    estimate_separator_boundaries,
    parse_json_stream,
    persist_resolution,
    resolve_separators,
)


def _line(driver: str, lap: int, sector: int, segment: int, status: int, value: str | None = "1"):
    segment_data = {"Status": status}
    if value is not None:
        segment_data["Value"] = value
    return {
        "Lines": {
            driver: {
                "LapNumber": lap,
                "Sectors": {str(sector): {"Segments": {str(segment): segment_data}}},
            }
        }
    }


def test_estimate_uses_first_evaluated_transition_and_median() -> None:
    records = []
    lookup = {}
    for driver, distance in (("1", 100.0), ("2", 102.0), ("3", 98.0)):
        records.extend([
            ["00:00:01:000", _line(driver, 1, 0, 0, 0, None)],
            ["00:00:02:000", _line(driver, 1, 0, 0, 2048)],
            # A later purple/green update must not add a second sample.
            ["00:00:03:000", _line(driver, 1, 0, 0, 2048, "2")],
        ])
        lookup[(driver, 1)] = {"SessionTime": [0, 2, 10], "Distance": [0, distance, distance * 10]}
    assert estimate_separator_distances(records, lookup, track_length=2000) == [100.0]


def test_estimate_maps_live_and_telemetry_by_sector_time_percent() -> None:
    records = []
    lookup = {}
    for driver, offset, lap_distance in (("1", 0, 1000), ("2", 10, 1020), ("3", 20, 980)):
        records.extend([
            [offset + 1, {"Lines": {driver: {
                "NumberOfLaps": 0,
                "Sectors": {"0": {"Segments": {"0": {"Status": 0}}}},
            }}}],
            [offset + 45, {"Lines": {driver: {
                "NumberOfLaps": 0,
                "Sectors": {"0": {"Segments": {"0": {"Status": 2048}}}},
            }}}],
            [offset + 90, {"Lines": {driver: {
                "NumberOfLaps": 1,
                "LastLapTime": {"Value": "1:30.000"},
            }}}],
        ])
        # Absolute SessionTime is intentionally unrelated to the archive
        # clock; only the per-lap percentage is a stable join key.
        lookup[(driver, 1)] = {
            "SessionTime": [1000, 1090],
            "LapTimePercent": [0, 100],
            "SectorTimePercent": {"0": [0, 100]},
            "Distance": [0, lap_distance],
        }
    diagnostics = {}
    assert estimate_separator_distances(
        records, lookup, track_length=1100, diagnostics=diagnostics
    ) == [1000.0]
    assert diagnostics["consistent_laps"] == 3
    assert diagnostics["duration_mismatch"] == 0


def test_sector_local_percent_is_not_shifted_by_previous_sector() -> None:
    records = []
    lookup = {}
    for driver, offset in (("1", 0), ("2", 100), ("3", 200)):
        records.extend([
            [offset + 0, {"Lines": {driver: {"NumberOfLaps": 0,
                "Sectors": {"0": {"Segments": {"0": {"Status": 0}}}}}}}],
            [offset + 30, {"Lines": {driver: {"NumberOfLaps": 0,
                "Sectors": {"0": {"Segments": {"0": {"Status": 2048}}}}}}}],
            [offset + 31, {"Lines": {driver: {"NumberOfLaps": 0,
                "Sectors": {"1": {"Segments": {
                    "0": {"Status": 0}, "1": {"Status": 0}
                }}}}}}],
            [offset + 45, {"Lines": {driver: {"NumberOfLaps": 0,
                "Sectors": {"1": {"Segments": {"0": {"Status": 2048}}}}}}}],
            [offset + 60, {"Lines": {driver: {"NumberOfLaps": 0,
                "Sectors": {"1": {"Segments": {"1": {"Status": 2048}}}}}}}],
            [offset + 90, {"Lines": {driver: {"NumberOfLaps": 1,
                "LastLapTime": {"Value": "1:30.000"}}}}],
        ])
        lookup[(driver, 1)] = {
            "SectorTimePercent": {
                "0": [0, 100, 200, 300],
                "1": [-100, 0, 50, 100],
            },
            "Distance": [0, 300, 600, 900],
        }
    # S1 completion is 300 m. The first S2 mini-sector is halfway through S2,
    # therefore 600 m, independent of how much lap time S1 consumed.
    assert estimate_separator_distances(records, lookup, track_length=1000) == [300.0, 600.0, 900.0]


def test_explicit_sector_completion_takes_priority_over_last_mini_segment() -> None:
    records = []
    lookup = {}
    for driver, offset in (("1", 0), ("2", 100), ("3", 200)):
        records.extend([
            [offset + 0, {"Lines": {driver: {"NumberOfLaps": 0,
                "Sectors": {"0": {"Segments": {"0": {"Status": 0}}}}}}}],
            [offset + 25, {"Lines": {driver: {"NumberOfLaps": 0,
                "Sectors": {"0": {"Segments": {"0": {"Status": 2048}}}}}}}],
            # The mini-segment transition would imply 100% at t=25, but the
            # explicit sector update says that S1 ends at t=50.
            [offset + 50, {"Lines": {driver: {"NumberOfLaps": 0,
                "Sectors": {"0": {"Status": 2048, "Value": "0:50.000"}}}}}],
            [offset + 100, {"Lines": {driver: {"NumberOfLaps": 1,
                "LastLapTime": {"Value": "1:40.000"}}}}],
        ])
        lookup[(driver, 1)] = {
            "SectorTimePercent": {"0": [0, 100]},
            "Distance": [0, 300],
            "SectorDistanceRange": {"0": [0, 300]},
        }
    assert estimate_separator_distances(records, lookup, track_length=1000) == [150.0]
    assert estimate_separator_boundaries(records, lookup, track_length=1000) == [
        SeparatorBoundary(150.0, 0, 0)
    ]


def test_sector_interpolation_is_clamped_to_fastf1_sector_distance_range() -> None:
    records = []
    lookup = {}
    for driver, offset in (("1", 0), ("2", 100), ("3", 200)):
        records.extend([
            [offset + 0, {"Lines": {driver: {"NumberOfLaps": 0,
                "Sectors": {"0": {"Segments": {"0": {"Status": 0}}}}}}}],
            [offset + 50, {"Lines": {driver: {"NumberOfLaps": 0,
                "Sectors": {"0": {"Segments": {"0": {"Status": 2048}}}}}}}],
            [offset + 100, {"Lines": {driver: {"NumberOfLaps": 1,
                "LastLapTime": {"Value": "1:40.000"}}}}],
        ])
        lookup[(driver, 1)] = {
            "SectorTimePercent": {"0": [0, 100]},
            # Deliberately wider than the actual FastF1 sector range.
            "Distance": [0, 1000],
            "SectorDistanceRange": {"0": [100, 800]},
        }
    assert estimate_separator_distances(records, lookup, track_length=1000) == [800.0]


def test_missing_sector_coordinates_are_excluded_in_normalized_mode() -> None:
    records = []
    lookup = {}
    for driver, offset in (("1", 0), ("2", 100), ("3", 200)):
        records.extend([
            [offset + 20, {"Lines": {driver: {"NumberOfLaps": 0,
                # S2 has a completion, but S1 has no boundary to define S2's
                # local origin.
                "Sectors": {"1": {"Segments": {"0": {"Status": 0}}}}}}}],
            [offset + 50, {"Lines": {driver: {"NumberOfLaps": 0,
                "Sectors": {"1": {"Segments": {"0": {"Status": 2048}}}}}}}],
            [offset + 100, {"Lines": {driver: {"NumberOfLaps": 1,
                "LastLapTime": {"Value": "1:40.000"}}}}],
        ])
        lookup[(driver, 1)] = {
            "LapTimePercent": [0, 100], "Distance": [0, 1000],
            "SectorTimePercent": {"1": [0, 100]},
        }
    with pytest.raises(SeparatorEstimationError):
        estimate_separator_distances(records, lookup, track_length=1000)


def test_fastf1_sector_ranges_are_built_from_sector_times() -> None:
    telemetry = pd.DataFrame({
        "SessionTime": pd.to_timedelta([0, 10, 20, 30, 40, 50, 60], unit="s"),
        "Distance": [0, 100, 200, 300, 400, 500, 600],
    })
    telemetry.add_distance = lambda: telemetry
    lap = SimpleNamespace(
        DriverNumber="1", LapNumber=1, IsAccurate=True, Deleted=False,
        PitInTime=None, PitOutTime=None, LapTime=pd.to_timedelta(60, unit="s"),
        Sector1Time=pd.to_timedelta(20, unit="s"), Sector2Time=pd.to_timedelta(20, unit="s"),
        Sector3Time=pd.to_timedelta(20, unit="s"), get_telemetry=lambda: telemetry,
    )

    class Laps:
        iloc = [lap]

        def __len__(self):
            return 1

    lookup, track_length = build_distance_lookup(SimpleNamespace(laps=Laps()))
    assert track_length == 600
    assert lookup[("1", 1)]["SectorDistanceRange"] == {
        "0": [0.0, 200.0], "1": [200.0, 400.0], "2": [400.0, 600.0],
    }


def test_inconsistent_fastf1_sector_times_do_not_create_sector_mapping() -> None:
    telemetry = pd.DataFrame({
        "SessionTime": pd.to_timedelta([0, 10, 20, 30, 40], unit="s"),
        "Distance": [0, 100, 200, 300, 400],
    })
    telemetry.add_distance = lambda: telemetry
    lap = SimpleNamespace(
        DriverNumber="1", LapNumber=1, IsAccurate=True, Deleted=False,
        PitInTime=None, PitOutTime=None, LapTime=pd.to_timedelta(40, unit="s"),
        Sector1Time=pd.to_timedelta(10, unit="s"), Sector2Time=pd.to_timedelta(10, unit="s"),
        Sector3Time=pd.to_timedelta(10, unit="s"), get_telemetry=lambda: telemetry,
    )

    class Laps:
        iloc = [lap]

        def __len__(self):
            return 1

    lookup, track_length = build_distance_lookup(SimpleNamespace(laps=Laps()))
    assert track_length == 400
    assert "SectorTimePercent" not in lookup[("1", 1)]


def test_live_timing_lap_validation_rejects_inconsistent_duration() -> None:
    records = [
        [90, {"Lines": {"1": {"NumberOfLaps": 1, "LastLapTime": {"Value": "1:30.000"}}}}],
        [200, {"Lines": {"1": {"NumberOfLaps": 2, "LastLapTime": {"Value": "1:30.000"}}}}],
    ]
    windows, diagnostics = build_live_timing_lap_windows(records)
    assert [window.lap for window in windows] == [1]
    assert diagnostics["duration_mismatch"] == 1


def test_estimate_rejects_insufficient_and_out_of_track_samples() -> None:
    records = [
        ["00:00:01:000", _line("1", 1, 0, 0, 2048)],
        ["00:00:02:000", _line("2", 1, 0, 0, 2048)],
        ["00:00:03:000", _line("3", 1, 0, 0, 2048)],
    ]
    for record in records:
        record[1]["Lines"][next(iter(record[1]["Lines"]))]["Sectors"]["0"]["Segments"]["0"]["Distance"] = 1000
    with pytest.raises(SeparatorEstimationError):
        estimate_separator_distances(records, track_length=1000)


def test_stream_parser_accepts_archive_lines() -> None:
    raw = '00:00:01:000{"Lines":{"1":{"LapNumber":1}}}\r\n'
    parsed = parse_json_stream(raw)
    assert parsed[0][0] == "00:00:01:000"
    assert parsed[0][1]["Lines"]["1"]["LapNumber"] == 1


def test_static_archive_resolves_indexes_and_caches() -> None:
    payloads = {
        "https://example.test/static/2025/Index.json": {"Meetings": [{
            "Location": "Test Circuit", "Path": "2025/Test/",
            "Sessions": [{"Name": "Practice 1", "Path": "2025/Test/Practice/"}],
        }]},
        "https://example.test/static/2025/Test/Practice/Index.json": {"Files": ["TimingData.jsonStream"]},
        "https://example.test/static/2025/Test/Practice/TimingData.jsonStream": "00:00:01:000{}\r\n",
    }
    calls = []

    class Response:
        status_code = 200

        def __init__(self, value):
            self.content = json.dumps(value).encode() if not isinstance(value, str) else value.encode()

    def get(url, timeout):
        calls.append((url, timeout))
        return Response(payloads[url])

    session = SimpleNamespace(name="Practice 1", api_path="/static/fallback/",
                              event=SimpleNamespace(year=2025, Location="Test Circuit"))
    client = StaticArchiveClient(base_url="https://example.test", http_get=get)
    assert client.timing_data(session) == [["00:00:01:000", {}]]
    assert len(calls) == 3
    assert all(timeout == 15 for _, timeout in calls)


def test_resolution_prefers_saved_and_persists_estimates_atomically(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"Year": 2025, "Round": 1, "Session": "FP1",
                                       "corners": {"1": [-5, 5]}, "separator": [500],
                                       "other": {"keep": True}}), encoding="utf-8")
    session = SimpleNamespace(name="Practice 1", event=SimpleNamespace(year=2025, Location="Test"))
    resolution = SeparatorResolution([123.45], "estimated", pending_save=True)
    persist_resolution(resolution, config_path, session)
    saved = json.loads(config_path.read_text())
    assert saved["other"] == {"keep": True}
    assert saved["separators"]["2025"]["Test"] == [123.5]
    selected = resolve_separators(session, config_path, client=StaticArchiveClient(http_get=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError())))
    assert selected.source == "saved_auto"
    assert selected.separators == [123.5]


def test_structured_resolution_round_trips_with_legacy_distance_projection(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"Year": 2025, "Round": 1, "Session": "FP1"}), encoding="utf-8")
    session = SimpleNamespace(name="Practice 1", event=SimpleNamespace(year=2025, Location="Test"))
    boundaries = [SeparatorBoundary(123.45, 0, 7), SeparatorBoundary(456.78, 1, 2)]
    persist_resolution(
        SeparatorResolution([123.45, 456.78], "estimated", pending_save=True, boundaries=boundaries),
        config_path,
        session,
    )
    saved = json.loads(config_path.read_text())
    assert saved["separators"]["2025"]["Test"] == {
        "schema_version": 1,
        "boundaries": [
            {"distance": 123.5, "sector": 0, "segment": 7},
            {"distance": 456.8, "sector": 1, "segment": 2},
        ],
    }
    selected = resolve_separators(session, config_path)
    assert selected.separators == [123.5, 456.8]
    assert selected.boundaries == [
        SeparatorBoundary(123.5, 0, 7), SeparatorBoundary(456.8, 1, 2)
    ]
