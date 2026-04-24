import json
import os
from logging import Logger
from typing import Any

import fastf1
from fastf1.core import Lap
from matplotlib import pyplot as plt
from opentelemetry import trace
from pandas.core.interchange.dataframe_protocol import DataFrame
from plotly import graph_objects

import constants
import setup

tracer = trace.get_tracer(__name__)


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
                 corners: DataFrame):
        self.year = year
        self.gp = gp
        self.session = session
        self.current = current
        self.previous = previous
        self.corners = corners

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

    def get_corners(self) -> DataFrame:
        return self.corners


@tracer.start_as_current_span("plot_brake_distance")
def plot_brake_distance(log: Logger, comparison: Comparison):
    """brakeを比較
    Args:
        comparison: Comparison
        log: ロガー
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    current_car_data = comparison.get_current().get_lap().get_car_data().add_distance()
    ax.plot(current_car_data.Distance, current_car_data.Brake, linestyle='solid',
            label=f"{comparison.get_year()}: {comparison.get_current().get_lap().Driver}",
            color=constants.team_color[comparison.get_year()].get(
                int(comparison.get_current().get_lap().DriverNumber), '#808080'))
    previous_car_data = comparison.get_previous().get_lap().get_car_data().add_distance()
    ax.plot(previous_car_data.Distance, previous_car_data.Brake, color='black', linestyle='dashed',
            label=f"{comparison.get_previous_year()}: {comparison.get_previous().get_lap().Driver}")
    v_min = min(int(previous_car_data.Brake.min()), int(current_car_data.Brake.min()))
    v_max = max(int(previous_car_data.Brake.max()), int(current_car_data.Brake.max()))
    ax.vlines(x=comparison.get_corners().Distance, ymin=v_min, ymax=v_max, linestyles='dotted', colors='grey')
    for _, corner in comparison.get_corners().iterrows():
        txt = f"{corner.Number}{corner.Letter}"
        ax.text(corner.Distance, v_min - 0.05, txt, va='center_baseline', ha='center', size='small')

    ax.set_ylim(v_min - 0.1, v_max + 0.1)
    ax.legend(fontsize='small')
    ax.grid(True)
    output_path = f"./images/comparison/{comparison.get_gp()}/{comparison.get_session()}/brake_distance.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)


@tracer.start_as_current_span("plot_n_gear_distance")
def plot_n_gear_distance(log: Logger, comparison: Comparison):
    """nGearを比較
    Args:
        comparison: Comparison
        log: ロガー
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    current_car_data = comparison.get_current().get_lap().get_car_data().add_distance()
    ax.plot(current_car_data.Distance, current_car_data.nGear, linestyle='solid',
            label=f"{comparison.get_year()}: {comparison.get_current().get_lap().Driver}",
            color=constants.team_color[comparison.get_year()].get(
                int(comparison.get_current().get_lap().DriverNumber), '#808080'))
    previous_car_data = comparison.get_current().get_lap().get_car_data().add_distance()
    ax.plot(previous_car_data.Distance, previous_car_data.nGear, color='black', linestyle='dashed',
            label=f"{comparison.get_previous_year()}: {comparison.get_previous().get_lap().Driver}")
    v_min = min(int(previous_car_data.nGear.min()), int(current_car_data.nGear.min()))
    v_max = max(int(previous_car_data.nGear.max()), int(current_car_data.nGear.max()))
    ax.vlines(x=comparison.get_corners().Distance, ymin=v_min, ymax=v_max, linestyles='dotted', colors='grey')
    for _, corner in comparison.get_corners().iterrows():
        txt = f"{corner.Number}{corner.Letter}"
        ax.text(corner.Distance, v_min - 0.25, txt, va='center_baseline', ha='center', size='small')

    ax.set_ylim(v_min - 0.5, v_max + 0.5)
    ax.legend(fontsize='small')
    ax.grid(True)
    output_path = f"./images/comparison/{comparison.get_gp()}/{comparison.get_session()}/gear_distance.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)


@tracer.start_as_current_span("plot_rpm_distance")
def plot_rpm_distance(log: Logger, comparison: Comparison):
    """RPMを比較
    Args:
        comparison: Comparison
        log: ロガー
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    current_car_data = comparison.get_current().get_lap().get_car_data().add_distance()
    ax.plot(current_car_data.Distance, current_car_data.RPM, linestyle='solid',
            label=f"{comparison.get_year()}: {comparison.get_current().get_lap().Driver}",
            color=constants.team_color[comparison.get_year()].get(
                int(comparison.get_current().get_lap().DriverNumber), '#808080'))
    previous_car_data = comparison.get_previous().get_lap().get_car_data().add_distance()
    ax.plot(previous_car_data.Distance, previous_car_data.RPM, color='black', linestyle='dashed',
            label=f"{comparison.get_previous_year()}: {comparison.get_previous().get_lap().Driver}")
    v_min = min(int(previous_car_data.RPM.min()), int(current_car_data.RPM.min()))
    v_max = max(int(previous_car_data.RPM.max()), int(current_car_data.RPM.max()))
    ax.vlines(x=comparison.get_corners().Distance, ymin=v_min, ymax=v_max, linestyles='dotted', colors='grey')

    for _, corner in comparison.get_corners().iterrows():
        txt = f"{corner.Number}{corner.Letter}"
        ax.text(corner.Distance, v_min - 250, txt, va='center_baseline', ha='center', size='small')

    ax.set_ylim(v_min - 500, v_max + 500)
    ax.legend(fontsize='small')
    ax.grid(True)
    output_path = f"./images/comparison/{comparison.get_gp()}/{comparison.get_session()}/rpm_distance.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)


@tracer.start_as_current_span("plot_speed_distance")
def plot_speed_distance(log: Logger, comparison: Comparison):
    """スピードを比較
    Args:
        comparison: Comparison
        log: ロガー
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    current_car_data = comparison.get_current().get_lap().get_car_data().add_distance()
    ax.plot(current_car_data.Distance, current_car_data.Speed, linestyle='solid',
            label=f"{comparison.get_year()}: {comparison.get_current().get_lap().Driver}",
            color=constants.team_color[comparison.get_year()].get(
                int(comparison.get_current().get_lap().DriverNumber), '#808080'))
    previous_car_data = comparison.get_previous().get_lap().get_car_data().add_distance()
    ax.plot(previous_car_data.Distance, previous_car_data.Speed, linestyle='dashed', color='black',
            label=f"{comparison.get_previous_year()}: {comparison.get_previous().get_lap().Driver}")
    v_min = min(int(previous_car_data.Speed.min()), int(current_car_data.Speed.min()))
    v_max = max(int(previous_car_data.Speed.max()), int(current_car_data.Speed.max()))
    ax.vlines(x=comparison.get_corners().Distance, ymin=v_min, ymax=v_max, linestyles='dotted', colors='grey')
    ax.hlines(y=list(range(0, int(v_max), 25)), xmin=0, xmax=previous_car_data.Distance.max(), colors='lightgrey')
    for _, corner in comparison.get_corners().iterrows():
        txt = f"{corner.Number}{corner.Letter}"
        ax.text(corner.Distance, v_min - 5, txt, va='center_baseline', ha='center', size='small')
    ax.set_ylim(v_min - 10, v_max + 10)
    ax.legend(fontsize='small')
    ax.grid(True)
    output_path = f"./images/comparison/{comparison.get_gp()}/{comparison.get_session()}/speed_distance.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)


@tracer.start_as_current_span("plot_throttle_distance")
def plot_throttle_distance(log: Logger, comparison: Comparison):
    """throttleを比較
    Args:
        comparison: Comparison
        log: ロガー
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    current_car_data = comparison.get_current().get_lap().get_car_data().add_distance()
    ax.plot(current_car_data.Distance, current_car_data.Throttle, linestyle='solid',
            label=f"{comparison.get_year()}: {comparison.get_current().get_lap().Driver}",
            color=constants.team_color[comparison.get_year()].get(
                int(comparison.get_current().get_lap().DriverNumber), '#808080'))
    previous_car_data = comparison.get_previous().get_lap().get_car_data().add_distance()
    ax.plot(previous_car_data.Distance, previous_car_data.Throttle, linestyle='dashed', color='black',
            label=f"{comparison.get_previous_year()}: {comparison.get_previous().get_lap().Driver}")
    v_min = min(int(previous_car_data.Throttle.min()), int(current_car_data.Throttle.min()))
    v_max = max(int(previous_car_data.Throttle.max()), int(current_car_data.Throttle.max()))
    ax.vlines(x=comparison.get_corners().Distance, ymin=v_min, ymax=v_max, linestyles='dotted', colors='grey')
    ax.hlines(y=[10, 20, 30, 40, 50, 60, 70, 80, 90], xmin=0, xmax=previous_car_data.Distance.max(), colors='lightgrey')
    for _, corner in comparison.get_corners().iterrows():
        txt = f"{corner.Number}{corner.Letter}"
        ax.text(corner.Distance, v_min - 2.5, txt, va='center_baseline', ha='center', size='small')
    ax.set_ylim(v_min - 5, v_max + 5)
    ax.legend(fontsize='small')
    ax.grid(True)
    output_path = f"./images/comparison/{comparison.get_gp()}/{comparison.get_session()}/throttle_distance.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)


@tracer.start_as_current_span("summary")
def summary(log: Logger, comparison: Comparison):
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    current_car_data = comparison.get_current().get_lap().get_car_data().add_distance()
    ax.plot(current_car_data.Distance, current_car_data.Throttle, linestyle='solid',
            label=f"{comparison.get_year()}: {comparison.get_current().get_lap().Driver}",
            color=constants.team_color[comparison.get_year()].get(
                int(comparison.get_current().get_lap().DriverNumber), '#808080'))
    titles = []
    title_colors = []
    c = []
    c_colors = []
    p = []
    p_colors = []

    titles.append("LapTime(s)")
    c.append(comparison.get_current().get_lap().LapTime.total_seconds())
    p.append(comparison.get_previous().get_lap().LapTime.total_seconds())
    title_colors.append("lightgray")
    c_win = comparison.get_current().get_lap().LapTime > comparison.get_previous().get_lap().LapTime
    c_colors.append("#d4edda" if c_win else "white")
    p_colors.append("#d4edda" if not c_win else "white")
    titles.append("LapTime(%)")
    c.append("{:.3f}".format(
        comparison.get_current().get_lap().LapTime.total_seconds() / comparison.get_previous().get_lap().LapTime.total_seconds()))
    p.append(1)
    c_win = comparison.get_current().get_lap().LapTime > comparison.get_previous().get_lap().LapTime
    c_colors.append("#d4edda" if c_win else "white")
    p_colors.append("#d4edda" if not c_win else "white")

    titles.append("Sector1Time(s)")
    c.append(comparison.get_current().get_lap().Sector1Time.total_seconds())
    p.append(comparison.get_previous().get_lap().Sector1Time.total_seconds())
    title_colors.append("lightgray")
    c_win = comparison.get_current().get_lap().Sector1Time > comparison.get_previous().get_lap().Sector1Time
    c_colors.append("#d4edda" if c_win else "white")
    p_colors.append("#d4edda" if not c_win else "white")
    titles.append("Sector1Time(%)")
    c.append("{:.3f}".format(
        comparison.get_current().get_lap().Sector1Time.total_seconds() / comparison.get_previous().get_lap().Sector1Time.total_seconds()))
    p.append(1)
    c_win = comparison.get_current().get_lap().Sector1Time > comparison.get_previous().get_lap().Sector1Time
    c_colors.append("#d4edda" if c_win else "white")
    p_colors.append("#d4edda" if not c_win else "white")

    titles.append("Sector2Time(s)")
    c.append(comparison.get_current().get_lap().Sector2Time.total_seconds())
    p.append(comparison.get_previous().get_lap().Sector2Time.total_seconds())
    title_colors.append("lightgray")
    c_win = comparison.get_current().get_lap().Sector2Time > comparison.get_previous().get_lap().Sector2Time
    c_colors.append("#d4edda" if c_win else "white")
    p_colors.append("#d4edda" if not c_win else "white")
    titles.append("Sector2Time(%)")
    c.append("{:.3f}".format(
        comparison.get_current().get_lap().Sector2Time.total_seconds() / comparison.get_previous().get_lap().Sector2Time.total_seconds()))
    p.append(1)
    c_win = comparison.get_current().get_lap().Sector2Time > comparison.get_previous().get_lap().Sector2Time
    c_colors.append("#d4edda" if c_win else "white")
    p_colors.append("#d4edda" if not c_win else "white")

    titles.append("Sector3Time(s)")
    c.append(comparison.get_current().get_lap().Sector3Time.total_seconds())
    p.append(comparison.get_previous().get_lap().Sector3Time.total_seconds())
    title_colors.append("lightgray")
    c_win = comparison.get_current().get_lap().Sector3Time > comparison.get_previous().get_lap().Sector3Time
    c_colors.append("#d4edda" if c_win else "white")
    p_colors.append("#d4edda" if not c_win else "white")
    titles.append("Sector3Time(%)")
    c.append("{:.3f}".format(
        comparison.get_current().get_lap().Sector3Time.total_seconds() / comparison.get_previous().get_lap().Sector3Time.total_seconds()))
    p.append(1)
    c_win = comparison.get_current().get_lap().Sector3Time > comparison.get_previous().get_lap().Sector3Time
    c_colors.append("#d4edda" if c_win else "white")
    p_colors.append("#d4edda" if not c_win else "white")

    titles.append("SpeedFL")
    c.append(comparison.get_current().get_lap().SpeedFL)
    p.append(comparison.get_previous().get_lap().SpeedFL)
    title_colors.append("lightgray")
    c_win = comparison.get_current().get_lap().SpeedFL < comparison.get_previous().get_lap().SpeedFL
    c_colors.append("#d4edda" if c_win else "white")
    p_colors.append("#d4edda" if not c_win else "white")

    titles.append("SpeedI1")
    c.append(comparison.get_current().get_lap().SpeedI1)
    p.append(comparison.get_previous().get_lap().SpeedI1)
    title_colors.append("lightgray")
    c_win = comparison.get_current().get_lap().SpeedI1 < comparison.get_previous().get_lap().SpeedI1
    c_colors.append("#d4edda" if c_win else "white")
    p_colors.append("#d4edda" if not c_win else "white")

    titles.append("SpeedI2")
    c.append(comparison.get_current().get_lap().SpeedI2)
    p.append(comparison.get_previous().get_lap().SpeedI2)
    title_colors.append("lightgray")
    c_win = comparison.get_current().get_lap().SpeedI2 < comparison.get_previous().get_lap().SpeedI2
    c_colors.append("#d4edda" if c_win else "white")
    p_colors.append("#d4edda" if not c_win else "white")

    titles.append("SpeedST")
    c.append(comparison.get_current().get_lap().SpeedST)
    p.append(comparison.get_previous().get_lap().SpeedST)
    title_colors.append("lightgray")
    c_win = comparison.get_current().get_lap().SpeedST < comparison.get_previous().get_lap().SpeedST
    c_colors.append("#d4edda" if c_win else "white")
    p_colors.append("#d4edda" if not c_win else "white")

    titles.append("Max(Speed)")
    c.append(comparison.get_current().get_lap().telemetry.Speed.max())
    p.append(comparison.get_previous().get_lap().telemetry.Speed.max())
    title_colors.append("lightgray")
    c_win = comparison.get_current().get_lap().telemetry.Speed.max() < comparison.get_previous().get_lap().telemetry.Speed.max()
    c_colors.append("#d4edda" if c_win else "white")
    p_colors.append("#d4edda" if not c_win else "white")

    titles.append("Compound")
    c.append(comparison.get_current().get_lap().Compound)
    p.append(comparison.get_previous().get_lap().Compound)
    title_colors.append("lightgray")
    c_colors.append("white")
    p_colors.append("white")

    titles.append("TyreLife")
    c.append(comparison.get_current().get_lap().TyreLife)
    p.append(comparison.get_previous().get_lap().TyreLife)
    title_colors.append("lightgray")
    c_colors.append("white")
    p_colors.append("white")

    titles.append("Max(AirTemp)")
    c.append(comparison.get_current().get_weather().AirTemp.max())
    p.append(comparison.get_previous().get_weather().AirTemp.max())
    title_colors.append("lightgray")
    c_colors.append("white")
    p_colors.append("white")

    titles.append("Min(AirTemp)")
    c.append(comparison.get_current().get_weather().AirTemp.min())
    p.append(comparison.get_previous().get_weather().AirTemp.min())
    title_colors.append("lightgray")
    c_colors.append("white")
    p_colors.append("white")

    titles.append("Max(TrackTemp)")
    c.append(comparison.get_current().get_weather().TrackTemp.max())
    p.append(comparison.get_previous().get_weather().TrackTemp.max())
    title_colors.append("lightgray")
    c_colors.append("white")
    p_colors.append("white")

    titles.append("Min(TrackTemp)")
    c.append(comparison.get_current().get_weather().TrackTemp.min())
    p.append(comparison.get_previous().get_weather().TrackTemp.min())
    title_colors.append("lightgray")
    c_colors.append("white")
    p_colors.append("white")

    fig = graph_objects.Figure(data=[graph_objects.Table(
        header={'values': ["", comparison.get_previous_year(), comparison.get_year()],
                'fill_color': 'lightgrey', 'align': 'center'},
        cells={'values': [titles, p, c], 'fill_color': [title_colors, c_colors, p_colors], 'align': 'center'}
    )])

    output_path = f"./images/comparison/{comparison.get_gp()}/{comparison.get_session()}/summary.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.write_image(output_path, width=1920, height=1080)
    log.info(f"Saved plot to {output_path}")


@tracer.start_as_current_span("main")
def __main():
    log = setup.log()
    config = None
    with open('./config.json', 'r', encoding='utf-8') as file:
        config = json.load(file)
    if config is None:
        raise Exception("Config must be provided")

    setup.fast_f1()

    year = config['Year']
    round = config['RoundName']
    session = config['Session']
    try:
        current = fastf1.get_session(year, round, session)
    except Exception as exception:
        log.warning(exception.args)
        return
    current.load(messages=False)
    try:
        previous = fastf1.get_session(year - 1, round, session)
    except Exception as exception:
        log.warning(exception.args)
        return
    previous.load(messages=False)
    log.info(f"{round} {session}")

    current_lap = current.laps.pick_fastest()
    if current_lap is None:
        return
    previous_lap = previous.laps.pick_fastest()
    if previous_lap is None:
        return

    comparison = Comparison(year, round, session, SessionSummary(current_lap, current.weather_data),
                            SessionSummary(previous_lap, previous.weather_data), current.get_circuit_info().corners)
    summary(log, comparison)

    plot_brake_distance(log, comparison)
    plot_n_gear_distance(log, comparison)
    plot_rpm_distance(log, comparison)
    plot_speed_distance(log, comparison)
    plot_throttle_distance(log, comparison)


if __name__ == "__main__":
    __main()
