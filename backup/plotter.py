import datetime
import logging
import os

from matplotlib import pyplot
from plotly import graph_objects

import constants
from backup.domain.lap import Lap
from backup.domain.stint import Stint
from backup.domain.weather import Weather

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
    style = {"color": constants.team_color_info_2025.get(no, '#808080'),
             "linestyle": "solid" if constants.camera_info_2025.get(no, 'black') == "black" else "dashed",
             "label": constants.name_info_2025.get(no, 'UNDEFINED'), "linewidth": "1"}
    return style


def plot_tyres(stint_map: dict[int, dict[int, Stint]], order: list[int]):
    fig, ax = pyplot.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    max_lap = 0
    y = 0
    for driver_number in order:
        if driver_number not in stint_map:
            continue
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
            bar = ax.barh(y=y,
                          width=width,
                          left=start,
                          color=constants.compound_colors.get(stint.compound, 'gray'),
                          edgecolor='black' if stint.is_new else 'gray'
                          )
            ax.bar_label(bar, labels=[str(stint.start_laps)],
                         label_type="center")
            start += width
            if start > max_lap:
                max_lap = start
        y += 1
    ax.grid(True)
    ax.set(yticks=[i for i in range(0, len(order))], yticklabels=[str(i) for i in order], xlim=(0, max_lap))
    pyplot.grid(axis='x', linestyle=':', alpha=0.7)
    output_path: str = f"{images_path}/tyres.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    pyplot.close(fig)


def plot_gap_to_top(dicts: dict[int, dict[int, Lap]], filename: str, d: int):
    fig, ax = pyplot.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for no, data in dicts.items():
        style = set_style(no)
        x = sorted(list(data.keys()))
        y = [data[i].gap_to_top for i in x]
        ax.plot(x, y, **style)
    ax.grid(True)
    ax.legend(fontsize='small')
    ax.invert_yaxis()
    output_path = f"{images_path}/{filename}.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    pyplot.close(fig)
    if d is not None:
        ax.set_ylim(d, 0)
        output_path = f"{images_path}/{filename}_{d}.png"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.savefig(output_path, bbox_inches='tight')
        log.info(f"Saved plot to {output_path}")
        pyplot.close(fig)


def plot_gap_to_ahead(dicts: dict[int, dict[int, Lap]], filename: str, d: int):
    fig, ax = pyplot.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for no, data in dicts.items():
        style = set_style(no)
        x = sorted(list(data.keys()))
        y = [data[i].gap_to_ahead for i in x]
        ax.plot(x, y, **style)
    ax.grid(True)
    ax.legend(fontsize='small')
    ax.invert_yaxis()
    output_path = f"{images_path}/{filename}.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    pyplot.close(fig)
    if d is not None:
        ax.set_ylim(d, 0)
        output_path = f"{images_path}/{filename}_{d}.png"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.savefig(output_path, bbox_inches='tight')
        log.info(f"Saved plot to {output_path}")
        pyplot.close(fig)


def plot_positions(dicts: dict[int, dict[int, Lap]], filename: str):
    fig, ax = pyplot.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for no, data in dicts.items():
        style = set_style(no)
        x = sorted(list(data.keys()))
        y = [data[i].position for i in x]
        ax.plot(x, y, **style)
    ax.grid(True)
    ax.legend(fontsize='small')
    ax.invert_yaxis()
    output_path: str = f"{images_path}/{filename}.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    pyplot.close(fig)


def plot_laptime(dicts: dict[int, dict[int, Lap]], filename: str, d: int):
    fig, ax = pyplot.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
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
    min_time = min(all_y) if len(all_y) > 0 else 0
    ax.grid(True)
    ax.set_ylim(min_time + 20, min_time)
    ax.legend(fontsize='small')
    output_path: str = f"{images_path}/{filename}.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    pyplot.close(fig)
    if all_y and d is not None:
        threshold = min_time + d
        capped_max_time = max(v for v in all_y if v <= threshold)
        log.info(f"min: {min_time}, capped max: {capped_max_time}")
        ax.grid(True)
        ax.set_ylim(capped_max_time, min_time)
        output_path: str = f"{images_path}/{filename}_{d}.png"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.savefig(output_path, bbox_inches='tight')
        log.info(f"Saved plot to {output_path}")
        pyplot.close(fig)


def plot_laptime_diff(dicts: dict[int, dict[int, Lap]], order: list[int], filename: str):
    _, max_laps_dict = max(
        dicts.items(),
        key=lambda item: len(item[1])
    )
    header = ['Lap']
    max_lap_key = max(max_laps_dict.keys())
    numbers = [i for i in range(max_lap_key, 1, -1)]
    data_rows = [numbers]
    fill_colors = [["#f0f0f0"] * len(numbers)]

    for no in order:
        data = dicts[no]
        header.append(str(no))
        lap_times = []
        colors = []
        for i in range(max_lap_key, 1, -1):
            if i not in data or i - 1 not in data:
                lap_times.append('---')
                colors.append('#808080')  # gray
                continue
            diff = data[i].time - data[i - 1].time
            if diff < -10 or diff > 10:
                lap_times.append("{:.3f}".format(diff))
                colors.append('#808080')  # gray
            elif diff > 0.1:
                lap_times.append("{:.3f}".format(diff))
                colors.append('#FF8488')  # light red
            elif diff < -0.1:
                lap_times.append("{:.3f}".format(diff))
                colors.append('#ADD8E6')  # light blue
            else:
                lap_times.append("{:.3f}".format(diff))
                colors.append('#ffffff')  # white
        data_rows.append(lap_times)
        fill_colors.append(colors)
    fig = graph_objects.Figure(data=[graph_objects.Table(
        header=dict(values=header, fill_color='lightgrey', align='center'),
        cells=dict(values=data_rows, fill_color=fill_colors, align='center')
    )], layout=dict(width=1920, height=1080, margin=dict(l=20, r=20, t=20, b=20)))
    output_path: str = f"{images_path}/{filename}.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.write_image(output_path, width=1920, height=1080)
    log.info(f"Saved plot to {output_path}")


def plot_weather(m: dict[datetime.datetime, Weather]):
    fig, ax = pyplot.subplots(figsize=(12.8, 7.2), dpi=150)
    x = [i for i in sorted(m.keys())]
    y = [m[i].air_temp for i in x]
    ax.plot(x, y)
    ax.grid(True)
    output_path = f"{images_path}/air_temp.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    pyplot.close(fig)

    fig, ax = pyplot.subplots(figsize=(12.8, 7.2), dpi=150)
    x = [i for i in sorted(m.keys())]
    y = [m[i].rain_fall for i in x]
    ax.plot(x, y)
    ax.grid(True)
    output_path = f"{images_path}/rainfall.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    pyplot.close(fig)

    fig, ax = pyplot.subplots(figsize=(12.8, 7.2), dpi=150)
    x = [i for i in sorted(m.keys())]
    y = [m[i].track_temp for i in x]
    ax.plot(x, y)
    ax.grid(True)
    output_path = f"{images_path}/track_temp.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    pyplot.close(fig)

    fig, ax = pyplot.subplots(figsize=(12.8, 7.2), dpi=150)
    x = [i for i in sorted(m.keys())]
    y = [m[i].wind_speed for i in x]
    ax.plot(x, y)
    ax.grid(True)
    output_path = f"{images_path}/wind_speed.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    log.info(f"Saved plot to {output_path}")
    pyplot.close(fig)
