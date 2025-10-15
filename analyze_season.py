import datetime
import os
from itertools import accumulate

import fastf1.plotting
from matplotlib import pyplot as plt
from plotly import graph_objects

import setup


def main():
    config = setup.load_config()

    log = setup.log()
    if config is None:
        log.warning("no config")
        return

    season = config["Year"]
    setup.fast_f1()
    schedule = fastf1.get_event_schedule(season, include_testing=False)

    driver_colors = {}

    # {"round_number": {"name": "Japan", "sprint": true, "sprint_position": {"abbreviation": 1},"grid_position": {"abbreviation": 1}, "position": {"abbreviation": 1}}}
    results = {}

    schedule = schedule.sort_values(by='RoundNumber')
    now = datetime.datetime.now()
    for _, event in schedule.iterrows():
        if now < event.EventDate:
            break
        if event.RoundNumber not in results:
            results[event.RoundNumber] = {"name": event.EventName, "date": event.EventDate, "grid_position": {},
                                          "position": {}, "point": {}, "sprint": False}

        gp = results[event.RoundNumber]
        if event.EventFormat == "sprint_qualifying":
            sprint = fastf1.get_session(season, event.EventName, "S")
            sprint.load(laps=False, telemetry=False, weather=False, messages=False)
            gp["sprint"] = True
            if "sprint_position" not in gp:
                gp["sprint_position"] = {}
            if "sprint_point" not in gp:
                gp["sprint_point"] = {}
            for _, driver_row in sprint.results.iterrows():
                gp["sprint_position"][driver_row.Abbreviation] = driver_row.Position
                gp["sprint_point"][driver_row.Abbreviation] = driver_row.Points

        race = fastf1.get_session(season, event.EventName, "R")
        race.load(laps=False, telemetry=False, weather=False, messages=False)
        for _, driver_row in race.results.iterrows():
            abbreviation = driver_row.Abbreviation
            gp["grid_position"][abbreviation] = driver_row.GridPosition
            gp["position"][abbreviation] = driver_row.Position
            gp["point"][abbreviation] = driver_row.Points
            driver_colors[abbreviation] = race.get_driver(abbreviation).TeamColor

    latest = len(results) + 1

    if latest == 1:
        return

    base_dir = f"./images/{season}"

    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    champion_points = []
    for k, v in driver_colors.items():
        y = []
        for i in range(1, latest):
            sum_point = results[i]["point"].get(k, 0)
            if results[i]["sprint"]:
                sum_point += results[i]["sprint_point"].get(k, 0)
            y.append(sum_point)
        if sum(y) > sum(champion_points):
            champion_points = y
        ax.plot([i for i in range(1, latest)], [sum(y[:i + 1]) for i in range(len(y))], label=k,
                color='#' + v, linewidth=1)
    ax.legend(fontsize='small')
    ax.grid(True)
    output_path = f"{base_dir}/standings.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    plt.close(fig)
    log.info(f"Saved plot to {output_path}")

    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for k, v in driver_colors.items():
        y = []
        for i in range(1, latest):
            p = results[i]["point"].get(k, 0)
            if results[i]["sprint"]:
                p += results[i]["sprint_point"].get(k, 0)
            y.append(p)
        ax.plot([i for i in range(1, latest)], y, label=k, color='#' + v, linewidth=1)
    ax.legend(fontsize='small')
    ax.grid(True)
    output_path = f"{base_dir}/results.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    plt.close(fig)
    log.info(f"Saved plot to {output_path}")

    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout="tight")
    for k, v in driver_colors.items():
        y = []
        for i in range(1, latest):
            p = results[i]["point"].get(k, 0)
            if results[i]["sprint"]:
                p += results[i]["sprint_point"].get(k, 0)
            y.append(p)
        diff = [a - b for a, b in zip(accumulate(y), accumulate(champion_points))]
        ax.plot([i for i in range(1, latest)], diff, label=k, color="#" + v, linewidth=1)
    ax.legend(fontsize='small')
    ax.grid(True)
    output_path = f"{base_dir}/diffs.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    plt.close(fig)
    log.info(f"Saved plot to {output_path}")

    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    x = [i for i in range(1, latest)]
    for k, v in driver_colors.items():
        y = [results[i]["grid_position"].get(k, 21) for i in range(1, latest)]
        ax.plot(x, y, label=k, color='#' + v, linewidth=1)
    ax.legend(fontsize='small')
    ax.grid(True)
    ax.invert_yaxis()
    output_path = f"{base_dir}/grid_positions.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    plt.close(fig)
    log.info(f"Saved plot to {output_path}")

    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for k, v in driver_colors.items():
        y = [results[i]["grid_position"].get(k, 21) - results[i]["position"].get(k, 21) for i in range(1, latest)]
        ax.plot(x, y, label=k, color='#' + v, linewidth=1)
    ax.legend(fontsize='small')
    ax.grid(True)
    output_path = f"{base_dir}/grid_to_results.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    plt.close(fig)
    log.info(f"Saved plot to {output_path}")

    numbers = [event.RoundNumber for _, event in schedule.iterrows()]

    output_path = f"{base_dir}/points.png"
    res = [[event.RoundNumber for _, event in schedule.iterrows()]]
    headers = ["name"]
    for k, v in driver_colors.items():
        headers.append(k)
        r = []
        for i in numbers:
            if i not in results:
                r.append(0)
                continue
            r.append(results[i]["position"].get(k, 0))
        res.append(r)
    fig = graph_objects.Figure(data=[graph_objects.Table(
        header=dict(values=headers, fill_color='lightgrey', align='center'),
        cells=dict(values=res, align='center')
    )])
    fig.update_layout(
        autosize=True,
        margin=dict(autoexpand=True)
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.write_image(output_path, width=1920, height=2160)
    log.info(f"Saved plot to {output_path}")

    output_path = f"{base_dir}/events.png"
    if os.path.exists(output_path):
        return
    fig = graph_objects.Figure(data=[graph_objects.Table(
        header=dict(values=["number", "name", "sprint", "date"], fill_color='lightgrey', align='center'),
        cells=dict(values=[numbers,
                           [event.EventName for _, event in schedule.iterrows()],
                           [event.EventFormat == "sprint_qualifying" for _, event in schedule.iterrows()],
                           [event.EventDate for _, event in schedule.iterrows()]],
                   fill_color=[["white" if i % 2 == 0 else "#f2f2f2" for i in range(1, len(numbers) + 1)]],
                   align='center')
    )])
    fig.update_layout(
        autosize=True,
        margin=dict(autoexpand=True)
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.write_image(output_path, width=1920, height=2160)
    log.info(f"Saved plot to {output_path}")


if __name__ == "__main__":
    main()
