"""Tests for short-run track visualizations."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import pandas as pd
import numpy as np

from visualizations.short_runs import plot_speed_on_track
from visualizations.short_runs import (
    _gear_colorscale,
    _save_interactive_driver_telemetry,
    _save_interactive_track_map,
)


def test_summary_scatter_values_and_interactive_report(tmp_path):
    from visualizations import short_runs
    from visualizations.report import SessionReport

    telemetry = pd.DataFrame({
        "Throttle": [100, 100, 0], "Distance": [0, 50, 100],
        "Time": pd.to_timedelta([0, 1, 2], unit="s"), "Speed": [200, 300, 250],
    })
    lap = SimpleNamespace(Driver="VER", Team="Red Bull", TyreLife=3,
                          LapTime=pd.Timedelta(seconds=90), telemetry=telemetry,
                          get_car_data=lambda: telemetry)
    laps = MagicMock()
    laps.DriverNumber.unique.return_value = np.array(["1"])
    laps.__getitem__.return_value = laps
    laps.pick_drivers.return_value = laps
    laps.sort_values.return_value = laps
    laps.pick_fastest.return_value = lap
    laps.empty = False
    laps.__len__.return_value = 1
    laps.iloc = pd.DataFrame({
        "Sector1Time": [pd.Timedelta(seconds=29)],
        "Sector2Time": [pd.Timedelta(seconds=30)],
        "Sector3Time": [pd.Timedelta(seconds=30)],
    }).iloc
    laps.Driver = pd.Series(["VER"])
    laps.Team = pd.Series(["Red Bull"])
    session = SimpleNamespace(laps=laps, drivers=["1"], name="Qualifying",
                              event=SimpleNamespace(EventName="Test"))
    cases = [
        (short_runs.plot_speed_and_laptime, 300, 90),
        (short_runs.plot_tyre_age_and_laptime, 3, 90),
        (short_runs.plot_flat_out, 100, 100),
        (short_runs.plot_ideal_best, 90, 89),
        (short_runs.plot_ideal_best_diff, -1, 89),
    ]
    report = SessionReport(session, tmp_path / "images", report_dir=tmp_path / "reports")
    with (
        report,
        patch("visualizations.short_runs.fastf1.plotting.get_team_color", return_value="blue"),
        patch("plotly.graph_objects.Figure.write_image", autospec=True,
              side_effect=lambda figure, path, **kwargs: Path(path).touch()),
    ):
        for plot, x, y in cases:
            plot(session, MagicMock(), output_dir=tmp_path / "images")
            item = list(report._items.values())[-1]
            figure = json.loads(item.figure_json)
            assert figure["data"][0]["x"] == [x]
            assert figure["data"][0]["y"] == [y]
            assert "[" in figure["layout"]["xaxis"]["title"]["text"]
            assert "[" in figure["layout"]["yaxis"]["title"]["text"]
        html = report.write().read_text()
    assert html.count('class="plotly-container') == 5
    assert '<img ' not in html


def test_speed_on_track_uses_colored_line_collection_and_vertical_colorbar() -> None:
    telemetry = pd.DataFrame(
        {
            "X": [0.0, 10.0, 20.0],
            "Y": [0.0, 5.0, 0.0],
            "Speed": [100.0, 150.0, 120.0],
        }
    )
    lap = SimpleNamespace(
        Driver="VER",
        get_telemetry=lambda: telemetry,
    )
    selection = MagicMock()
    selection.pick_fastest.return_value = lap
    laps = MagicMock()
    laps.pick_drivers.return_value = selection
    session = SimpleNamespace(
        drivers=["1"],
        laps=laps,
        event=SimpleNamespace(year=2026, RoundNumber=1, Location="Test"),
        name="Qualifying",
    )

    with (
        patch("visualizations.short_runs.save_matplotlib") as save,
        patch("visualizations.short_runs.save_plotly") as save_plotly,
    ):
        plot_speed_on_track(session, MagicMock(), output_dir=Path("plots"))

    figure = save.call_args.args[0]
    try:
        assert any(isinstance(collection, LineCollection) for collection in figure.axes[0].collections)
        assert len(figure.axes) == 2
        assert figure.axes[1].get_ylabel() == "Speed"
    finally:
        plt.close(figure)
    interactive = save_plotly.call_args.args[0]
    assert [trace.name for trace in interactive.data] == ["VER"]
    assert interactive.layout.meta["f1ExplorerKind"] == "trackMap"
    assert save_plotly.call_args.args[1] == Path("plots/speed_on_track.png")


def test_interactive_shift_map_driver_dropdown_uses_session_speed_order() -> None:
    telemetry = pd.DataFrame(
        {
            "X": [0.0, 10.0, 20.0],
            "Y": [0.0, 5.0, 0.0],
            "nGear": [2, 4, 6],
        }
    )
    track_data = {
        "2": (SimpleNamespace(Driver="HAM"), telemetry),
        "1": (SimpleNamespace(Driver="VER"), telemetry),
    }

    class QuickLaps:
        empty = False
        DriverNumber = pd.Series(["1", "2"])

        def sort_values(self, by):
            return self

    session = SimpleNamespace(
        laps=SimpleNamespace(pick_quicklaps=lambda: QuickLaps()),
        event=SimpleNamespace(EventName="GP", year=2026),
        name="Qualifying",
    )

    with patch("visualizations.short_runs.save_plotly") as save:
        _save_interactive_track_map(
            session,
            MagicMock(),
            track_data,
            key="shift_on_track",
            value_key="nGear",
            value_label="Gear",
            colorscale=_gear_colorscale(),
            color_range=(0.5, 8.5),
            colorbar_ticks=list(range(1, 9)),
            output_dir=Path("plots"),
        )

    figure = save.call_args.args[0]
    assert [trace.name for trace in figure.data] == ["VER", "HAM"]
    assert [trace.visible for trace in figure.data] == [True, False]
    assert [button.label for button in figure.layout.updatemenus[0].buttons] == ["VER", "HAM"]
    assert save.call_args.args[1] == Path("plots/shift_on_track.png")


def test_interactive_driver_telemetry_is_ordered_by_fastest_session_lap() -> None:
    def make_car_data(offset: float):
        car_data = SimpleNamespace(
            Distance=pd.Series([0.0, 100.0]),
            Speed=pd.Series([200.0 + offset, 250.0 + offset]),
            Throttle=pd.Series([50.0, 100.0]),
            Brake=pd.Series([0.0, 1.0]),
        )
        car_data.add_distance = lambda: car_data
        return car_data

    laps_by_driver = {}
    for driver_number, driver_name, lap_time, offset in (
        ("1", "VER", 80.0, 0.0),
        ("2", "HAM", 82.0, 10.0),
    ):
        laps_by_driver[driver_number] = SimpleNamespace(
            Driver=driver_name,
            DriverNumber=driver_number,
            Team="Team",
            LapTime=pd.to_timedelta(lap_time, unit="s"),
            get_car_data=lambda offset=offset: make_car_data(offset),
        )

    class QuickLaps:
        empty = False
        DriverNumber = pd.Series(["1", "2"])

        def sort_values(self, by):
            return self

        def unique(self):
            return self.DriverNumber.unique()

    class Laps:
        def pick_quicklaps(self):
            return QuickLaps()

        def pick_drivers(self, driver_number):
            selection = MagicMock()
            selection.pick_fastest.return_value = laps_by_driver[str(driver_number)]
            return selection

    session = SimpleNamespace(
        laps=Laps(),
        event=SimpleNamespace(EventName="GP", year=2026),
        name="Practice 1",
        get_circuit_info=lambda: SimpleNamespace(corners=pd.DataFrame()),
    )

    with (
        patch("visualizations.short_runs.fastf1.plotting.get_team_color", return_value="blue"),
        patch("visualizations.short_runs.save_plotly") as save,
    ):
        _save_interactive_driver_telemetry(
            session,
            MagicMock(),
            key="throttle",
            label="Throttle [%]",
            value_func=lambda data: data.Throttle,
            title="Throttle",
            output_dir=Path("plots"),
        )

    figure = save.call_args.args[0]
    assert [trace.name for trace in figure.data] == ["VER", "HAM"]
    assert save.call_args.args[1] == Path("plots/throttle.png")
