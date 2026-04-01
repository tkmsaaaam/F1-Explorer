import json
import os
from logging import Logger

import fastf1
from fastf1.core import Session
from matplotlib import pyplot as plt
from opentelemetry import trace

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


@tracer.start_as_current_span("main")
def __main():
    log = setup.log()
    config = None
    with open('./config.json', 'r', encoding='utf-8') as file:
        config = json.load(file)
    if config is None:
        raise Exception("Config must be provided")

    setup.fast_f1()

    round = config['Comparison']['Round']
    session = config['Comparison']['Session']
    try:
        current = fastf1.get_session(2026, round, session)
    except Exception as exception:
        log.warning(exception.args)
        return
    current.load(messages=False)
    try:
        previous = fastf1.get_session(2025, round, session)
    except Exception as exception:
        log.warning(exception.args)
        return
    previous.load(messages=False)
    log.info(f"{round} {session}")
    plot_brake_distance(log, current, previous, round, session)
    plot_n_gear_distance(log, current, previous, round, session)
    plot_rpm_distance(log, current, previous, round, session)
    plot_speed_distance(log, current, previous, round, session)
    plot_throttle_distance(log, current, previous, round, session)


if __name__ == "__main__":
    __main()
