import datetime
import os
from logging import Logger
from typing import cast

import fastf1
import pandas
from fastf1.core import Session, Laps
from matplotlib import pyplot as plt
from matplotlib.patches import Patch
# noinspection PyPackageRequirements
from opentelemetry import trace
from plotly import graph_objects

import constants
import util
from visualizations.domain.driver import Driver
from visualizations.domain.lap import Lap
from visualizations.domain.tyre import Tyre

tracer = trace.get_tracer(__name__)


def determine_linestyle(year: int, driver: int) -> str:
    if constants.camera.get(year, {}).get(driver, 'black') == "black":
        return "solid"
    else:
        return "dashed"


@tracer.start_as_current_span("execute")
def execute(session: Session, log: Logger, images_path: str, logs_path: str, lap_time_range: int | None,
            gap_top_range: int | None,
            gap_ahead_range: int | None):
    driver_laps_set = make_driver_laps_set(session.laps)
    start_by_position_by_number = make_lap_start_by_position_by_number(session.laps)
    laptime(log, images_path, "laptime_graph", session, lap_time_range, driver_laps_set)
    gap_to_ahead_table(log, f"{images_path}/gap_ahead_table.png", driver_laps_set, start_by_position_by_number)
    gap_to_top_table(log, f"{images_path}/gap_top_table.png", driver_laps_set, session)
    gap_to_ahead_graph(log, images_path, "gap_ahead_graph", session, gap_ahead_range, driver_laps_set,
                       start_by_position_by_number)
    gap_to_top_graph(log, images_path, "gap_top_graph", session, gap_top_range, driver_laps_set)
    positions(log, f"{images_path}/position.png", session, driver_laps_set)
    speed_first_10s(log, f"{images_path}/speed_first_10s.png", session)
    speed_until_turn1(log, f"{images_path}/speed_until_turn1.png", session)
    tyres(log, f"{images_path}/tyres.png", driver_laps_set)
    write_messages(session, logs_path)
    write_track_status(session, logs_path)
    try:
        os.remove(f"{logs_path}/timestamp.txt")
    except FileNotFoundError:
        pass
    util.write_to_file_top(f"{logs_path}/timestamp.txt", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class DriverLaps:
    def __init__(self, driver: Driver, laps: dict[int, Lap]):
        self.__driver = driver
        self.__laps = laps

    def get_driver(self) -> Driver:
        return self.__driver

    def get_laps(self) -> dict[int, Lap]:
        return self.__laps


def make_driver_laps_set(laps: Laps) -> set[DriverLaps]:
    result = set()
    grouped = laps.groupby(['DriverNumber'])
    for _, stint_laps in grouped:
        l = stint_laps.iloc[0]
        driver: Driver = Driver(int(l.DriverNumber), l.Driver, l.Team)
        laps: dict[int, Lap] = {}
        for _, l in cast(Laps, stint_laps).iterlaps():
            # noinspection PyTypeChecker
            lap: Lap = Lap(l.LapTime.total_seconds(), l.Time, l.Position, pandas.isna(l.PitOutTime),
                           Tyre(l.Compound, l.FreshTyre))
            # convert lap number to native int to avoid numpy float/int issues later
            laps[int(l.LapNumber)] = lap
        result.add(DriverLaps(driver, laps))
    return result


def make_lap_start_by_position_by_number(laps: Laps) -> dict[int, dict[int, datetime.datetime]]:
    result = {}
    for i in range(0, len(laps)):
        lap_number = laps.LapNumber.iloc[i]
        if lap_number not in result:
            result[lap_number] = {laps.Position.iloc[i]: laps.Time.iloc[i]}
        else:
            result[lap_number][laps.Position.iloc[i]] = laps.Time.iloc[i]
    return result


@tracer.start_as_current_span("laptime")
def laptime(log: Logger, filepath: str, filename: str, session: Session, r: int | None, lap_logs: set[DriverLaps]):
    """x = ラップ番号, y = ラップタイムのドライバーごとの推移
    Args:
        log: ロガー
        filepath: 画像を保存する先のpath
        filename: ファイル名
        session: セッション
        r: y軸の幅
        lap_logs: ドライバーごとのラップ
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for lap_log in lap_logs:
        lap_numbers = sorted(lap_log.get_laps().keys())
        lap_times = [
            l.get_time() if (l := lap_log.get_laps().get(i)) is not None else None
            for i in lap_numbers
        ]
        color = fastf1.plotting.get_team_color(lap_log.get_driver().get_team_name(), session)
        ax.plot(lap_numbers, lap_times, color=color, label=lap_log.get_driver().get_name(), linewidth=0.5,
                linestyle=determine_linestyle(session.event.year, lap_log.get_driver().get_number()))
    minimum: datetime.timedelta = session.laps.sort_values(by='LapTime').LapTime.min()
    maximum: datetime.timedelta = session.laps[
        session.laps.IsAccurate
        & (session.laps.Deleted == False)
        & (session.laps.TrackStatus == '1')
        ].sort_values(by='LapTime', ascending=False).LapTime.max()
    ax.legend(fontsize='small')
    ax.set_ylim(top=minimum.total_seconds() - 0.1, bottom=maximum.total_seconds() + 0.1)
    ax.grid(True)
    output_path = f"{filepath}/{filename}.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)
    if r is not None:
        ax.set_ylim(top=minimum.total_seconds(), bottom=minimum.total_seconds() + r)
        ax.grid(True)
        output_path = f"{filepath}/{filename}_{r}.png"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.savefig(output_path, bbox_inches='tight')
        log.info(f"Saved plot to {output_path}")
        plt.close(fig)


def make_top_time_map(all_laps: Laps) -> dict[int, datetime.datetime]:
    fastest = {}
    for i in range(0, len(all_laps)):
        if all_laps.Position.iloc[i] != 1:
            continue
        fastest[all_laps.LapNumber.iloc[i]] = all_laps.Time.iloc[i]
    return fastest


@tracer.start_as_current_span("gap_to_ahead_table")
def gap_to_ahead_table(log: Logger, filepath: str, lap_logs: set[DriverLaps],
                       position_logs: dict[int, dict[int, datetime.datetime]]):
    """ラップごとのギャップの一覧を作成する
    Args:
        log: ロガー
        filepath: 画像を保存する先のpathとファイル名
        lap_logs: ドライバーごとのラップ
        position_logs: ラップごとのポジション
    """
    header = ["Lap"]
    all_gaps = []
    fill_colors = []
    max_laps = 0
    sorted_lap_logs = sorted(
        lap_logs,
        key=lambda dl: dl.get_laps()[max(dl.get_laps().keys())].get_position()
    )
    for driver_laps in sorted_lap_logs:
        gaps = []
        colors = []
        # ensure we iterate over integer lap numbers; keys may be numpy types
        lap_keys = driver_laps.get_laps().keys()
        start = int(min(lap_keys))
        end = int(max(lap_keys))
        for i in range(start, end):
            lap = driver_laps.get_laps().get(i)
            if lap is None:
                gaps.append('---')
                colors.append('#ffffff')
                continue
            if lap.get_position() == 1:
                gaps.append("{:.3f}".format(0))
                colors.append('#ffffff')
                continue
            positions_by_lap = position_logs.get(i)
            if positions_by_lap is None:
                gaps.append('---')
                colors.append('#ffffff')
                continue
            ahead = positions_by_lap.get(lap.get_position() - 1)
            if ahead is None:
                gaps.append('---')
                colors.append('#ffffff')
                continue
            diff = (lap.get_at() - ahead).total_seconds()
            gaps.append(diff)
            if diff < 3:
                colors.append('#9966ff')
            elif diff > 20:
                colors.append('#e95464')
            else:
                colors.append('#ffffff')
        if len(gaps) > max_laps:
            max_laps = len(gaps)
        header.append(driver_laps.get_driver().get_name())
        all_gaps.append(gaps)
        fill_colors.append(colors)
    fig = graph_objects.Figure(
        data=[graph_objects.Table(
            header=graph_objects.table.Header(
                values=header, fill=graph_objects.table.header.Fill(color='lightgrey'), align='center'),
            cells=graph_objects.table.Cells(
                values=[list(range(1, max_laps + 1))] + all_gaps,
                fill=graph_objects.table.cells.Fill(color=[["#f0f0f0"] * max_laps] + fill_colors),
                align='center'))],
        layout=graph_objects.Layout(autosize=True, margin=graph_objects.Margin(autoexpand=True)))

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    fig.write_image(filepath, width=1920, height=1620)
    log.info(f"Saved plot to {filepath}")


@tracer.start_as_current_span("gap_to_top_table")
def gap_to_top_table(log: Logger, filepath: str, lap_logs: set[DriverLaps], session: Session):
    """ラップごとのTopへのギャップの一覧を作成する
    Args:
        log: ロガー
        filepath: 画像を保存する先のpathとファイル名
        lap_logs: ドライバーごとのラップ
        session: Session
    """
    header = ["Lap"]
    all_gaps = []
    fill_colors = []
    max_laps = 0
    top_time_map = make_top_time_map(session.laps)
    sorted_lap_logs = sorted(
        lap_logs,
        key=lambda dl: dl.get_laps()[max(dl.get_laps().keys())].get_position()
    )
    for driver_laps in sorted_lap_logs:
        gaps = []
        colors = []
        # ensure we iterate over integer lap numbers; keys may be numpy types
        lap_keys = driver_laps.get_laps().keys()
        start = int(min(lap_keys))
        end = int(max(lap_keys))
        for i in range(start, end):
            lap = driver_laps.get_laps().get(i)
            if lap is None:
                gaps.append('---')
                colors.append('#ffffff')
                continue
            if lap.get_position() == 1:
                gaps.append("{:.3f}".format(0))
                colors.append('gold')
                continue
            top = top_time_map.get(i)
            if top is None:
                gaps.append('---')
                colors.append('#ffffff')
                continue
            diff = (lap.get_at() - top).total_seconds()
            gaps.append(diff)
            if diff < 5:
                colors.append('#9966ff')
            elif diff < 30:
                colors.append('#e95464')
            else:
                colors.append('#ffffff')
        if len(gaps) > max_laps:
            max_laps = len(gaps)
        header.append(driver_laps.get_driver().get_name())
        all_gaps.append(gaps)
        fill_colors.append(colors)
    fig = graph_objects.Figure(
        data=[graph_objects.Table(
            header=graph_objects.table.Header(
                values=header, fill=graph_objects.table.header.Fill(color='lightgrey'), align='center'),
            cells=graph_objects.table.Cells(
                values=[list(range(1, max_laps + 1))] + all_gaps,
                fill=graph_objects.table.cells.Fill(
                    color=[["#f0f0f0"] * max_laps] + fill_colors), align='center'))],
        layout=graph_objects.Layout(autosize=True, margin=graph_objects.Margin(autoexpand=True)))

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    fig.write_image(filepath, width=1920, height=1620)
    log.info(f"Saved plot to {filepath}")


@tracer.start_as_current_span("gap_to_ahead")
def gap_to_ahead_graph(log: Logger, filepath: str, filename: str, session: Session, r: int | None,
                       lap_logs: set[DriverLaps],
                       position_logs: dict[int, dict[int, datetime.datetime]]):
    """x = ラップ番号, y = 前走とのギャップのドライバーごとの推移
    Args:
        log: ロガー
        filepath: 画像を保存する先のpath
        filename: 画像名
        session: セッション
        r: y軸の幅
        lap_logs: ドライバーごとのラップ
        position_logs: ラップごとのポジション
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for driver_laps in lap_logs:
        x = sorted(driver_laps.get_laps().keys())
        y = [
            ((l := driver_laps.get_laps().get(i)) is not None and
             (p_log := position_logs.get(i)) is not None and
             (p_target := p_log.get(l.get_position() - 1)) is not None
             ) and (l.get_at() - p_target).total_seconds() or 0
            for i in x
        ]
        line_style = determine_linestyle(session.event.year, driver_laps.get_driver().get_number())
        ax.plot(x, y, color=fastf1.plotting.get_team_color(driver_laps.get_driver().get_team_name(), session),
                label=driver_laps.get_driver().get_name(),
                linestyle=line_style, linewidth=0.5)
    ax.legend(fontsize='small')
    ax.set_ylim(top=0, bottom=30)
    ax.grid(True)
    output_path = f"{filepath}/{filename}.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)
    if r is not None:
        ax.set_ylim(top=0, bottom=r)
        output_path = f"{filepath}/{filename}_{r}.png"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.savefig(output_path, bbox_inches='tight')
        log.info(f"Saved plot to {output_path}")
        plt.close(fig)


@tracer.start_as_current_span("gap_to_top")
def gap_to_top_graph(log: Logger, filepath: str, filename: str, session: Session, r: int | None,
                     lap_logs: set[DriverLaps]):
    """x = ラップ番号, y = トップとのギャップのドライバーごとの推移
    Args:
        log: ロガー
        filepath: 画像を保存する先のpath
        filename: ファイル名
        session: セッション
        r: y軸の幅
        lap_logs: ドライバーごとのラップ
    """
    top_time_map = make_top_time_map(session.laps)
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for lap_log in lap_logs:
        color = fastf1.plotting.get_team_color(lap_log.get_driver().get_team_name(), session)
        x = sorted(lap_log.get_laps().keys())
        y = [
            (l.get_at() - t).total_seconds()
            if (l := lap_log.get_laps().get(i)) is not None and (t := top_time_map.get(i)) is not None
            else 0
            for i in x
        ]
        line_style = determine_linestyle(session.event.year, lap_log.get_driver().get_number())
        ax.plot(x, y, linewidth=0.5, color=color, label=lap_log.get_driver().get_name(), linestyle=line_style)
    ax.legend(fontsize='small')
    ax.invert_yaxis()
    ax.set_ylim(top=0, bottom=60)
    ax.grid(True)
    output_path = f"{filepath}/{filename}.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)
    if r is not None:
        ax.set_ylim(top=0, bottom=r)
        ax.grid(True)
        output_path = f"{filepath}/{filename}_{r}.png"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.savefig(output_path, bbox_inches='tight')
        log.info(f"Saved plot to {output_path}")
        plt.close(fig)


@tracer.start_as_current_span("positions")
def positions(log: Logger, filepath: str, session: Session, lap_logs: set[DriverLaps]):
    """x = ラップ番号, y = ポジションのドライバーごとの推移
    Args:
        log: ロガー
        filepath: 画像を保存する先のpathとファイル名
        session: セッション
        lap_logs: ドライバーごとのラップ
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for lap_log in lap_logs:
        color = fastf1.plotting.get_team_color(lap_log.get_driver().get_team_name(), session)
        x = sorted(lap_log.get_laps().keys())
        y = [
            l.get_position() if (l := lap_log.get_laps().get(i)) is not None else 0
            for i in x
        ]
        line_style = determine_linestyle(session.event.year, lap_log.get_driver().get_number())
        ax.plot(x, y, linewidth=1, color=color, label=lap_log.get_driver().get_name(), linestyle=line_style)

    ax.legend(fontsize='small')
    ax.invert_yaxis()
    ax.grid(True)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    fig.savefig(filepath, bbox_inches='tight')
    log.info(f"Saved plot to {filepath}")
    plt.close(fig)


@tracer.start_as_current_span("speed_first_10s")
def speed_first_10s(log: Logger, filepath: str, session: Session) -> None:
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    v_min = float('inf')
    v_max = float('-inf')
    for driver in session.drivers:
        laps = session.laps.pick_drivers(driver)
        lap = laps.pick_fastest()
        if lap is None:
            continue
        car_data = lap.get_car_data().copy()
        car_data["TimeSeconds"] = car_data.Time.dt.total_seconds()
        car_data = car_data[car_data.TimeSeconds <= 10]
        driver_number = int(lap.DriverNumber)
        ax.plot(
            car_data.TimeSeconds,
            car_data.Speed,
            label=lap.Driver, linewidth=0.5,
            color=constants.team_color[session.event.EventDate.year][driver_number],
            linestyle=determine_linestyle(session.event.year, driver_number)
        )
        v_min = min(v_min, int(car_data.Speed.min()) + 50)
        v_max = max(v_max, int(car_data.Speed.max()) + 10)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Speed (km/h)")
    ax.set_title("Speed for First 10 Seconds")
    ax.set_ylim(v_min, v_max)
    ax.legend()
    ax.grid()
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    fig.savefig(filepath, bbox_inches='tight')
    log.info(f"Saved plot to {filepath}")
    plt.close(fig)


@tracer.start_as_current_span("speed_until_turn1")
def speed_until_turn1(log: Logger, filepath: str, session: Session) -> None:
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    circuit_info = session.get_circuit_info()
    if circuit_info is None:
        return
    first_corner_distance = circuit_info.corners.iloc[0].Distance
    v_min = float('inf')
    v_max = float('-inf')
    for driver in session.drivers:
        laps = session.laps.pick_drivers(driver)
        lap = laps.pick_fastest()
        if lap is None:
            continue
        car_data = lap.get_car_data().add_distance()[
            lap.get_car_data().add_distance().Distance <= first_corner_distance]
        driver_number = int(lap.DriverNumber)
        ax.plot(
            car_data.Distance,
            car_data.Speed,
            label=lap.Driver, linewidth=0.5,
            color=constants.team_color[session.event.EventDate.year][driver_number],
            linestyle=determine_linestyle(session.event.year, driver_number)
        )
        v_min = min(v_min, int(cast(pandas.Series, car_data.Speed).min()) + 50)
        v_max = max(v_max, int(cast(pandas.Series, car_data.Speed).max()) + 10)
    ax.set_xlabel("Distance (m)")
    ax.set_ylabel("Speed (km/h)")
    ax.set_title("Speed until Turn 1")
    ax.set_ylim(v_min, v_max)
    ax.axvline(first_corner_distance, linestyle='dotted', color='grey')
    ax.legend()
    ax.grid()
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    fig.savefig(filepath, bbox_inches='tight')
    log.info(f"Saved plot to {filepath}")
    plt.close(fig)


@tracer.start_as_current_span("tyres")
def tyres(log: Logger, filepath: str, lap_logs: set[DriverLaps]):
    """x = ラップ番号, y = 使用タイヤのドライバーごとの推移
    Args:
        log: ロガー
        filepath:
        lap_logs: ドライバーごとのラップ
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    y = 0
    for lap_log in lap_logs:
        x = sorted(lap_log.get_laps().keys())
        start = 0
        for i in x:
            lap = lap_log.get_laps().get(i)
            if lap is None:
                continue
            if not lap.get_pit_out() and i != max(x):
                continue
            j = i - 1
            if j < 1:
                continue
            previous = lap_log.get_laps().get(j)
            if previous is None:
                continue
            ax.barh(y=y,
                    width=j - start,
                    left=start,
                    color=constants.compound_color.get(previous.get_tyre().get_compound(), 'gray'),
                    edgecolor='black' if previous.get_tyre().get_new() else 'gray'
                    )
            start = j
        y += 1
    ax.set_yticks([i for i in range(0, len(lap_logs))])
    ax.set_yticklabels([str(driver.get_driver().get_number()) for driver in lap_logs])
    legend_elements = [Patch(facecolor=color, edgecolor='black', label=compound)
                       for compound, color in constants.compound_color.items()]
    ax.legend(handles=legend_elements, title='Compound', loc='upper right', fontsize='small')
    ax.grid(True)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    fig.savefig(filepath, bbox_inches='tight')
    log.info(f"Saved plot to {filepath}")
    plt.close(fig)


@tracer.start_as_current_span("write_messages")
def write_messages(session: Session, logs_path: str):
    try:
        os.remove(f"{logs_path}/race_control.txt")
    except FileNotFoundError:
        pass
    messages = session.race_control_messages.sort_values('Time')
    for i in range(0, len(messages)):
        t = session.race_control_messages.Time.iloc[i]
        l = session.race_control_messages.Lap.iloc[i]
        c = session.race_control_messages.Category.iloc[i]
        f = session.race_control_messages.Flag.iloc[i]
        s = session.race_control_messages.Scope.iloc[i]
        n = session.race_control_messages.RacingNumber.iloc[i]
        m = session.race_control_messages.Message.iloc[i]
        message = util.join_with_colon(str(t), str(l), str(c), str(f), str(s), str(n), str(m))
        util.write_to_file_top(f"{logs_path}/race_control.txt", message)


@tracer.start_as_current_span("write_track_status")
def write_track_status(session: Session, logs_path: str):
    try:
        os.remove(f"{logs_path}/track_status.txt")
    except FileNotFoundError:
        pass
    messages = session.track_status.sort_values('Time')
    for i in range(0, len(messages)):
        t = session.race_control_messages.Time.iloc[i]
        s = session.race_control_messages.Status.iloc[i]
        m = session.race_control_messages.Message.iloc[i]
        message = util.join_with_colon(str(t), str(s), str(m))
        util.write_to_file_top(f"{logs_path}/track_status.txt", message)
