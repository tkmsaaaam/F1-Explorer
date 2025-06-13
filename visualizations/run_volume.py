import os
from logging import Logger

import pandas
from fastf1.core import Session
from matplotlib import pyplot as plt
from plotly import graph_objects

import config
import util


def plot_lap_number_by_timing(session: Session, driver_numbers: list[int], log: Logger):
    """
    y = ラップ番号
    x = 時間
    Args:
        session: 分析対象のセッション
        driver_numbers: セッションに参加している車番一覧
        log: ロガー
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    legends = []
    for driver_number in driver_numbers:
        laps = session.laps.pick_drivers(driver_number).sort_values(by='LapNumber')
        d = config.f1_driver_info_2025.get(driver_number, {
            "acronym": "UNDEFINED",
            "driver": "Undefined",
            "team": "Undefined",
            "team_color": "#808080",
            "t_cam": "black"
        })
        stint_number = 0
        x = []
        y = []
        for i in range(1, len(laps)):
            lap = laps.iloc[i]
            if not lap.IsAccurate:
                continue
            stint = int(lap.Stint)
            if stint_number != stint and len(x) > 0 and len(y) > 0:
                if driver_number in legends:
                    ax.plot(x, y)
                else:
                    ax.plot(x, y, color=d["team_color"], linestyle="solid" if d["t_cam"] == "black" else "dashed",
                            label=d["acronym"])
                    legends.append(driver_number)
                x = []
                y = []
            if not pandas.isna(lap.LapStartDate):
                x.append(lap.LapStartDate)
                y.append(lap.LapNumber)
            stint_number = stint
        if len(x) > 0 and len(y) > 0:
            if driver_number in legends:
                ax.plot(x, y)
            else:
                ax.plot(x, y, color=d["team_color"], linestyle="solid" if d["t_cam"] == "black" else "dashed",
                        label=d["acronym"])
                legends.append(driver_number)
    if ax.get_legend() is not None:
        ax.legend()
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/lap_number_by_timing.png"
    util.save(fig, ax, output_path, log)


def plot_laptime(session: Session, log: Logger):
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


def plot_laptime_by_lap_number(session: Session, driver_numbers: list[int], log: Logger):
    """
    y = ラップタイム
    x = ラップ番号
    Args:
        session: 分析対象のセッション
        driver_numbers: セッションに参加している車番一覧
        log: ロガー
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    legends = []
    for driver_number in driver_numbers:
        laps = session.laps.pick_drivers(driver_number).sort_values(by='LapNumber')
        d = config.f1_driver_info_2025.get(driver_number, {
            "acronym": "UNDEFINED",
            "driver": "Undefined",
            "team": "Undefined",
            "team_color": "#808080",
            "t_cam": "black"
        })
        stint_number = 0
        x = []
        y = []
        for i in range(1, len(laps)):
            lap = laps.iloc[i]
            if not lap.IsAccurate:
                continue
            stint = int(lap.Stint)
            if stint_number != stint and len(x) > 0 and len(y) > 0:
                if driver_number in legends:
                    ax.plot(x, y)
                else:
                    ax.plot(x, y, color=d["team_color"], linestyle="solid" if d["t_cam"] == "black" else "dashed",
                            label=d["acronym"])
                    legends.append(driver_number)
                x = []
                y = []
            x.append(lap.LapNumber)
            y.append(lap.LapTime.seconds)
            stint_number = stint
        if len(x) > 0 and len(y) > 0:
            if driver_number in legends:
                ax.plot(x, y)
            else:
                ax.plot(x, y, color=d["team_color"], linestyle="solid" if d["t_cam"] == "black" else "dashed",
                        label=d["acronym"])
                legends.append(driver_number)
    minimum = session.laps.LapTime.min().seconds
    ax.set_ylim(top=minimum, bottom=minimum * 1.25)
    ax.legend()
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/laptime_by_lap_number.png"
    util.save(fig, ax, output_path, log)


def plot_laptime_by_timing(session: Session, driver_numbers: list[int], log: Logger):
    """
    y = ラップタイム
    x = 時間
    Args:
        session: 分析対象のセッション
        driver_numbers: セッションに参加している車番一覧
        log: ロガー
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    legends = []
    for driver_number in driver_numbers:
        laps = session.laps.pick_drivers(driver_number).sort_values(by='LapNumber')
        d = config.f1_driver_info_2025.get(driver_number, {
            "acronym": "UNDEFINED",
            "driver": "Undefined",
            "team": "Undefined",
            "team_color": "#808080",
            "t_cam": "black"
        })
        stint_number = 0
        x = []
        y = []
        for i in range(1, len(laps)):
            lap = laps.iloc[i]
            if not lap.IsAccurate:
                continue
            stint = int(lap.Stint)
            if stint_number != stint and len(x) > 0 and len(y) > 0:
                if driver_number in legends:
                    ax.plot(x, y)
                else:
                    ax.plot(x, y, color=d["team_color"], linestyle="solid" if d["t_cam"] == "black" else "dashed",
                            label=d["acronym"])
                    legends.append(driver_number)
                x = []
                y = []
            if not pandas.isna(lap.LapStartDate):
                x.append(lap.LapStartDate)
                y.append(lap.LapTime.seconds)
            stint_number = stint
        if len(x) > 0 and len(y) > 0:
            if driver_number in legends:
                ax.plot(x, y)
            else:
                ax.plot(x, y, color=d["team_color"], linestyle="solid" if d["t_cam"] == "black" else "dashed",
                        label=d["acronym"])
                legends.append(driver_number)
    minimum = session.laps.LapTime.min().seconds
    ax.set_ylim(top=minimum, bottom=minimum * 1.25)
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/laptime_by_timing.png"
    ax.invert_yaxis()
    if ax.get_legend() is not None:
        ax.legend()
    util.save(fig, ax, output_path, log)
