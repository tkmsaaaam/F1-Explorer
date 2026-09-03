import datetime
import os
from typing import cast

import fastf1
import fastf1.plotting
import matplotlib as mpl
import matplotlib.pyplot as plt
import pandas
import plotly.graph_objects as go
import structlog
from fastf1.core import Session, Laps
# noinspection PyPackageRequirements
from opentelemetry import trace

import constants
import util
from visualizations.domain.driver import Driver
from visualizations.domain.driver_laps import DriverLaps
from visualizations.domain.lap import Lap
from visualizations.domain.tyre import Tyre
from visualizations.output import save_matplotlib, save_plotly
from visualizations.race_metrics import (
    gap_to_ahead as calculate_gap_to_ahead,
    gap_to_leader as calculate_gap_to_leader,
    lap_times_by_position,
    top_time_map,
)
from visualizations.style import driver_linestyle

tracer = trace.get_tracer(__name__)


@tracer.start_as_current_span("execute")
def execute(session: Session, log: structlog.stdlib.BoundLogger, images_path: str, logs_path: str, lap_time_range: int | None,
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
    tyres(log, f"{images_path}/tyres.png", session.laps)
    write_messages(session, logs_path)
    write_track_status(session, logs_path)
    try:
        os.remove(f"{logs_path}/timestamp.txt")
    except FileNotFoundError:
        pass
    util.write_to_file_top(f"{logs_path}/timestamp.txt", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


def make_driver_laps_set(laps: Laps) -> list[DriverLaps]:
    result = []
    grouped = laps.groupby(['DriverNumber'])
    for _, stint_laps in grouped:
        first_lap = stint_laps.iloc[0]
        driver = Driver(int(first_lap.DriverNumber), first_lap.Driver, first_lap.Team)
        lap_map: dict[int, Lap] = {}
        for _, lap_row in cast(Laps, stint_laps).iterlaps():
            if any(pandas.isna(value) for value in (
                    lap_row.LapNumber, lap_row.LapTime, lap_row.Time, lap_row.Position)):
                continue
            # noinspection PyTypeChecker
            lap = Lap(
                lap_row.LapTime.total_seconds(),
                lap_row.Time,
                lap_row.Position,
                not pandas.isna(lap_row.PitOutTime),
                Tyre(lap_row.Compound, lap_row.FreshTyre),
            )
            lap_map[int(lap_row.LapNumber)] = lap
        if lap_map:
            result.append(DriverLaps(driver, lap_map))
    return sorted(result, key=lambda item: item.driver.number)


def make_lap_start_by_position_by_number(laps: Laps) -> dict[int, dict[int, datetime.datetime]]:
    return lap_times_by_position(make_driver_laps_set(laps))


@tracer.start_as_current_span("laptime")
def laptime(log: structlog.stdlib.BoundLogger, filepath: str, filename: str, session: Session, r: int | None, lap_logs: list[DriverLaps]):
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
                linestyle=driver_linestyle(session.event.year, lap_log.get_driver().get_number()))
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
    if r is not None:
        ax.set_ylim(top=minimum.total_seconds(), bottom=minimum.total_seconds() + r)
        ax.grid(True)
        output_path = f"{filepath}/{filename}_{r}.png"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.savefig(output_path, bbox_inches='tight')
        log.info(f"Saved plot to {output_path}")
    plt.close(fig)


def make_top_time_map(all_laps: Laps) -> dict[int, datetime.datetime]:
    return top_time_map(make_driver_laps_set(all_laps))


@tracer.start_as_current_span("gap_to_ahead_table")
def gap_to_ahead_table(log: structlog.stdlib.BoundLogger, filepath: str, lap_logs: list[DriverLaps],
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
        for i in range(start, end + 1):
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
    fig = go.Figure(
        data=[go.Table(
            header=go.table.Header(
                values=header, fill=go.table.header.Fill(color='lightgrey'), align='center'),
            cells=go.table.Cells(
                values=[list(range(1, max_laps + 1))] + all_gaps,
                fill=go.table.cells.Fill(color=[["#f0f0f0"] * max_laps] + fill_colors),
                align='center'))],
        layout=go.Layout(autosize=True, margin=go.layout.Margin(autoexpand=True)))

    save_plotly(fig, filepath, log, width=1920, height=1620)


@tracer.start_as_current_span("gap_to_top_table")
def gap_to_top_table(log: structlog.stdlib.BoundLogger, filepath: str, lap_logs: list[DriverLaps], session: Session):
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
        for i in range(start, end + 1):
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
    fig = go.Figure(
        data=[go.Table(
            header=go.table.Header(
                values=header, fill=go.table.header.Fill(color='lightgrey'), align='center'),
            cells=go.table.Cells(
                values=[list(range(1, max_laps + 1))] + all_gaps,
                fill=go.table.cells.Fill(
                    color=[["#f0f0f0"] * max_laps] + fill_colors), align='center'))],
        layout=go.Layout(autosize=True, margin=go.layout.Margin(autoexpand=True)))

    save_plotly(fig, filepath, log, width=1920, height=1620)


@tracer.start_as_current_span("gap_to_ahead")
def gap_to_ahead_graph(log: structlog.stdlib.BoundLogger, filepath: str, filename: str, session: Session, r: int | None,
                       lap_logs: list[DriverLaps],
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
        gap_series = calculate_gap_to_ahead(driver_laps, position_logs)
        x = [lap_number for lap_number, _ in gap_series]
        y = [gap for _, gap in gap_series]
        line_style = driver_linestyle(session.event.year, driver_laps.get_driver().get_number())
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
    if r is not None:
        ax.set_ylim(top=0, bottom=r)
        output_path = f"{filepath}/{filename}_{r}.png"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.savefig(output_path, bbox_inches='tight')
        log.info(f"Saved plot to {output_path}")
    plt.close(fig)


@tracer.start_as_current_span("gap_to_top")
def gap_to_top_graph(log: structlog.stdlib.BoundLogger, filepath: str, filename: str, session: Session, r: int | None,
                     lap_logs: list[DriverLaps]):
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
        gap_series = calculate_gap_to_leader(lap_log, top_time_map)
        x = [lap_number for lap_number, _ in gap_series]
        y = [gap for _, gap in gap_series]
        line_style = driver_linestyle(session.event.year, lap_log.get_driver().get_number())
        ax.plot(x, y, linewidth=0.5, color=color, label=lap_log.get_driver().get_name(), linestyle=line_style)
    ax.legend(fontsize='small')
    ax.invert_yaxis()
    ax.set_ylim(top=0, bottom=60)
    ax.grid(True)
    output_path = f"{filepath}/{filename}.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    if r is not None:
        ax.set_ylim(top=0, bottom=r)
        ax.grid(True)
        output_path = f"{filepath}/{filename}_{r}.png"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.savefig(output_path, bbox_inches='tight')
        log.info(f"Saved plot to {output_path}")
    plt.close(fig)


@tracer.start_as_current_span("positions")
def positions(log: structlog.stdlib.BoundLogger, filepath: str, session: Session, lap_logs: list[DriverLaps]):
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
        line_style = driver_linestyle(session.event.year, lap_log.get_driver().get_number())
        ax.plot(x, y, linewidth=1, color=color, label=lap_log.get_driver().get_name(), linestyle=line_style)

    ax.legend(fontsize='small')
    ax.invert_yaxis()
    ax.grid(True)
    save_matplotlib(fig, filepath, log)


@tracer.start_as_current_span("speed_first_10s")
def speed_first_10s(log: structlog.stdlib.BoundLogger, filepath: str, session: Session) -> None:
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
            linestyle=driver_linestyle(session.event.year, driver_number)
        )
        v_min = min(v_min, int(car_data.Speed.min()) + 50)
        v_max = max(v_max, int(car_data.Speed.max()) + 10)
    if v_min == float('inf') or v_max == float('-inf'):
        plt.close(fig)
        return
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Speed (km/h)")
    ax.set_title("Speed for First 10 Seconds")
    ax.set_ylim(v_min, v_max)
    ax.legend()
    ax.grid()
    save_matplotlib(fig, filepath, log)


@tracer.start_as_current_span("speed_until_turn1")
def speed_until_turn1(log: structlog.stdlib.BoundLogger, filepath: str, session: Session) -> None:
    circuit_info = session.get_circuit_info()
    if circuit_info is None:
        return
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
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
            linestyle=driver_linestyle(session.event.year, driver_number)
        )
        v_min = min(v_min, int(cast(pandas.Series, car_data.Speed).min()) + 50)
        v_max = max(v_max, int(cast(pandas.Series, car_data.Speed).max()) + 10)
    if v_min == float('inf') or v_max == float('-inf'):
        plt.close(fig)
        return
    ax.set_xlabel("Distance (m)")
    ax.set_ylabel("Speed (km/h)")
    ax.set_title("Speed until Turn 1")
    ax.set_ylim(v_min, v_max)
    ax.axvline(first_corner_distance, linestyle='dotted', color='grey')
    ax.legend()
    ax.grid()
    save_matplotlib(fig, filepath, log)


@tracer.start_as_current_span("tyres")
def tyres(log: structlog.stdlib.BoundLogger, filepath: str, laps: Laps):
    """x = ラップ番号, y = 使用タイヤのドライバーごとの推移
    Args:
        log: ロガー
        filepath:
        laps: セッションの全ラップ
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    driver_laps = []
    for driver_number, grouped_laps in laps.groupby('DriverNumber'):
        grouped_laps = grouped_laps.dropna(subset=['LapNumber']).sort_values('LapNumber')
        grouped_laps = grouped_laps.drop_duplicates(subset=['LapNumber'], keep='last')
        if grouped_laps.empty:
            continue
        positions = grouped_laps.Position.dropna()
        final_position = float(positions.iloc[-1]) if not positions.empty else float('inf')
        driver_laps.append((str(driver_number), grouped_laps, final_position))
    driver_laps.sort(key=lambda item: (-int(item[1].LapNumber.max()), item[2], item[0]))

    max_lap = 0
    for y, (_, grouped_laps, _) in enumerate(driver_laps):
        previous_stint = object()
        for lap in grouped_laps.itertuples():
            lap_number = int(lap.LapNumber)
            max_lap = max(max_lap, lap_number)
            compound_color = constants.compound_color.get(str(lap.Compound).upper(), 'gray')
            rgb = mpl.colors.to_rgb(compound_color)
            luminance = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
            annotation_color = (0, 0, 0, 0.50) if luminance > 0.55 else (1, 1, 1, 0.72)
            boundary_color = '#222222' if luminance > 0.55 else '#f2f2f2'

            stint = None if pandas.isna(lap.Stint) else lap.Stint
            stint_start = previous_stint != stint
            previous_stint = stint
            tyre_age = _format_tyre_age(lap.TyreLife)
            label = tyre_age
            if stint_start:
                if pandas.isna(lap.FreshTyre):
                    tyre_state = '?'
                else:
                    tyre_state = 'N' if bool(lap.FreshTyre) else 'U'
                label = f"{tyre_age} {tyre_state}"

            ax.barh(
                y=y,
                width=1,
                left=lap_number - 0.5,
                height=0.78,
                color=compound_color,
                edgecolor=(0, 0, 0, 0.22),
                linewidth=0.35,
                zorder=2,
            )
            ax.text(
                lap_number,
                y,
                label,
                ha='center',
                va='center',
                fontsize=5.5,
                color=annotation_color,
                zorder=4,
            )
            if stint_start:
                ax.vlines(
                    lap_number - 0.5,
                    y - 0.39,
                    y + 0.39,
                    color=boundary_color,
                    linewidth=2.2,
                    zorder=3,
                )

    ax.set_yticks(range(len(driver_laps)))
    ax.set_yticklabels([driver_number for driver_number, _, _ in driver_laps])
    if max_lap:
        ax.set_xlim(0.5, max_lap + 0.5)
    ax.set_xlabel('Lap')
    ax.invert_yaxis()
    legend_elements = [mpl.patches.Patch(facecolor=color, edgecolor='black', label=compound)
                       for compound, color in constants.compound_color.items()]
    legend_elements.extend([
        mpl.lines.Line2D([0], [0], color='#222222', linewidth=2.2, label='Stint start / tyre change'),
        mpl.lines.Line2D([], [], color='none', label='Number: tyre age; N: new; U: used'),
    ])
    ax.legend(
        handles=legend_elements,
        title='Compound',
        loc='upper center',
        bbox_to_anchor=(0.5, -0.10),
        ncol=4,
        fontsize='small',
    )
    ax.set_axisbelow(True)
    ax.grid(True, axis='x', alpha=0.25)
    save_matplotlib(fig, filepath, log)


def _format_tyre_age(value: object) -> str:
    if pandas.isna(value):
        return '?'
    age = float(value)
    return str(int(age)) if age.is_integer() else f"{age:g}"


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
