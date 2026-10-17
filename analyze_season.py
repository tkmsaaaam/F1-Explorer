import datetime
import base64
import os
import zoneinfo
from itertools import accumulate
from typing import Final, cast

import fastf1
import plotly.graph_objects as go
import pandas
import structlog.stdlib
from fastf1.core import DriverResult
from fastf1.events import EventSchedule
from fastf1.ergast import Ergast
# noinspection PyPackageRequirements
from opentelemetry import trace

from f1_explorer import constants
from f1_explorer import config as config_module
from f1_explorer.season_mileage import (
    Driver, SESSION_ROWS, WeekendMetrics, analyze_session, apply_driver_aliases, render_report_section, session_code,
)

tracer = trace.get_tracer(__name__)


class Weekend:
    def __init__(self, gp_name: str):
        self.__gp_name = gp_name.replace('Grand Prix', '').strip()
        self.__grid_position: dict[str, int] = {}
        self.__position: dict[str, int] = {}
        self.__point: dict[str, int] = {}
        self.__sprint_point: dict[str, int] = {}
        self.__has_race_result = False

    def set_grid_position(self, abbreviation: str, v: int):
        self.__has_race_result = True
        self.__grid_position[abbreviation] = v

    def set_position(self, abbreviation: str, v: int):
        self.__position[abbreviation] = v

    def set_point(self, abbreviation: str, v: int):
        self.__point[abbreviation] = v

    def set_sprint_point(self, abbreviation: str, v: int):
        self.__sprint_point[abbreviation] = v

    def has_race_result(self) -> bool:
        return self.__has_race_result

    def has_sprint_result(self) -> bool:
        return bool(self.__sprint_point)

    def recorded_position(self, abbreviation: str) -> int | None:
        return self.__position.get(abbreviation)

    def has_driver_result(self, abbreviation: str) -> bool:
        return abbreviation in self.__position or abbreviation in self.__sprint_point

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


def __season_driver_order(year: int, drivers: dict[str, Driver], results: dict[int, Weekend],
                          log: structlog.stdlib.BoundLogger) -> list[str]:
    """Prefer the latest published championship order, including countback ties."""
    published: dict[str, int] = {}
    if drivers:
        try:
            response = Ergast().get_driver_standings(season=year, round="last", limit=100)
            if not response.content or response.content[0].empty:
                raise ValueError("No published driver standings")
            for row in response.content[0].itertuples(index=False):
                for key, driver in drivers.items():
                    same_id = key == str(row.driverId)
                    same_fallback = (key.startswith("number:")
                                     and driver.number == str(getattr(row, "driverNumber", ""))
                                     and driver.abbreviation == str(getattr(row, "driverCode", "")))
                    if same_id or same_fallback:
                        published[key] = int(row.position)
        except Exception as exception:
            log.warning("Could not load driver standings; using loaded results", reason=str(exception))

    def sort_key(driver: Driver) -> tuple:
        if driver.key in published:
            return (0, published[driver.key])
        points = sum(gp.get_point(driver.abbreviation) + gp.get_sprint_point(driver.abbreviation)
                     for gp in results.values())
        positions = [gp.recorded_position(driver.abbreviation) for gp in results.values()]
        max_position = max((gp.recorded_position(other.abbreviation) or 0
                            for gp in results.values() for other in drivers.values()), default=0)
        countback = tuple(-positions.count(position) for position in range(1, max_position + 1))
        participant = any(gp.has_driver_result(driver.abbreviation) for gp in results.values())
        return (1, not participant, -points, countback, driver.abbreviation, driver.key)

    return [driver.key for driver in sorted(drivers.values(), key=sort_key)]


def _sprint_point_rows(results: dict[int, Weekend], schedule: EventSchedule) -> list[tuple[int, str]]:
    """List loaded sprint results in calendar order, using venue labels."""
    locations = {int(event.RoundNumber): str(event.Location)
                 for event in schedule.itertuples(index=False)
                 if pandas.notna(getattr(event, "Location", None))}
    return [(round_number, locations.get(round_number, weekend.get_gp_name()))
            for round_number, weekend in sorted(results.items()) if weekend.has_sprint_result()]


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
                         log: structlog.stdlib.BoundLogger,
                         mileage_html: str = "") -> None:
    """Write the season dashboard, keeping the generated charts self-contained."""
    report_dir = f"./reports/{year}"
    output_path = f"{report_dir}/season.html"
    sections: list[str] = []
    for index, (title, chart) in enumerate(charts):
        sections.append(f'<section><h2>{title}</h2>{__plot_html(chart, include_plotlyjs=index == 0)}</section>')
    if points is not None:
        encoded = base64.b64encode(points).decode("ascii")
        sections.append(f'<section><h2>Season summary</h2><img src="data:image/png;base64,{encoded}" alt="Season summary"></section>')
    if mileage_html:
        sections.append(mileage_html)
    event_encoded = base64.b64encode(__render_events(schedule)).decode("ascii")
    sections.insert(0, f'<section><h2>Race calendar</h2><img src="data:image/png;base64,{event_encoded}" alt="Race calendar"></section>')
    html = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>F1 season report</title>
<style>body{font-family:system-ui,sans-serif;margin:2rem;background:#f7f7f7;color:#222}section{background:#fff;margin:1rem auto;padding:1rem;max-width:1400px;box-shadow:0 1px 4px #bbb}img{display:block;max-width:100%;height:auto;margin:auto}h1,h2{margin-top:0}.table-scroll{overflow:auto;max-width:100%}table{border-collapse:collapse;min-width:100%;font-size:.85rem}th,td{border:1px solid #ddd;padding:.35rem;text-align:center;white-space:nowrap}thead th,tbody th{position:sticky;background:#eee}thead th{top:0}tbody th{left:0}small{display:block;font-weight:normal}details{white-space:normal;font-size:.75rem}select{padding:.4rem}</style></head>
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
    log = config_module.log()
    try:
        config = config_module.load_config()
    except Exception as exception:
        log.warning('setup is failed', args=exception.args)
        return
    config.set_attribute_to_span()
    config_module.fast_f1()
    schedule = fastf1.get_event_schedule(config.get_year(), include_testing=False).sort_values(by='RoundNumber')

    drivers: dict[int, DriverResult] = {}
    results: dict[int, Weekend] = {}
    mileage_drivers = {}
    mileage_weekends: list[WeekendMetrics] = []
    identity_by_number = {}
    identity_history_by_number = {}

    now = datetime.datetime.now().astimezone()
    for event in schedule.itertuples(index=False):
        round_number = int(event.RoundNumber)
        event_metrics = WeekendMetrics(str(event.EventName), round_number)
        session_names = [getattr(event, f"Session{index}", "") for index in range(1, 6)]
        session_dates = [getattr(event, f"Session{index}Date", None) for index in range(1, 6)]
        any_started = False
        session_objects = {}
        for session_name, session_date in zip(session_names, session_dates):
            code = session_code(str(session_name)) if session_name else None
            if code is None:
                continue
            if code in {"Q", "SQ"}:
                for index in range(1, 4):
                    event_metrics.sessions[f"{code}{index}"] = "planned"
            if code in SESSION_ROWS:
                event_metrics.sessions[code] = "planned"
            try:
                scheduled = None if session_date is None or pandas.isna(session_date) else pandas.Timestamp(session_date).to_pydatetime()
                if scheduled is not None:
                    compare_now = now.astimezone(scheduled.tzinfo) if scheduled.tzinfo else now.replace(tzinfo=None)
                    if scheduled > compare_now:
                        continue
            except (TypeError, ValueError, OverflowError):
                pass
            any_started = True
            try:
                session = fastf1.get_session(config.get_year(), str(event.EventName), str(session_name))
                session.load(laps=True, telemetry=False, weather=False, messages=True)
                session_objects[code] = session
                terminal = False
                status_data = getattr(session, "session_status", None)
                if status_data is not None and not status_data.empty:
                    last_status = str(status_data.iloc[-1].get("Status", ""))
                    terminal = last_status in {"Finished", "Finalised", "Ends", "Inactive"}
                provisional = not terminal and scheduled is not None and (
                    now - (scheduled.astimezone(now.tzinfo) if scheduled.tzinfo else scheduled.replace(tzinfo=now.tzinfo))
                ).total_seconds() < 12 * 3600
                identity_aliases = {}
                found_drivers, found_metrics = analyze_session(
                    session, code, provisional=provisional,
                    identity_by_number=identity_by_number,
                    identity_history_by_number=identity_history_by_number,
                    identity_aliases=identity_aliases,
                )
                apply_driver_aliases(mileage_drivers, mileage_weekends + [event_metrics], identity_aliases)
                mileage_drivers.update(found_drivers)
                for key, metric in found_metrics.items():
                    event_metrics.drivers.setdefault(key, type(metric)()).laps.update(metric.laps)
                    event_metrics.drivers[key].attacks.update(metric.attacks)
                has_laps = getattr(session, "laps", None) is not None and not session.laps.empty
                state = "unknown" if not has_laps else "provisional" if provisional else "available"
                if code in SESSION_ROWS:
                    event_metrics.sessions[code] = state
                if code in {"Q", "SQ"}:
                    for index in range(1, 4):
                        event_metrics.sessions[f"{code}{index}"] = state
            except Exception as exception:
                log.warning("Could not load season session", event=str(event.EventName), session=str(session_name), reason=str(exception))
                if code in SESSION_ROWS:
                    event_metrics.sessions[code] = "failed"
                if code in {"Q", "SQ"}:
                    for index in range(1, 4):
                        event_metrics.sessions[f"{code}{index}"] = "failed"

        if any_started:
            mileage_weekends.append(event_metrics)

        gp = Weekend(cast(str, event.EventName))
        race = session_objects.get("R")
        if race is not None and hasattr(race, "results") and race.results is not None:
            for driver_row in race.results.itertuples(index=False):
                abbreviation: str = cast(str, driver_row.Abbreviation)
                gp.set_grid_position(abbreviation, int(driver_row.GridPosition) if pandas.notna(driver_row.GridPosition) else 0)
                gp.set_position(abbreviation, int(driver_row.Position) if pandas.notna(driver_row.Position) else 0)
                gp.set_point(abbreviation, int(driver_row.Points) if pandas.notna(driver_row.Points) else 0)
                if driver_row.DriverNumber not in drivers:
                    drivers[int(cast(str, driver_row.DriverNumber))] = race.get_driver(abbreviation)
            results[round_number] = gp
        sprint = session_objects.get("S")
        if sprint is not None and hasattr(sprint, "results") and sprint.results is not None:
            for driver_row in sprint.results.itertuples(index=False):
                gp.set_sprint_point(cast(str, driver_row.Abbreviation),
                                    int(driver_row.Points) if pandas.notna(driver_row.Points) else 0)
            results.setdefault(round_number, gp)

    base_dir: Final = f"./images/{config.get_year()}"
    column_order = __season_driver_order(config.get_year(), mileage_drivers, results, log)
    mileage_html = render_report_section(mileage_drivers, mileage_weekends, driver_order=column_order)
    if len(results) == 0:
        if config.get_year() > now.year and not mileage_weekends:
            return
        __save_season_report(config.get_year(), base_dir, schedule, [], None, log, mileage_html)
        return

    x = sorted(results)
    latest = len(x)
    charts: list[tuple[str, go.Figure]] = []
    for title, value_fn, invert in (
            ("Championship standings", lambda v, i: sum(
                results[j].get_point(v.Abbreviation) + results[j].get_sprint_point(v.Abbreviation)
                for j in x if j <= i), False),
            ("Race points", lambda v, i: results[i].get_point(v.Abbreviation) + results[i].get_sprint_point(v.Abbreviation), False),
            ("Gap to champion", None, False),
            ("Grid positions", lambda v, i: (results[i].get_grid_position(v.Abbreviation)
                                               if results[i].has_race_result() else None), True)):
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
        positions = [results[i].get_position(v.Abbreviation) if results[i].has_race_result() else None for i in x]
        grids = [results[i].get_grid_position(v.Abbreviation) if results[i].has_race_result() else None for i in x]
        y = [None if grid is None or position is None else grid - position
             for grid, position in zip(grids, positions)]
        hover_text = ["race not run" if difference is None else f'{difference:+.0f} ({grid:.0f} - {position:.0f})'
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
    sprint_rows = _sprint_point_rows(results, schedule)
    summaries = ["", "point sum", "point", "order", "grid", "top10", "top3"]
    if sprint_rows:
        summaries.append("Sprint")

    for k, v in drivers.items():
        values = [
            f"{'{:.0f}'.format(results[i].get_point(v.Abbreviation))} ({'{:.0f}'.format(results[i].get_grid_position(v.Abbreviation))})" if results[i].has_race_result() else "—"
            for i in x]
        sum_point = sum([
            results[i].get_point(v.Abbreviation) + results[i].get_sprint_point(v.Abbreviation) for i in x
        ])
        race_rounds = [i for i in x if results[i].has_race_result()]
        positions = [results[i].get_position(v.Abbreviation) for i in race_rounds]
        grids = [results[i].get_grid_position(v.Abbreviation) for i in race_rounds]
        point_finish = sum(1 for i in race_rounds if results[i].get_point(v.Abbreviation) > 0)
        top3_finish = sum(1 for i in race_rounds if results[i].get_point(v.Abbreviation) >= 15)
        count_by_order = [sum(
            p == rank for p in (
                results[i].get_position(v.Abbreviation) for i in race_rounds
            )
        ) for rank in one_to_ten]

        values_map[k] = values + [
            "", sum_point, "{:.2f}".format(sum_point / latest),
            "{:.2f}".format(sum(positions) / len(race_rounds)) if race_rounds else "—",
            "{:.2f}".format(sum(grids) / len(race_rounds)) if race_rounds else "—",
            point_finish, top3_finish] + ([sum(results[round_number].get_sprint_point(v.Abbreviation)
                                              for round_number, _ in sprint_rows)] if sprint_rows else []) + [
                results[round_number].get_sprint_point(v.Abbreviation) for round_number, _ in sprint_rows
            ] + [""] + count_by_order

        sum_map[k] = sum_point

        color_map[k] = ([color_master_map.get(
            results[i].get_position(v.Abbreviation), 'white'
        ) for i in x]
                        + ['lightgrey']
                        + ['white'] * (len(summaries) - 1 + len(sprint_rows))
                        + ['lightgrey']
                        + ['white'] * len(one_to_ten))

    column_rank = {mileage_drivers[key].number: rank for rank, key in enumerate(column_order)}
    drivers_standing = sorted(sum_map, key=lambda number: (column_rank.get(str(number), len(column_rank)),
                                                          -sum_map[number]))

    round_numbers = [x + summaries + list(range(1, len(sprint_rows) + 1)) + [""] + [f"{i}" for i in one_to_ten]]
    event_names = [
        [results[i].get_gp_name() for i in x]
        + [""] * len(summaries)
        + [location for _, location in sprint_rows]
        + [""]
        + [""] * len(one_to_ten)
    ]

    topic_colors = [['lightgrey'] * len(round_numbers[0])]
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

    points = cast(bytes, fig.to_image(format="png", width=1920,
                                     height=max(2160, 36 * (len(round_numbers[0]) + 1) + 80)))

    if config.get_year() > now.year:
        return
    __save_season_report(config.get_year(), base_dir, schedule, charts, points, log, mileage_html)


if __name__ == "__main__":
    __main()
