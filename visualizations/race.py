import datetime
import os
from logging import Logger

import fastf1
import pandas as pd
from fastf1 import plotting
from fastf1.core import Session
from matplotlib import pyplot as plt
from matplotlib.patches import Patch
from plotly import graph_objects

import config
import util


def execute(session: Session, log: Logger, images_path: str, logs_path: str, lap_time_range: int | None,
            gap_top_range: int | None,
            gap_ahead_range: int | None):
    laptime(log, images_path, "laptime", session, lap_time_range)
    laptime_diff(log, f"{images_path}/laptime_diffs.png", session)
    gap(log, f"{images_path}/gap.png", session)
    gap_to_ahead(log, images_path, "gap_ahead", session, gap_ahead_range)
    gap_to_top(log, images_path, "gap_top", session, gap_top_range)
    positions(log, f"{images_path}/position.png", session)
    tyres(session, log, f"{images_path}/tyres.png")
    write_messages(session, logs_path)
    write_track_status(session, logs_path)
    try:
        os.remove(f"{logs_path}/timestamp.txt")
    except FileNotFoundError:
        pass
    util.write_to_file_top(f"{logs_path}/timestamp.txt", str(datetime.datetime.now()))


def laptime(log: Logger, filepath: str, filename: str, session: Session, r: int):
    """
    x = ラップ番号, y = ラップタイムのドライバーごとの推移
    Args:
        log: ロガー
        filepath: 画像を保存する先のpath
        filename: ファイル名
        session: セッション
        r: y軸の幅
    """
    minimum = session.laps.sort_values(by='LapTime').iloc[0].LapTime.total_seconds()
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    grouped = session.laps.groupby(['DriverNumber'])
    for _, stint_laps in grouped:
        if stint_laps.empty:
            continue
        driver_name = stint_laps.Driver.iloc[0]
        color = fastf1.plotting.get_team_color(stint_laps.Team.iloc[0], session)
        stint_laps = stint_laps.sort_values(by='LapNumber')
        lap_times = stint_laps['LapTime'].dt.total_seconds().tolist()
        lap_numbers = stint_laps['LapNumber']
        ax.plot(lap_numbers, lap_times, color=color,
                linestyle="solid" if config.camera_info_2025.get(int(stint_laps.DriverNumber.iloc[0]),
                                                                 'black') == "black" else "dashed",
                label=driver_name)
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


def laptime_diff(log: Logger, filepath: str, session: Session):
    """
    x = ラップ番号, y = ラップタイム-前のラップタイムのドライバーごとの推移
    Args:
        log: ロガー
        filepath: 画像を保存する先のpathとファイル名
        session: セッション
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    grouped = session.laps.groupby(['DriverNumber'])
    for _, stint_laps in grouped:
        if stint_laps.empty:
            continue
        driver_name = stint_laps.Driver.iloc[0]
        color = fastf1.plotting.get_team_color(stint_laps.Team.iloc[0], session)
        stint_laps = stint_laps.sort_values(by='LapNumber')
        lap_times = [
            stint_laps.LapTime.iloc[i].total_seconds() - stint_laps.LapTime.iloc[i - 1].total_seconds()
            for i in range(1, len(stint_laps) - 1)
        ]
        lap_numbers = [stint_laps.LapNumber.iloc[i] for i in range(1, len(stint_laps) - 1)]
        ax.plot(lap_numbers, lap_times, color=color,
                linestyle="solid" if config.camera_info_2025.get(stint_laps.DriverNumber.iloc[0],
                                                                 'black') == "black" else "dashed",
                label=driver_name)
    ax.legend(fontsize='small')
    ax.invert_yaxis()
    ax.set_ylim(bottom=-0.3, top=0.3)
    ax.grid(True)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    fig.savefig(filepath, bbox_inches='tight')
    log.info(f"Saved plot to {filepath}")
    plt.close(fig)


def gap(log: Logger, filepath: str, session: Session):
    """
    ラップごとのギャップの一覧を作成する
    Args:
        log: ロガー
        filepath: 画像を保存する先のpathとファイル名
        session: セッション
    """
    results = {}
    for lap_number in session.laps.LapNumber.unique():
        lap_data = session.laps[session.laps.LapNumber == lap_number].sort_values(by=['Position', 'LapNumber'])
        for i in range(0, len(lap_data)):
            current = lap_data.iloc[i]
            driver_name = current.Driver
            if driver_name not in results:
                results[driver_name] = {'gap': [], 'color': []}
            if current.Position == 1:
                results[driver_name]['gap'].append("{:.3f}".format(0))
                results[driver_name]['color'].append('#ffffff')
                continue
            ahead = lap_data.iloc[i - 1]
            diff = (current.Time - ahead.Time).total_seconds()
            results[driver_name]['gap'].append("{:.3f}".format(diff))
            if diff < 3:
                results[driver_name]['color'].append('#9966ff')
            elif diff > 20:
                results[driver_name]['color'].append('#e95464')
            else:
                results[driver_name]['color'].append('#ffffff')
    max_laps = int(session.laps.LapNumber.max())
    header = ["Lap"]
    lap_numbers = list(range(1, max_laps + 1))
    data_rows = [lap_numbers]
    fill_colors = [["#f0f0f0"] * max_laps]
    for driver_name, l in results.items():
        header.append(driver_name)
        data_rows.append(l['gap'])
        fill_colors.append(l['color'])
    fig = graph_objects.Figure(data=[graph_objects.Table(
        header=dict(values=header, fill_color='lightgrey', align='center'),
        cells=dict(values=data_rows, fill_color=fill_colors, align='center')
    )])
    fig.update_layout(
        autosize=True,
        margin=dict(autoexpand=True)
    )

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    fig.write_image(filepath, width=1920, height=1620)
    log.info(f"Saved plot to {filepath}")


def gap_to_ahead(log: Logger, filepath: str, filename: str, session: Session, r: int):
    """
    x = ラップ番号, y = 前走とのギャップのドライバーごとの推移
    Args:
        log: ロガー
        filepath: 画像を保存する先のpath
        filename: 画像名
        session: セッション
        r: y軸の幅
    """
    mapping = {}
    for lap_number in session.laps.sort_values(by=['LapNumber', 'Position']).LapNumber.unique():
        lap_data = session.laps[session.laps.LapNumber == lap_number].sort_values(by='Position')

        for i in range(1, len(lap_data)):
            current = lap_data.iloc[i]
            ahead = lap_data.iloc[i - 1]
            diff = current.Time - ahead.Time
            driver_number = int(current.DriverNumber)
            if driver_number not in mapping:
                mapping[driver_number] = {}
            mapping[driver_number][lap_number] = diff.total_seconds()
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for no, laps in mapping.items():
        if len(laps) < 1:
            continue
        driver = session.get_driver(str(no))
        line_style = "solid" if config.camera_info_2025.get(no, 'black') == "black" else "dashed"
        x = sorted(laps.keys())
        y = [laps[lap] for lap in x]
        ax.plot(x, y, color=fastf1.plotting.get_team_color(driver.TeamName, session), label=driver.Abbreviation,
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


def gap_to_top(log: Logger, filepath: str, filename: str, session: Session, r: int):
    """
    x = ラップ番号, y = トップとのギャップのドライバーごとの推移
    Args:
        log: ロガー
        filepath: 画像を保存する先のpath
        filename: ファイル名
        session: セッション
        r: y軸の幅
    """
    mapping = {}
    for lap_number in session.laps.sort_values(by=['LapNumber', 'Position']).LapNumber.unique():
        lap_data = session.laps[session.laps.LapNumber == lap_number].sort_values(by='Position')

        for i in range(1, len(lap_data)):
            current = lap_data.iloc[i]
            top = lap_data.iloc[0]

            diff = current.Time - top.Time

            driver_number = int(current.DriverNumber)
            if driver_number not in mapping:
                mapping[driver_number] = {}
            mapping[driver_number][lap_number] = diff.total_seconds()
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for no, laps in mapping.items():
        if len(laps) < 1:
            continue
        driver = session.get_driver(str(no))
        line_style = "solid" if config.camera_info_2025.get(no, 'black') == "black" else "dashed"
        x = sorted(laps.keys())
        y = [laps[lap] for lap in x]
        ax.plot(x, y, color=fastf1.plotting.get_team_color(driver.TeamName, session), label=driver.Abbreviation,
                linestyle=line_style, linewidth=1)

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


def positions(log: Logger, filepath: str, session: Session):
    """
    x = ラップ番号, y = ポジションのドライバーごとの推移
    Args:
        log: ロガー
        filepath: 画像を保存する先のpathとファイル名
        session: セッション
    """
    position_map = {}
    for drv in session.laps.DriverNumber.unique():
        driver_laps = session.laps[session.laps.DriverNumber == drv]
        position_map[int(drv)] = {
            int(row.LapNumber): int(row.Position)
            for _, row in driver_laps.iterrows()
            if not pd.isna(row.Position)
        }
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for no, laps in position_map.items():
        if len(laps) < 1:
            continue
        driver = session.get_driver(str(no))
        line_style = "solid" if config.camera_info_2025.get(no, 'black') == "black" else "dashed"
        x = sorted(laps.keys())
        y = [laps[lap] for lap in x]
        ax.plot(x, y, color=fastf1.plotting.get_team_color(driver.TeamName, session), label=driver.Abbreviation,
                linestyle=line_style, linewidth=1)

    ax.legend(fontsize='small')
    ax.invert_yaxis()
    ax.grid(True)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    fig.savefig(filepath, bbox_inches='tight')
    log.info(f"Saved plot to {filepath}")
    plt.close(fig)


def tyres(session: Session, log: Logger, filepath: str):
    """
    x = ラップ番号, y = 使用タイヤのドライバーごとの推移
    Args:
        log: ロガー
        filepath: 画像を保存する先のpathとファイル名
        session: セッション
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    driver_y = {}  # ドライバー → Y軸位置
    for i, driver in enumerate(session.drivers):
        driver_laps = session.laps.pick_drivers(driver)
        driver_laps = driver_laps[~driver_laps.Compound.isnull()]  # Compoundがあるラップのみ

        prev_compound = None
        stint_start = None

        driver_y[driver] = i
        y = i

        for _, lap in driver_laps.iterrows():
            compound = lap.Compound
            lap_number = lap.LapNumber

            if prev_compound is None:
                prev_compound = compound
                stint_start = lap_number
            elif compound != prev_compound:
                # スティント終了、プロット
                edge = 'gray'
                if 'New' in lap and lap.New == True:
                    edge = 'black'
                ax.barh(y=y,
                        width=lap_number - stint_start,
                        left=stint_start,
                        color=config.compound_colors.get(prev_compound, 'gray'),
                        edgecolor=edge)
                prev_compound = compound
                stint_start = lap_number

        # 最後のスティントを描画
        if stint_start is not None:
            edge = 'gray'
            if 'New' in driver_laps.iloc[-1] and driver_laps.iloc[-1].New == True:
                edge = 'black'
            ax.barh(y=y,
                    width=driver_laps.iloc[-1].LapNumber - stint_start + 1,
                    left=stint_start,
                    color=config.compound_colors.get(prev_compound, 'gray'),
                    edgecolor=edge)

    # 軸設定
    ax.set_yticks(list(driver_y.values()))
    ax.set_yticklabels(list(driver_y.keys()))

    # 凡例
    legend_elements = [Patch(facecolor=color, edgecolor='black', label=compound)
                       for compound, color in config.compound_colors.items()]
    ax.legend(handles=legend_elements, title='Compound', loc='upper right', fontsize='small')
    ax.grid(True)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    fig.savefig(filepath, bbox_inches='tight')
    log.info(f"Saved plot to {filepath}")
    plt.close(fig)


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
