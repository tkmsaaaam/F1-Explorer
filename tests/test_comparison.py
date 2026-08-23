from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas

from visualizations.comparison import _plot_driver_lap_telemetry


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
        patch("visualizations.comparison.plt.subplots", return_value=(fig, ax)),
        patch("visualizations.comparison.plt.tight_layout"),
        patch("visualizations.comparison.fastf1.plotting.get_team_color", return_value="blue"),
        patch("visualizations.comparison.save_matplotlib") as save,
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
        patch("visualizations.comparison.plt.subplots", return_value=(fig, MagicMock())),
        patch("visualizations.comparison.plt.close") as close,
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
