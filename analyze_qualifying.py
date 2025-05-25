import logging
import os

import fastf1
import fastf1.plotting
import matplotlib as mpl
import numpy as np
from matplotlib import pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.pyplot import colormaps

import config

year = 2025
race_number = 8
ses = 'FP2'

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

fastf1.Cache.enable_cache('./cache')
session = fastf1.get_session(year, race_number, ses)
session.load()

log.info(f"{year} Race {race_number} {session.event.EventName} {ses}")
circuit_info = session.get_circuit_info()


def plot_annotate_speed_trace(session, driver_number: int):
    """
    ドライバーごとに最速ラップのスピード変化をコースマップにプロットする
    Args:
        session: 分析対象のセッション
        driver_number: 分析対象の車番
    """
    fig, ax = plt.subplots()
    laps = session.laps.pick_drivers(driver_number).pick_fastest()
    car_data = laps.get_car_data().add_distance()
    team_color = fastf1.plotting.get_team_color(laps['Team'],
                                                session=session)
    camera_color = config.f1_driver_info_2025[driver_number]['t_cam']
    style = "solid" if camera_color == "black" else "dashed"

    ax.plot(car_data['Distance'], car_data['Speed'],
            color=team_color, label=laps['Driver'], linestyle=style)
    v_min = car_data['Speed'].min()
    v_max = car_data['Speed'].max()
    ax.vlines(x=circuit_info.corners['Distance'], ymin=v_min - 20, ymax=v_max + 20,
              linestyles='dotted', colors='grey')
    for _, corner in circuit_info.corners.iterrows():
        txt = f"{corner['Number']}{corner['Letter']}"
        ax.text(corner['Distance'], v_min - 30, txt,
                va='center_baseline', ha='center', size='small')

    ax.set_xlabel('Distance in m')
    ax.set_ylabel('Speed in km/h')
    ax.legend()
    ax.set_ylim(v_min - 40, v_max + 20)

    output_path = f"./images/{year}/{race_number}_{session.event.Location}/{session.name.replace(' ', '')}/circuit_speed/{driver_number}_{laps['Driver']}.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")


def plot_gear_shift_on_track(session, driver_number: int):
    """
    ドライバーごとに最速ラップのシフト変化をコースマップにプロットする
    Args:
        session: 分析対象のセッション
        driver_number: 分析対象の車番
    """
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

    plt.gca().add_collection(lc_comp)
    plt.axis('equal')
    plt.tick_params(labelleft=False, left=False, labelbottom=False, bottom=False)

    cbar = plt.colorbar(mappable=lc_comp, label="Gear",
                        boundaries=np.arange(1, 10))
    cbar.set_ticks(np.arange(1.5, 9.5))
    cbar.set_ticklabels(np.arange(1, 9))

    output_path = f"./images/{year}/{race_number}_{session.event.Location}/{session.name.replace(' ', '')}/shift_on_track/{driver_number}_{lap['Driver']}.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")


def plot_speed_on_track(session, driver_number):
    """
    ドライバーごとに最速ラップのスピードをグラフにする
    Args:
        session: 分析対象のセッション
        driver_number: 分析対象の車番
    """
    # Uncomparable
    lap = session.laps.pick_drivers(driver_number).pick_fastest()
    x = lap.telemetry['X']
    y = lap.telemetry['Y']
    color = lap.telemetry['Speed']

    points = np.array([x, y]).T.reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)

    fig, ax = plt.subplots(sharex=True, sharey=True, figsize=(12, 6.75))

    plt.subplots_adjust(left=0.1, right=0.9, top=0.9, bottom=0.12)
    ax.axis('off')

    ax.plot(lap.telemetry['X'], lap.telemetry['Y'],
            color='black', linestyle='-', linewidth=16, zorder=0)

    colormap = mpl.cm.plasma
    norm = plt.Normalize(color.min(), color.max())
    lc = LineCollection(segments, cmap=colormap, norm=norm,
                        linestyle='-', linewidth=5)

    lc.set_array(color)

    ax.add_collection(lc)

    ax = 0.25, 0.05, 0.5, 0.05
    color_bar_axes = fig.add_axes(ax)
    normalLegend = mpl.colors.Normalize(vmin=color.min(), vmax=color.max())
    mpl.colorbar.ColorbarBase(color_bar_axes, norm=normalLegend, cmap=colormap,
                              orientation="horizontal")
    plt.style.use('dark_background')
    output_path = f"./images/{year}/{race_number}_{session.event.Location}/{session.name.replace(' ', '')}/speed_on_track/{driver_number}_{lap['Driver']}.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    rect = 0, 0.08, 1, 1
    plt.tight_layout(rect=rect)
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")


def plot_speed_and_laptime(session, driver_numbers: list[int]):
    """
    ドライバーごとの最速のラップタイムとそのラップでの最高速度とをプロットする
    Args:
        session: 分析対象のセッション
        driver_numbers: セッションに参加している車番一覧
    """
    driver_names = {}
    lap_times = []
    top_speeds = []
    driver_colors = []

    for driver_number in driver_numbers:
        lap = session.laps.pick_drivers(driver_number).pick_fastest()
        if lap is None:
            continue
        car_data = lap.get_car_data()

        max_speed = car_data['Speed'].max()
        lap_times.append(lap['LapTime'].total_seconds())
        top_speeds.append(max_speed)
        driver_names[driver_number] = lap['Driver']
        driver_colors.append(config.f1_driver_info_2025[driver_number]['team_color'])

    fig, ax = plt.subplots()

    ax.scatter(top_speeds, lap_times, c=driver_colors)

    for i, driver_number in enumerate(driver_names.values()):
        ax.annotate(driver_number, (top_speeds[i], lap_times[i]), fontsize=9, ha='right')

    ax.set_xlabel("Top Speed [km/h]")
    ax.set_ylabel("Lap Time [s]")
    ax.set_title("Fastest Lap: Top Speed vs Lap Time")
    plt.gca().invert_yaxis()
    plt.tight_layout()
    output_path = f"./images/{year}/{race_number}_{session.event.Location}/{session.name.replace(' ', '')}/speed_and_laptime.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")


def plot_all_laps(session, driver_numbers: list[int]):
    """
    ドライバーごとのアウトラップとインラップを除く全ラップの開始時間とタイムをプロット
    Args:
        session: 分析対象のセッション
        driver_numbers: セッションに参加している車番一覧
    """
    fig, ax = plt.subplots(figsize=(10, 6))
    for driver_number in driver_numbers:
        laps = session.laps.pick_drivers(driver_number).sort_values(by='LapNumber')
        d = config.f1_driver_info_2025[driver_number]
        style = {"color": d["team_color"], "linestyle": "solid" if d["t_cam"] == "black" else "dashed",
                 "label": d["acronym"]}
        stint_number = 0
        x = []
        y = []
        for i in range(1, len(laps)):
            lap = laps.iloc[i]
            if not lap['IsAccurate']:
                continue
            stint = int(lap['Stint'])
            if stint_number != stint and len(x) > 0 and len(y) > 0:
                ax.plot(x, y, **style)
                x = []
                y = []
            x.append(lap['LapStartDate'])
            y.append(lap['LapTime'].seconds)
            stint_number = stint
        if len(x) > 0 and len(y) > 0:
            ax.plot(x, y, **style)
    plt.tight_layout()
    plt.style.use('dark_background')
    output_path = f"./images/{year}/{race_number}_{session.event.Location}/{session.name.replace(' ', '')}/all_laps.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")


def plot_laps_timing(session, driver_numbers: list[int]):
    """
    アウトラップとインラップを除く全ラップの開始時間とタイムをプロット
    Args:
        session: 分析対象のセッション
        driver_numbers: セッションに参加している車番一覧
    """
    for driver_number in driver_numbers:
        fig, ax = plt.subplots()
        laps = session.laps.pick_drivers(driver_number).sort_values(by='LapNumber')
        driver = config.f1_driver_info_2025[driver_number]
        stint_number = 0
        x = []
        y = []
        style = {}
        for i in range(1, len(laps)):
            lap = laps.iloc[i]
            if not lap['IsAccurate']:
                continue
            style = {"color": config.compound_colors[lap['Compound']]}
            stint = int(lap['Stint'])
            if stint_number != stint and len(x) > 0 and len(y) > 0:
                ax.plot(x, y, **style)
                x = []
                y = []
            x.append(lap['LapStartDate'])
            y.append(lap['LapTime'].seconds)
            stint_number = stint
        if len(x) > 0 and len(y) > 0:
            ax.plot(x, y, **style)
        plt.tight_layout()
        plt.style.use('dark_background')
        output_path = f"./images/{year}/{race_number}_{session.event.Location}/{session.name.replace(' ', '')}/laps/timing/{driver_number}_{driver['acronym']}.png"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        log.info(f"Saved plot to {output_path}")


def plot_laps_age(session, driver_numbers: list[int]):
    """
    ドライバーごとのアウトラップとインラップを除く全ラップのタイヤエイジとタイムをプロット
    Args:
        session: 分析対象のセッション
        driver_numbers: セッションに参加している車番一覧
    """
    for driver_number in driver_numbers:
        fig, ax = plt.subplots(figsize=(10, 6))
        laps = session.laps.pick_drivers(driver_number).sort_values(by='LapNumber')
        driver = config.f1_driver_info_2025[driver_number]
        stint_number = 0
        x = []
        y = []
        style = {}
        for i in range(1, len(laps)):
            lap = laps.iloc[i]
            if not lap['IsAccurate']:
                continue
            style = {"color": config.compound_colors[lap['Compound']]}
            stint = int(lap['Stint'])
            if stint_number != stint and len(x) > 0 and len(y) > 0:
                ax.plot(x, y, **style)
                x = []
                y = []
            x.append(lap['TyreLife'])
            y.append(lap['LapTime'].seconds)
            stint_number = stint
        if len(x) > 0 and len(y) > 0:
            ax.plot(x, y, **style)
        plt.tight_layout()
        plt.style.use('dark_background')
        output_path = f"./images/{year}/{race_number}_{session.event.Location}/{session.name.replace(' ', '')}/laps/age/{driver_number}_{driver['acronym']}.png"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        log.info(f"Saved plot to {output_path}")


def plot_ideal_best(session, driver_numbers: list[int]):
    """
    ドライバーごとの最速ラップのラップタイムと区間自己ベストを繋いだタイムをプロットする
    Args:
        session: 分析対象のセッション
        driver_numbers: セッションに参加している車番一覧
    """
    for driver_number in driver_numbers:
        fig, ax = plt.subplots()
        laps = session.laps.pick_drivers(driver_number).sort_values(by='LapNumber')
        driver = config.f1_driver_info_2025[driver_number]
        sec1 = 60
        sec2 = 60
        sec3 = 60
        for i in range(1, len(laps)):
            lap = laps.iloc[i]
            if not lap['IsAccurate']:
                continue
            if sec1 > lap['Sector1Time'].seconds:
                sec1 = lap['Sector1Time'].seconds
            if sec2 > lap['Sector2Time'].seconds:
                sec2 = lap['Sector2Time'].seconds
            if sec3 > lap['Sector3Time'].seconds:
                sec3 = lap['Sector3Time'].seconds
        x = session.laps.pick_drivers(driver_number).pick_fastest()['LapTime'].seconds
        y = sec1 + sec2 + sec3
        ax.scatter(x, y, c=driver['team_color'])
        ax.annotate(driver['acronym'], (x, y), fontsize=9, ha='right')
    plt.tight_layout()
    output_path = f"./images/{year}/{race_number}_{session.event.Location}/{session.name.replace(' ', '')}/ideal_best.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")


def plot_ideal_best_diff(session, driver_numbers: list[int]):
    """
    ドライバーごとの最速ラップと区間自己ベストを繋いだタイムの差分をプロットする
    Args:
        session: 分析対象のセッション
        driver_numbers: セッションに参加している車番一覧
    """
    fig, ax = plt.subplots()
    for driver_number in driver_numbers:
        laps = session.laps.pick_drivers(driver_number).sort_values(by='LapNumber')
        driver = config.f1_driver_info_2025[driver_number]
        sec1 = 60
        sec2 = 60
        sec3 = 60
        for i in range(1, len(laps)):
            lap = laps.iloc[i]
            if not lap['IsAccurate']:
                continue
            if sec1 > lap['Sector1Time'].seconds:
                sec1 = lap['Sector1Time'].seconds
            if sec2 > lap['Sector2Time'].seconds:
                sec2 = lap['Sector2Time'].seconds
            if sec3 > lap['Sector3Time'].seconds:
                sec3 = lap['Sector3Time'].seconds
        y = sec1 + sec2 + sec3
        x = y - session.laps.pick_drivers(driver_number).pick_fastest()['LapTime'].seconds
        ax.scatter(x, y, c=driver['team_color'])
        ax.annotate(driver['acronym'], (x, y), fontsize=9, ha='right')
    plt.tight_layout()
    output_path = f"./images/{year}/{race_number}_{session.event.Location}/{session.name.replace(' ', '')}/ideal_best_diff.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")


# main
drivers = list(map(int, session.drivers))
plot_speed_and_laptime(session, drivers)
plot_all_laps(session, drivers)
plot_ideal_best(session, drivers)
plot_ideal_best_diff(session, drivers)

plot_laps_timing(session, drivers)
plot_laps_age(session, drivers)

for driver in drivers:
    log.info(f"{driver}")
    plot_annotate_speed_trace(session, driver)
    plot_gear_shift_on_track(session, driver)
    plot_speed_on_track(session, driver)
