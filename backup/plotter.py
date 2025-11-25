import logging
import os

from matplotlib import pyplot as plt

import config
from backup.domain.Stint import Stint
from backup.domain.lap import Lap

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
    style = {"color": config.team_color_info_2025.get(no, '#808080'),
             "linestyle": "solid" if config.camera_info_2025.get(no, 'black') == "black" else "dashed",
             "label": config.name_info_2025.get(no, 'UNDEFINED'), "linewidth": "1"}
    return style


def plot_tyres(stint_map: dict[int, dict[int, Stint]]):
    sorted_drivers = sorted(stint_map.keys(),
                            key=lambda d: (config.team_info_2025.get(d, 'Undefined'),
                                           config.name_info_2025.get(d, "UNDEFINED")))

    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    max_lap = 0
    y = 0
    for driver_number in sorted_drivers:
        stints = stint_map[driver_number]
        stint_keys = sorted(stints.keys())
        start = 0
        for i in stint_keys:
            stint = stints[i]
            if stint.total_laps == 0:
                continue
            width = stint.total_laps
            if stint.start_laps != 0:
                width = width - stint.start_laps
            ax.barh(y=y,
                    width=width,
                    left=start,
                    color=config.compound_colors.get(stint.compound, 'gray'),
                    edgecolor='black' if stint.is_new else 'gray'
                    )
            start += width
            if start > max_lap:
                max_lap = start
        y += 1
    ax.set_yticks([i for i in range(0, len(sorted_drivers))])
    ax.set_yticklabels([str(i) for i in sorted_drivers])
    ax.set_xlim(0, max_lap)
    plt.grid(axis='x', linestyle=':', alpha=0.7)
    output_path: str = f"{images_path}/tyres.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)


def plot_gap_to_top(dicts: dict[int, dict[int, Lap]], filename: str, d: int):
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for no, data in dicts.items():
        style = set_style(no)
        x = sorted(list(data.keys()))
        y = [data[i].gap_to_top for i in x]
        ax.plot(x, y, **style)
    ax.legend(fontsize='small')
    ax.invert_yaxis()
    output_path = f"{images_path}/{filename}.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)
    if d is not None:
        ax.set_ylim(d, 0)
        output_path = f"{images_path}/{filename}_{d}.png"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.savefig(output_path, bbox_inches='tight')
        log.info(f"Saved plot to {output_path}")
        plt.close(fig)


def plot_gap_to_ahead(dicts: dict[int, dict[int, Lap]], filename: str, d: int):
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for no, data in dicts.items():
        style = set_style(no)
        x = sorted(list(data.keys()))
        y = [data[i].gap_to_ahead for i in x]
        ax.plot(x, y, **style)
    ax.legend(fontsize='small')
    ax.invert_yaxis()
    output_path = f"{images_path}/{filename}.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)
    if d is not None:
        ax.set_ylim(d, 0)
        output_path = f"{images_path}/{filename}_{d}.png"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.savefig(output_path, bbox_inches='tight')
        log.info(f"Saved plot to {output_path}")
        plt.close(fig)


def plot_positions(dicts: dict[int, dict[int, Lap]], filename: str):
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for no, data in dicts.items():
        style = set_style(no)
        x = sorted(list(data.keys()))
        y = []
        last_pos = None
        for i in x:
            pos = data.get(i, 180).position
            if pos != 0:
                last_pos = pos
                y.append(pos)
            else:
                if last_pos is not None:
                    y.append(last_pos)
                else:
                    y.append(0)
        ax.plot(x, y, **style)
    ax.legend(fontsize='small')
    ax.invert_yaxis()
    output_path: str = f"{images_path}/{filename}.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)


def plot_laptime(dicts: dict[int, dict[int, Lap]], filename: str, d: int):
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    all_y = []
    for no, data in dicts.items():
        style = set_style(no)

        x = []
        y = []
        for i in sorted(list(data.keys())):
            if i < 1:
                continue
            lap = data[i]
            if lap.time == 0:
                continue
            x.append(i)
            y.append(lap.time)
        all_y += y
        ax.plot(x, y, **style)

    if len(all_y) > 0:
        min_time = min(all_y)
    else:
        min_time = 0
    ax.set_ylim(min_time + 20, min_time)
    ax.legend(fontsize='small')
    output_path: str = f"{images_path}/{filename}.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)
    if all_y and d is not None:
        threshold = min_time + d
        capped_max_time = max(v for v in all_y if v <= threshold)
        log.info(f"min: {min_time}, capped max: {capped_max_time}")
        ax.set_ylim(capped_max_time, min_time)
        output_path: str = f"{images_path}/{filename}_{d}.png"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.savefig(output_path, bbox_inches='tight')
        log.info(f"Saved plot to {output_path}")
        plt.close(fig)


def plot_laptime_diff(dicts: dict[int, dict[int, Lap]], filename: str, minus: float, plus: float):
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for no, data in dicts.items():
        style = set_style(no)
        x = []
        y = []
        for i in sorted(list(data.keys())):
            if i - 1 not in data.keys():
                continue
            x.append(i)
            y.append(data.get(i, 180).time - data.get(i - 1, 180).time)
        ax.plot(x, y, **style)
    ax.invert_yaxis()
    if minus != 0 or plus != 0:
        ax.set_ylim(- minus, plus)
    ax.legend(fontsize='small')
    output_path: str = f"{images_path}/{filename}.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)


def plot_weather(m: dict, filename: str):
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    x = []
    y = []
    for k, v in sorted(m.items()):
        x.append(k)
        y.append(v)
    ax.plot(x, y)
    output_path = f"{images_path}/{filename}.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    plt.close(fig)
