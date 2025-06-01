import math
import os
from logging import Logger

import fastf1
import matplotlib as mpl
import numpy as np
import pandas
import plotly.express as px
from fastf1 import plotting
from fastf1.mvapi import CircuitInfo
from matplotlib import pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.pyplot import colormaps

import config
import util


def plot_best_laptime(session, driver_numbers: list[int], log: Logger, key: str):
    data = []
    minimum = 100
    maximum = 0
    for driver_number in driver_numbers:
        min = 100
        laps = session.laps.pick_drivers(driver_number).sort_values(by='LapNumber')
        driver_name = None
        color = None
        for i in range(0, len(laps)):
            lap = laps.iloc[i]
            if not lap.IsAccurate:
                continue
            if min > lap[key].total_seconds():
                min = lap[key].total_seconds()
                driver_name = lap.Driver
                color = config.f1_driver_info_2025.get(driver_number, {
                    "acronym": "UNDEFINED",
                    "driver": "Undefined",
                    "team": "Undefined",
                    "team_color": "#808080",
                    "t_cam": "black"
                })['team_color']
        if minimum > min:
            minimum = min
        if maximum < min:
            maximum = min
        data.append({
            'Acronym': driver_name,
            key: min,
            'Color': color
        })
    df = pandas.DataFrame(data).sort_values(key)
    fig = px.bar(
        df,
        x='Acronym',
        y=key,
        color="Acronym",
        text_auto=True,
        color_discrete_map={row["Acronym"]: row["Color"] for _, row in df.iterrows()}
    )
    fig.update_yaxes(
        range=[minimum - 0.1, maximum + 0.1],
        tickformat=".3f"  # 小数点1桁で表示
    )
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/{key}.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.write_image(output_path, width=1920, height=1080)
    log.info(f"Saved plot to {output_path}")


def plot_best_speed(session, driver_numbers: list[int], log: Logger, key: str):
    data = []
    minimum = 1000
    maximum = 0
    for driver_number in driver_numbers:
        min = 1000
        laps = session.laps.pick_drivers(driver_number).sort_values(by='LapNumber')
        driver_name = None
        color = None
        for i in range(0, len(laps)):
            lap = laps.iloc[i]
            if not lap.IsAccurate:
                continue
            if min > lap[key]:
                min = lap[key]
                driver_name = lap.Driver
                color = config.f1_driver_info_2025.get(driver_number, {
                    "acronym": "UNDEFINED",
                    "driver": "Undefined",
                    "team": "Undefined",
                    "team_color": "#808080",
                    "t_cam": "black"
                })['team_color']
        if minimum > min:
            minimum = min
        if maximum < min:
            maximum = min
        data.append({
            'Acronym': driver_name,
            key: min,
            'Color': color
        })
    df = pandas.DataFrame(data).sort_values(key)
    fig = px.bar(
        df,
        x='Acronym',
        y=key,
        color="Acronym",
        text_auto=True,
        color_discrete_map={row["Acronym"]: row["Color"] for _, row in df.iterrows()}
    )
    fig.update_yaxes(
        range=[minimum - 5, maximum + 5],
        tickformat=".1f"  # 小数点1桁で表示
    )
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/{key}.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.write_image(output_path, width=1920, height=1080)
    log.info(f"Saved plot to {output_path}")


def plot_ideal_best(session, driver_numbers: list[int], log: Logger):
    """
    y = 理論値
    x = ラップタイム
    Args:
        session: 分析対象のセッション
        driver_numbers: セッションに参加している車番一覧
        log: ロガー
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    for driver_number in driver_numbers:
        laps = session.laps.pick_drivers(driver_number).sort_values(by='LapNumber')
        driver = config.f1_driver_info_2025.get(driver_number, {
            "acronym": "UNDEFINED",
            "driver": "Undefined",
            "team": "Undefined",
            "team_color": "#808080",
            "t_cam": "black"
        })
        sec1 = 60
        sec2 = 60
        sec3 = 60
        for i in range(1, len(laps)):
            lap = laps.iloc[i]
            if not lap.IsAccurate:
                continue
            if sec1 > lap.Sector1Time.seconds:
                sec1 = lap.Sector1Time.seconds
            if sec2 > lap.Sector2Time.seconds:
                sec2 = lap.Sector2Time.seconds
            if sec3 > lap.Sector3Time.seconds:
                sec3 = lap.Sector3Time.seconds
        x = session.laps.pick_drivers(driver_number).pick_fastest().LapTime.seconds
        y = sec1 + sec2 + sec3
        ax.scatter(x, y, c=driver['team_color'])
        ax.annotate(driver['acronym'], (x, y), fontsize=9, ha='right')
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/ideal_best.png"
    util.save(fig, ax, output_path, log)


def plot_ideal_best_diff(session, driver_numbers: list[int], log: Logger):
    """
    y = 理論値 - ラップタイム
    x = ラップタイム
    Args:
        session: 分析対象のセッション
        driver_numbers: セッションに参加している車番一覧
        log: ロガー
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    for driver_number in driver_numbers:
        laps = session.laps.pick_drivers(driver_number).sort_values(by='LapNumber')
        driver = config.f1_driver_info_2025.get(driver_number, {
            "acronym": "UNDEFINED",
            "driver": "Undefined",
            "team": "Undefined",
            "team_color": "#808080",
            "t_cam": "black"
        })
        sec1 = 60
        sec2 = 60
        sec3 = 60
        for i in range(1, len(laps)):
            lap = laps.iloc[i]
            if not lap.IsAccurate:
                continue
            if sec1 > lap.Sector1Time.seconds:
                sec1 = lap.Sector1Time.seconds
            if sec2 > lap.Sector2Time.seconds:
                sec2 = lap.Sector2Time.seconds
            if sec3 > lap.Sector3Time.seconds:
                sec3 = lap.Sector3Time.seconds
        y = sec1 + sec2 + sec3
        x = y - session.laps.pick_drivers(driver_number).pick_fastest().LapTime.seconds
        ax.scatter(x, y, c=driver['team_color'])
        ax.annotate(driver['acronym'], (x, y), fontsize=9, ha='right')
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/ideal_best_diff.png"
    util.save(fig, ax, output_path, log)


def plot_gear_shift_on_track(session, driver_numbers: list[str], log: Logger):
    """
    ドライバーごとに最速ラップのシフト変化をコースマップにプロットする
    Args:
        session: 分析対象のセッション
        driver_numbers: セッションに参加している車番一覧
    """
    for driver_number in driver_numbers:
        fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
        lap = session.laps.pick_drivers(driver_number).pick_fastest()
        tel = lap.get_telemetry()
        x = np.array(tel['X'].values)
        y = np.array(tel['Y'].values)

        points = np.array([x, y]).T.reshape(-1, 1, 2)
        segments = np.concatenate([points[:-1], points[1:]], axis=1)
        gear = tel['nGear'].to_numpy().astype(float)

        cmap = colormaps['Paired']
        lc_comp = LineCollection(segments, norm=plt.Normalize(1, cmap.N + 1), cmap=cmap)
        lc_comp.set_array(gear)
        lc_comp.set_linewidth(4)

        fig.gca().add_collection(lc_comp)
        ax.axis('equal')
        ax.tick_params(labelleft=False, left=False, labelbottom=False, bottom=False)

        cbar = fig.colorbar(mappable=lc_comp, label="Gear",
                            boundaries=np.arange(1, 10))
        cbar.set_ticks(np.arange(1.5, 9.5))
        cbar.set_ticklabels(np.arange(1, 9))
        output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/shift_on_track/{driver_number}_{lap.Driver}.png"
        util.save(fig, ax, output_path, log)


def plot_speed_and_laptime(session, driver_numbers: list[int], log: Logger):
    """
    y = ラップタイム
    x = 最高速
    Args:
        session: 分析対象のセッション
        driver_numbers: セッションに参加している車番一覧
        log: ロガー
    """
    lap_times = []
    top_speeds = []
    driver_colors = []
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    for driver_number in driver_numbers:
        lap = session.laps.pick_drivers(driver_number).pick_fastest()
        if lap is None:
            continue
        car_data = lap.get_car_data()
        max_speed = car_data.Speed.max()
        top_speeds.append(max_speed)
        y = lap.LapTime.total_seconds()
        lap_times.append(y)
        ax.annotate(lap.Driver, (max_speed, y), fontsize=9, ha='right')
        driver_colors.append(config.f1_driver_info_2025.get(driver_number, {
            "acronym": "UNDEFINED",
            "driver": "Undefined",
            "team": "Undefined",
            "team_color": "#808080",
            "t_cam": "black"
        })['team_color'])

    ax.scatter(top_speeds, lap_times, c=driver_colors)
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/speed_and_laptime.png"
    util.save(fig, ax, output_path, log)


def plot_speed_distance(session, driver_numbers: list[str], circuit_info: CircuitInfo, log: Logger):
    """
    y = スピード
    x = 距離
    Args:
        session: 分析対象のセッション
        driver_numbers: セッションに参加している車番一覧
        circuit_info: サーキット情報
        log: ロガー
    """
    for driver_number in driver_numbers:
        fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)

        laps = session.laps.pick_drivers(driver_number).pick_fastest()
        car_data = laps.get_car_data().add_distance()
        team_color = fastf1.plotting.get_team_color(laps.Team,
                                                    session=session)
        camera_color = config.f1_driver_info_2025.get(int(driver_number), {
            "acronym": "UNDEFINED",
            "driver": "Undefined",
            "team": "Undefined",
            "team_color": "#808080",
            "t_cam": "black"
        })['t_cam']
        style = "solid" if camera_color == "black" else "dashed"

        ax.plot(car_data.Distance, car_data.Speed,
                color=team_color, label=laps.Driver, linestyle=style)
        v_min = car_data.Speed.min()
        v_max = car_data.Speed.max()
        ax.vlines(x=circuit_info.corners.Distance, ymin=v_min - 20, ymax=v_max + 20,
                  linestyles='dotted', colors='grey')
        for _, corner in circuit_info.corners.iterrows():
            txt = f"{corner.Number}{corner.Letter}"
            ax.text(corner.Distance, v_min - 30, txt,
                    va='center_baseline', ha='center', size='small')
        ax.set_ylim(v_min - 40, v_max + 20)

        output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/speed_distance/{driver_number}_{laps.Driver}.png"
        util.save(fig, ax, output_path, log)


def plot_speed_distance_comparison(session, driver_numbers: list[str], circuit_info: CircuitInfo, log: Logger):
    drivers_per_fig = 5
    num_groups = math.ceil(len(driver_numbers) / drivers_per_fig)

    for group_index in range(num_groups):
        fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)

        start = group_index * drivers_per_fig
        end = start + drivers_per_fig
        driver_group = driver_numbers[start:end]

        for driver_number in driver_group:
            laps = session.laps.pick_drivers(driver_number).pick_fastest()
            car_data = laps.get_car_data().add_distance()

            team_color = fastf1.plotting.get_team_color(laps.Team, session=session)
            driver_info = config.f1_driver_info_2025.get(int(driver_number), {
                "acronym": "UNDEFINED",
                "driver": "Undefined",
                "team": "Undefined",
                "team_color": "#808080",
                "t_cam": "black"
            })
            camera_color = driver_info['t_cam']
            style = "solid" if camera_color == "black" else "dashed"

            ax.plot(car_data.Distance, car_data.Speed,
                    color=team_color, label=laps.Driver, linestyle=style)

        v_min = float('inf')
        v_max = float('-inf')

        for driver_number in driver_group:
            laps = session.laps.pick_drivers(driver_number).pick_fastest()
            car_data = laps.get_car_data().add_distance()
            v_min = min(v_min, car_data.Speed.min())
            v_max = max(v_max, car_data.Speed.max())

        ax.vlines(x=circuit_info.corners.Distance, ymin=v_min - 20, ymax=v_max + 20,
                  linestyles='dotted', colors='grey')

        for _, corner in circuit_info.corners.iterrows():
            txt = f"{corner.Number}{corner.Letter}"
            ax.text(corner.Distance, v_min - 30, txt,
                    va='center_baseline', ha='center', size='small')

        ax.set_ylim(v_min - 40, v_max + 20)
        ax.legend()

        output_path = (
            f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/"
            f"{session.name.replace(' ', '')}/speed_distance/comparison/{start + 1}_{min(end, len(driver_numbers))}.png"
        )
        util.save(fig, ax, output_path, log)


def plot_speed_on_track(session, driver_numbers: list[str], log: Logger):
    """
    ドライバーごとに最速ラップのスピードをグラフにする
    Args:
        session: 分析対象のセッション
        driver_numbers: セッションに参加している車番一覧
        log: ロガー
    """
    # Uncomparable
    for driver_number in driver_numbers:
        lap = session.laps.pick_drivers(driver_number).pick_fastest()
        x = lap.telemetry['X']
        y = lap.telemetry['Y']
        color = lap.telemetry['Speed']

        points = np.array([x, y]).T.reshape(-1, 1, 2)
        segments = np.concatenate([points[:-1], points[1:]], axis=1)

        fig, ax = plt.subplots(sharex=True, sharey=True, figsize=(12.8, 7.2))
        rect = 0, 0.08, 1, 1
        fig.tight_layout(rect=rect)

        fig.subplots_adjust(left=0.1, right=0.9, top=0.9, bottom=0.12)
        ax.axis('off')

        ax.plot(lap.telemetry['X'], lap.telemetry['Y'],
                color='black', linestyle='-', linewidth=16, zorder=0)

        colormap = mpl.cm.plasma
        norm = plt.Normalize(color.min(), color.max())
        lc = LineCollection(segments, cmap=colormap, norm=norm,
                            linestyle='-', linewidth=5)

        lc.set_array(color)

        ax.add_collection(lc)
        axes = 0.25, 0.05, 0.5, 0.05

        color_bar_axes = fig.add_axes(axes)
        normalLegend = mpl.colors.Normalize(vmin=color.min(), vmax=color.max())
        mpl.colorbar.ColorbarBase(color_bar_axes, norm=normalLegend, cmap=colormap,
                                  orientation="horizontal")
        output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/speed_on_track/{driver_number}_{lap.Driver}.png"
        util.save(fig, ax, output_path, log)


def _plot_driver_telemetry(session, circuit_info, log,
                           driver_numbers, key, ylabel, value_func):
    import matplotlib.pyplot as plt
    from fastf1 import plotting

    group_size = 5
    for i in range(0, len(driver_numbers), group_size):
        group = driver_numbers[i:i + group_size]
        fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)

        v_min, v_max = float('inf'), float('-inf')

        for driver_number in group:
            laps = session.laps.pick_drivers(driver_number).pick_fastest()
            if laps.empty:
                continue

            car_data = laps.get_car_data().add_distance()
            driver_name = laps.Driver
            team_color = plotting.get_team_color(laps.Team, session=session)
            camera_color = config.f1_driver_info_2025.get(int(driver_number), {}).get('t_cam', 'black')
            linestyle = 'solid' if camera_color == 'black' else 'dashed'

            y_data = value_func(car_data)
            ax.plot(car_data.Distance, y_data, label=driver_name,
                    color=team_color, linestyle=linestyle)

            v_min = min(v_min, y_data.min())
            v_max = max(v_max, y_data.max())

        # コーナー線と番号
        for _, corner in circuit_info.corners.iterrows():
            ax.axvline(x=corner.Distance, linestyle='dotted', color='grey', linewidth=0.8)
            ax.text(corner.Distance, v_min - (v_max - v_min) * 0.05,
                    f"{corner.Number}{corner.Letter}",
                    va='center_baseline', ha='center', size='small')

        ax.set_ylim(v_min - 0.1 * (v_max - v_min), v_max + 0.1 * (v_max - v_min))
        ax.set_ylabel(ylabel)
        ax.set_xlabel("Distance [m]")
        ax.grid(True)
        ax.legend(loc='upper right', fontsize='small')
        plt.tight_layout()

        output_path = (
            f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/"
            f"{session.name.replace(' ', '')}/{key}/{i + 1}-{i + len(group)}.png"
        )
        util.save(fig, ax, output_path, log)
        plt.close(fig)


def plot_throttle(session, circuit_info, log):
    driver_numbers = session.laps['DriverNumber'].unique()
    driver_numbers.sort()
    _plot_driver_telemetry(
        session, circuit_info, log,
        driver_numbers,
        key='throttle',
        ylabel='Throttle [%]',
        value_func=lambda data: data.Throttle
    )


def plot_brake(session, circuit_info, log):
    driver_numbers = session.laps['DriverNumber'].unique()
    driver_numbers.sort()
    _plot_driver_telemetry(
        session, circuit_info, log,
        driver_numbers,
        key='brake',
        ylabel='Brake',
        value_func=lambda data: data.Brake.astype(float)
    )


def plot_drs(session, circuit_info, log):
    driver_numbers = session.laps['DriverNumber'].unique()
    driver_numbers.sort()
    _plot_driver_telemetry(
        session, circuit_info, log,
        driver_numbers,
        key='drs',
        ylabel='DRS',
        value_func=lambda data: data.DRS.astype(float)
    )


def plot_tyre_age_and_laptime(session, driver_numbers: list[int], log: Logger):
    """
    y = ラップタイム
    x = タイヤ使用歴
    Args:
        session: 分析対象のセッション
        driver_numbers: セッションに参加している車番一覧
        log: ロガー
    """
    lap_times = []
    tyre_life_list = []
    driver_colors = []
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    for driver_number in driver_numbers:
        lap = session.laps.pick_drivers(driver_number).pick_fastest()
        if lap is None:
            continue

        tyre_life = lap.TyreLife
        lap_times.append(lap.LapTime.total_seconds())
        tyre_life_list.append(tyre_life)
        ax.annotate(lap.Driver, (tyre_life, lap.LapTime.total_seconds()), fontsize=9, ha='right')
        driver_colors.append(config.f1_driver_info_2025.get(driver_number, {
            "acronym": "UNDEFINED",
            "driver": "Undefined",
            "team": "Undefined",
            "team_color": "#808080",
            "t_cam": "black"
        })['team_color'])

    ax.scatter(tyre_life_list, lap_times, c=driver_colors)
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/tyre_age_and_laptime.png"
    fig.gca().invert_yaxis()
    util.save(fig, ax, output_path, log)
