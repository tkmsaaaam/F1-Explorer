import datetime
import base64
import os
import zoneinfo
from itertools import accumulate
from typing import Final, cast

import fastf1
import plotly.graph_objects as go
import structlog.stdlib
from fastf1.core import DriverResult
from fastf1.events import EventSchedule
# noinspection PyPackageRequirements
from opentelemetry import trace

import constants
import setup

tracer = trace.get_tracer(__name__)


class Weekend:
    def __init__(self, gp_name: str):
        self.__gp_name = gp_name.replace('Grand Prix', '').strip()
        self.__grid_position: dict[str, int] = {}
        self.__position: dict[str, int] = {}
        self.__point: dict[str, int] = {}
        self.__sprint_point: dict[str, int] = {}

    def set_grid_position(self, abbreviation: str, v: int):
        self.__grid_position[abbreviation] = v

    def set_position(self, abbreviation: str, v: int):
        self.__position[abbreviation] = v

    def set_point(self, abbreviation: str, v: int):
        self.__point[abbreviation] = v

    def set_sprint_point(self, abbreviation: str, v: int):
        self.__sprint_point[abbreviation] = v

    def get_gp_name(self):
        return self.__gp_name

    def get_grid_position(self, abbreviation: str) -> int:
        if abbreviation in self.__grid_position:
            return self.__grid_position[abbreviation]
        return len(self.__grid_position) + 1

    def get_position(self, abbreviation: str) -> int:
        if abbreviation in self.__position:
            return self.__position[abbreviation]
        return len(self.__position) + 1

    def get_point(self, abbreviation: str) -> int:
        if abbreviation in self.__point:
            return self.__point[abbreviation]
        return 0

    def get_sprint_point(self, abbreviation: str) -> int:
        if abbreviation in self.__sprint_point:
            return self.__sprint_point[abbreviation]
        return 0


def get_color(v: DriverResult) -> str:
    if v.TeamColor == 'nan':
        return '808080'
    return v.TeamColor


def determine_linestyle(year: int, driver: int) -> str:
    if constants.camera.get(year, {}).get(driver, 'black') == "black":
        return "solid"
    else:
        return "dash"


def __render_events(schedule: EventSchedule) -> bytes:
    fig = go.Figure(
        data=[go.Table(
            header=go.table.Header(
                values=["number", "name", "sprint", "datetime"],
                fill=go.table.header.Fill(color='lightgrey'), align="center"),
            cells=go.table.Cells(
                values=[[event.RoundNumber for _, event in schedule.iterrows()],
                        [event.EventName for _, event in schedule.iterrows()],
                        [event.EventFormat == "sprint_qualifying" for _, event in schedule.iterrows()],
                        [datetime.datetime.fromtimestamp(event.Session5Date.timestamp(),
                                                         tz=zoneinfo.ZoneInfo("Asia/Tokyo")) for _, event in
                         schedule.iterrows()]],
                fill=go.table.cells.Fill(
                    color=[["white" if event.RoundNumber % 2 == 0 else "#f2f2f2" for _, event in schedule.iterrows()]]),
                align='center'))],
        layout=go.Layout(autosize=True, margin=go.layout.Margin(autoexpand=True)))

    return cast(bytes, fig.to_image(format="png", width=1920, height=2160))


def __plot_html(fig: go.Figure, include_plotlyjs: bool = False) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=include_plotlyjs,
                       config={"responsive": True, "displaylogo": False})


def __line_plot(title: str, x: list[int], series: list[tuple[str, list[float], str, str]],
                invert_y: bool = False) -> go.Figure:
    fig = go.Figure()
    for name, y, color, linestyle in series:
        fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name=name,
                                 line={"color": color, "width": 1, "dash": linestyle}))
    fig.update_layout(title=title, template="plotly_white", hovermode="x unified",
                      xaxis={"title": "Round", "dtick": 1}, yaxis={"title": "Position" if invert_y else "Points",
                                                                   "autorange": "reversed" if invert_y else True},
                      legend={"font": {"size": 10}}, margin={"l": 50, "r": 20, "t": 50, "b": 45})
    return fig


def __save_season_report(year: int, image_dir: str, schedule: EventSchedule,
                         charts: list[tuple[str, go.Figure]], points: bytes | None,
                         log: structlog.stdlib.BoundLogger) -> None:
    """Write the season dashboard, keeping the generated charts self-contained."""
    report_dir = f"./reports/{year}"
    output_path = f"{report_dir}/season.html"
    sections: list[str] = []
    for index, (title, chart) in enumerate(charts):
        sections.append(f'<section><h2>{title}</h2>{__plot_html(chart, include_plotlyjs=index == 0)}</section>')
    if points is not None:
        encoded = base64.b64encode(points).decode("ascii")
        sections.append(f'<section><h2>Season summary</h2><img src="data:image/png;base64,{encoded}" alt="Season summary"></section>')
    event_encoded = base64.b64encode(__render_events(schedule)).decode("ascii")
    sections.insert(0, f'<section><h2>Race calendar</h2><img src="data:image/png;base64,{event_encoded}" alt="Race calendar"></section>')
    html = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>F1 season report</title>
<style>body{font-family:system-ui,sans-serif;margin:2rem;background:#f7f7f7;color:#222}section{background:#fff;margin:1rem auto;padding:1rem;max-width:1400px;box-shadow:0 1px 4px #bbb}img{display:block;max-width:100%;height:auto;margin:auto}h1,h2{margin-top:0}</style></head>
<body><h1>F1 season report: YEAR</h1>CONTENT</body></html>""".replace("YEAR", str(year)).replace("CONTENT", "\n".join(sections))
    os.makedirs(report_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as report_file:
        report_file.write(html)
    for filename in ("standings.png", "results.png", "diffs.png", "grid_positions.png", "grid_to_results.png"):
        old_path = f"{image_dir}/{filename}"
        if os.path.exists(old_path):
            os.remove(old_path)
    log.info("Saved season report", path=output_path)


@tracer.start_as_current_span("main")
def __main():
    log = setup.log()
    try:
        config = setup.load_config()
    except Exception as exception:
        log.warning('setup is failed', args=exception.args)
        return
    config.set_attribute_to_span()
    setup.fast_f1()
    schedule = fastf1.get_event_schedule(config.get_year(), include_testing=False).sort_values(by='RoundNumber')

    drivers: dict[int, DriverResult] = {}
    results: dict[int, Weekend] = {}

    now = datetime.datetime.now()
    for event in schedule.itertuples(index=False):
        if now < event.EventDate:
            break
        if event.RoundNumber not in results:
            results[cast(int, event.RoundNumber)] = Weekend(cast(str, event.EventName))

        gp: Weekend = results[cast(int, event.RoundNumber)]
        if event.EventFormat == "sprint_qualifying":
            sprint = fastf1.get_session(config.get_year(), cast(str, event.EventName), "S")
            sprint.load(laps=False, telemetry=False, weather=False, messages=False)
            for driver_row in sprint.results.itertuples(index=False):
                gp.set_sprint_point(cast(str, driver_row.Abbreviation), cast(int, driver_row.Points))
        race = fastf1.get_session(config.get_year(), event.EventName, "R")
        race.load(laps=False, telemetry=False, weather=False, messages=False)
        for driver_row in race.results.itertuples(index=False):
            abbreviation: str = cast(str, driver_row.Abbreviation)
            gp.set_grid_position(abbreviation, cast(int, driver_row.GridPosition))
            gp.set_position(abbreviation, cast(int, driver_row.Position))
            gp.set_point(abbreviation, cast(int, driver_row.Points))
            if driver_row.DriverNumber not in drivers:
                drivers[int(cast(str, driver_row.DriverNumber))] = race.get_driver(abbreviation)

    base_dir: Final = f"./images/{config.get_year()}"
    if len(results) == 0:
        if config.get_year() > now.year:
            return
        __save_season_report(config.get_year(), base_dir, schedule, [], None, log)
        return

    latest = len(results) + 1

    x = list(range(1, latest))
    charts: list[tuple[str, go.Figure]] = []
    for title, value_fn, invert in (
            ("Championship standings", lambda v, i: sum(
                results[j].get_point(v.Abbreviation) + results[j].get_sprint_point(v.Abbreviation)
                for j in range(1, i + 1)), False),
            ("Race points", lambda v, i: results[i].get_point(v.Abbreviation) + results[i].get_sprint_point(v.Abbreviation), False),
            ("Gap to champion", None, False),
            ("Grid positions", lambda v, i: results[i].get_grid_position(v.Abbreviation), True)):
        series = []
        for k, v in drivers.items():
            if value_fn is None:
                own = [results[i].get_point(v.Abbreviation) + results[i].get_sprint_point(v.Abbreviation) for i in x]
                champion = max(([
                    results[i].get_point(other.Abbreviation) + results[i].get_sprint_point(other.Abbreviation)
                    for i in x] for other in drivers.values()), key=sum)
                y = [a - b for a, b in zip(accumulate(own), accumulate(champion))]
            else:
                y = [value_fn(v, i) for i in x]
            series.append((v.Abbreviation, y, '#' + get_color(v), determine_linestyle(config.get_year(), k)))
        charts.append((title, __line_plot(title, x, series, invert_y=invert)))

    grid_to_result = go.Figure()
    for k, v in drivers.items():
        positions = [results[i].get_position(v.Abbreviation) for i in x]
        grids = [results[i].get_grid_position(v.Abbreviation) for i in x]
        y = [grid - position for grid, position in zip(grids, positions)]
        hover_text = [f'{difference:+.0f} ({grid:.0f} - {position:.0f})'
                      for difference, grid, position in zip(y, grids, positions)]
        filled = constants.camera.get(config.get_year(), {}).get(k, 'black') == 'black'
        color = '#' + get_color(v)
        grid_to_result.add_trace(go.Scatter(
            x=x, y=y, text=hover_text, mode='lines+markers', name=v.Abbreviation,
            line={'color': color, 'width': 1, 'dash': determine_linestyle(config.get_year(), k)},
            marker={'size': 7, 'color': color if filled else 'white',
                    'line': {'color': color, 'width': 1}},
            hovertemplate='%{fullData.name}: %{text}<extra></extra>',
        ))
    grid_to_result.update_layout(title='Grid to result', template='plotly_white', hovermode='x unified',
                                 xaxis={'title': 'Round', 'dtick': 1}, yaxis={'title': 'Grid - result'},
                                 legend={'font': {'size': 10}})
    charts.append(('Grid to result', grid_to_result))

    values_map = {}
    sum_map = {}
    color_map = {}

    color_master_map: Final = {1: 'gold', 2: 'silver', 3: 'darkgoldenrod', 4: '#4B0000', 5: '#660000', 6: '#800000',
                               7: '#990000', 8: '#B20000', 9: '#CC0000', 10: '#E60000'}
    one_to_ten = sorted(color_master_map.keys())
    summaries: Final = ["", "point sum", "point", "order", "grid", "top10", "top3", "sprint", ""]

    for k, v in drivers.items():
        values = [
            f"{'{:.0f}'.format(results[i].get_point(v.Abbreviation))} ({'{:.0f}'.format(results[i].get_grid_position(v.Abbreviation))})" if i in results else 0
            for i in range(1, latest)]
        sum_point = sum([
            results[i].get_point(v.Abbreviation) + results[i].get_sprint_point(v.Abbreviation) for i in range(1, latest)
        ])
        positions = [results[i].get_position(v.Abbreviation) if i in results else 0 for i in range(1, latest)]
        grids = [results[i].get_grid_position(v.Abbreviation) if i in results else 0 for i in range(1, latest)]
        point_finish = sum(1 for i in range(1, latest) if results[i].get_point(v.Abbreviation) > 0)
        top3_finish = sum(1 for i in range(1, latest) if results[i].get_point(v.Abbreviation) >= 15)
        sprint = sum([results[i].get_sprint_point(v.Abbreviation) if i in results else 0 for i in range(1, latest)])
        count_by_order = [sum(
            p == rank for p in (
                results[i].get_position(v.Abbreviation) if i in results else 0 for i in range(1, latest)
            )
        ) for rank in one_to_ten]

        values_map[k] = values + [
            "", sum_point, "{:.2f}".format(sum_point / (latest - 1)), "{:.2f}".format(sum(positions) / (latest - 1)),
            "{:.2f}".format(sum(grids) / (latest - 1)), point_finish, top3_finish, sprint, ""] + count_by_order

        sum_map[k] = sum_point

        color_map[k] = ([color_master_map.get(
            results[i].get_position(v.Abbreviation), 'white'
        ) if i in results else 'white' for i in range(1, latest)]
                        + ['lightgrey']
                        + ['white'] * (len(summaries) - 2)
                        + ['lightgrey']
                        + ['white'] * (len(one_to_ten) - 1))

    drivers_standing = [k for k, _ in sorted(sum_map.items(), key=lambda kk: kk[1], reverse=True)]

    round_numbers = [sorted(results.keys()) + summaries + [f"{i}" for i in one_to_ten]]
    event_names = [
        [r.get_gp_name() if (r := results.get(i)) is not None else "---" for i in sorted(results.keys())]
        + [""] * len(summaries)
        + [""] * len(one_to_ten)
    ]

    topic_colors = [['lightgrey'] * (len(schedule) + 1)]
    fig = go.Figure(
        data=[go.Table(
            header=go.table.Header(
                values=["No", "name"] + [f"{i} {drivers[k].Abbreviation}" for i, k in enumerate(drivers_standing, 1)],
                fill=go.table.header.Fill(
                    color=(['lightgrey', 'lightgrey'] + ['#' + get_color(drivers[k]) for k in drivers_standing])),
                align='center'),
            cells=go.table.Cells(
                values=round_numbers + event_names + [values_map[k] for k in drivers_standing],
                fill=go.table.cells.Fill(
                    color=topic_colors + topic_colors + [color_map[k] for k in drivers_standing]),
                align='center',
                font=go.table.cells.Font(color='darkgrey')))],
        layout=go.Layout(autosize=True, margin=go.layout.Margin(autoexpand=True)))

    points = cast(bytes, fig.to_image(format="png", width=1920, height=2160))

    if config.get_year() > now.year:
        return
    __save_season_report(config.get_year(), base_dir, schedule, charts, points, log)


if __name__ == "__main__":
    __main()
