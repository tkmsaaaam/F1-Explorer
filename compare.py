import json
import os
from logging import Logger

import fastf1
from fastf1.core import Session
from matplotlib import pyplot as plt
from opentelemetry import trace
from plotly import graph_objects

import constants
import setup

tracer = trace.get_tracer(__name__)


@tracer.start_as_current_span("plot_brake_distance")
def plot_brake_distance(log: Logger, current: Session, previous: Session, gp: str, session: str):
    """brakeを比較
    Args:
        current: 2026 Session
        previous: 2025 Session
        session: session
        gp: Grand Prix name
        log: ロガー
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    current_lap = current.laps.pick_fastest()
    circuit_info = current.get_circuit_info()
    if current_lap is None:
        return
    current_car_data = current_lap.get_car_data().add_distance()
    ax.plot(current_car_data.Distance, current_car_data.Brake, label=f"2026: {current_lap.Driver}", linestyle="solid",
            color=constants.team_color[2026].get(int(current_lap.DriverNumber), '#808080'))
    previous_lap = previous.laps.pick_fastest()
    if previous_lap is None:
        return
    previous_car_data = previous_lap.get_car_data().add_distance()
    ax.plot(previous_car_data.Distance, previous_car_data.Brake, label=f"2025: {previous_lap.Driver}",
            linestyle="dashed", color=constants.team_color[2025].get(int(previous_lap.DriverNumber), '#808080'))

    v_min = min(previous_car_data.Brake.min(), current_car_data.Brake.min())
    v_max = max(previous_car_data.Brake.max(), current_car_data.Brake.max())
    ax.vlines(x=circuit_info.corners.Distance, ymin=v_min, ymax=v_max, linestyles='dotted', colors='grey')

    for _, corner in circuit_info.corners.iterrows():
        txt = f"{corner.Number}{corner.Letter}"
        ax.text(corner.Distance, v_min - 0.05, txt, va='center_baseline', ha='center', size='small')

    ax.set_ylim(v_min - 0.1, v_max + 0.1)
    ax.legend(fontsize='small')
    ax.grid(True)
    output_path = f"./images/comparison/{gp}/{session}/brake_distance.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)


@tracer.start_as_current_span("plot_n_gear_distance")
def plot_n_gear_distance(log: Logger, current: Session, previous: Session, gp: str, session: str):
    """nGearを比較
    Args:
        current: 2026 Session
        previous: 2025 Session
        session: session
        gp: Grand Prix name
        log: ロガー
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    current_lap = current.laps.pick_fastest()
    circuit_info = current.get_circuit_info()
    if current_lap is None:
        return
    current_car_data = current_lap.get_car_data().add_distance()
    ax.plot(current_car_data.Distance, current_car_data.nGear, label=f"2026: {current_lap.Driver}",
            linestyle="solid",
            color=constants.team_color[2026].get(int(current_lap.DriverNumber), '#808080'))
    previous_lap = previous.laps.pick_fastest()
    if previous_lap is None:
        return
    previous_car_data = previous_lap.get_car_data().add_distance()
    ax.plot(previous_car_data.Distance, previous_car_data.nGear, label=f"2025: {previous_lap.Driver}",
            linestyle="dashed", color=constants.team_color[2025].get(int(previous_lap.DriverNumber), '#808080'))

    v_min = min(previous_car_data.nGear.min(), current_car_data.nGear.min())
    v_max = max(previous_car_data.nGear.max(), current_car_data.nGear.max())
    ax.vlines(x=circuit_info.corners.Distance, ymin=v_min, ymax=v_max, linestyles='dotted', colors='grey')

    for _, corner in circuit_info.corners.iterrows():
        txt = f"{corner.Number}{corner.Letter}"
        ax.text(corner.Distance, v_min - 0.25, txt, va='center_baseline', ha='center', size='small')

    ax.set_ylim(v_min - 0.5, v_max + 0.5)
    ax.legend(fontsize='small')
    ax.grid(True)
    output_path = f"./images/comparison/{gp}/{session}/gear_distance.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)


@tracer.start_as_current_span("plot_rpm_distance")
def plot_rpm_distance(log: Logger, current: Session, previous: Session, gp: str, session: str):
    """RPMを比較
    Args:
        current: 2026 Session
        previous: 2025 Session
        session: session
        gp: Grand Prix name
        log: ロガー
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    current_lap = current.laps.pick_fastest()
    circuit_info = current.get_circuit_info()
    if current_lap is None:
        return
    current_car_data = current_lap.get_car_data().add_distance()
    ax.plot(current_car_data.Distance, current_car_data.RPM, label=f"2026: {current_lap.Driver}",
            linestyle="solid",
            color=constants.team_color[2026].get(int(current_lap.DriverNumber), '#808080'))
    previous_lap = previous.laps.pick_fastest()
    if previous_lap is None:
        return
    previous_car_data = previous_lap.get_car_data().add_distance()
    ax.plot(previous_car_data.Distance, previous_car_data.RPM, label=f"2025: {previous_lap.Driver}",
            linestyle="dashed", color=constants.team_color[2025].get(int(previous_lap.DriverNumber), '#808080'))

    v_min = min(previous_car_data.RPM.min(), current_car_data.RPM.min())
    v_max = max(previous_car_data.RPM.max(), current_car_data.RPM.max())
    ax.vlines(x=circuit_info.corners.Distance, ymin=v_min, ymax=v_max, linestyles='dotted', colors='grey')

    for _, corner in circuit_info.corners.iterrows():
        txt = f"{corner.Number}{corner.Letter}"
        ax.text(corner.Distance, v_min - 250, txt, va='center_baseline', ha='center', size='small')

    ax.set_ylim(v_min - 500, v_max + 500)
    ax.legend(fontsize='small')
    ax.grid(True)
    output_path = f"./images/comparison/{gp}/{session}/rpm_distance.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)


@tracer.start_as_current_span("plot_speed_distance")
def plot_speed_distance(log: Logger, current: Session, previous: Session, gp: str, session: str):
    """スピードを比較
    Args:
        current: 2026 Session
        previous: 2025 Session
        session: session
        gp: Grand Prix name
        log: ロガー
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    current_lap = current.laps.pick_fastest()
    circuit_info = current.get_circuit_info()
    if current_lap is None:
        return
    current_car_data = current_lap.get_car_data().add_distance()
    ax.plot(current_car_data.Distance, current_car_data.Speed, label=f"2026: {current_lap.Driver}", linestyle="solid",
            color=constants.team_color[2026].get(int(current_lap.DriverNumber), '#808080'))
    previous_lap = previous.laps.pick_fastest()
    if previous_lap is None:
        return
    previous_car_data = previous_lap.get_car_data().add_distance()
    ax.plot(previous_car_data.Distance, previous_car_data.Speed, label=f"2025: {previous_lap.Driver}",
            linestyle="dashed", color=constants.team_color[2025].get(int(previous_lap.DriverNumber), '#808080'))

    v_min = min(previous_car_data.Speed.min(), current_car_data.Speed.min())
    v_max = max(previous_car_data.Speed.max(), current_car_data.Speed.max())
    ax.vlines(x=circuit_info.corners.Distance, ymin=v_min, ymax=v_max, linestyles='dotted', colors='grey')
    ax.hlines(y=list(range(0, int(v_max), 25)), xmin=0, xmax=previous_car_data.Distance.max(), colors='lightgrey')

    for _, corner in circuit_info.corners.iterrows():
        txt = f"{corner.Number}{corner.Letter}"
        ax.text(corner.Distance, v_min - 5, txt, va='center_baseline', ha='center', size='small')

    ax.set_ylim(v_min - 10, v_max + 10)
    ax.legend(fontsize='small')
    ax.grid(True)
    output_path = f"./images/comparison/{gp}/{session}/speed_distance.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)


@tracer.start_as_current_span("plot_throttle_distance")
def plot_throttle_distance(log: Logger, current: Session, previous: Session, gp: str, session: str):
    """throttleを比較
    Args:
        current: 2026 Session
        previous: 2025 Session
        session: session
        gp: Grand Prix name
        log: ロガー
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    current_lap = current.laps.pick_fastest()
    circuit_info = current.get_circuit_info()
    if current_lap is None:
        return
    current_car_data = current_lap.get_car_data().add_distance()
    ax.plot(current_car_data.Distance, current_car_data.Throttle, label=f"2026: {current_lap.Driver}",
            linestyle="solid",
            color=constants.team_color[2026].get(int(current_lap.DriverNumber), '#808080'))
    previous_lap = previous.laps.pick_fastest()
    if previous_lap is None:
        return
    previous_car_data = previous_lap.get_car_data().add_distance()
    ax.plot(previous_car_data.Distance, previous_car_data.Throttle, label=f"2025: {previous_lap.Driver}",
            linestyle="dashed", color=constants.team_color[2025].get(int(previous_lap.DriverNumber), '#808080'))

    v_min = min(previous_car_data.Throttle.min(), current_car_data.Throttle.min())
    v_max = max(previous_car_data.Throttle.max(), current_car_data.Throttle.max())
    ax.vlines(x=circuit_info.corners.Distance, ymin=v_min, ymax=v_max, linestyles='dotted', colors='grey')
    ax.hlines(y=[10, 20, 30, 40, 50, 60, 70, 80, 90], xmin=0, xmax=previous_car_data.Distance.max(), colors='lightgrey')

    for _, corner in circuit_info.corners.iterrows():
        txt = f"{corner.Number}{corner.Letter}"
        ax.text(corner.Distance, v_min - 2.5, txt, va='center_baseline', ha='center', size='small')

    ax.set_ylim(v_min - 5, v_max + 5)
    ax.legend(fontsize='small')
    ax.grid(True)
    output_path = f"./images/comparison/{gp}/{session}/throttle_distance.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)


@tracer.start_as_current_span("summary")
def summary(log: Logger, current: Session, previous: Session, gp: str, session: str, year: int):
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    current_lap = current.laps.pick_fastest()
    circuit_info = current.get_circuit_info()
    if current_lap is None:
        return
    current_car_data = current_lap.get_car_data().add_distance()
    ax.plot(current_car_data.Distance, current_car_data.Throttle, label=f"2026: {current_lap.Driver}",
            linestyle="solid",
            color=constants.team_color[2026].get(int(current_lap.DriverNumber), '#808080'))
    previous_lap = previous.laps.pick_fastest()
    if previous_lap is None:
        return

    titles = []
    title_colors = []
    c = []
    c_colors = []
    p = []
    p_colors = []

    titles.append("LapTime(s)")
    c.append(current_lap.LapTime.total_seconds())
    p.append(previous_lap.LapTime.total_seconds())
    title_colors.append("lightgray")
    c_win = current_lap.LapTime > previous_lap.LapTime
    c_colors.append("white" if c_win else "lightgray")
    p_colors.append("white" if not c_win else "lightgray")
    titles.append("LapTime(%)")
    c.append("{:.3f}".format(current_lap.LapTime.total_seconds() / previous_lap.LapTime.total_seconds()))
    p.append(1)
    c_win = current_lap.LapTime > previous_lap.LapTime
    c_colors.append("white" if c_win else "lightgray")
    p_colors.append("white" if not c_win else "lightgray")

    titles.append("Sector1Time(s)")
    c.append(current_lap.Sector1Time.total_seconds())
    p.append(previous_lap.Sector1Time.total_seconds())
    title_colors.append("lightgray")
    c_win = current_lap.Sector1Time > previous_lap.Sector1Time
    c_colors.append("white" if c_win else "lightgray")
    p_colors.append("white" if not c_win else "lightgray")
    titles.append("Sector1Time(%)")
    c.append("{:.3f}".format(current_lap.Sector1Time.total_seconds() / previous_lap.Sector1Time.total_seconds()))
    p.append(1)
    c_win = current_lap.Sector1Time > previous_lap.Sector1Time
    c_colors.append("white" if c_win else "lightgray")
    p_colors.append("white" if not c_win else "lightgray")

    titles.append("Sector2Time(s)")
    c.append(current_lap.Sector2Time.total_seconds())
    p.append(previous_lap.Sector2Time.total_seconds())
    title_colors.append("lightgray")
    c_win = current_lap.Sector2Time > previous_lap.Sector2Time
    c_colors.append("white" if c_win else "lightgray")
    p_colors.append("white" if not c_win else "lightgray")
    titles.append("Sector2Time(%)")
    c.append("{:.3f}".format(current_lap.Sector2Time.total_seconds() / previous_lap.Sector2Time.total_seconds()))
    p.append(1)
    c_win = current_lap.Sector2Time > previous_lap.Sector2Time
    c_colors.append("white" if c_win else "lightgray")
    p_colors.append("white" if not c_win else "lightgray")

    titles.append("Sector3Time(s)")
    c.append(current_lap.Sector3Time.total_seconds())
    p.append(previous_lap.Sector3Time.total_seconds())
    title_colors.append("lightgray")
    c_win = current_lap.Sector3Time > previous_lap.Sector3Time
    c_colors.append("white" if c_win else "lightgray")
    p_colors.append("white" if not c_win else "lightgray")
    titles.append("Sector3Time(%)")
    c.append("{:.3f}".format(current_lap.Sector3Time.total_seconds() / previous_lap.Sector3Time.total_seconds()))
    p.append(1)
    c_win = current_lap.Sector3Time > previous_lap.Sector3Time
    c_colors.append("white" if c_win else "lightgray")
    p_colors.append("white" if not c_win else "lightgray")

    titles.append("SpeedFL")
    c.append(current_lap.SpeedFL)
    p.append(previous_lap.SpeedFL)
    title_colors.append("lightgray")
    c_win = current_lap.SpeedFL < previous_lap.SpeedFL
    c_colors.append("white" if c_win else "lightgray")
    p_colors.append("white" if not c_win else "lightgray")

    titles.append("SpeedI1")
    c.append(current_lap.SpeedI1)
    p.append(previous_lap.SpeedI1)
    title_colors.append("lightgray")
    c_win = current_lap.SpeedI1 < previous_lap.SpeedI1
    c_colors.append("white" if c_win else "lightgray")
    p_colors.append("white" if not c_win else "lightgray")

    titles.append("SpeedI2")
    c.append(current_lap.SpeedI2)
    p.append(previous_lap.SpeedI2)
    title_colors.append("lightgray")
    c_win = current_lap.SpeedI2 < previous_lap.SpeedI2
    c_colors.append("white" if c_win else "lightgray")
    p_colors.append("white" if not c_win else "lightgray")

    titles.append("SpeedST")
    c.append(current_lap.SpeedST)
    p.append(previous_lap.SpeedST)
    title_colors.append("lightgray")
    c_win = current_lap.SpeedST < previous_lap.SpeedST
    c_colors.append("white" if c_win else "lightgray")
    p_colors.append("white" if not c_win else "lightgray")

    titles.append("Max(Speed)")
    c.append(current.laps.pick_fastest().telemetry.Speed.max())
    p.append(previous.laps.pick_fastest().telemetry.Speed.max())
    title_colors.append("lightgray")
    c_win = current.laps.pick_fastest().telemetry.Speed.max() < previous.laps.pick_fastest().telemetry.Speed.max()
    c_colors.append("white" if c_win else "lightgray")
    p_colors.append("white" if not c_win else "lightgray")

    titles.append("Compound")
    c.append(current_lap.Compound)
    p.append(previous_lap.Compound)
    title_colors.append("lightgray")
    c_colors.append("white")
    p_colors.append("white")

    titles.append("TyreLife")
    c.append(current_lap.TyreLife)
    p.append(previous_lap.TyreLife)
    title_colors.append("lightgray")
    c_colors.append("white")
    p_colors.append("white")

    titles.append("Max(AirTemp)")
    c.append(current.weather_data.AirTemp.max())
    p.append(previous.weather_data.AirTemp.max())
    title_colors.append("lightgray")
    c_colors.append("white")
    p_colors.append("white")

    titles.append("Min(AirTemp)")
    c.append(current.weather_data.AirTemp.min())
    p.append(previous.weather_data.AirTemp.min())
    title_colors.append("lightgray")
    c_colors.append("white")
    p_colors.append("white")

    titles.append("Max(TrackTemp)")
    c.append(current.weather_data.TrackTemp.max())
    p.append(previous.weather_data.TrackTemp.max())
    title_colors.append("lightgray")
    c_colors.append("white")
    p_colors.append("white")

    titles.append("Min(TrackTemp)")
    c.append(current.weather_data.TrackTemp.min())
    p.append(previous.weather_data.TrackTemp.min())
    title_colors.append("lightgray")
    c_colors.append("white")
    p_colors.append("white")

    fig = graph_objects.Figure(data=[graph_objects.Table(
        header={'values': ["", year - 1, year], 'fill_color': 'lightgrey', 'align': 'center'},
        cells={'values': [titles, p, c], 'fill_color': [title_colors, c_colors, p_colors], 'align': 'center'}
    )])

    output_path = f"./images/comparison/{gp}/{session}/summary.png"
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
    summary(log, current, previous, round, session, year)
    plot_brake_distance(log, current, previous, round, session)
    plot_n_gear_distance(log, current, previous, round, session)
    plot_rpm_distance(log, current, previous, round, session)
    plot_speed_distance(log, current, previous, round, session)
    plot_throttle_distance(log, current, previous, round, session)


if __name__ == "__main__":
    __main()
