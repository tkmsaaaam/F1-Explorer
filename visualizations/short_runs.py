import math
import os
from logging import Logger

import fastf1
import matplotlib as mpl
import matplotlib.cm as cm
import numpy as np
import pandas
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from fastf1 import plotting
from fastf1.core import Session
from fastf1.mvapi import CircuitInfo
from matplotlib import pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colorbar import ColorbarBase
from matplotlib.pyplot import colormaps

import config


def compute_and_save_corner_tables_plotly(
        session: Session,
        filename_base: str,
        log: Logger
):
    corners_df = session.get_circuit_info().corners
    corners = list(zip(
        corners_df['Number'].astype(str) + corners_df['Letter'].fillna(''),
        corners_df['Distance']
    ))
    corners.sort(key=lambda x: x[1])

    driver_times = {}

    for driver_number in session.drivers:
        laps = session.laps.pick_drivers(driver_number).pick_fastest()
        if laps is None or laps.empty:
            continue

        car_data = laps.get_car_data().add_distance()
        times = []
        for name, dist in corners:
            before_corner = car_data[car_data['Distance'] < dist]
            if not before_corner.empty:
                time_before = before_corner.iloc[-1]['Time'].total_seconds()
                times.append((name, dist, time_before))
        driver_times[driver_number] = times

    abbreviations = [session.get_driver(d).Abbreviation for d in session.drivers]

    # 区間タイム表
    segment_rows = []
    for i in range(1, len(corners)):
        name = corners[i][0]
        dist = corners[i][1] - corners[i - 1][1]
        row = [name, round(dist, 1)]
        for driver_number in session.drivers:
            times = driver_times.get(driver_number)
            if times and len(times) > i:
                delta = times[i][2] - times[i - 1][2]
                row.append(round(delta, 3))
            else:
                row.append(None)
        segment_rows.append(row)

    segment_header = ["corner", "distance"] + abbreviations
    segment_data = list(zip(*segment_rows))  # 転置して列ごとに

    fig_segment = go.Figure(data=[go.Table(
        header=dict(values=segment_header, fill_color='lightgrey', align='center'),
        cells=dict(values=segment_data, align='center')
    )])
    pio.write_image(fig_segment, f"{filename_base}_segments.png", width=1920, height=1080)
    log.info(f"Segment table saved to {filename_base}_segments.png")

    # 区間タイム順位表
    segment_rank_rows = []
    for row in segment_rows:
        name, dist = row[0], row[1]
        segment_times = row[2:]
        time_with_driver = [(t, d) for t, d in zip(segment_times, session.drivers) if t is not None]
        sorted_times = sorted(time_with_driver)
        time_to_rank = {d: rank + 1 for rank, (_, d) in enumerate(sorted_times)}

        rank_row = [name, dist]
        for d in session.drivers:
            rank_row.append(time_to_rank.get(d, None))
        segment_rank_rows.append(rank_row)

    rank_header = ["corner", "distance"] + abbreviations
    rank_data = list(zip(*segment_rank_rows))

    fig_segment_ranks = go.Figure(data=[go.Table(
        header=dict(values=rank_header, fill_color='lightgrey', align='center'),
        cells=dict(values=rank_data, align='center')
    )])
    pio.write_image(fig_segment_ranks, f"{filename_base}_segment_ranks.png", width=1920, height=1080)
    log.info(f"Segment rank table saved to {filename_base}_segment_ranks.png")

    # 積算タイム表
    total_rows = []
    for i in range(len(corners)):
        name = corners[i][0]
        dist = corners[i][1]
        row = [name, round(dist, 1)]
        for driver_number in session.drivers:
            times = driver_times.get(driver_number)
            if times and len(times) > i:
                row.append(round(times[i][2], 3))
            else:
                row.append(None)
        total_rows.append(row)

    total_header = ["corner", "distance"] + abbreviations
    total_data = list(zip(*total_rows))

    fig_total = go.Figure(data=[go.Table(
        header=dict(values=total_header, fill_color='lightgrey', align='center'),
        cells=dict(values=total_data, align='center')
    )])
    pio.write_image(fig_total, f"{filename_base}_totals.png", width=1920, height=1080)
    log.info(f"Total time table saved to {filename_base}_totals.png")
    # セッション最速ラップドライバーのセグメントタイムを取得
    best_driver_number = session.laps.pick_fastest().DriverNumber
    best_driver_segments = []
    best_times = driver_times.get(best_driver_number)
    if not best_times or len(best_times) < 2:
        log.warning("Fastest lap driver has insufficient segment data.")
    else:
        for i in range(1, len(best_times)):
            seg_time = best_times[i][2] - best_times[i - 1][2]
            best_driver_segments.append(seg_time)

    # ギャップ表の作成
    segment_gap_rows_to_fastest = []
    for i in range(1, len(corners)):
        name = corners[i][0]
        dist = corners[i][1] - corners[i - 1][1]
        row = [name, round(dist, 1)]
        best_time = best_driver_segments[i - 1] if i - 1 < len(best_driver_segments) else None
        for driver_number in session.drivers:
            times = driver_times.get(driver_number)
            if times and len(times) > i and best_time is not None:
                time = times[i][2] - times[i - 1][2]
                gap = round(time - best_time, 3)
                row.append(gap)
            else:
                row.append(None)
        segment_gap_rows_to_fastest.append(row)

    gap_header2 = ["corner", "distance"] + abbreviations
    gap_data2 = list(zip(*segment_gap_rows_to_fastest))

    fig_segment_gaps2 = go.Figure(data=[go.Table(
        header=dict(values=gap_header2, fill_color='lightgrey', align='center'),
        cells=dict(values=gap_data2, align='center')
    )])
    pio.write_image(fig_segment_gaps2, f"{filename_base}_gaps_to_fastest_lap.png", width=1920, height=1080)
    log.info(f"Gaps to fastest lap table saved to {filename_base}_gaps_to_fastest_lap.png")


def plot_best_laptime(session: Session, driver_numbers: list[int], log: Logger, key: str):
    data = []
    all_minimum = 100
    all_maximum = 0
    for driver_number in driver_numbers:
        minimum = 100
        laps = session.laps.pick_drivers(driver_number).sort_values(by='LapNumber')
        if laps.empty:
            continue
        driver_name = laps.Driver.iloc[0]
        color = fastf1.plotting.get_team_color(laps.Team.iloc[0], session)
        for i in range(0, len(laps)):
            lap = laps.iloc[i]
            if not lap.IsAccurate:
                continue
            if minimum > lap[key].total_seconds():
                minimum = lap[key].total_seconds()
        if minimum == 100:
            continue
        if all_minimum > minimum:
            all_minimum = minimum
        if all_maximum < minimum:
            all_maximum = minimum
        data.append({
            'Acronym': driver_name,
            key: minimum,
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
        range=[all_minimum - 0.1, all_maximum + 0.1],
        tickformat=".3f"  # 小数点1桁で表示
    )
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/{key}.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.write_image(output_path, width=1920, height=1080)
    log.info(f"Saved plot to {output_path}")


def plot_best_speed(session: Session, driver_numbers: list[int], log: Logger, key: str):
    """
    key（セクター）ごとの最高速をプロットする
    Args:
        session: セッション
        driver_numbers: ドライバーの車番一番
        log: ロガー
        key: セクター
    """
    data = []
    all_minimum = 1000
    all_maximum = 0
    for driver_number in driver_numbers:
        maximum = 0
        laps = session.laps.pick_drivers(driver_number).sort_values(by='LapNumber')
        if laps.empty:
            continue
        driver_name = laps.Driver.iloc[0]
        color = fastf1.plotting.get_team_color(laps.Team.iloc[0], session)
        for i in range(0, len(laps)):
            lap = laps.iloc[i]
            if not lap.IsAccurate:
                continue
            if maximum < lap[key]:
                maximum = lap[key]
        if maximum == 0:
            continue
        if all_minimum > maximum:
            all_minimum = maximum
        if all_maximum < maximum:
            all_maximum = maximum
        data.append({
            'Acronym': driver_name,
            key: maximum,
            'Color': color
        })
    df = pandas.DataFrame(data).sort_values(key, ascending=False)
    fig = px.bar(
        df,
        x='Acronym',
        y=key,
        color="Acronym",
        text_auto=True,
        color_discrete_map={row["Acronym"]: row["Color"] for _, row in df.iterrows()}
    )
    fig.update_yaxes(
        range=[all_minimum - 5, all_maximum + 5],
        tickformat=".1f"  # 小数点1桁で表示
    )
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/{key}.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.write_image(output_path, width=1920, height=1080)
    log.info(f"Saved plot to {output_path}")


def plot_flat_out(session: Session, log: Logger):
    driver_numbers = session.laps['DriverNumber'].unique()
    driver_numbers.sort()
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for driver_number in driver_numbers:
        lap = session.laps.pick_drivers(driver_number).pick_fastest()
        if lap is None:
            continue
        start_distance = 0
        sum_distance = 0
        start_time = 0
        sum_time = 0
        for i in range(0, len(lap.telemetry)):
            e = lap.telemetry.iloc[i]
            if e.Throttle > lap.telemetry.Throttle.max() - 3:
                if start_distance == 0:
                    start_distance = e.Distance
                    start_time = e.Time.total_seconds()
            else:
                if start_distance != 0:
                    sum_distance += e.Distance - start_distance
                    start_distance = 0
                    sum_time += e.Time.total_seconds() - start_time
                    start_time = 0
        if lap.telemetry.Throttle.iloc[-1] > lap.telemetry.Throttle.max() - 3 and start_time != 0:
            sum_distance += lap.telemetry.Distance.iloc[-1] - start_distance
            sum_time += lap.telemetry.Time.iloc[-1].total_seconds() - start_time
        x = sum_distance / lap.telemetry.Distance.iloc[-1]
        y = sum_time / (lap.telemetry.Time.iloc[-1].total_seconds() - lap.telemetry.Time.iloc[0].total_seconds())
        color = fastf1.plotting.get_team_color(lap.Team, session)
        ax.scatter(x, y, c=color)
        ax.annotate(lap.Driver, (x, y), fontsize=9, ha='right')
    ax.grid(True)
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/flat_out.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)


def plot_ideal_best(session: Session, driver_numbers: list[int], log: Logger):
    """
    y = 理論値
    x = ラップタイム
    Args:
        session: 分析対象のセッション
        driver_numbers: セッションに参加している車番一覧
        log: ロガー
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for driver_number in driver_numbers:
        laps = session.laps.pick_drivers(driver_number).sort_values(by='LapNumber')
        sec1 = 60
        sec2 = 60
        sec3 = 60
        if laps.empty:
            continue
        acronym = laps.Driver.iloc[0]
        color = fastf1.plotting.get_team_color(laps.Team.iloc[0], session)
        for i in range(1, len(laps)):
            lap = laps.iloc[i]
            if not lap.IsAccurate:
                continue
            if sec1 > lap.Sector1Time.total_seconds():
                sec1 = lap.Sector1Time.total_seconds()
            if sec2 > lap.Sector2Time.total_seconds():
                sec2 = lap.Sector2Time.total_seconds()
            if sec3 > lap.Sector3Time.total_seconds():
                sec3 = lap.Sector3Time.total_seconds()
        fastest = session.laps.pick_drivers(driver_number).pick_fastest()
        if fastest is None:
            continue
        x = fastest.LapTime.total_seconds()
        y = sec1 + sec2 + sec3
        ax.scatter(x, y, c=color)
        ax.annotate(acronym, (x, y), fontsize=9, ha='right')
    ax.grid(True)
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/ideal_best.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)


def plot_ideal_best_diff(session: Session, driver_numbers: list[int], log: Logger):
    """
    y = ラップタイム - 理論値
    x = ラップタイム
    Args:
        session: 分析対象のセッション
        driver_numbers: セッションに参加している車番一覧
        log: ロガー
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for driver_number in driver_numbers:
        laps = session.laps.pick_drivers(driver_number).sort_values(by='LapNumber')
        sec1 = 60
        sec2 = 60
        sec3 = 60
        if laps.empty:
            continue
        acronym = laps.Driver.iloc[0]
        color = fastf1.plotting.get_team_color(laps.Team.iloc[0], session)
        for i in range(1, len(laps)):
            lap = laps.iloc[i]
            if not lap.IsAccurate:
                continue
            if sec1 > lap.Sector1Time.total_seconds():
                sec1 = lap.Sector1Time.total_seconds()
            if sec2 > lap.Sector2Time.total_seconds():
                sec2 = lap.Sector2Time.total_seconds()
            if sec3 > lap.Sector3Time.total_seconds():
                sec3 = lap.Sector3Time.total_seconds()
        y = sec1 + sec2 + sec3
        fastest = session.laps.pick_drivers(driver_number).pick_fastest()
        if fastest is None:
            continue
        x = y - fastest.LapTime.total_seconds()
        ax.scatter(x, y, c=color)
        ax.annotate(acronym, (x, y), fontsize=9, ha='right')
    ax.grid(True)
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/ideal_best_diff.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)


def plot_gear_shift_on_track(session: Session, driver_numbers: list[str], log: Logger):
    """
    ドライバーごとに最速ラップのシフト変化をコースマップにプロットする
    Args:
        session: 分析対象のセッション
        driver_numbers: セッションに参加している車番一覧
        log: ロガー
    """
    for driver_number in driver_numbers:
        fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
        lap = session.laps.pick_drivers(driver_number).pick_fastest()
        if lap is None:
            continue
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
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.savefig(output_path, bbox_inches='tight')
        log.info(f"Saved plot to {output_path}")
        plt.close(fig)


def plot_speed_and_laptime(session: Session, driver_numbers: list[int], log: Logger):
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
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
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
        driver_colors.append(fastf1.plotting.get_team_color(lap.Team, session))

    ax.scatter(top_speeds, lap_times, c=driver_colors)
    ax.grid(True)
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/speed_and_laptime.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)


def plot_speed_distance(session: Session, driver_numbers: list[str], circuit_info: CircuitInfo, log: Logger):
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
        fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')

        laps = session.laps.pick_drivers(driver_number).pick_fastest()
        if laps is None:
            continue
        car_data = laps.get_car_data().add_distance()
        team_color = fastf1.plotting.get_team_color(laps.Team, session)
        style = "solid" if config.camera_info_2025.get(int(driver_number), 'black') == "black" else "dashed"

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
        ax.grid(True)
        output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/speed_distance/{driver_number}_{laps.Driver}.png"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.savefig(output_path, bbox_inches='tight')
        log.info(f"Saved plot to {output_path}")
        plt.close(fig)


def plot_speed_distance_comparison(session: Session, driver_numbers: list[str], circuit_info: CircuitInfo, log: Logger):
    """
    スピードを比較
    Args:
        session: セッション
        driver_numbers: ドライバーの車番一覧
        circuit_info: サーキット
        log: ロガー
    """
    drivers_per_fig = 5
    num_groups = math.ceil(len(driver_numbers) / drivers_per_fig)

    for group_index in range(num_groups):
        fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')

        start = group_index * drivers_per_fig
        end = start + drivers_per_fig
        driver_group = driver_numbers[start:end]

        for driver_number in driver_group:
            laps = session.laps.pick_drivers(driver_number).pick_fastest()
            if laps is None:
                continue
            car_data = laps.get_car_data().add_distance()

            team_color = fastf1.plotting.get_team_color(laps.Team, session)
            style = "solid" if config.camera_info_2025.get(int(driver_number), 'black') == "black" else "dashed"

            ax.plot(car_data.Distance, car_data.Speed,
                    color=team_color, label=laps.Driver, linestyle=style)

        v_min = float('inf')
        v_max = float('-inf')

        for driver_number in driver_group:
            laps = session.laps.pick_drivers(driver_number).pick_fastest()
            if laps is None:
                continue
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
        ax.legend(fontsize='small')
        ax.grid(True)
        output_path = (
            f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/"
            f"{session.name.replace(' ', '')}/speed_distance/comparison/{start + 1}_{min(end, len(driver_numbers))}.png"
        )
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.savefig(output_path, bbox_inches='tight')
        log.info(f"Saved plot to {output_path}")
        plt.close(fig)


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
        if lap is None:
            continue
        x = lap.telemetry['X']
        y = lap.telemetry['Y']
        color = lap.telemetry['Speed']

        points = np.array([x, y]).T.reshape(-1, 1, 2)
        segments = np.concatenate([points[:-1], points[1:]], axis=1)

        fig, ax = plt.subplots(sharex=True, sharey=True, figsize=(12.8, 7.2), layout='tight')
        rect = 0, 0.08, 1, 1
        fig.tight_layout(rect=rect)

        fig.subplots_adjust(left=0.1, right=0.9, top=0.9, bottom=0.12)
        ax.axis('off')

        ax.plot(lap.telemetry['X'], lap.telemetry['Y'],
                color='black', linestyle='-', linewidth=16, zorder=0)

        colormap = cm.get_cmap("plasma")
        norm = plt.Normalize(color.min(), color.max())
        lc = LineCollection(segments, cmap=colormap, norm=norm,
                            linestyle='-', linewidth=5)

        lc.set_array(color)

        ax.add_collection(lc)
        axes = 0.25, 0.05, 0.5, 0.05

        color_bar_axes = fig.add_axes(axes)
        normal_legend = mpl.colors.Normalize(vmin=color.min(), vmax=color.max())
        mpl.colorbar.ColorbarBase(color_bar_axes, norm=normal_legend, cmap=colormap,
                                  orientation="horizontal")
        ax.grid(True)
        output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/speed_on_track/{driver_number}_{lap.Driver}.png"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.savefig(output_path, bbox_inches='tight')
        log.info(f"Saved plot to {output_path}")
        plt.close(fig)


def _plot_driver_telemetry(session: Session, log: Logger,
                           driver_numbers: list[int], key: str, label, value_func):
    group_size = 5
    for i in range(0, len(driver_numbers), group_size):
        group = driver_numbers[i:i + group_size]
        fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')

        v_min, v_max = float('inf'), float('-inf')

        for driver_number in group:
            laps = session.laps.pick_drivers(driver_number).pick_fastest()
            if laps is None or laps.empty:
                continue

            car_data = laps.get_car_data().add_distance()
            driver_name = laps.Driver
            team_color = fastf1.plotting.get_team_color(laps.Team, session)
            camera_color = config.camera_info_2025.get(int(driver_number), 'black')
            line_style = 'solid' if camera_color == 'black' else 'dashed'

            y_data = value_func(car_data)
            ax.plot(car_data.Distance, y_data, label=driver_name,
                    color=team_color, linestyle=line_style)

            v_min = min(v_min, y_data.min())
            v_max = max(v_max, y_data.max())

        # コーナー線と番号
        for _, corner in session.get_circuit_info().corners.iterrows():
            ax.axvline(x=corner.Distance, linestyle='dotted', color='grey', linewidth=0.8)
            ax.text(corner.Distance, v_min - (v_max - v_min) * 0.05,
                    f"{corner.Number}{corner.Letter}",
                    va='center_baseline', ha='center', size='small')

        ax.set_ylim(v_min - 0.1 * (v_max - v_min), v_max + 0.1 * (v_max - v_min))
        ax.set_ylabel(label)
        ax.set_xlabel("Distance [m]")
        ax.grid(True)
        ax.legend(loc='upper right', fontsize='small')
        plt.tight_layout()

        output_path = (
            f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/"
            f"{session.name.replace(' ', '')}/{key}/{i + 1}-{i + len(group)}.png"
        )
        ax.grid(True)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.savefig(output_path, bbox_inches='tight')
        log.info(f"Saved plot to {output_path}")
        plt.close(fig)


def plot_throttle(session: Session, log: Logger):
    driver_numbers = session.laps['DriverNumber'].unique()
    _plot_driver_telemetry(
        session, log,
        driver_numbers,
        key='throttle',
        label='Throttle [%]',
        value_func=lambda data: data.Throttle
    )


def plot_brake(session: Session, log: Logger):
    driver_numbers = session.laps['DriverNumber'].unique()
    _plot_driver_telemetry(
        session, log,
        driver_numbers,
        key='brake',
        label='Brake',
        value_func=lambda data: data.Brake.astype(float)
    )


def plot_drs(session: Session, log: Logger):
    driver_numbers = session.laps['DriverNumber'].unique()
    _plot_driver_telemetry(session, log,
                           driver_numbers,
                           key='drs',
                           label='DRS',
                           value_func=lambda data: data.DRS.astype(float)
                           )


def plot_telemetry(session: Session, log: Logger,
                   driver_numbers: list[int], key: str, label, value_func):
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')

    v_min, v_max = float('inf'), float('-inf')

    name = ''
    for driver_number in driver_numbers:
        laps = session.laps.pick_drivers(driver_number).pick_fastest()
        if laps is None or laps.empty:
            continue

        car_data = laps.get_car_data().add_distance()
        driver_name = laps.Driver
        team_color = fastf1.plotting.get_team_color(laps.Team, session)
        camera_color = config.camera_info_2025.get(int(driver_number), 'black')
        line_style = 'solid' if camera_color == 'black' else 'dashed'

        y_data = value_func(car_data)
        ax.plot(car_data.Distance, y_data, label=driver_name,
                color=team_color, linestyle=line_style)

        v_min = min(v_min, y_data.min())
        v_max = max(v_max, y_data.max())
        name = name + f"{driver_name}_"

    # コーナー線と番号
    for _, corner in session.get_circuit_info().corners.iterrows():
        ax.axvline(x=corner.Distance, linestyle='dotted', color='grey', linewidth=0.8)
        ax.text(corner.Distance, v_min - (v_max - v_min) * 0.05,
                f"{corner.Number}{corner.Letter}",
                va='center_baseline', ha='center', size='small')

    ax.set_ylim(v_min - 0.1 * (v_max - v_min), v_max + 0.1 * (v_max - v_min))
    ax.set_ylabel(label)
    ax.set_xlabel("Distance [m]")
    ax.grid(True)
    ax.legend(loc='upper right', fontsize='small')
    plt.tight_layout()

    output_path = (
        f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/"
        f"{session.name.replace(' ', '')}/{key}/{name}.png"
    )
    ax.grid(True)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)


def plot_tyre_age_and_laptime(session: Session, driver_numbers: list[int], log: Logger):
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
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for driver_number in driver_numbers:
        lap = session.laps.pick_drivers(driver_number).pick_fastest()
        if lap is None:
            continue

        tyre_life = lap.TyreLife
        lap_times.append(lap.LapTime.total_seconds())
        tyre_life_list.append(tyre_life)
        ax.annotate(lap.Driver, (tyre_life, lap.LapTime.total_seconds()), fontsize=9, ha='right')
        driver_colors.append(fastf1.plotting.get_team_color(lap.Team, session))

    ax.scatter(tyre_life_list, lap_times, c=driver_colors)
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/tyre_age_and_laptime.png"
    fig.gca().invert_yaxis()
    ax.grid(True)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)
