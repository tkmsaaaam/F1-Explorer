import bisect
import logging

from matplotlib import pyplot as plt

import config
import util

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",  # Log format
    handlers=[
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

results_path = "../live/data/results"
logs_path = results_path + "/logs"
images_path = results_path + "/images"


def set_style(no: int) -> dict[str, str]:
    d = config.f1_driver_info_2025.get(no, {
        "acronym": "UNDEFINED",
        "driver": "Undefined",
        "team": "Undefined",
        "team_color": "#808080",
        "t_cam": "black"
    })
    style = {"color": d["team_color"], "linestyle": "solid" if d["t_cam"] == "black" else "dashed",
             "label": d["acronym"], "linewidth": "0.75"}
    return style


def plot_tyres(stint_map: dict):
    # チーム→ドライバー順で並び替え
    sorted_drivers = sorted(stint_map.keys(),
                            key=lambda d: (config.f1_driver_info_2025.get(d, {
                                "acronym": "UNDEFINED",
                                "driver": "Undefined",
                                "team": "Undefined",
                                "team_color": "#808080",
                                "t_cam": "black"
                            })["team"],
                                           config.f1_driver_info_2025.get(d, {
                                               "acronym": "UNDEFINED",
                                               "driver": "Undefined",
                                               "team": "Undefined",
                                               "team_color": "#808080",
                                               "t_cam": "black"
                                           })["acronym"]))

    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    y_ticks = []
    y_tick_labels = []

    max_lap = 0
    for i, driver_number in enumerate(sorted_drivers):
        y = i
        x = 0
        y_ticks.append(y)
        acronym = config.f1_driver_info_2025.get(driver_number, {
            "acronym": "UNDEFINED",
            "driver": "Undefined",
            "team": "Undefined",
            "team_color": "#808080",
            "t_cam": "black"
        })["acronym"]
        y_tick_labels.append(acronym)

        driver_stints = stint_map[driver_number]
        for stint_num in sorted(driver_stints.keys()):
            stint = driver_stints[stint_num]
            width = stint["TotalLaps"]
            if "StartLaps" in stint:
                width = width - stint["StartLaps"]
            compound = stint.get("Compound", "UNKNOWN")
            color = config.compound_colors.get(compound.upper(), "black")
            rect = plt.Rectangle((x, y - 0.4), width, 0.8, facecolor=color, edgecolor='black', linestyle='-',
                                 linewidth=2)
            ax.add_patch(rect)
            x += width
            if x > max_lap:
                max_lap = x

    ax.set_yticks(y_ticks)
    ax.set_yticklabels(y_tick_labels)
    ax.set_xlim(0, max_lap)
    plt.grid(axis='x', linestyle=':', alpha=0.7)
    output_path: str = f"{images_path}/tyres.png"
    util.save(fig, ax, output_path, log)


def plot_with_lap_end(map_by_timedelta, target_map, filename: str):
    m_by_lap_end = {}
    for driver, lap_dict in map_by_timedelta.items():
        # 対象ドライバーの position 情報を取得してソート
        time_points = sorted(target_map.get(driver, {}).keys())
        time_to_position = target_map.get(driver, {})

        driver_result = {}

        for lap, t in lap_dict.items():
            # t 以下で最大の time_point を探す
            idx = bisect.bisect_right(time_points, t)
            if idx == 0:
                position = None  # それ以前の position が存在しない
            else:
                nearest_time = time_points[idx - 1]
                position = time_to_position[nearest_time]
            driver_result[lap] = position

        m_by_lap_end[driver] = driver_result

    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    for no, laps in m_by_lap_end.items():
        style = set_style(no)
        x = sorted(laps.keys())
        y = [laps[lap] for lap in x]
        ax.plot(x, y, **style)
    ax.legend()
    ax.invert_yaxis()
    output_path = f"{images_path}/{filename}.png"
    util.save(fig, ax, output_path, log)


def plot_positions(map_by_timedelta: dict, target_map: dict, filename: str):
    lap_end_positions = {}
    for driver, lap_dict in map_by_timedelta.items():
        # 対象ドライバーの position 情報を取得してソート
        time_points = sorted(target_map.get(driver, {}).keys())
        time_to_position = target_map.get(driver, {})

        driver_result = {}

        for lap, t in lap_dict.items():
            # t 以下で最大の time_point を探す
            idx = bisect.bisect_right(time_points, t)
            if idx == 0:
                position = None  # それ以前の position が存在しない
            else:
                nearest_time = time_points[idx - 1]
                position = time_to_position[nearest_time]

            driver_result[lap] = position

        lap_end_positions[driver] = driver_result

    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    current_positon_map = {}
    for no, laps in lap_end_positions.items():
        current_positon_map[laps[len(laps) + 1]] = no

    for p in range(1, len(current_positon_map) + 1):
        if not p in current_positon_map:
            continue
        no = current_positon_map[p]
        laps = lap_end_positions[no]
        style = set_style(no)
        x = sorted(laps.keys())
        y = [laps[lap] for lap in x]
        ax.plot(x, y, **style)
    ax.legend()
    ax.invert_yaxis()
    output_path: str = f"{images_path}/{filename}.png"
    util.save(fig, ax, output_path, log)


def plot_laptime(dicts: dict, filename: str):
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    all_y = []
    for no, data in dicts.items():
        style = set_style(no)
        x = list(data.keys())
        y = list(data.values())
        all_y.extend(y)
        ax.plot(x, y, **style)

    if all_y:
        min_time = min(all_y)
        threshold = min_time + 10.0
        # 10秒以内の値の最大値を探す
        capped_max_time = max(v for v in all_y if v <= threshold)
        log.info(f"min: {min_time}, capped max: {capped_max_time}")
        ax.set_ylim(min_time, capped_max_time)
    ax.legend()
    ax.invert_yaxis()
    output_path: str = f"{images_path}/{filename}.png"
    util.save(fig, ax, output_path, log)


def plot_laptime_diff(dicts: dict, filename: str, minus: float, plus: float):
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    for no, data in dicts.items():
        style = set_style(no)
        x = []
        y = []
        for lap in range(2, len(data) + 1):
            if lap in data and lap - 1 in data:
                delta = data[lap] - data[lap - 1]
                if abs(delta) <= 5.0:  # 5秒以上の差をスキップ
                    x.append(lap)
                    y.append(delta)
        ax.plot(x, y, **style)
    ax.invert_yaxis()
    if minus != 0 or plus != 0:
        ax.set_ylim(- minus, plus)
    ax.legend()
    output_path: str = f"{images_path}/{filename}.png"
    util.save(fig, ax, output_path, log)


def plot_weather(m: dict, filename: str):
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    x = []
    y = []
    for k, v in sorted(m.items()):
        x.append(k)
        y.append(v)
    ax.plot(x, y)
    output_path = f"{images_path}/{filename}.png"
    util.save(fig, ax, output_path, log)
