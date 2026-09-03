from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas
from fastf1.core import Laps

from visualizations.run_volume import (
    _laps_without_pit_laps,
    _make_interactive_laptime_by_lap_number,
    _make_interactive_laptime_by_timing,
    plot_laptime,
)


def _laps(driver_numbers: list[str], lap_numbers: list[int]) -> Laps:
    count = len(driver_numbers)
    return Laps(pandas.DataFrame({
        "DriverNumber": driver_numbers,
        "LapNumber": lap_numbers,
        "LapTime": pandas.to_timedelta([f"{80 + index}s" for index in range(count)]),
        "Driver": driver_numbers,
        "Compound": ["SOFT"] * count,
        "TyreLife": list(range(1, count + 1)),
        "Stint": [1] * count,
        "PitInTime": pandas.to_timedelta([None] * count),
        "PitOutTime": pandas.to_timedelta([None] * count),
        "LapStartTime": pandas.to_timedelta([f"{index * 90}s" for index in range(count)]),
        "LapStartDate": pandas.to_datetime([f"2026-08-23 13:{index:02d}:00" for index in range(count)]),
    }))


def test_qualifying_laptime_table_has_one_section_per_qualifying_period():
    q1 = _laps(["1", "16"], [1, 1])
    q2 = _laps(["1", "16"], [2, 2])
    q3 = _laps(["1"], [3])
    session_laps = MagicMock()
    session_laps.split_qualifying_sessions.return_value = [q1, q2, q3]
    abbreviations = {"1": "VER", "16": "LEC"}
    session = SimpleNamespace(
        name="Qualifying",
        drivers=["1", "16"],
        laps=session_laps,
        get_driver=lambda driver: SimpleNamespace(Abbreviation=abbreviations[str(driver)]),
    )

    with patch("visualizations.run_volume.save_plotly") as save:
        plot_laptime(session, MagicMock(), split_qualifying=True, output_dir="test-output")

    figure = save.call_args.args[0]
    assert len(figure.data) == 3
    assert [trace.header.values[0] for trace in figure.data] == ["Q1 Lap", "Q2 Lap", "Q3 Lap"]
    assert list(figure.data[2].header.values) == ["Q3 Lap", "VER"]


def test_sprint_qualifying_uses_sq_section_labels():
    q1 = _laps(["1"], [1])
    session_laps = MagicMock()
    session_laps.split_qualifying_sessions.return_value = [q1, q1, q1]
    session = SimpleNamespace(
        name="Sprint Qualifying",
        drivers=["1"],
        laps=session_laps,
        get_driver=lambda _: SimpleNamespace(Abbreviation="VER"),
    )

    with patch("visualizations.run_volume.save_plotly") as save:
        plot_laptime(session, MagicMock(), split_qualifying=True, output_dir="test-output")

    assert [trace.header.values[0] for trace in save.call_args.args[0].data] == ["SQ1 Lap", "SQ2 Lap", "SQ3 Lap"]


def test_qualifying_laptime_table_excludes_pit_laps_and_packs_remaining_laps():
    q1 = _laps(
        ["1"] * 6 + ["16"] * 6,
        [1, 2, 3, 4, 5, 6] * 2,
    )
    q1.loc[q1.index[[0, 4, 6, 10]], "PitOutTime"] = pandas.to_timedelta([10, 20, 30, 40], unit="s")
    q1.loc[q1.index[[3, 9]], "PitInTime"] = pandas.to_timedelta([250, 260], unit="s")
    q1.loc[q1.index[[4, 5, 10, 11]], "Stint"] = 2
    session_laps = MagicMock()
    session_laps.split_qualifying_sessions.return_value = [q1]
    abbreviations = {"1": "VER", "16": "LEC"}
    session = SimpleNamespace(
        name="Qualifying",
        drivers=["1", "16"],
        laps=session_laps,
        get_driver=lambda driver: SimpleNamespace(Abbreviation=abbreviations[str(driver)]),
    )

    with patch("visualizations.run_volume.save_plotly") as save:
        plot_laptime(session, MagicMock(), split_qualifying=True, output_dir="test-output")

    table = save.call_args.args[0].data[0]
    assert list(table.cells.values[0]) == ["1", "2", "3"]
    assert list(table.cells.values[1]) == ["81.0<br>(S1)", "82.0<br>(S1)", "85.0<br>(S2)"]
    assert list(table.cells.values[2]) == ["87.0<br>(S1)", "88.0<br>(S1)", "91.0<br>(S2)"]


def test_qualifying_laptime_by_timing_uses_table_laps_and_breaks_lines_between_stints():
    laps = _laps(["1"] * 6, [1, 2, 3, 4, 5, 6])
    laps.loc[laps.index[[0, 4]], "PitOutTime"] = pandas.to_timedelta([10, 20], unit="s")
    laps.loc[laps.index[3], "PitInTime"] = pandas.to_timedelta(250, unit="s")
    laps.loc[laps.index[[4, 5]], "Stint"] = 2
    session = SimpleNamespace(laps=laps, results=pandas.DataFrame())

    displayed_laps = _laps_without_pit_laps(laps)
    figure = _make_interactive_laptime_by_timing(session, displayed_laps)

    assert list(displayed_laps.LapNumber) == [2, 3, 6]
    assert list(figure.data[0].y) == [81.0, 82.0, None, 85.0]
    assert [row[0] for row in figure.data[0].customdata] == [2, 3, None, 6]


def _race_session(name: str) -> SimpleNamespace:
    starts = pandas.to_datetime([
        "2026-08-23 13:00:00",
        "2026-08-23 13:02:00",
        "2026-08-23 13:04:00",
        "2026-08-23 13:07:00",
        "2026-08-23 13:09:00",
    ])
    laps = Laps(pandas.DataFrame({
        "DriverNumber": ["1"] * 5,
        "Driver": ["VER"] * 5,
        "LapNumber": [1, 2, 3, 4, 5],
        "LapTime": pandas.to_timedelta([80, 90, 120, 85, 110], unit="s"),
        "Compound": ["MEDIUM"] * 5,
        "TyreLife": [1, 2, 3, 4, 5],
        "Stint": [1] * 5,
        "PitInTime": pandas.to_timedelta([None, None, None, None, 780], unit="s"),
        "PitOutTime": pandas.to_timedelta([None] * 5, unit="s"),
        "TrackStatus": ["1", "1", "2", "1", "1"],
        "IsAccurate": [True] * 5,
        "Deleted": [False] * 5,
        "FastF1Generated": [False] * 5,
        "LapStartDate": starts,
        "LapStartTime": pandas.to_timedelta([0, 120, 240, 420, 540], unit="s"),
    }))
    messages = pandas.DataFrame({
        "Time": pandas.to_datetime(["2026-08-23 13:02:30"]),
        "Flag": ["BLUE"],
        "Scope": ["Driver"],
        "RacingNumber": ["1"],
    })
    return SimpleNamespace(
        name=name,
        laps=laps,
        race_control_messages=messages,
        t0_date=pandas.Timestamp("2026-08-23 13:00:00"),
        results=pandas.DataFrame({"DriverNumber": ["1"], "Position": [1]}),
    )


def test_race_and_sprint_interactive_laptime_range_uses_narrower_window():
    for name in ("Race", "Sprint"):
        figure = _make_interactive_laptime_by_lap_number(_race_session(name))

        assert list(figure.layout.yaxis.range) == [94.5, 79.5]
        assert figure.layout.yaxis.autorange is False
        # Laps outside the initial window remain available for zooming out.
        assert list(figure.data[0].y) == [80.0, 90.0, 120.0, 85.0, 110.0]


def test_race_interactive_laptime_range_can_use_laptime_graph_window():
    session = _race_session("Race")
    session.laps.loc[session.laps.index[4], "IsAccurate"] = False

    figure = _make_interactive_laptime_by_lap_number(session)

    assert list(figure.layout.yaxis.range) == [90.1, 79.9]


def test_non_race_interactive_laptime_range_keeps_full_autorange():
    figure = _make_interactive_laptime_by_lap_number(_race_session("Qualifying"))

    assert figure.layout.yaxis.range is None
    assert figure.layout.yaxis.autorange == "reversed"
