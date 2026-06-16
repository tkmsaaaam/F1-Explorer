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
from fastf1.core import Session, Lap
from matplotlib import pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colorbar import ColorbarBase
from matplotlib.pyplot import colormaps
# noinspection PyPackageRequirements
from opentelemetry import trace

import constants

tracer = trace.get_tracer(__name__)


@tracer.start_as_current_span("compute_competitive_drivers")
def compute_competitive_drivers(session: Session, log: Logger, c: int) -> list[int]:
    """トップcチームの早い方のドライバーの車番を算出する
    Args:
        session: セッション
        log: ログ
        c: 何チームのドライバーを比較するか

    Returns:
        最速ラップ順に並べた際にトップ4チームの早い方のドライバーの車番
    """
    n = list()
    teams = set()
    for driver_number in session.drivers:
        driver = session.get_driver(driver_number)
        if driver['TeamName'] not in teams:
            n.append(driver['DriverNumber'])
            teams.add(driver['TeamName'])
            log.info(f"{len(n)}: {driver['TeamName']}'s fastest {driver['Abbreviation']}")
        if len(n) > c - 1:
            break
    return n


@tracer.start_as_current_span("compute_and_save_segment_tables_plotly")
def compute_and_save_segment_tables_plotly(
        session: Session,
        filename_base: str,
        segment_boundaries: list[float],
        log: Logger
):
    """mini segmentごとのタイムをプロットする
    Args:
        session: セッション
        filename_base: ファイル名のprefix
        segment_boundaries: セグメントの境界値一覧
        log: ロガー
    """
    segment_boundaries = sorted(segment_boundaries)
    driver_times: dict[str, list[float | None]] = {}
    abbreviations = [session.get_driver(d).Abbreviation for d in session.drivers]

    for driver_number in session.drivers:
        laps = session.laps.pick_drivers(driver_number).pick_fastest()
        if laps is None or laps.empty:
            continue

        car_data = laps.get_car_data().add_distance()
        times: list[float | None] = []
        for dist in segment_boundaries:
            before_point = car_data[car_data['Distance'] < dist]
            times.append(before_point.iloc[-1]['Time'].total_seconds() if not before_point.empty else None)
        driver_times[driver_number] = times

    circuit = session.get_circuit_info()
    if circuit is None:
        return
        # セグメント名と距離差
    segment_rows = []
    for i in range(1, len(segment_boundaries)):
        name = f"{i}"
        dist = round(segment_boundaries[i] - segment_boundaries[i - 1], 1)
        corners_df = circuit.corners
        filtered = corners_df[
            (corners_df['Distance'] >= segment_boundaries[i - 1]) & (corners_df['Distance'] <= segment_boundaries[i])
            ]
        row = [name, dist, filtered['Number'].tolist()]
        for driver_number in session.drivers:
            t = driver_times.get(driver_number)
            if t is None:
                row.append(0)
                continue
            c = t[i]
            b = t[i - 1]
            if c is None:
                row.append(0)
                continue
            if b is None:
                row.append(0)
                continue
            row.append(round(c - b, 3))
        segment_rows.append(row)

    segment_header = ["segment", "distance", "corners"] + abbreviations
    segment_data = list(zip(*segment_rows))

    fig_segment = go.Figure(data=[go.Table(
        header={'values': segment_header, 'fill_color': 'lightgrey', 'align': 'center'},
        cells={'values': segment_data, 'align': 'center'}
    )])
    fig_segment.write_image(f"{filename_base}_durations.png", width=1920, height=1080)
    log.info(f"Segment table saved to {filename_base}_durations.png")

    segment_rank_rows = []
    for row in segment_rows:
        name, dist = row[0], row[1]
        times = row[3:]
        time_with_driver = [(t, d) for t, d in zip(times, session.drivers) if t is not None]
        sorted_times = sorted(time_with_driver)
        time_to_rank = {d: rank + 1 for rank, (_, d) in enumerate(sorted_times)}
        segment_rank_rows.append([name, dist] + [time_to_rank.get(d, None) for d in session.drivers])

    rank_header = ["segment", "distance"] + abbreviations
    rank_data = list(zip(*segment_rank_rows))

    fig_ranks = go.Figure(data=[go.Table(
        header={'values': rank_header, 'fill_color': 'lightgrey', 'align': 'center'},
        cells={'values': rank_data, 'align': 'center'}
    )])
    fig_ranks.write_image(f"{filename_base}_ranks.png", width=1920, height=1080)
    log.info(f"Segment rank table saved to {filename_base}_ranks.png")

    best = session.laps.pick_fastest()
    if best is None:
        return
        # セッション最速ラップのドライバー
    best_driver_number = best.DriverNumber
    best_times = driver_times.get(best_driver_number)

    if not best_times or len(best_times) < 2:
        log.warning("Fastest lap driver has insufficient segment data.")
        return

    best_deltas = []
    for i in range(1, len(best_times)):
        c = best_times[i]
        b = best_times[i - 1]
        best_deltas.append(b - c if b is not None and c is not None else None)

    circuit = session.get_circuit_info()
    if circuit is None:
        return
    gap_rows = []
    for i in range(1, len(segment_boundaries)):
        name = f"{i}"
        dist = round(segment_boundaries[i] - segment_boundaries[i - 1], 1)
        corners_df = circuit.corners
        filtered = corners_df[
            (corners_df['Distance'] >= segment_boundaries[i - 1]) & (corners_df['Distance'] <= segment_boundaries[i])
            ]
        row = [name, dist, filtered['Number'].tolist()]
        best_time = best_deltas[i - 1]
        if best_time is None:
            continue
        for driver_number in session.drivers:
            t = driver_times.get(driver_number)
            if t is None:
                row.append(0)
                continue
            c = t[i]
            b = t[i - 1]
            if c is None:
                row.append(0)
                continue
            if b is None:
                row.append(0)
                continue
            row.append(round((c - b) - best_time, 3))
        gap_rows.append(row)

    gap_header = ["segment", "distance", "corners"] + abbreviations
    gap_data = list(zip(*gap_rows))

    fig_gap = go.Figure(data=[go.Table(
        header={'values': gap_header, 'fill_color': 'lightgrey', 'align': 'center'},
        cells={'values': gap_data, 'align': 'center'}
    )])
    fig_gap.write_image(f"{filename_base}_gaps_to_best.png", width=1920, height=1080)
    log.info(f"Gap table saved to {filename_base}_gaps_to_best.png")


@tracer.start_as_current_span("plot_best_laptime")
def plot_best_laptime(session: Session, log: Logger, key: str):
    """keyを順位で並べる
    Args:
        session: セッション
        log: ロガー
        key: 並べる対象
    """
    data = []
    for driver_number in session.drivers:
        laps = session.laps[session.laps.IsAccurate].pick_drivers(driver_number).sort_values(by='LapNumber')
        if laps.empty:
            continue
        team = laps.Team.iloc[0]
        color = 'white' if team == '' else fastf1.plotting.get_team_color(team, session)
        l = [laps.iloc[i][key].total_seconds() for i in range(0, len(laps))]
        data.append({'Acronym': laps.Driver.iloc[0], key: min(l), 'Color': color})
    if len(data) == 0:
        return
    df = pandas.DataFrame(data).sort_values(key)
    fig = px.bar(
        df,
        x='Acronym',
        y=key,
        color="Acronym",
        text_auto=True,
        color_discrete_map={row["Acronym"]: row["Color"] for _, row in df.iterrows()}
    )
    fig.update_yaxes(range=[min([i[key] for i in data]) - 0.1, max([i[key] for i in data]) + 0.1], tickformat=".3f")
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/{key}.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.write_image(output_path, width=1920, height=1080)
    log.info(f"Saved plot to {output_path}")


@tracer.start_as_current_span("plot_best_speed")
def plot_best_speed(session: Session, log: Logger, key: str):
    """key（セクター）ごとの最高速をプロットする
    Args:
        session: セッション
        log: ロガー
        key: セクター
    """
    data = []
    for driver_number in session.drivers:
        laps = session.laps[session.laps.IsAccurate].pick_drivers(driver_number).sort_values(by='LapNumber')
        if laps.empty:
            continue
        team = laps.Team.iloc[0]
        color = 'white' if team == '' else fastf1.plotting.get_team_color(team, session)
        maximum = max([laps.iloc[i][key] for i in range(0, len(laps))])
        data.append({'Acronym': laps.Driver.iloc[0], key: maximum, 'Color': color})
    df = pandas.DataFrame(data).sort_values(key, ascending=False)
    fig = px.bar(
        df,
        x='Acronym',
        y=key,
        color="Acronym",
        text_auto=True,
        color_discrete_map={row["Acronym"]: row["Color"] for _, row in df.iterrows()}
    )
    fig.update_yaxes(range=[min([i[key] for i in data]) - 5, max([i[key] for i in data]) + 5], tickformat=".1f")
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/{key}.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.write_image(output_path, width=1920, height=1080)
    log.info(f"Saved plot to {output_path}")


@tracer.start_as_current_span("plot_flat_out")
def plot_flat_out(session: Session, log: Logger):
    """全開率をプロットする
    Args:
        session: セッション
        log: ロガー
    """
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
            if e.Throttle > float(lap.telemetry.Throttle.max()) - 3:
                if start_distance == 0:
                    start_distance = e.Distance
                    start_time = e.Time.total_seconds()
            else:
                if start_distance != 0:
                    sum_distance += e.Distance - start_distance
                    start_distance = 0
                    sum_time += e.Time.total_seconds() - start_time
                    start_time = 0
        z = lap.telemetry.iloc[-1]
        if z.Throttle > float(lap.telemetry.Throttle.max()) - 3 and start_time != 0:
            sum_distance += z.Distance - start_distance
            sum_time += z.Time.total_seconds() - start_time
        x = sum_distance / z.Distance
        y = sum_time / (z.Time.total_seconds() - lap.telemetry.Time.iloc[0].total_seconds())
        try:
            color = fastf1.plotting.get_team_color(lap.Team, session)
        except AttributeError:
            color = 'gray'
        ax.scatter(x, y, c=color)
        ax.annotate(lap.Driver, (x, y), fontsize=9, ha='right')
    ax.grid(True)
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/flat_out.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)


@tracer.start_as_current_span("plot_ideal_best")
def plot_ideal_best(session: Session, log: Logger):
    """y = 理論値
    x = ラップタイム
    Args:
        session: 分析対象のセッション
        log: ロガー
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for driver_number in session.drivers:
        laps = session.laps[session.laps.IsAccurate].pick_drivers(driver_number).sort_values(by='LapNumber')
        if laps.empty:
            continue
        fastest = laps.pick_fastest()
        if fastest is None:
            continue
        x = fastest.LapTime.total_seconds()
        sec1 = min([laps.iloc[i].Sector1Time.total_seconds() for i in range(0, len(laps))])
        sec2 = min([laps.iloc[i].Sector2Time.total_seconds() for i in range(0, len(laps))])
        sec3 = min([laps.iloc[i].Sector3Time.total_seconds() for i in range(0, len(laps))])
        y = sec1 + sec2 + sec3
        acronym = laps.Driver.iloc[0]
        try:
            color = fastf1.plotting.get_team_color(laps.Team.iloc[0], session)
        except AttributeError:
            color = 'gray'
        ax.scatter(x, y, c=color)
        ax.annotate(acronym, (x, y), fontsize=9, ha='right')
    ax.grid(True)
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/ideal_best.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)


@tracer.start_as_current_span("plot_ideal_best_diff")
def plot_ideal_best_diff(session: Session, log: Logger):
    """y = ラップタイム - 理論値
    x = ラップタイム
    Args:
        session: 分析対象のセッション
        log: ロガー
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for driver_number in session.drivers:
        laps = session.laps[session.laps.IsAccurate].pick_drivers(driver_number).sort_values(by='LapNumber')
        if laps.empty:
            continue
        acronym = laps.Driver.iloc[0]
        try:
            color = fastf1.plotting.get_team_color(laps.Team.iloc[0], session)
        except AttributeError:
            color = 'gray'
        sec1 = min([laps.iloc[i].Sector1Time.total_seconds() for i in range(0, len(laps))])
        sec2 = min([laps.iloc[i].Sector2Time.total_seconds() for i in range(0, len(laps))])
        sec3 = min([laps.iloc[i].Sector3Time.total_seconds() for i in range(0, len(laps))])
        y = sec1 + sec2 + sec3
        fastest = laps.pick_fastest()
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


@tracer.start_as_current_span("plot_gear_shift_on_track")
def plot_gear_shift_on_track(session: Session, log: Logger):
    """ドライバーごとに最速ラップのシフト変化をコースマップにプロットする
    Args:
        session: 分析対象のセッション
        log: ロガー
    """
    for driver_number in session.drivers:
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

        cbar = fig.colorbar(mappable=lc_comp, label="Gear", boundaries=np.arange(1, 10))
        cbar.set_ticks(np.arange(1.5, 9.5))
        cbar.set_ticklabels(np.arange(1, 9))
        output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/shift_on_track/{driver_number}_{lap.Driver}.png"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.savefig(output_path, bbox_inches='tight')
        log.info(f"Saved plot to {output_path}")
        plt.close(fig)


@tracer.start_as_current_span("plot_speed_and_laptime")
def plot_speed_and_laptime(session: Session, log: Logger):
    """y = ラップタイム
    x = 最高速
    Args:
        session: 分析対象のセッション
        log: ロガー
    """
    lap_times = []
    top_speeds = []
    driver_colors = []
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for driver_number in session.drivers:
        lap = session.laps.pick_drivers(driver_number).pick_fastest()
        if lap is None:
            continue
        car_data = lap.get_car_data()
        max_speed: float = car_data.Speed.max()
        top_speeds.append(max_speed)
        y = lap.LapTime.total_seconds()
        lap_times.append(y)
        ax.annotate(lap.Driver, (max_speed, y), fontsize=9, ha='right')
        try:
            color = fastf1.plotting.get_team_color(lap.Team, session)
        except AttributeError:
            color = 'gray'
        driver_colors.append(color)

    ax.scatter(top_speeds, lap_times, c=driver_colors)
    ax.grid(True)
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/speed_and_laptime.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)


@tracer.start_as_current_span("plot_speed_distance")
def plot_speed_distance(session: Session, log: Logger):
    """y = スピード
    x = 距離
    Args:
        session: 分析対象のセッション
        log: ロガー
    """
    circuit_info = session.get_circuit_info()
    if circuit_info is None:
        return
    for driver_number in session.drivers:
        fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')

        laps = session.laps.pick_drivers(driver_number).pick_fastest()
        if laps is None:
            continue
        car_data = laps.get_car_data().add_distance()
        try:
            team_color = fastf1.plotting.get_team_color(laps.Team, session)
        except AttributeError:
            team_color = 'gray'
        style = "solid" if constants.camera[session.event.year].get(int(driver_number),
                                                                    'black') == "black" else "dashed"

        ax.plot(car_data.Distance, car_data.Speed, color=team_color, label=laps.Driver, linestyle=style)
        v_min: float = car_data.Speed.min()
        v_max: float = car_data.Speed.max()
        ax.vlines(x=circuit_info.corners.Distance, ymin=v_min - 20, ymax=v_max + 20, linestyles='dotted', colors='grey')
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


@tracer.start_as_current_span("plot_speed_distance_comparison")
def plot_speed_distance_comparison(session: Session, log: Logger):
    """スピードを比較
    Args:
        session: セッション
        log: ロガー
    """
    drivers_per_fig = 5
    driver_numbers = session.drivers
    num_groups = math.ceil(len(driver_numbers) / drivers_per_fig)
    circuit_info = session.get_circuit_info()
    if circuit_info is None:
        return
    for group_index in range(num_groups):
        start = group_index * drivers_per_fig
        driver_group = driver_numbers[start:] if group_index == num_groups - 1 else driver_numbers[
            start:start + drivers_per_fig]
        fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
        for driver_number in driver_group:
            laps = session.laps.pick_drivers(driver_number).pick_fastest()
            if laps is None:
                continue
            car_data = laps.get_car_data().add_distance()
            try:
                team_color = fastf1.plotting.get_team_color(laps.Team, session)
            except AttributeError:
                team_color = 'gray'
            style = "solid" if constants.camera[session.event.year].get(int(driver_number),
                                                                        'black') == "black" else "dashed"
            ax.plot(car_data.Distance, car_data.Speed,
                    color=team_color, label=laps.Driver, linestyle=style, linewidth=1, alpha=0.5)
        v_min, v_max = float('inf'), float('-inf')
        for driver_number in driver_group:
            laps = session.laps.pick_drivers(driver_number).pick_fastest()
            if laps is None:
                continue
            car_data = laps.get_car_data().add_distance()
            minimum: float = car_data.Speed.min()
            maximum: float = car_data.Speed.max()
            v_min, v_max = min(v_min, minimum), max(v_max, maximum)

        if v_min == float('inf') or v_max == float('-inf'):
            continue

        ax.vlines(x=circuit_info.corners.Distance, ymin=v_min - 20, ymax=v_max + 20, linestyles='dotted', colors='grey')

        for _, corner in circuit_info.corners.iterrows():
            txt = f"{corner.Number}{corner.Letter}"
            ax.text(corner.Distance, v_min - 30, txt, va='center_baseline', ha='center', size='small')
        ax.set_ylim(v_min - 40, v_max + 20)
        ax.legend(fontsize='small')
        ax.grid(True)
        output_path = (
            f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/"
            f"{session.name.replace(' ', '')}/speed_distance/comparison/{start + 1}_.png"
        )
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.savefig(output_path, bbox_inches='tight')
        log.info(f"Saved plot to {output_path}")
        plt.close(fig)


@tracer.start_as_current_span("plot_speed_on_track")
def plot_speed_on_track(session: Session, log: Logger):
    """ドライバーごとに最速ラップのスピードをグラフにする
    Args:
        session: 分析対象のセッション
        log: ロガー
    """
    # Uncomparable
    for driver_number in session.drivers:
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

        ax.plot(lap.telemetry['X'], lap.telemetry['Y'], color='black', linestyle='-', linewidth=16, zorder=0)

        colormap = cm.get_cmap("plasma")
        norm = plt.Normalize(color.min(), color.max())
        lc = LineCollection(segments, cmap=colormap, norm=norm, linestyle='-', linewidth=5)

        lc.set_array(color)

        ax.add_collection(lc)
        axes = 0.25, 0.05, 0.5, 0.05

        color_bar_axes = fig.add_axes(axes)
        normal_legend = mpl.colors.Normalize(vmin=color.min(), vmax=color.max())
        mpl.colorbar.ColorbarBase(color_bar_axes, norm=normal_legend, cmap=colormap, orientation="horizontal")
        ax.grid(True)
        output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/speed_on_track/{driver_number}_{lap.Driver}.png"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.savefig(output_path, bbox_inches='tight')
        log.info(f"Saved plot to {output_path}")
        plt.close(fig)


@tracer.start_as_current_span("plot_time_distance_comparison")
def plot_time_distance_comparison(session: Session, log: Logger):
    """driver_group 内最速との差分を表示する

    x = 距離（group内最速ドライバー基準）
    y = 最速との差分秒数

    各ドライバーの car_data は計測点が異なるため、
    5m ごとに線形補間して共通距離軸へ再サンプリングする。
    """
    drivers_per_fig = 5
    resample_step = 5.0  # 1 / 5 / 10 など変更可

    driver_numbers = session.drivers
    num_groups = math.ceil(len(driver_numbers) / drivers_per_fig)
    circuit_info = session.get_circuit_info()
    if circuit_info is None:
        return

    for group_index in range(num_groups):
        start = group_index * drivers_per_fig
        driver_group = driver_numbers[start:start + drivers_per_fig]
        lap_map: dict[str, Lap] = {}
        for driver_number in driver_group:
            lap = session.laps.pick_drivers(driver_number).pick_fastest()
            if lap is None:
                continue
            lap_map[str(driver_number)] = lap
        if not lap_map:
            continue
        fastest_driver_number = min(lap_map.keys(), key=lambda dn: lap_map[dn].LapTime.total_seconds())
        fastest_lap = lap_map[fastest_driver_number]
        fastest_car_data = fastest_lap.get_car_data().add_distance()
        fastest_dist = fastest_car_data["Distance"].to_numpy()
        fastest_time = np.array([t.total_seconds() for t in fastest_car_data["Time"]], dtype=float)
        uniq_idx = np.unique(fastest_dist, return_index=True)[1]
        fastest_dist = fastest_dist[np.sort(uniq_idx)]
        fastest_time = fastest_time[np.sort(uniq_idx)]
        max_distance = fastest_dist.max()
        common_distance = np.arange(0.0, max_distance, resample_step)
        ref_time = np.interp(common_distance, fastest_dist, fastest_time)
        fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout="tight")
        v_min = 0.0
        v_max = 0.0
        for driver_number, lap in lap_map.items():
            car_data = lap.get_car_data().add_distance()
            dist = car_data["Distance"].to_numpy()
            tm = np.array([t.total_seconds() for t in car_data["Time"]], dtype=float)
            uniq_idx = np.unique(dist, return_index=True)[1]
            dist = dist[np.sort(uniq_idx)]
            tm = tm[np.sort(uniq_idx)]
            interp_time = np.interp(common_distance, dist, tm)
            delta = interp_time - ref_time
            try:
                team_color = fastf1.plotting.get_team_color(lap.Team, session)
            except AttributeError:
                team_color = 'gray'
            style = (
                "solid"
                if constants.camera[session.event.year].get(
                    int(driver_number), "black"
                ) == "black"
                else "dashed"
            )
            label = lap.Driver
            if driver_number == fastest_driver_number:
                label += " (FASTEST)"
            ax.plot(
                common_distance,
                delta,
                color=team_color,
                linestyle=style,
                label=label
            )
            v_min = min(v_min, float(delta.min()))
            v_max = max(v_max, float(delta.max()))
        valid_corners = circuit_info.corners[
            circuit_info.corners.Distance <= max_distance
            ]
        if v_max > 3:
            v_max = 3
        if v_min < -3:
            v_min = -3
        ax.vlines(
            x=valid_corners.Distance,
            ymin=v_min,
            ymax=v_max,
            linestyles="dotted",
            colors="grey"
        )

        for _, corner in valid_corners.iterrows():
            txt = f"{corner.Number}{corner.Letter}"
            ax.text(
                corner.Distance,
                v_min,
                txt,
                va="bottom",
                ha="center",
                size="small"
            )
        ax.axhline(0, linestyle="--", linewidth=1)
        ax.set_xlabel(f"Distance (m) - {fastest_lap.Driver} reference")
        ax.set_ylabel("Delta Time (s)")
        ax.set_title(
            f"{session.event['EventName']} {session.name}\n"
            f"Delta to fastest in group ({fastest_lap.Driver})"
        )
        ax.set_xlim(0, max_distance)
        ax.set_ylim(v_min, v_max)
        ax.grid(True)
        ax.legend(fontsize="small")
        output_path = (
            f"./images/{session.event.year}/"
            f"{session.event.RoundNumber}_{session.event.Location}/"
            f"{session.name.replace(' ', '')}/"
            f"time_distance_delta/{start + 1}_.png"
        )
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.savefig(output_path, bbox_inches="tight")
        log.info(f"Saved plot to {output_path}")
        plt.close(fig)


def _plot_driver_telemetry(session: Session, log: Logger,
                           driver_numbers: list[int], key: str, label, value_func):
    group_size = 5
    circuit_info = session.get_circuit_info()
    if circuit_info is None:
        return
    for i in range(0, len(driver_numbers), group_size):
        group = driver_numbers[i:] if i + group_size >= len(driver_numbers) else driver_numbers[i:i + group_size]
        fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
        v_min, v_max = float('inf'), float('-inf')

        for driver_number in group:
            laps = session.laps.pick_drivers(driver_number).pick_fastest()
            if laps is None or laps.empty:
                continue

            car_data = laps.get_car_data().add_distance()
            driver_name = laps.Driver
            try:
                team_color = fastf1.plotting.get_team_color(laps.Team, session)
            except AttributeError:
                team_color = 'gray'
            camera_color = constants.camera[session.event.year].get(int(driver_number), 'black')
            line_style = 'solid' if camera_color == 'black' else 'dashed'

            y_data = value_func(car_data)
            ax.plot(car_data.Distance, y_data, label=driver_name, linewidth=1, color=team_color, linestyle=line_style,
                    alpha=0.5)
            v_min, v_max = min(v_min, y_data.min()), max(v_max, y_data.max())

        if v_min == float('inf') or v_max == float('-inf'):
            continue
        if v_min == 0.0 and v_max == 0.0:
            continue

        for _, corner in circuit_info.corners.iterrows():
            ax.axvline(x=corner.Distance, linestyle='dotted', color='grey', linewidth=0.8)
            ax.text(corner.Distance, v_min - (v_max - v_min) * 0.05, f"{corner.Number}{corner.Letter}",
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


@tracer.start_as_current_span("make_mini_segment")
def make_mini_segment(session: Session, log: Logger, corner_map: dict[str, list[int]], separators: list[int]) -> list[
    int]:
    """ミニセグメント作成する
    Args:
        session: 分析対象のセッション
        log: ロガー
        corner_map: コーナー
        separators: コーナー以外の境界
    """
    fastest_lap = session.laps.pick_fastest()
    if fastest_lap is None:
        return []
    car_data = fastest_lap.get_telemetry().add_distance()
    segment_boundaries = [0] + [car_data.iloc[-1].Distance] if car_data.iloc[-1] is not None else []
    circuit_info = session.get_circuit_info()
    if circuit_info is None:
        return segment_boundaries
    corners_df = circuit_info.corners
    for c in range(0, len(corners_df)):
        corner = corners_df.iloc[c]
        if corner is None:
            continue
        i = str(corner['Number'])
        if not i in corner_map:
            continue
        diffs = corner_map[i]
        for d in diffs:
            segment_boundaries.append(corner.Distance + d)
    log.info(f"{corner_map} {separators} corners_list: {list(corners_df.Distance)}, segment_list: {segment_boundaries}")
    return segment_boundaries + separators


@tracer.start_as_current_span("plot_mini_segment_on_circuit")
def plot_mini_segment_on_circuit(session: Session, log: Logger, segment_boundaries: list[int], image_name: str):
    """ミニセグメントをプロットする
    Args:
        session: 分析対象のセッション
        log: ロガー
        segment_boundaries: セグメントの境界
        image_name: 画像名
    """
    # ベストタイムを記録したドライバーのベストラップを取得
    fastest_lap = session.laps.pick_fastest()
    if fastest_lap is None:
        return
    driver = fastest_lap.Driver
    car_data = fastest_lap.get_telemetry().add_distance()

    segment_boundaries.sort()
    # プロット
    x = car_data['X'].values
    y = car_data['Y'].values
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    ax.plot(x, y, color='lightgrey', linewidth=2)

    for i in range(1, len(segment_boundaries)):
        start = segment_boundaries[i - 1]
        end = segment_boundaries[i]
        mask = (car_data['Distance'] >= start) & (car_data['Distance'] <= end)
        seg_x = car_data[mask]['X'].values
        seg_y = car_data[mask]['Y'].values
        color = 'black' if i % 2 == 0 else 'red'
        ax.plot(seg_x, seg_y, color=color, linewidth=3)

        mid_index = mask[mask].index[len(mask[mask]) // 2]
        mid_x: float = car_data.X.loc[mid_index]
        mid_y: float = car_data.Y.loc[mid_index]
        ax.text(mid_x, mid_y, f"{i}", fontsize=8, color='blue', ha='center', va='center')

    ax.set_aspect('equal')
    ax.set_title(f"Mini Segments of Best Lap - {driver}")
    ax.axis('off')

    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/{image_name}.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)


@tracer.start_as_current_span("plot_throttle")
def plot_throttle(session: Session, log: Logger):
    """y = スロットル
    x = 距離
    Args:
        session: 分析対象のセッション
        log: ロガー
    """
    driver_numbers = session.laps['DriverNumber'].unique()
    _plot_driver_telemetry(
        session, log,
        driver_numbers.tolist(),
        key='throttle',
        label='Throttle [%]',
        value_func=lambda data: data.Throttle
    )


@tracer.start_as_current_span("plot_brake")
def plot_brake(session: Session, log: Logger):
    """y = ブレーキ
    x = 距離
    Args:
        session: 分析対象のセッション
        log: ロガー
    """
    driver_numbers = session.laps['DriverNumber'].unique()
    _plot_driver_telemetry(
        session, log,
        driver_numbers.tolist(),
        key='brake',
        label='Brake',
        value_func=lambda data: data.Brake.astype(float)
    )


@tracer.start_as_current_span("plot_drs")
def plot_drs(session: Session, log: Logger):
    """y = DRS
    x = 距離
    Args:
        session: 分析対象のセッション
        log: ロガー
    """
    driver_numbers = session.laps['DriverNumber'].unique()
    _plot_driver_telemetry(session, log,
                           driver_numbers.tolist(),
                           key='drs',
                           label='DRS',
                           value_func=lambda data: data.DRS.astype(float)
                           )


@tracer.start_as_current_span("plot_telemetry")
def plot_telemetry(session: Session, log: Logger,
                   driver_numbers: list[int], key: str, label, value_func):
    """y = key
    x = 距離
    Args:
        session: 分析対象のセッション
        log: ロガー
        driver_numbers: 車番一覧
        key: プロットするテレメトリーのキー
        label: プロットするテレメトリーのラベル
        value_func: プロットするテレメトリー
    """
    circuit_info = session.get_circuit_info()
    if circuit_info is None:
        return
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
        camera_color = constants.camera[session.event.year].get(int(driver_number), 'black')
        line_style = 'solid' if camera_color == 'black' else 'dashed'

        y_data = value_func(car_data)
        ax.plot(car_data.Distance, y_data, label=driver_name,
                color=team_color, linestyle=line_style)

        v_min, v_max = min(v_min, y_data.min()), max(v_max, y_data.max())
        name = name + f"{driver_name}_"

    # コーナー線と番号
    for _, corner in circuit_info.corners.iterrows():
        ax.axvline(x=corner.Distance, linestyle='dotted', color='grey', linewidth=0.8)
        ax.text(corner.Distance, v_min - (v_max - v_min) * 0.05,
                f"{corner.Number}{corner.Letter}",
                va='center_baseline', ha='center', size='small')

    if v_min == 0.0 and v_max == 0.0:
        return

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


@tracer.start_as_current_span("plot_tyre_age_and_laptime")
def plot_tyre_age_and_laptime(session: Session, log: Logger):
    """y = ラップタイム
    x = タイヤ使用歴
    Args:
        session: 分析対象のセッション
        log: ロガー
    """
    lap_times = []
    tyre_life_list = []
    driver_colors = []
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for driver_number in session.drivers:
        lap = session.laps.pick_drivers(driver_number).pick_fastest()
        if lap is None:
            continue

        tyre_life = lap.TyreLife
        lap_times.append(lap.LapTime.total_seconds())
        tyre_life_list.append(tyre_life)
        ax.annotate(lap.Driver, (tyre_life, lap.LapTime.total_seconds()), fontsize=9, ha='right')
        try:
            color = fastf1.plotting.get_team_color(lap.Team, session)
        except AttributeError:
            color = 'gray'
        driver_colors.append(color)

    ax.scatter(tyre_life_list, lap_times, c=driver_colors)
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}/tyre_age_and_laptime.png"
    fig.gca().invert_yaxis()
    ax.grid(True)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)
