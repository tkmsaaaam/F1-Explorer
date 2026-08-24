from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas
from fastf1.core import Laps

from visualizations.run_volume import plot_laptime


def _laps(driver_numbers: list[str], lap_numbers: list[int]) -> Laps:
    count = len(driver_numbers)
    return Laps(pandas.DataFrame({
        "DriverNumber": driver_numbers,
        "LapNumber": lap_numbers,
        "LapTime": pandas.to_timedelta([f"{80 + index}s" for index in range(count)]),
        "Compound": ["SOFT"] * count,
        "PitInTime": [pandas.NaT] * count,
        "PitOutTime": [pandas.NaT] * count,
        "LapStartTime": pandas.to_timedelta([f"{index * 90}s" for index in range(count)]),
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
