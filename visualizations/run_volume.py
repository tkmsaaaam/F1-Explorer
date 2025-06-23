import os
from logging import Logger

import fastf1.plotting
from fastf1.core import Session
from matplotlib import pyplot as plt
from plotly import graph_objects

import config
import util


def plot_lap_number_by_timing(session: Session, log: Logger):
    """
    y = ラップ番号
    x = 時間
    Args:
        session: 分析対象のセッション
        log: ロガー
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    grouped = session.laps.groupby(['Stint', 'DriverNumber'])
    for (stint_num, driver_number), stint_laps in grouped:
        if len(stint_laps) < 1:
            continue
        driver_name = stint_laps.Driver.iloc[0]
        color = fastf1.plotting.get_team_color(stint_laps.Team.iloc[0], session)
        stint_laps = stint_laps.sort_values(by='LapNumber')
        lap_numbers = stint_laps['LapNumber']
        lap_starts = stint_laps['LapStartDate']
        if stint_num == 1:
            ax.plot(lap_starts, lap_numbers, color=color,
                    linestyle="solid" if config.camera_info_2025.get(int(driver_number),
                                                                     'black') == "black" else "dashed",
                    label=driver_name)
        else:
            ax.plot(lap_starts, lap_numbers, color=color,
                    linestyle="solid" if config.camera_info_2025.get(int(driver_number),
                                                                     'black') == "black" else "dashed")
    ax.legend(fontsize='small')
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/lap_number_by_timing.png"
    util.save(fig, ax, output_path, log)


def plot_laptime(session: Session, log: Logger):
    """
    ラップごとのタイムの一覧を作成する
    Args:
        session: セッション
        log: ロガー
    """
    laps = session.laps
    header = ["Lap"] + [session.get_driver(driver_number)['Abbreviation'] for driver_number in session.drivers]

    max_laps = max(len(laps[laps['DriverNumber'] == d]) for d in session.drivers)
    lap_numbers = list(range(1, max_laps + 1))
    data_rows = [lap_numbers]
    fill_colors = [["#f0f0f0"] * max_laps]

    for driver in header:
        if driver == 'Lap':
            continue
        driver_laps = laps[laps['Driver'] == driver].sort_values(by='LapNumber')
        lap_times = []
        bg_colors = []
        for i in range(0, len(driver_laps)):
            lap = driver_laps.iloc[i]
            lap_times.append(lap.LapTime.total_seconds())
            compound = lap.Compound
            bg_colors.append(config.compound_colors.get(compound, "#dddddd"))
        if len(driver_laps) < max_laps:
            for i in range(0, max_laps - len(driver_laps)):
                lap_times.append("")
                bg_colors.append("#f0f0f0")
        data_rows.append(lap_times)
        fill_colors.append(bg_colors)

    # テーブル描画
    fig = graph_objects.Figure(data=[graph_objects.Table(
        header=dict(values=header, fill_color='lightgrey', align='center'),
        cells=dict(values=data_rows, fill_color=fill_colors, align='center')
    )])
    fig.update_layout(
        autosize=True,
        margin=dict(autoexpand=True)
    )

    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/laptimes.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.write_image(output_path, width=1920, height=1620)
    log.info(f"Saved plot to {output_path}")


def plot_laptime_by_lap_number(session: Session, log: Logger):
    """
    y = ラップタイム
    x = ラップ番号
    Args:
        session: 分析対象のセッション
        log: ロガー
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    grouped = session.laps.groupby(['DriverNumber'])
    for _, stint_laps in grouped:
        if len(stint_laps) < 1:
            continue
        driver_name = stint_laps.Driver.iloc[0]
        color = fastf1.plotting.get_team_color(stint_laps.Team.iloc[0], session)
        stint_laps = stint_laps.sort_values(by='LapNumber')
        lap_times = stint_laps['LapTime'].dt.total_seconds().tolist()
        lap_numbers = stint_laps['LapNumber']
        ax.plot(lap_numbers, lap_times, color=color,
                linestyle="solid" if config.camera_info_2025.get(stint_laps.DriverNumber.iloc[0],
                                                                 'black') == "black" else "dashed",
                label=driver_name)
    minimum = session.laps.LapTime.min().total_seconds()
    ax.set_ylim(top=minimum, bottom=minimum * 1.25)
    ax.legend(fontsize='small')
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/laptime_by_lap_number.png"
    util.save(fig, ax, output_path, log)


def plot_laptime_by_timing(session: Session, log: Logger):
    """
    y = ラップタイム
    x = 時間
    Args:
        session: 分析対象のセッション
        log: ロガー
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    grouped = session.laps.groupby(['DriverNumber'])
    for _, stint_laps in grouped:
        if len(stint_laps) < 1:
            continue
        driver_name = stint_laps.Driver.iloc[0]
        color = fastf1.plotting.get_team_color(stint_laps.Team.iloc[0], session)
        stint_laps = stint_laps.sort_values(by='LapNumber')
        lap_times = stint_laps['LapTime'].dt.total_seconds().tolist()
        lap_starts = stint_laps['LapStartDate']
        ax.plot(lap_starts, lap_times, color=color,
                linestyle="solid" if config.camera_info_2025.get(stint_laps.DriverNumber.iloc[0],
                                                                 'black') == "black" else "dashed",
                label=driver_name)
    minimum = session.laps.LapTime.min().seconds
    ax.set_ylim(top=minimum, bottom=minimum * 1.25)
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/laptime_by_timing.png"
    ax.legend(fontsize='small')
    util.save(fig, ax, output_path, log)
