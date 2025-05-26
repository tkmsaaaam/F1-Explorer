import bisect
import logging
import statistics

from matplotlib import pyplot as plt

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",  # Log format
    handlers=[
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

results_path = config.live_data_path + "/results"
logs_path = results_path + "/logs"
images_path = results_path + "/images"


def set_style(no: int):
    d = config.f1_driver_info_2025[no]
    style = {"color": d["team_color"], "linestyle": "solid" if d["t_cam"] == "black" else "dashed",
             "label": d["acronym"]}
    return style


def plot_tyres(stint_map):
    # チーム→ドライバー順で並び替え
    sorted_drivers = sorted(stint_map.keys(),
                            key=lambda d: (config.f1_driver_info_2025[d]["team"],
                                           config.f1_driver_info_2025[d]["acronym"]))

    fig, ax = plt.subplots(figsize=(10, 6))
    yticks = []
    yticklabels = []

    max_lap = 0
    for i, driver_number in enumerate(sorted_drivers):
        y = i
        x = 0
        yticks.append(y)
        acronym = config.f1_driver_info_2025[driver_number]["acronym"]
        yticklabels.append(acronym)

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

    ax.set_yticks(yticks)
    ax.set_yticklabels(yticklabels)
    ax.set_xlim(0, max_lap)
    plt.grid(axis='x', linestyle=':', alpha=0.7)
    plt.tight_layout()
    output_path: str = f"{images_path}/tyres.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")


def plot_with_lap_end(map_by_timedelta, target_map, filename: str, minimum: int, maximum: int):
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

    fig, ax = plt.subplots(figsize=(10, 6))

    for no, laps in m_by_lap_end.items():
        style = set_style(no)
        x = sorted(laps.keys())
        y = [laps[lap] for lap in x]
        ax.plot(x, y, **style)
    ax.legend()
    ax.invert_yaxis()
    ax.set_ylim(minimum, maximum)
    plt.tight_layout()
    output_path = f"{images_path}/{filename}.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")


def plot_positions(map_by_timedelta, target_map, filename: str):
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

    fig, ax = plt.subplots(figsize=(10, 6))
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
    plt.tight_layout()
    output_path: str = f"{images_path}/{filename}.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")


def plot(dicts, filename: str, minus: int, plus: int):
    fig, ax = plt.subplots(figsize=(10, 6))
    all_y = []
    for no, data in dicts.items():
        style = set_style(no)
        x = list(data.keys())
        y = list(data.values())
        all_y.extend(data.values())
        ax.plot(x, y, **style)
    if all_y and (minus != 0 or plus != 0):
        median_time = statistics.median(all_y)
        log.info(f"median: {median_time}, minimum: {median_time - minus}, maximum: {median_time + plus}")
        ax.set_ylim(median_time - minus, median_time + plus)
    ax.invert_yaxis()
    ax.legend()
    plt.tight_layout()
    output_path: str = f"{images_path}/{filename}.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")


def plot_laptime_diff(dicts, filename: str, minus: float, plus: float):
    fig, ax = plt.subplots(figsize=(10, 6))
    for no, data in dicts.items():
        style = set_style(no)
        x = [lap for lap in range(2, len(data) + 1) if lap in data and lap - 1 in data]
        y = [data[lap] - data[lap - 1] for lap in x]
        ax.plot(x, y, **style)
    ax.invert_yaxis()
    if minus != 0 or plus != 0:
        ax.set_ylim(- minus, plus)
    ax.legend()
    plt.tight_layout()
    output_path: str = f"{images_path}/{filename}.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")


def plot_weather(m, filename):
    fig, ax = plt.subplots(figsize=(10, 6))
    x = []
    y = []
    for k, v in sorted(m.items()):
        x.append(k)
        y.append(v)
    ax.plot(x, y)
    ax.invert_yaxis()
    plt.tight_layout()
    output_path = f"{images_path}/{filename}.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
