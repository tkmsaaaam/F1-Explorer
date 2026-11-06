from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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
        patch("compare.plt.close"),
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
    fig.savefig.assert_called_once_with(
        "./images/comparison/Test/Q/gear_distance.png", bbox_inches="tight"
    )
