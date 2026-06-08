import datetime
import os
from logging import Logger
from typing import Final

import fastf1
# noinspection PyPackageRequirements
from opentelemetry import trace
from plotly import graph_objects

import constants

tracer = trace.get_tracer(__name__)


@tracer.start_as_current_span("plot_tyre")
def plot_tyre(year: int, race_number: int, log: Logger):
    drivers = {}
    sessions: Final[list[str]] = ['FP1', 'FP2', 'FP3', 'SQ', 'S', 'Q', 'R']
    session = None
    order = []
    for session_name in sessions:
        try:
            session = fastf1.get_session(year, race_number, session_name)
        except ValueError:
            continue
        session.load(weather=False, messages=False, telemetry=False)
        if session is not None and len(session.drivers) > 0:
            order = [d for d in session.results.Abbreviation]
        if datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) < session.date:
            continue
        for driver in session.drivers:
            driver_laps = session.laps.pick_drivers(driver)
            laps = driver_laps[driver_laps['FreshTyre']].drop_duplicates(subset=['Stint'], keep='first')
            session_names = [session_name for _ in range(len(laps))]
            bg_colors = [constants.compound_color.get(lap.Compound, "#dddddd") for lap in laps.itertuples()]
            driver_name = session.get_driver(driver)['Abbreviation']
            if len(session_names) > 0:
                if driver_name in drivers:
                    drivers[driver_name]['Sessions'].extend(session_names)
                    drivers[driver_name]['Colors'].extend(bg_colors)
                else:
                    drivers[driver_name] = {'Sessions': session_names, 'Colors': bg_colors}

    if session is None:
        return
    sprint = session.event.EventFormat == 'sprint_qualifying'
    max_rows = max(len(d["Sessions"]) for d in drivers.values())
    diff = set(drivers.keys()) - set(order)
    l = order + list(diff)
    table_columns = [
        [(f"{drivers.get(v)['Colors'].count(color)}("
          f"{constants.compound_counts_sprint.get(color, 0) if sprint else constants.compound_counts_sprint.get(color, 0)}"
          f")")
         for color in constants.compound_color.values()
         ] +
        drivers.get(v)["Sessions"] + [""] * (max_rows - len(drivers.get(v)["Sessions"])) for v in l
    ]
    table_colors = [
        [color for color in constants.compound_color.values()] +
        drivers.get(v)["Colors"] + ["white"] * (max_rows - len(drivers.get(v)["Colors"])) for v in l
    ]

    fig = graph_objects.Figure(data=[graph_objects.Table(
        header={'values': l, 'fill_color': 'lightgrey', 'align': 'center'},
        cells={'values': table_columns, 'fill_color': table_colors, 'align': 'center'}
    )])

    session = fastf1.get_session(year, race_number, 'FP1')
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/tyres.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.write_image(output_path, width=1920, height=1080)
    log.info(f"Saved plot to {output_path}")
