from __future__ import annotations

import json
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import pandas as pd

from f1_explorer.separator_estimator import (
    SeparatorEstimationError,
    SeparatorBoundary,
    SeparatorResolution,
    StaticArchiveClient,
    _find_session_path,
    _session_key,
    build_distance_lookup,
    build_live_timing_lap_windows,
    coerce_separator_boundary,
    estimate_separator_distances,
    estimate_separator_boundaries,
    parse_json_stream,
    persist_resolution,
    resolve_separators,
)


def _line(driver: str, lap: int, sector: int, segment: int, status: int, value: str | None = "1"):
    segment_data: dict[str, int | str] = {"Status": status}
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


@pytest.mark.parametrize("frequency", ["original", 2])
def test_fastf1_distance_lookup_skips_driver_ahead_and_preserves_telemetry(
    monkeypatch, frequency
) -> None:
    from fastf1.core import Lap, Session, Telemetry

    monkeypatch.setattr(Telemetry, "TELEMETRY_FREQUENCY", frequency)

    session_date = pd.Timestamp("2026-01-01", tz="UTC")

    class Event(dict):
        def get_session_date(self, *_args, **_kwargs):
            return session_date

    session = Session(
        Event(EventName="Test", EventDate=session_date), "Practice 1"
    )
    session._t0_date = session_date
    car_times = pd.to_timedelta([0, 2, 4, 6, 8, 10, 12], unit="s")
    position_times = pd.to_timedelta([0, 3, 6, 9, 12], unit="s")
    session._car_data = {
        "1": Telemetry(pd.DataFrame({
            "Date": session_date + car_times,
            "SessionTime": car_times,
            "Time": car_times,
            "Speed": [100, 110, 120, 130, 140, 150, 160],
            "Throttle": [100] * 7,
            "Brake": [False] * 7,
            "nGear": [3] * 7,
            "RPM": [10000] * 7,
            "Source": ["car"] * 7,
        }))
    }
    session._pos_data = {
        "1": Telemetry(pd.DataFrame({
            "Date": session_date + position_times,
            "SessionTime": position_times,
            "Time": position_times,
            "X": [0, 3, 6, 9, 12],
            "Y": [0] * 5,
            "Z": [0] * 5,
            "Status": ["OnTrack"] * 5,
            "Source": ["pos"] * 5,
        }))
    }
    for telemetry in (session._car_data["1"], session._pos_data["1"]):
        telemetry.session = session
        telemetry.driver = "1"
    lap = Lap({
        "DriverNumber": "1", "LapNumber": 1,
        "LapStartTime": pd.to_timedelta(1, unit="s"),
        "Time": pd.to_timedelta(11, unit="s"),
        "LapTime": pd.to_timedelta(10, unit="s"),
        "Sector1Time": pd.to_timedelta(3, unit="s"),
        "Sector2Time": pd.to_timedelta(3, unit="s"),
        "Sector3Time": pd.to_timedelta(4, unit="s"),
    })
    lap.session = session

    ahead_calls = []

    def add_driver_ahead(telemetry):
        ahead_calls.append(True)
        return telemetry.assign(DriverAhead="", DistanceToDriverAhead=float("nan"))

    monkeypatch.setattr(Telemetry, "add_driver_ahead", add_driver_ahead)
    # FastF1 currently constructs Timedelta(seconds=...) without an explicit
    # unit when using a numeric telemetry frequency; pandas warns on that
    # dependency code path.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="The 'generic' unit for NumPy timedelta is deprecated.*",
            category=DeprecationWarning,
            module=r"fastf1\.core",
        )
        expected = lap.get_telemetry().add_distance()
    assert ahead_calls
    ahead_calls.clear()

    def unexpected_get_telemetry():
        raise AssertionError("raw FastF1 path must avoid get_telemetry")

    monkeypatch.setattr(lap, "get_telemetry", unexpected_get_telemetry)

    class Laps:
        iloc = [lap]

        def __len__(self):
            return 1

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="The 'generic' unit for NumPy timedelta is deprecated.*",
            category=DeprecationWarning,
            module=r"fastf1\.core",
        )
        lookup, track_length = build_distance_lookup(SimpleNamespace(laps=Laps()))
    result = lookup[("1", 1)]
    assert not ahead_calls
    assert track_length == pytest.approx(float(expected["Distance"].iloc[-1]))
    expected_times = [value.total_seconds() for value in expected["SessionTime"]]
    expected_distances = expected["Distance"].tolist()
    assert result["SessionTime"] == expected_times
    assert result["Distance"] == expected_distances
    assert expected_times[0] == 1.0
    assert expected_times[-1] == 11.0


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


def test_invalid_laps_are_skipped_before_raw_telemetry_access() -> None:
    invalid_laps = [
        SimpleNamespace(
            DriverNumber="1", LapNumber=1, IsAccurate=False,
            get_car_data=Mock(), get_pos_data=Mock(), get_telemetry=Mock(),
        ),
        SimpleNamespace(
            DriverNumber="2", LapNumber=2, PitInTime=pd.to_timedelta(1, unit="s"),
            get_car_data=Mock(), get_pos_data=Mock(), get_telemetry=Mock(),
        ),
    ]

    class Laps:
        iloc = invalid_laps

        def __len__(self):
            return len(self.iloc)

    assert build_distance_lookup(SimpleNamespace(laps=Laps())) == ({}, None)
    for lap in invalid_laps:
        lap.get_car_data.assert_not_called()
        lap.get_pos_data.assert_not_called()
        lap.get_telemetry.assert_not_called()


@pytest.mark.parametrize(
    "failure", ["empty_car", "raw_accessor", "missing_session_time"]
)
def test_fastf1_raw_telemetry_failures_skip_lap_without_fallback(failure) -> None:
    from fastf1.core import Telemetry

    get_telemetry = Mock()
    lap = SimpleNamespace(
        DriverNumber="1", LapNumber=1, IsAccurate=True, Deleted=False,
        PitInTime=None, PitOutTime=None,
        get_telemetry=get_telemetry,
    )
    if failure == "empty_car":
        empty = Telemetry(pd.DataFrame(columns=["Date", "Time", "SessionTime", "Speed", "Source"]))
        get_car_data = Mock(return_value=empty)
        get_pos_data = Mock(return_value=empty)
    elif failure == "missing_session_time":
        malformed = Telemetry(pd.DataFrame({
            "Date": pd.date_range("2026-01-01", periods=3, freq="s", tz="UTC"),
            "Time": pd.to_timedelta([0, 1, 2], unit="s"),
            "Speed": [100, 110, 120],
            "Source": ["car"] * 3,
        }))
        empty = Telemetry(pd.DataFrame(columns=["Date", "Time", "SessionTime", "X", "Y", "Z", "Source"]))
        get_car_data = Mock(return_value=malformed)
        get_pos_data = Mock(return_value=empty)
    else:
        empty = Telemetry(pd.DataFrame(columns=["Date", "Time", "SessionTime", "X", "Y", "Z", "Source"]))
        get_car_data = Mock(side_effect=ValueError("synthetic telemetry failure"))
        get_pos_data = Mock(return_value=empty)
    lap.get_car_data = get_car_data
    lap.get_pos_data = get_pos_data

    class Laps:
        iloc = [lap]

        def __len__(self):
            return 1

    assert build_distance_lookup(SimpleNamespace(laps=Laps())) == ({}, None)
    get_pos_data.assert_called_once_with(pad=1, pad_side="both")
    get_car_data.assert_called_once_with(pad=1, pad_side="both")
    get_telemetry.assert_not_called()


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


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("event, available, expected", [
    pytest.param({"EventName": "B GP"}, True, "B", id="event-name"),
    pytest.param(SimpleNamespace(Location="B"), True, "B", id="location"),
    pytest.param({"EventName": "B GP"}, False, "fallback", id="session-absent"),
    pytest.param({}, True, "fallback", id="no-event-info"),
    pytest.param({"Location": "A", "EventName": "B GP"}, True, "B", id="name-over-location"),
])
def test_static_archive_resolves_indexes_and_caches(reverse, event, available, expected) -> None:
    meetings = [
        {"Name": "A GP", "Location": "A", "Sessions": [{"Name": "Sprint Shootout", "Path": "A/"}]},
        {"Name": "B GP", "Location": "B", "Sessions": [
            {"Name": "Sprint Shootout" if available else "Practice 1", "Path": "B/"}
        ]},
    ]
    base = "https://example.test/static/"
    payloads = {
        base + "2025/Index.json": {"Meetings": meetings[::-1] if reverse else meetings},
        base + expected + "/Index.json": {"Files": ["TimingData.jsonStream"]},
        base + expected + "/TimingData.jsonStream": "00:00:01:000{}\r\n",
    }
    calls = []

    class Response:
        status_code = 200

        def __init__(self, value):
            self.content = json.dumps(value).encode() if not isinstance(value, str) else value.encode()

    def get(url, timeout):
        calls.append((url, timeout))
        return Response(payloads[url])

    session = SimpleNamespace(name="SQ", api_path="/static/fallback/", event=event, year=2025)
    client = StaticArchiveClient(base_url="https://example.test", http_get=get)
    assert client.timing_data(session) == [["00:00:01:000", {}]]
    assert len(calls) == 3
    assert all(timeout == 15 for _, timeout in calls)
    calls.clear()
    assert client.timing_data(session) == [["00:00:01:000", {}]]
    assert calls == []


def test_static_archive_requires_a_session_path() -> None:
    class Response:
        status_code = 200
        content = json.dumps({"Meetings": []}).encode()

    session = SimpleNamespace(name="Practice 1", api_path=None,
                              event={"Location": "X"}, year=2025)
    client = StaticArchiveClient(
        base_url="https://example.test",
        http_get=lambda *_, **__: Response(),
    )
    with pytest.raises(SeparatorEstimationError, match="session path is missing"):
        client.timing_data(session)


def test_flat_archive_requires_unique_session() -> None:
    session = SimpleNamespace(name="SQ")
    row = {"SessionName": "Sprint_Shootout", "Path": "B/"}
    assert _find_session_path([row], session) == "B/"
    assert _find_session_path([row, dict(row, Path="A/")], session) is None


@pytest.mark.parametrize("name, expected", [
    (None, ""),
    (float("nan"), ""),
    ("Sprint_Shootout", "sprint qualifying"),
    ("sprint shootout", "sprint qualifying"),
    ("Unknown_Session", "unknown session"),
])
def test_session_key_normalises_archive_spellings(name, expected) -> None:
    assert _session_key(name) == expected


def test_grouped_archive_matches_official_event_names_and_lowercase_meetings() -> None:
    meetings = [{
        "Name": "Bahrain", "OfficialName": "Bahrain Grand Prix", "Location": "Sakhir",
        "Sessions": [{"Name": "Practice 1", "Path": "bahrain/"}],
    }]
    event = pd.Series({"Location": "Sakhir", "EventName": "Bahrain",
                       "OfficialEventName": "Bahrain Grand Prix"})
    assert _find_session_path(
        {"meetings": meetings}, SimpleNamespace(name="FP1", event=event)
    ) == "bahrain/"
    assert _find_session_path({"Meetings": meetings}, SimpleNamespace(
        name="Practice 1", event=pd.Series({"OfficialEventName": "Bahrain Grand Prix"})
    )) == "bahrain/"


def test_session_path_accepts_nested_and_flat_index_shapes() -> None:
    session = SimpleNamespace(name="Practice 1", event={"Location": "Sakhir"})
    meeting = {"Name": "Bahrain", "Location": "Sakhir",
               "Sessions": [{"Name": "Practice 1", "Path": "nested/"}]}
    assert _find_session_path({"Season": {"Meetings": [meeting]}}, session) == "nested/"
    # An unrelated empty ``Sessions`` key must not turn a flat index into meetings.
    flat = [{"SessionName": "Practice 1", "Path": "flat/", "Sessions": []}]
    assert _find_session_path(flat, session) == "flat/"
    # A session without its own path must not yield the meeting-level path.
    pathless = {"Name": "Bahrain", "Location": "Sakhir", "Path": "meeting/",
                "Sessions": [{"Name": "Practice 1"}]}
    assert _find_session_path({"Meetings": [pathless]}, session) is None
    # A matched meeting without sessions, or a mapping instead of a list, is unusable.
    assert _find_session_path({"Meetings": [{"Name": "Bahrain", "Location": "Sakhir"}]},
                              session) is None
    assert _find_session_path({"Meetings": {"A": meeting}}, session) is None


def test_meeting_lookup_prefers_event_name_over_shared_location() -> None:
    # The archive lists pre-season testing and the Bahrain GP at the same
    # location; the event name must select the race meeting.
    meetings = [
        {"Name": "Pre-Season Testing", "Location": "Sakhir",
         "Sessions": [{"Name": "Practice 1", "Path": "testing/"}]},
        {"Name": "Bahrain", "OfficialName": "Bahrain Grand Prix", "Location": "Sakhir",
         "Sessions": [{"Name": "Practice 1", "Path": "grand-prix/"}]},
    ]
    event = pd.Series({"Location": "Sakhir", "EventName": "Bahrain"})
    session = SimpleNamespace(name="Practice 1", event=event)
    assert _find_session_path({"Meetings": meetings}, session) == "grand-prix/"
    # With no distinguishing name, a shared location stays ambiguous.
    location_only = SimpleNamespace(name="Practice 1",
                                    event=pd.Series({"Location": "Sakhir"}))
    assert _find_session_path({"Meetings": meetings}, location_only) is None
    # Duplicate event names are disambiguated by location when possible.
    duplicate_names = meetings + [{"Name": "Bahrain", "Location": "Elsewhere",
                                   "Sessions": [{"Name": "Practice 1", "Path": "other/"}]}]
    assert _find_session_path({"Meetings": duplicate_names}, session) == "grand-prix/"


def test_grouped_archive_without_event_requires_unique_session() -> None:
    meetings = [
        {"Name": "A", "Sessions": [{"Name": "Practice 1", "Path": "a/"}]},
        {"Name": "B", "Sessions": [{"Name": "Qualifying", "Path": "b/"}]},
    ]
    session = SimpleNamespace(name="Qualifying", event=None)
    assert _find_session_path({"Meetings": meetings}, session) == "b/"
    assert _find_session_path({"Meetings": meetings + [
        {"Name": "C", "Sessions": [{"Name": "Qualifying", "Path": "c/"}]},
    ]}, session) is None
    assert _find_session_path(
        {"Meetings": meetings}, SimpleNamespace(name=None, event=None)
    ) is None


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


@pytest.mark.parametrize("value", [None, 12.0, object()])
def test_distance_lookup_rejects_non_iterable_samples(value):
    from f1_explorer.separator_estimator import _lookup_distance

    lookup = {("1", 1): {"SessionTime": value, "Distance": [0.0, 100.0]}}
    assert _lookup_distance(lookup, "1", 1, 5.0, {}) is None


@pytest.mark.parametrize("value", [
    float("nan"), float("inf"), 0.0, -5.0, None, 12.0, {}, {"sector": 1, "segment": 2},
])
def test_coerce_separator_boundary_rejects_non_positive_or_invalid_entries(value):
    assert coerce_separator_boundary(value) is None


def test_coerce_separator_boundary_accepts_instances_and_valid_mappings():
    boundary = SeparatorBoundary(120.5, 0, 2)
    assert coerce_separator_boundary(boundary) is boundary
    parsed = coerce_separator_boundary({"Distance": 120.5, "Sector": 0, "Segment": 2})
    assert parsed == boundary
    assert coerce_separator_boundary(
        {"distance": 3.0, "sector_index": 1, "segment_index": 4}) == SeparatorBoundary(3.0, 1, 4)


def test_optional_session_metadata_and_track_status():
    from f1_explorer.separator_estimator import _location, _year, affected_intervals_from_session

    session = SimpleNamespace(event=None, year=2026, laps=None, track_status=None)
    assert _location(session) == ""
    assert _year(session) == 2026
    assert build_distance_lookup(session) == ({}, None)
    assert affected_intervals_from_session(session) == []
    session.event = {"year": 2025, "Location": " Baku "}
    assert (_year(session), _location(session)) == (2025, "Baku")
    session.track_status = pd.DataFrame({"Time": pd.to_timedelta([20, 0, 10], unit="s"),
                                         "Status": ["1", "1", "4"]})
    assert affected_intervals_from_session(session) == [(10.0, 20.0)]
