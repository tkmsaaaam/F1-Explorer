import datetime
import os
from logging import Logger

import fastf1
import pandas
from fastf1.core import Session, Laps
from matplotlib import pyplot as plt
from matplotlib.patches import Patch
from opentelemetry import trace
from plotly import graph_objects

import constants
import util
from visualizations.domain.driver import Driver
from visualizations.domain.lap import Lap
from visualizations.domain.tyre import Tyre

tracer = trace.get_tracer(__name__)


@tracer.start_as_current_span("execute")
def execute(session: Session, log: Logger, images_path: str, logs_path: str, lap_time_range: int | None,
            gap_top_range: int | None,
            gap_ahead_range: int | None):
    driver_laps_set = make_driver_laps_set(session.laps)
    start_by_position_by_number = make_lap_start_by_position_by_number(session.laps)
    laptime(log, images_path, "laptime", session, lap_time_range, driver_laps_set)
    gap(log, f"{images_path}/gap.png", driver_laps_set, start_by_position_by_number)
    gap_to_ahead(log, images_path, "gap_ahead", session, gap_ahead_range, driver_laps_set, start_by_position_by_number)
    gap_to_top(log, images_path, "gap_top", session, gap_top_range, driver_laps_set)
    positions(log, f"{images_path}/position.png", session, driver_laps_set)
    tyres(log, f"{images_path}/tyres.png", driver_laps_set)
    write_messages(session, logs_path)
    write_track_status(session, logs_path)
    try:
        os.remove(f"{logs_path}/timestamp.txt")
    except FileNotFoundError:
        pass
    util.write_to_file_top(f"{logs_path}/timestamp.txt", str(datetime.datetime.now()))


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
        driver: Driver = Driver(int(stint_laps.DriverNumber.iloc[0]), stint_laps.Driver.iloc[0],
                                stint_laps.Team.iloc[0])
        laps: dict[int, Lap] = {}
        for i in range(0, len(stint_laps)):
            lap: Lap = Lap(stint_laps.LapTime.iloc[i].total_seconds(), stint_laps.Time.iloc[i],
                           stint_laps.Position.iloc[i], pandas.isna(stint_laps.PitOutTime.iloc[i]),
                           Tyre(stint_laps.Compound.iloc[i], stint_laps.FreshTyre.iloc[i]))
            laps[stint_laps.LapNumber.iloc[i]] = lap
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
def laptime(log: Logger, filepath: str, filename: str, session: Session, r: int, lap_logs: set[DriverLaps]):
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
        lap_times = [lap_log.get_laps().get(i).get_time() for i in lap_numbers]
        color = fastf1.plotting.get_team_color(lap_log.get_driver().get_team_name(), session)
        ax.plot(lap_numbers, lap_times, color=color, label=lap_log.get_driver().get_name(),
                linestyle="solid" if constants.camera[session.event.year].get(lap_log.get_driver().get_number(),
                                                                              'black') == "black" else "dashed")
    minimum = session.laps.sort_values(by='LapTime').iloc[0].LapTime.total_seconds()
    ax.legend(fontsize='small')
    ax.set_ylim(top=minimum, bottom=minimum + 15)
    ax.grid(True)
    output_path = f"{filepath}/{filename}.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)
    if r is not None:
        ax.set_ylim(top=minimum, bottom=minimum + r)
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


@tracer.start_as_current_span("gap")
def gap(log: Logger, filepath: str, lap_logs: set[DriverLaps],
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
    for driver_laps in lap_logs:
        gaps = []
        colors = []
        for i in range(min(driver_laps.get_laps()), max(driver_laps.get_laps()) + 1):
            lap = driver_laps.get_laps().get(i)
            if lap.get_position() == 1:
                gaps.append("{:.3f}".format(0))
                colors.append('#ffffff')
                continue
            diff = (lap.get_at() - position_logs.get(i).get(lap.get_position() - 1)).total_seconds()
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

    fig = graph_objects.Figure(data=[graph_objects.Table(
        header=dict(values=header, fill_color='lightgrey', align='center'),
        cells=dict(values=[list(range(1, max_laps + 1))] + all_gaps, fill_color=[["#f0f0f0"] * max_laps] + fill_colors,
                   align='center')
    )], layout=dict(autosize=True, margin=dict(autoexpand=True)))

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    fig.write_image(filepath, width=1920, height=1620)
    log.info(f"Saved plot to {filepath}")


@tracer.start_as_current_span("gap_to_ahead")
def gap_to_ahead(log: Logger, filepath: str, filename: str, session: Session, r: int, lap_logs: set[DriverLaps],
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
        y = [(driver_laps.get_laps().get(i).get_at() - position_logs.get(i).get(
            driver_laps.get_laps().get(i).get_position() - 1)).total_seconds() for i in x]
        line_style = "solid" if constants.camera[session.event.year].get(driver_laps.get_driver().get_number(),
                                                                         'black') == "black" else "dashed"
        ax.plot(x, y, color=fastf1.plotting.get_team_color(driver_laps.get_driver().get_team_name(), session),
                label=driver_laps.get_driver().get_name(),
                linestyle=line_style, linewidth=1)
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
def gap_to_top(log: Logger, filepath: str, filename: str, session: Session, r: int, lap_logs: set[DriverLaps]):
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
        y = [(lap_log.get_laps().get(i).get_at() - top_time_map.get(i)).total_seconds() for i in x]
        line_style = "solid" if constants.camera[session.event.year].get(lap_log.get_driver().get_number(),
                                                                         'black') == "black" else "dashed"
        ax.plot(x, y, linewidth=1, color=color, label=lap_log.get_driver().get_name(), linestyle=line_style)
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
        y = [lap_log.get_laps().get(i).get_position() for i in x]
        line_style = "solid" if constants.camera[session.event.year].get(lap_log.get_driver().get_number(),
                                                                         'black') == "black" else "dashed"
        ax.plot(x, y, linewidth=1, color=color, label=lap_log.get_driver().get_name(), linestyle=line_style)

    ax.legend(fontsize='small')
    ax.invert_yaxis()
    ax.grid(True)
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
            if not lap_log.get_laps().get(i).get_pit_out() and i != max(x):
                continue
            j = i - 1
            if j < 1:
                continue
            ax.barh(y=y,
                    width=j - start,
                    left=start,
                    color=constants.compound_color.get(lap_log.get_laps().get(j).get_tyre().get_compound(), 'gray'),
                    edgecolor='black' if lap_log.get_laps().get(j).get_tyre().get_new() else 'gray'
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
