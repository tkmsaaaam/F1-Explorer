from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch

import pandas

from f1_explorer.visualizations.comparison import _plot_driver_lap_telemetry


def _session_with_lap():
    car_data = SimpleNamespace(
        Distance=pandas.Series([0.0, 100.0]),
        Throttle=pandas.Series([50.0, 100.0]),
    )
    car_data.add_distance = lambda: car_data
    lap = SimpleNamespace(
        Driver="VER",
        DriverNumber="1",
        LapNumber=2,
        LapTime=pandas.to_timedelta(80, unit="s"),
        Team="Red Bull Racing",
        empty=False,
        get_car_data=lambda: car_data,
    )
    selection = MagicMock()
    selection.pick_fastest.return_value = lap
    laps = MagicMock()
    laps.pick_drivers.return_value = selection
    circuit = SimpleNamespace(corners=pandas.DataFrame({"Distance": []}))
    return SimpleNamespace(
        event=SimpleNamespace(year=2026, RoundNumber=1, Location="Test"),
        name="Qualifying",
        laps=laps,
        get_circuit_info=lambda: circuit,
    )


def test_measurement_axis_label_is_not_overwritten_by_series_label():
    session = _session_with_lap()
    fig = MagicMock()
    ax = MagicMock()

    with (
        patch("f1_explorer.visualizations.comparison.plt.subplots", return_value=(fig, ax)),
        patch("f1_explorer.visualizations.comparison.plt.tight_layout"),
        patch("f1_explorer.visualizations.comparison.fastf1.plotting.get_team_color", return_value="blue"),
        patch("f1_explorer.visualizations.comparison.save_matplotlib") as save,
    ):
        _plot_driver_lap_telemetry(
            session,
            MagicMock(),
            [[{"Driver": "VER", "Fastest": True}]],
            "throttle",
            "Throttle [%]",
            lambda data: data.Throttle,
        )

    ax.set_ylabel.assert_called_once_with("Throttle [%]")
    assert ax.plot.call_args.kwargs["label"].startswith("VER 2")
    save.assert_called_once()


def test_empty_comparison_closes_the_created_figure():
    session = _session_with_lap()
    fig = MagicMock()

    with (
        patch("f1_explorer.visualizations.comparison.plt.subplots", return_value=(fig, MagicMock())),
        patch("f1_explorer.visualizations.comparison.plt.close") as close,
    ):
        _plot_driver_lap_telemetry(
            session,
            MagicMock(),
            [[]],
            "throttle",
            "Throttle [%]",
            lambda data: data.Throttle,
        )

    close.assert_called_once_with(fig)


def test_yearly_gear_comparison_uses_previous_lap_and_both_ranges(tmp_path, monkeypatch):
    # Inline import keeps compare.py's plotly / fastf1.mvapi imports out of test collection;
    # resolves because tests run as `python -m pytest` from the repo root (AGENTS.md).
    import compare

    def _year_summary(driver, number, distances, gears):
        data = SimpleNamespace(
            Distance=pandas.Series(distances),
            nGear=pandas.Series(gears),
        )
        data.add_distance = lambda: data
        lap = SimpleNamespace(Driver=driver, DriverNumber=number, get_car_data=lambda: data)
        return compare.SessionSummary(lap, pandas.DataFrame())

    current = _year_summary("VER", "1", [0.0, 100.0], [4, 6])
    previous = _year_summary("HAM", "44", [0.0, 120.0], [2, 8])
    circuit = SimpleNamespace(corners=pandas.DataFrame({"Number": [1], "Distance": [50.0]}))
    comparison = compare.Comparison(2026, "Test", "Q", current, previous, circuit)
    fig, ax = MagicMock(), MagicMock()
    monkeypatch.chdir(tmp_path)
    with (
        patch("compare.plt.subplots", return_value=(fig, ax)),
        patch("compare.save_matplotlib") as save,
    ):
        compare.plot_n_gear_distance(MagicMock(), comparison)

    assert len(ax.plot.call_args_list) == 2
    for call, expected, label in zip(
        ax.plot.call_args_list,
        [current, previous],
        ["2026: VER", "2025: HAM"],
    ):
        data = expected.get_lap().get_car_data()
        pandas.testing.assert_series_equal(call.args[0], data.Distance)
        pandas.testing.assert_series_equal(call.args[1], data.nGear)
        assert call.kwargs["label"] == label
    assert ax.plot.call_args_list[0].kwargs["color"] == "#ff8000"  # team_color[2026].get(int("1"))
    assert ax.plot.call_args_list[1].kwargs["linestyle"] == "dashed"
    ax.set_ylim.assert_called_once_with(1.5, 8.5)
    assert ax.vlines.call_args.kwargs["ymin"] == 2
    assert ax.vlines.call_args.kwargs["ymax"] == 8
    save.assert_called_once_with(fig, "./images/comparison/Test/Q/gear_distance.png", ANY)


def _yearly_comparison():
    import compare

    def summary(driver, number, offset):
        data = SimpleNamespace(**{
            key: pandas.Series(values) + offset
            for key, values in {
                "Distance": [0, 100, 200], "Brake": [0, 1, 0], "nGear": [2, 5, 8],
                "RPM": [5000, 10000, 12000], "Speed": [100, 200, 300], "Throttle": [0, 50, 100],
            }.items()
        })
        data.add_distance = lambda: data
        lap = SimpleNamespace(
            Driver=driver, DriverNumber=number, get_car_data=lambda: data,
            telemetry=data, Compound="SOFT", TyreLife=3 + offset,
            **{key: pandas.to_timedelta(value + offset, unit="s") for key, value in
               {"LapTime": 90, "Sector1Time": 20, "Sector2Time": 30, "Sector3Time": 40}.items()},
            **{key: value + offset for key, value in
               {"SpeedFL": 250, "SpeedI1": 260, "SpeedI2": 270, "SpeedST": 280}.items()},
        )
        return compare.SessionSummary(lap, pandas.DataFrame({
            "AirTemp": [20 + offset, 25 + offset], "TrackTemp": [30 + offset, 40 + offset]}))

    return compare.Comparison(2026, "Test", "Q", summary("VER", "1", 0), summary("HAM", "44", 2),
                              SimpleNamespace(corners=pandas.DataFrame({"Number": [1], "Distance": [50.0]})))


def test_all_yearly_metrics_preserve_data_and_axes(tmp_path, monkeypatch):
    import compare
    monkeypatch.chdir(tmp_path)
    comparison = _yearly_comparison()
    for name, column, filename, pad, horizontal in [
        ("brake", "Brake", "brake", .1, None),
        ("n_gear", "nGear", "gear", .5, None),
        ("rpm", "RPM", "rpm", 500, None),
        ("speed", "Speed", "speed", 10, list(range(0, 302, 25))),
        ("throttle", "Throttle", "throttle", 5, list(range(10, 100, 10))),
    ]:
        fig, ax = MagicMock(), MagicMock()
        with patch("compare.plt.subplots", return_value=(fig, ax)), patch("compare.save_matplotlib") as save:
            getattr(compare, f"plot_{name}_distance")(MagicMock(), comparison)
        current = comparison.current.lap.get_car_data()
        previous = comparison.previous.lap.get_car_data()
        for call, data in zip(ax.plot.call_args_list, [current, previous]):
            pandas.testing.assert_series_equal(call.args[0], data.Distance)
            pandas.testing.assert_series_equal(call.args[1], getattr(data, column))
        # Pin the series styling: solid current with the team color, dashed black previous.
        solid, dashed = ax.plot.call_args_list
        assert solid.kwargs["linestyle"] == "solid"
        assert solid.kwargs["label"] == "2026: VER"
        assert dashed.kwargs["linestyle"] == "dashed"
        low, high = int(getattr(current, column).min()), int(getattr(previous, column).max())
        ax.set_ylim.assert_called_once_with(low - pad, high + pad)
        # Corner labels sit half a pad below the axis floor.
        assert ax.text.call_args.args[:2] == (50.0, low - pad / 2)
        if horizontal is None:
            ax.hlines.assert_not_called()
        else:
            assert ax.hlines.call_args.kwargs["y"] == horizontal
            assert ax.hlines.call_args.kwargs["xmax"] == 202
        save.assert_called_once_with(
            fig, f"./images/comparison/Test/Q/{filename}_distance.png", ANY)


def test_yearly_summary_values_and_colors(tmp_path, monkeypatch):
    import compare
    import matplotlib.pyplot as plt
    monkeypatch.chdir(tmp_path)
    before = set(plt.get_fignums())
    # Names describe the side shaded green under the legacy comparator
    # polarity, not raw speed: the "slower" current lap is green for times.
    offsets = {"slower": (0, 2), "faster": (2, 0), "equal": (0, 0)}
    for mode, (offset, other) in offsets.items():
        comparison = _yearly_comparison()
        if mode == "faster":
            comparison.current, comparison.previous = comparison.previous, comparison.current
        elif mode == "equal":
            comparison.previous = comparison.current
        with patch("compare.save_plotly") as save:
            compare.summary(MagicMock(), comparison)
        figure = save.call_args.args[0]
        table = figure.data[0]
        assert list(table.header.values) == ["", 2025, 2026]
        assert list(table.cells.values[0]) == [
            "LapTime(s)", "LapTime(%)", "Sector1Time(s)", "Sector1Time(%)",
            "Sector2Time(s)", "Sector2Time(%)", "Sector3Time(s)", "Sector3Time(%)",
            "SpeedFL", "SpeedI1", "SpeedI2", "SpeedST", "Max(Speed)", "Compound", "TyreLife",
            "Max(AirTemp)", "Min(AirTemp)", "Max(TrackTemp)", "Min(TrackTemp)",
        ]
        expected_current, expected_previous = [], []
        for seconds in (90, 20, 30, 40):
            expected_current.extend([seconds + offset, f"{(seconds + offset) / (seconds + other):.3f}"])
            expected_previous.extend([seconds + other, "-"])
        def tail(delta):
            return [250 + delta, 260 + delta, 270 + delta, 280 + delta, 300 + delta,
                    "SOFT", 3 + delta, 25 + delta, 20 + delta, 40 + delta, 30 + delta]

        assert list(table.cells.values[1]) == expected_previous + tail(other)
        assert list(table.cells.values[2]) == expected_current + tail(offset)
        green, white = "#d4edda", "white"
        current_colors = [green if offset > other else white] * 8 + [green if offset < other else white] * 5
        previous_colors = [white if offset > other else green] * 8 + [white if offset < other else green] * 5
        assert list(table.cells.fill.color[0]) == ["lightgray"] * 19
        assert list(table.cells.fill.color[1]) == current_colors + [white] * 6
        assert list(table.cells.fill.color[2]) == previous_colors + [white] * 6
        assert save.call_args.args[1] == "./images/comparison/Test/Q/summary.png"
        assert save.call_args.kwargs == {"width": 1920, "height": 1080}
    assert set(plt.get_fignums()) == before
