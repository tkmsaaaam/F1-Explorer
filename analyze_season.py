import datetime
import os
from itertools import accumulate

import fastf1.plotting
from fastf1.core import DriverResult
from matplotlib import pyplot as plt
from opentelemetry import trace
from plotly import graph_objects

import config
import setup

tracer = trace.get_tracer(__name__)


class Weekend:
    def __init__(self, gp_name: str):
        self.gp_name = gp_name
        self.grid_position: dict[str, int] = {}
        self.position: dict[str, int] = {}
        self.point: dict[str, int] = {}
        self.sprint_point: dict[str, int] = {}

    def set_grid_position(self, k: str, v: int):
        self.grid_position[k] = v

    def set_position(self, k: str, v: int):
        self.position[k] = v

    def set_point(self, k: str, v: int):
        self.point[k] = v

    def set_sprint_point(self, k: str, v: int):
        self.sprint_point[k] = v

    def get_grid_position(self, k: str) -> int:
        if k in self.grid_position:
            return self.grid_position[k]
        return len(self.grid_position) + 1

    def get_position(self, k: str) -> int:
        if k in self.position:
            return self.position[k]
        return len(self.position) + 1

    def get_point(self, k: str) -> int:
        if k in self.point:
            return self.point[k]
        return 0

    def get_sprint_point(self, k: str) -> int:
        if k in self.sprint_point:
            return self.sprint_point[k]
        return 0


@tracer.start_as_current_span("main")
def main():
    c = setup.load_config()

    log = setup.log()
    if c is None:
        log.warning("no config")
        return
    trace.get_current_span().set_attributes(
        {"year": c['Year'], "round": c['Round'], "session": c['Session']})
    season = c["Year"]
    setup.fast_f1()
    schedule = fastf1.get_event_schedule(season, include_testing=False)

    drivers: dict[int, DriverResult] = {}
    results: dict[int, Weekend] = {}

    schedule = schedule.sort_values(by='RoundNumber')
    now = datetime.datetime.now()
    for _, event in schedule.iterrows():
        if now < event.EventDate:
            break
        if event.RoundNumber not in results:
            results[event.RoundNumber] = Weekend(event.EventName)

        gp: Weekend = results[event.RoundNumber]
        if event.EventFormat == "sprint_qualifying":
            sprint = fastf1.get_session(season, event.EventName, "S")
            sprint.load(laps=False, telemetry=False, weather=False, messages=False)
            for _, driver_row in sprint.results.iterrows():
                gp.set_sprint_point(driver_row.Abbreviation, driver_row.Points)

        race = fastf1.get_session(season, event.EventName, "R")
        race.load(laps=False, telemetry=False, weather=False, messages=False)
        for _, driver_row in race.results.iterrows():
            abbreviation = driver_row.Abbreviation
            gp.set_grid_position(abbreviation, driver_row.GridPosition)
            gp.set_position(abbreviation, driver_row.Position)
            gp.set_point(abbreviation, driver_row.Points)
            if driver_row.DriverNumber not in drivers:
                drivers[int(driver_row.DriverNumber)] = race.get_driver(abbreviation)

    if len(results) == 0:
        return

    latest = len(results) + 1
    base_dir = f"./images/{season}"

    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for k, v in drivers.items():
        y = [results[i].get_point(v.Abbreviation) + results[i].get_sprint_point(v.Abbreviation) for i in
             range(1, latest)]
        ax.plot([i for i in range(1, latest)], [sum(y[:i + 1]) for i in range(len(y))], label=v.Abbreviation,
                color='#' + v.TeamColor, linewidth=1,
                linestyle="solid" if config.camera_info.get(season, {}).get(k, 'black') == "black" else "dashed")
    ax.legend(fontsize='small')
    ax.grid(True)
    output_path = f"{base_dir}/standings.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    plt.close(fig)
    log.info(f"Saved plot to {output_path}")

    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for k, v in drivers.items():
        y = [results[i].get_point(v.Abbreviation) + results[i].get_sprint_point(v.Abbreviation) for i in
             range(1, latest)]
        ax.plot([i for i in range(1, latest)], y, label=v.Abbreviation, color='#' + v.TeamColor, linewidth=1,
                linestyle="solid" if config.camera_info.get(season, {}).get(k, 'black') == "black" else "dashed")
    ax.legend(fontsize='small')
    ax.grid(True)
    output_path = f"{base_dir}/results.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    plt.close(fig)
    log.info(f"Saved plot to {output_path}")

    champion_points = max(
        (
            [results[i].get_point(v.Abbreviation) + results[i].get_sprint_point(v.Abbreviation)
             for i in range(1, latest)]
            for v in drivers.values()
        ),
        key=sum,
    )
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout="tight")
    for k, v in drivers.items():
        y = [results[i].get_point(v.Abbreviation) + results[i].get_sprint_point(v.Abbreviation) for i in
             range(1, latest)]
        diff = [a - b for a, b in zip(accumulate(y), accumulate(champion_points))]
        ax.plot([i for i in range(1, latest)], diff, label=v.Abbreviation, color="#" + v.TeamColor, linewidth=1,
                linestyle="solid" if config.camera_info.get(season, {}).get(k, 'black') == "black" else "dashed")
    ax.legend(fontsize='small')
    ax.grid(True)
    output_path = f"{base_dir}/diffs.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    plt.close(fig)
    log.info(f"Saved plot to {output_path}")

    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    x = [i for i in range(1, latest)]
    for k, v in drivers.items():
        y = [results[i].get_grid_position(v.Abbreviation) for i in range(1, latest)]
        ax.plot(x, y, label=v.Abbreviation, color='#' + v.TeamColor, linewidth=1,
                linestyle="solid" if config.camera_info.get(season, {}).get(k, 'black') == "black" else "dashed")
    ax.legend(fontsize='small')
    ax.grid(True)
    ax.invert_yaxis()
    output_path = f"{base_dir}/grid_positions.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    plt.close(fig)
    log.info(f"Saved plot to {output_path}")

    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    for k, v in drivers.items():
        y = [results[i].get_grid_position(v.Abbreviation) - results[i].get_position(v.Abbreviation) for i in
             range(1, latest)]
        ax.plot(x, y, label=v.Abbreviation, color='#' + v.TeamColor, linewidth=1,
                linestyle="solid" if config.camera_info.get(season, {}).get(k, 'black') == "black" else "dashed")
    ax.legend(fontsize='small')
    ax.grid(True)
    output_path = f"{base_dir}/grid_to_results.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches='tight')
    plt.close(fig)
    log.info(f"Saved plot to {output_path}")

    values_map = {}
    sum_map = {}
    color_map = {}

    color_master_map = {1: 'gold', 2: 'silver', 3: 'darkgoldenrod', 4: '#4B0000', 5: '#660000', 6: '#800000',
                        7: '#990000', 8: '#B20000', 9: '#CC0000', 10: '#E60000'}
    one_to_ten = sorted(color_master_map.keys())
    summaries = ["point sum", "point", "order", "grid", "top10", "top3", "sprint"] + [f"{i}" for i in one_to_ten]
    for k, v in drivers.items():
        values = [
            f"{'{:.0f}'.format(results[i].get_point(v.Abbreviation))} ({'{:.0f}'.format(results[i].get_grid_position(v.Abbreviation))})" if i in results else 0
            for i in range(1, latest)]
        sum_point = sum([results[i].get_point(v.Abbreviation) + results[i].get_sprint_point(v.Abbreviation) for i in
                         range(1, latest)])
        positions = [results[i].get_position(v.Abbreviation) if i in results else 0 for i in range(1, latest)]
        grids = [results[i].get_grid_position(v.Abbreviation) if i in results else 0 for i in range(1, latest)]
        point_finish = sum(1 for i in range(1, latest) if results[i].get_point(v.Abbreviation) > 0)
        top3_finish = sum(1 for i in range(1, latest) if results[i].get_point(v.Abbreviation) >= 15)
        sprint = sum([results[i].get_sprint_point(v.Abbreviation) if i in results else 0 for i in range(1, latest)])
        count_by_order = [sum(p == rank for p in
                              (results[i].get_position(v.Abbreviation) if i in results else 0 for i in
                               range(1, latest))) for rank in one_to_ten]

        values_map[k] = values + [sum_point, "{:.2f}".format(sum_point / (latest - 1)),
                                  "{:.2f}".format(sum(positions) / (latest - 1)),
                                  "{:.2f}".format(sum(grids) / (latest - 1)), point_finish, top3_finish,
                                  sprint] + count_by_order

        sum_map[k] = sum_point

        color_map[k] = [color_master_map.get(results[i].get_position(v.Abbreviation),
                                             'white') if i in results else 'white' for i in
                        range(1, latest)] + ['white' for _ in range(0, len(summaries))]

    drivers_standing = [k for k, _ in sorted(sum_map.items(), key=lambda x: x[1], reverse=True)]

    headers = ["No", "name"] + [drivers[k].Abbreviation for k in drivers_standing]
    header_colors = (['lightgrey', 'lightgrey'] + ['#' + drivers[k].TeamColor for k in drivers_standing])

    round_numbers = [[event.RoundNumber for _, event in schedule.iterrows()] + summaries]
    event_names = [
        [event.EventName.replace('Grand Prix', '') for _, event in schedule.iterrows()] + ["" for _ in
                                                                                           range(0, len(summaries))]]

    topic_colors = [['lightgrey' for _ in range(1, len(schedule) + 2)]]

    fig = graph_objects.Figure(data=[graph_objects.Table(
        header=dict(values=headers, fill_color=header_colors, align='center'),
        cells=dict(values=round_numbers + event_names + [values_map[k] for k in drivers_standing],
                   fill_color=topic_colors + topic_colors + [color_map[k] for k in drivers_standing],
                   align='center', font_color='darkgrey')
    )], layout=dict(autosize=True, margin=dict(autoexpand=True)))

    output_path = f"{base_dir}/points.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.write_image(output_path, width=1920, height=2160)
    log.info(f"Saved plot to {output_path}")

    output_path = f"{base_dir}/events.png"
    if os.path.exists(output_path):
        return
    fig = graph_objects.Figure(data=[graph_objects.Table(
        header=dict(values=["number", "name", "sprint", "date"], fill_color='lightgrey', align='center'),
        cells=dict(values=[[event.RoundNumber for _, event in schedule.iterrows()],
                           [event.EventName for _, event in schedule.iterrows()],
                           [event.EventFormat == "sprint_qualifying" for _, event in schedule.iterrows()],
                           [event.EventDate for _, event in schedule.iterrows()]],
                   fill_color=[
                       ["white" if event.RoundNumber % 2 == 0 else "#f2f2f2" for _, event in schedule.iterrows()]],
                   align='center')
    )], layout=dict(autosize=True, margin=dict(autoexpand=True)))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.write_image(output_path, width=1920, height=2160)
    log.info(f"Saved plot to {output_path}")


if __name__ == "__main__":
    main()
