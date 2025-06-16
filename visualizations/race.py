import datetime
import os
from logging import Logger

import fastf1
import pandas as pd
from fastf1 import plotting
from fastf1.core import Session, Laps
from fastf1.ergast.structure import Drivers
from matplotlib import pyplot as plt
from matplotlib.patches import Patch

import config
import util


def execute(session: Session, log: Logger, images_path: str, logs_path: str):
    laptime(session.laps, log, f"{images_path}/laptime.png", session)
    laptime_diff(session.laps, log, f"{images_path}/laptime_diffs.png", session)
    gap_to_ahead(session.laps, log, f"{images_path}/gap_ahead.png", session)
    gap_to_top(session.laps, log, f"{images_path}/gap_top.png", session)
    positions(session.laps, log, f"{images_path}/position.png", session)
    tyres(session.laps, session.drivers, log, f"{images_path}/tyres.png")
    write_messages(session, logs_path)
    write_track_status(session, logs_path)
    try:
        os.remove(f"{logs_path}/timestamp.txt")
    except FileNotFoundError:
        pass
    util.write_to_file_top(f"{logs_path}/timestamp.txt", str(datetime.datetime.now()))


def laptime(laps: Laps, log: Logger, filepath: str, session: Session):
    # ドライバーごとにラップタイムを記録
    minimum = laps.sort_values(by='LapTime').iloc[0].LapTime.total_seconds()
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    grouped = session.laps.groupby(['DriverNumber'])
    for (driver_number), stint_laps in grouped:
        if len(stint_laps) < 1:
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
    ax.legend()
    ax.invert_yaxis()
    ax.set_ylim(top=minimum, bottom=minimum + 6)
    util.save(fig, ax, filepath, log)


def laptime_diff(laps: Laps, log: Logger, filepath: str, session: Session):
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    grouped = session.laps.groupby(['DriverNumber'])
    for (driver_number), stint_laps in grouped:
        if len(stint_laps) < 1:
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
    ax.legend()
    ax.invert_yaxis()
    ax.set_ylim(bottom=-0.3, top=0.3)
    util.save(fig, ax, filepath, log)


def gap_to_ahead(laps: Laps, log: Logger, filepath: str, session: Session):
    # ドライバー・ラップごとに並べる
    laps = laps.sort_values(by=['LapNumber', 'Position'])

    # ラップごとの前走車とのギャップを保持する辞書
    mapping = {}
    # 各ラップについて前走車との差を計算1
    for lap_number in laps.LapNumber.unique():
        lap_data = laps[laps.LapNumber == lap_number].copy()
        lap_data = lap_data.sort_values(by='Position')

        for i in range(1, len(lap_data)):
            current = lap_data.iloc[i]
            ahead = lap_data.iloc[i - 1]

            # 同じラップ内での差（前走車との差）
            diff = current.Time - ahead.Time

            driver_number = int(current.DriverNumber)
            if driver_number not in mapping:
                mapping[driver_number] = {}
            mapping[driver_number][lap_number] = diff.total_seconds()
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    for no, laps in mapping.items():
        if len(laps) < 1:
            continue
        driver = session.get_driver(str(no))
        line_style = "solid" if config.camera_info_2025.get(no, 'black') == "black" else "dashed"
        x = sorted(laps.keys())
        y = [laps[lap] for lap in x]
        ax.plot(x, y, color=fastf1.plotting.get_team_color(driver.TeamName, session), label=driver.Abbreviation,
                linestyle=line_style, linewidth=0.75)

    ax.legend()
    ax.invert_yaxis()
    ax.set_ylim(top=0, bottom=20)
    util.save(fig, ax, filepath, log)


def gap_to_top(laps: Laps, log: Logger, filepath: str, session: Session):
    mapping = {}
    laps.sort_values(by=['LapNumber', 'Position'])

    for lap_number in laps.LapNumber.unique():
        lap_data = laps[laps.LapNumber == lap_number].copy()
        lap_data = lap_data.sort_values(by='Position')

        for i in range(1, len(lap_data)):
            current = lap_data.iloc[i]
            top = lap_data.iloc[0]

            diff = current.Time - top.Time

            driver_number = int(current.DriverNumber)
            if driver_number not in mapping:
                mapping[driver_number] = {}
            mapping[driver_number][lap_number] = diff.total_seconds()
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    for no, laps in mapping.items():
        if len(laps) < 1:
            continue
        driver = session.get_driver(str(no))
        line_style = "solid" if config.camera_info_2025.get(no, 'black') == "black" else "dashed"
        x = sorted(laps.keys())
        y = [laps[lap] for lap in x]
        ax.plot(x, y, color=fastf1.plotting.get_team_color(driver.TeamName, session), label=driver.Abbreviation,
                linestyle=line_style, linewidth=0.75)

    ax.legend()
    ax.invert_yaxis()
    ax.set_ylim(top=0, bottom=30)
    util.save(fig, ax, filepath, log)


def positions(laps: Laps, log: Logger, filepath: str, session: Session):
    # ドライバーごとのポジションデータを構築
    position_map = {}

    for drv in laps.DriverNumber.unique():
        driver_laps = laps[laps.DriverNumber == drv]
        position_map[int(drv)] = {
            int(row.LapNumber): int(row.Position)
            for _, row in driver_laps.iterrows()
            if not pd.isna(row.Position)
        }
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    for no, laps in position_map.items():
        if len(laps) < 1:
            continue
        driver = session.get_driver(str(no))
        line_style = "solid" if config.camera_info_2025.get(no, 'black') == "black" else "dashed"
        x = sorted(laps.keys())
        y = [laps[lap] for lap in x]
        ax.plot(x, y, color=fastf1.plotting.get_team_color(driver.TeamName, session), label=driver.Abbreviation,
                linestyle=line_style, linewidth=0.75)

    ax.legend()
    ax.invert_yaxis()
    util.save(fig, ax, filepath, log)


def tyres(laps: Laps, drivers: Drivers, log: Logger, filepath: str):
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    driver_y = {}  # ドライバー → Y軸位置
    for i, driver in enumerate(drivers):
        driver_laps = laps.pick_drivers(driver)
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
    ax.legend(handles=legend_elements, title='Compound', loc='upper right')

    util.save(fig, ax, filepath, log)


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
