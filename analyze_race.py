import datetime
import os
from logging import Logger

import pandas as pd
from fastf1.core import Session, Laps
from fastf1.ergast.structure import Drivers
from matplotlib import pyplot as plt
from matplotlib.patches import Patch

import config
import util
from plotter import set_style


def execute(session: Session, log: Logger, dir_path: str):
    images = f"{dir_path}/images"
    logs = f"{dir_path}/logs"
    laptime(session.laps, log, f"{images}/laptime.png")
    laptime_diff(session.laps, log, f"{images}/laptime_diffs.png")
    gap_to_ahead(session.laps, log, f"{images}/gap_ahead.png")
    gap_to_top(session.laps, log, f"{images}/gap_top.png")
    positions(session.laps, log, f"{images}/position.png")
    tyres(session.laps, session.drivers, log, f"{images}/tyres.png")
    plot_weather(session, log, 'AirTemp', f"{images}/air_temp.png")
    plot_weather(session, log, 'TrackTemp', f"{images}/track_temp.png")
    plot_weather(session, log, 'WindSpeed', f"{images}/wind_speed.png")
    plot_weather(session, log, 'Rainfall', f"{images}/rainfall.png")
    write_messages(session, logs)
    write_track_status(session, logs)
    try:
        os.remove(f"{dir_path}/logs/timestamp.txt")
    except FileNotFoundError:
        pass
    util.write_to_file_top(f"{dir_path}/logs/timestamp.txt", str(datetime.datetime.now()))


def laptime(laps: Laps, log: Logger, filepath: str):
    # ドライバーごとにラップタイムを記録
    driver_lap_times = {}

    min = laps.sort_values(by='LapTime').iloc[0].LapTime.total_seconds()
    for drv in laps['DriverNumber'].unique():
        driver_laps = laps[laps['DriverNumber'] == drv].sort_values(by='LapNumber')
        lap_times = {
            int(lap.LapNumber): lap.LapTime.total_seconds()
            for _, lap in driver_laps.iterrows()
            if pd.notna(lap.LapTime)
        }
        driver_lap_times[int(drv)] = lap_times
    fig, ax = plt.subplots(figsize=(12, 8))
    plt.style.use('dark_background')
    for no, laps in driver_lap_times.items():
        style = set_style(no)
        x = sorted(laps.keys())
        y = [laps[lap] for lap in x]
        ax.plot(x, y, **style)
    ax.legend()
    ax.invert_yaxis()
    ax.set_ylim(top=min, bottom=min + 10)
    plt.tight_layout()
    plt.savefig(filepath, dpi=450, bbox_inches='tight')
    log.info(f"Saved plot to {filepath}")


def laptime_diff(laps: Laps, log: Logger, filepath: str):
    lap_delta_map = {}

    for drv in laps['DriverNumber'].unique():
        driver_laps = laps[laps['DriverNumber'] == drv].sort_values(by='LapNumber')
        deltas = {}
        for i in range(1, len(driver_laps)):
            curr_lap = driver_laps.iloc[i]
            prev_lap = driver_laps.iloc[i - 1]

            if pd.notna(curr_lap.LapTime) and pd.notna(prev_lap.LapTime):
                delta = curr_lap.LapTime.total_seconds() - prev_lap.LapTime.total_seconds()
                deltas[int(curr_lap.LapNumber)] = delta

        lap_delta_map[int(drv)] = deltas
    fig, ax = plt.subplots(figsize=(12, 8))
    plt.style.use('dark_background')
    for no, laps in lap_delta_map.items():
        style = set_style(no)
        x = sorted(laps.keys())
        y = [laps[lap] for lap in x]
        ax.plot(x, y, **style)
    ax.legend()
    ax.invert_yaxis()
    ax.set_ylim(bottom=-1, top=1)
    plt.tight_layout()
    plt.savefig(filepath, dpi=450, bbox_inches='tight')
    log.info(f"Saved plot to {filepath}")


def gap_to_ahead(laps: Laps, log: Logger, filepath: str):
    # ドライバー・ラップごとに並べる
    laps = laps.sort_values(by=['LapNumber', 'Position'])

    # ラップごとの前走車とのギャップを保持する辞書
    gap_to_ahead = {}
    # 各ラップについて前走車との差を計算
    for lap_number in laps['LapNumber'].unique():
        lap_data = laps[laps['LapNumber'] == lap_number].copy()
        lap_data = lap_data.sort_values(by='Position')

        for i in range(1, len(lap_data)):
            current = lap_data.iloc[i]
            ahead = lap_data.iloc[i - 1]

            # 同じラップ内での差（前走車との差）
            diff = current['Time'] - ahead['Time']

            driver_number = int(current['DriverNumber'])
            if driver_number not in gap_to_ahead:
                gap_to_ahead[driver_number] = {}
            gap_to_ahead[driver_number][lap_number] = diff.total_seconds()
    fig, ax = plt.subplots(figsize=(12, 8))
    plt.style.use('dark_background')
    for no, laps in gap_to_ahead.items():
        style = set_style(no)
        x = sorted(laps.keys())
        y = [laps[lap] for lap in x]
        ax.plot(x, y, **style)
    ax.legend()
    ax.invert_yaxis()
    ax.set_ylim(top=0)
    plt.tight_layout()
    plt.savefig(filepath, dpi=450, bbox_inches='tight')
    log.info(f"Saved plot to {filepath}")


def gap_to_top(laps: Laps, log: Logger, filepath: str):
    gap_to_top = {}
    laps.sort_values(by=['LapNumber', 'Position'])

    for lap_number in laps['LapNumber'].unique():
        lap_data = laps[laps['LapNumber'] == lap_number].copy()
        lap_data = lap_data.sort_values(by='Position')

        for i in range(1, len(lap_data)):
            current = lap_data.iloc[i]
            top = lap_data.iloc[0]

            diff = current['Time'] - top['Time']

            driver_number = int(current['DriverNumber'])
            if driver_number not in gap_to_top:
                gap_to_top[driver_number] = {}
            gap_to_top[driver_number][lap_number] = diff.total_seconds()
    fig, ax = plt.subplots(figsize=(12, 8))
    plt.style.use('dark_background')
    for no, laps in gap_to_top.items():
        style = set_style(no)
        x = sorted(laps.keys())
        y = [laps[lap] for lap in x]
        ax.plot(x, y, **style)
    ax.legend()
    ax.invert_yaxis()
    plt.tight_layout()
    plt.savefig(filepath, dpi=450, bbox_inches='tight')
    log.info(f"Saved plot to {filepath}")


def positions(laps: Laps, log: Logger, filepath: str):
    # ドライバーごとのポジションデータを構築
    position_map = {}

    for drv in laps['DriverNumber'].unique():
        driver_laps = laps[laps['DriverNumber'] == drv]
        position_map[drv] = {
            int(row.LapNumber): int(row.Position)
            for _, row in driver_laps.iterrows()
            if not pd.isna(row.Position)
        }
    fig, ax = plt.subplots(figsize=(12, 8))
    plt.style.use('dark_background')
    for no, laps in position_map.items():
        style = set_style(int(no))
        x = sorted(laps.keys())
        y = [laps[lap] for lap in x]
        ax.plot(x, y, **style)
    ax.legend()
    ax.invert_yaxis()
    plt.tight_layout()
    plt.savefig(filepath, dpi=450, bbox_inches='tight')
    log.info(f"Saved plot to {filepath}")


def tyres(laps: Laps, drivers: Drivers, log: Logger, filepath: str):
    # プロット準備
    fig, ax = plt.subplots(figsize=(12, 8))
    driver_y = {}  # ドライバー → Y軸位置
    for i, driver in enumerate(drivers):
        driver_laps = laps.pick_drivers(driver)
        driver_laps = driver_laps[~driver_laps['Compound'].isnull()]  # Compoundがあるラップのみ

        prev_compound = None
        stint_start = None

        driver_y[driver] = i
        y = i

        for _, lap in driver_laps.iterrows():
            compound = lap['Compound']
            lap_number = lap['LapNumber']

            if prev_compound is None:
                prev_compound = compound
                stint_start = lap_number
            elif compound != prev_compound:
                # スティント終了、プロット
                edge = 'gray'
                if 'New' in lap and lap['New'] == True:
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
            if 'New' in driver_laps.iloc[-1] and driver_laps.iloc[-1]['New'] == True:
                edge = 'black'
            ax.barh(y=y,
                    width=driver_laps.iloc[-1]['LapNumber'] - stint_start + 1,
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

    plt.tight_layout()
    plt.savefig(filepath, dpi=450, bbox_inches='tight')
    log.info(f"Saved plot to {filepath}")


def plot_weather(session: Session, log: Logger, key: str, filepath: str):
    fig, ax = plt.subplots(figsize=(10, 6))
    plt.style.use('dark_background')
    weather = session.weather_data.sort_values('Time')

    x = list((session.date + weather['Time']).values)
    y = weather[key].to_list()
    ax.plot(x, y)
    ax.invert_yaxis()
    plt.tight_layout()
    plt.gcf().autofmt_xdate()
    plt.savefig(filepath, dpi=300, bbox_inches='tight')
    log.info(f"Saved plot to {filepath}")


def write_messages(session: Session, logs_path: str):
    try:
        os.remove(f"{logs_path}/race_control.txt")
    except FileNotFoundError:
        pass
    messages = session.race_control_messages.sort_values('Time')
    for i in range(0, len(messages)):
        t = session.race_control_messages['Time'].iloc[i]
        l = session.race_control_messages['Lap'].iloc[i]
        c = session.race_control_messages['Category'].iloc[i]
        f = session.race_control_messages['Flag'].iloc[i]
        s = session.race_control_messages['Scope'].iloc[i]
        n = session.race_control_messages['RacingNumber'].iloc[i]
        m = session.race_control_messages['Message'].iloc[i]
        message = util.join_with_colon(str(t), str(l), str(c), str(f), str(s), str(n), str(m))
        util.write_to_file_top(f"{logs_path}/race_control.txt", message)


def write_track_status(session: Session, logs_path: str):
    try:
        os.remove(f"{logs_path}/track_status.txt")
    except FileNotFoundError:
        pass
    messages = session.track_status.sort_values('Time')
    for i in range(0, len(messages)):
        t = session.race_control_messages['Time'].iloc[i]
        s = session.race_control_messages['Status'].iloc[i]
        m = session.race_control_messages['Message'].iloc[i]
        message = util.join_with_colon(str(t), str(s), str(m))
        util.write_to_file_top(f"{logs_path}/track_status.txt", message)
