import json
from collections.abc import Callable, Sequence
from operator import gt, lt
from typing import Any, NamedTuple

import fastf1
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import structlog
from fastf1.core import Lap, Session
from fastf1.mvapi import CircuitInfo
# noinspection PyPackageRequirements
from opentelemetry import trace
from pandas import DataFrame

from f1_explorer import constants
from f1_explorer import config as config_module
from f1_explorer.visualizations.output import save_matplotlib, save_plotly

tracer = trace.get_tracer(__name__)


def new(session: Session) -> SessionSummary:
    lap = session.laps.pick_fastest()
    if lap is None:
        raise Exception("Session is invalid")

    return SessionSummary(lap, session.weather_data)


class SessionSummary:
    def __init__(self, lap: Lap, weather: DataFrame):
        self.lap = lap
        self.weather = weather

    def get_lap(self) -> Lap:
        return self.lap

    def get_weather(self) -> Any:
        return self.weather


class Comparison:
    def __init__(self, year: int, gp: str, session: str, current: SessionSummary, previous: SessionSummary,
                 circuit: CircuitInfo):
        self.year = year
        self.gp = gp
        self.session = session
        self.current = current
        self.previous = previous
        self.corners: dict[int, float] = {row.Number: row.Distance for _, row in circuit.corners.iterrows()}

    def get_year(self) -> int:
        return self.year

    def get_previous_year(self) -> int:
        return self.year - 1

    def get_gp(self) -> str:
        return self.gp

    def get_session(self) -> str:
        return self.session

    def get_current(self) -> SessionSummary:
        return self.current

    def get_previous(self) -> SessionSummary:
        return self.previous

    def get_corners(self) -> dict[int, float]:
        return self.corners


def _plot_metric(log: structlog.stdlib.BoundLogger, comparison: Comparison, column: str, filename: str, *,
                 pad: float, hlines: Callable[[float], Sequence[float]] | None = None) -> None:
    """Plot one car-data column for both years with corner markers.

    ``pad`` sets the y-axis headroom and also offsets the corner labels
    below ``v_min`` by half the pad.  ``hlines`` receives ``v_max`` and
    returns the horizontal grid line positions when wanted.
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    current_car_data = comparison.get_current().get_lap().get_car_data().add_distance()
    current_values = getattr(current_car_data, column)
    ax.plot(current_car_data.Distance, current_values, linestyle='solid',
            label=f"{comparison.get_year()}: {comparison.get_current().get_lap().Driver}",
            color=constants.team_color.get(comparison.get_year(), {}).get(
                int(comparison.get_current().get_lap().DriverNumber), '#808080'))
    previous_car_data = comparison.get_previous().get_lap().get_car_data().add_distance()
    previous_values = getattr(previous_car_data, column)
    ax.plot(previous_car_data.Distance, previous_values, color='black', linestyle='dashed',
            label=f"{comparison.get_previous_year()}: {comparison.get_previous().get_lap().Driver}")
    v_min = min(int(previous_values.min()), int(current_values.min()))
    v_max = max(int(previous_values.max()), int(current_values.max()))
    ax.vlines(x=comparison.get_corners().values(), ymin=v_min, ymax=v_max, linestyles='dotted', colors='grey')
    if hlines is not None:
        ax.hlines(y=hlines(v_max), xmin=0, xmax=previous_car_data.Distance.max(), colors="lightgrey")
    label_pad = pad / 2
    for number, distance in comparison.get_corners().items():
        ax.text(distance, v_min - label_pad, f"{number}\n{"{:.0f}".format(distance)}", va='center_baseline', ha='center',
                size='x-small')

    ax.set_ylim(v_min - pad, v_max + pad)
    ax.legend(fontsize='small')
    ax.grid(True)
    save_matplotlib(fig, f"./images/comparison/{comparison.get_gp()}/{comparison.get_session()}/{filename}", log)


@tracer.start_as_current_span("plot_brake_distance")
def plot_brake_distance(log: structlog.stdlib.BoundLogger, comparison: Comparison):
    _plot_metric(log, comparison, "Brake", "brake_distance.png", pad=0.1)


@tracer.start_as_current_span("plot_n_gear_distance")
def plot_n_gear_distance(log: structlog.stdlib.BoundLogger, comparison: Comparison):
    _plot_metric(log, comparison, "nGear", "gear_distance.png", pad=0.5)


@tracer.start_as_current_span("plot_rpm_distance")
def plot_rpm_distance(log: structlog.stdlib.BoundLogger, comparison: Comparison):
    _plot_metric(log, comparison, "RPM", "rpm_distance.png", pad=500)


@tracer.start_as_current_span("plot_speed_distance")
def plot_speed_distance(log: structlog.stdlib.BoundLogger, comparison: Comparison):
    _plot_metric(log, comparison, "Speed", "speed_distance.png",
                 pad=10, hlines=lambda maximum: list(range(0, int(maximum), 25)))


@tracer.start_as_current_span("plot_throttle_distance")
def plot_throttle_distance(log: structlog.stdlib.BoundLogger, comparison: Comparison):
    _plot_metric(log, comparison, "Throttle", "throttle_distance.png",
                 pad=5, hlines=lambda maximum: list(range(10, 100, 10)))


class _SummaryMetric(NamedTuple):
    """One row of the yearly summary table.

    ``wins`` is evaluated as ``wins(current, previous)`` with the legacy
    polarity untouched: for lap and sector times ``gt`` shades the current
    cell green when its time is the greater one.  ``None`` keeps the row
    white, and ``ratio`` rows also emit a ``(%)`` row under the same colors.
    """
    name: str
    value: Callable[[SessionSummary], Any]
    wins: Callable[[Any, Any], bool] | None
    ratio: bool


_SUMMARY_METRICS = (
    _SummaryMetric("LapTime", lambda summary: summary.get_lap().LapTime, gt, True),
    _SummaryMetric("Sector1Time", lambda summary: summary.get_lap().Sector1Time, gt, True),
    _SummaryMetric("Sector2Time", lambda summary: summary.get_lap().Sector2Time, gt, True),
    _SummaryMetric("Sector3Time", lambda summary: summary.get_lap().Sector3Time, gt, True),
    _SummaryMetric("SpeedFL", lambda summary: summary.get_lap().SpeedFL, lt, False),
    _SummaryMetric("SpeedI1", lambda summary: summary.get_lap().SpeedI1, lt, False),
    _SummaryMetric("SpeedI2", lambda summary: summary.get_lap().SpeedI2, lt, False),
    _SummaryMetric("SpeedST", lambda summary: summary.get_lap().SpeedST, lt, False),
    _SummaryMetric("Max(Speed)", lambda summary: summary.get_lap().telemetry.Speed.max(), lt, False),
    _SummaryMetric("Compound", lambda summary: summary.get_lap().Compound, None, False),
    _SummaryMetric("TyreLife", lambda summary: summary.get_lap().TyreLife, None, False),
    _SummaryMetric("Max(AirTemp)", lambda summary: summary.get_weather().AirTemp.max(), None, False),
    _SummaryMetric("Min(AirTemp)", lambda summary: summary.get_weather().AirTemp.min(), None, False),
    _SummaryMetric("Max(TrackTemp)", lambda summary: summary.get_weather().TrackTemp.max(), None, False),
    _SummaryMetric("Min(TrackTemp)", lambda summary: summary.get_weather().TrackTemp.min(), None, False),
)


@tracer.start_as_current_span("summary")
def summary(log: structlog.stdlib.BoundLogger, comparison: Comparison):
    titles, title_colors = [], []
    c, p, c_colors, p_colors = [], [], [], []
    for metric in _SUMMARY_METRICS:
        current = metric.value(comparison.get_current())
        previous = metric.value(comparison.get_previous())
        titles.append(f"{metric.name}(s)" if metric.ratio else metric.name)
        c.append(current.total_seconds() if metric.ratio else current)
        p.append(previous.total_seconds() if metric.ratio else previous)
        title_colors.append("lightgray")
        if metric.wins is None:
            current_color = previous_color = "white"
        else:
            current_wins = metric.wins(current, previous)
            current_color = "#d4edda" if current_wins else "white"
            previous_color = "white" if current_wins else "#d4edda"
        c_colors.append(current_color)
        p_colors.append(previous_color)
        if metric.ratio:
            titles.append(f"{metric.name}(%)")
            c.append("{:.3f}".format(current.total_seconds() / previous.total_seconds()))
            p.append("-")
            c_colors.append(current_color)
            p_colors.append(previous_color)
            title_colors.append("lightgray")

    fig = go.Figure(
        data=[go.Table(
            header=go.table.Header(
                values=["", comparison.get_previous_year(), comparison.get_year()],
                fill=go.table.header.Fill(color='lightgrey'), align='center'),
            cells=go.table.Cells(
                values=[titles, p, c],
                fill=go.table.cells.Fill(color=[title_colors, c_colors, p_colors]),
                align='center'
            )
        )]
    )

    save_plotly(fig, f"./images/comparison/{comparison.get_gp()}/{comparison.get_session()}/summary.png",
                log, width=1920, height=1080)


@tracer.start_as_current_span("main")
def __main():
    log = config_module.log()
    with config_module.CONFIG_PATH.open(encoding='utf-8') as file:
        config = json.load(file)
    if config is None:
        raise Exception("Config must be provided")

    year = config['Year']
    race = config.get('RoundName')
    if not isinstance(race, str) or not race.strip():
        raise SystemExit("Set RoundName in config.json to the Grand Prix name used in both years.")
    session = config['Session']
    config_module.fast_f1()
    try:
        current = fastf1.get_session(year, race, session)
    except Exception as exception:
        log.warning('setup is failed', args=exception.args)
        return
    current.load(messages=False)
    try:
        current_summary = new(current)
    except Exception as exception:
        log.warning('setup is failed', args=exception.args)
        return

    try:
        previous = fastf1.get_session(year - 1, race, session)
    except Exception as exception:
        log.warning('setup is failed', args=exception.args)
        return
    previous.load(messages=False)
    try:
        previous_summary = new(previous)
    except Exception as exception:
        log.warning('setup is failed', args=exception.args)
        return

    log.info("Comparing sessions", race=race, session=session)

    circuit = current.get_circuit_info()
    if circuit is None:
        return

    comparison = Comparison(year, race, session, current_summary, previous_summary, circuit)
    summary(log, comparison)

    plot_brake_distance(log, comparison)
    plot_n_gear_distance(log, comparison)
    plot_rpm_distance(log, comparison)
    plot_speed_distance(log, comparison)
    plot_throttle_distance(log, comparison)


if __name__ == "__main__":
    __main()
