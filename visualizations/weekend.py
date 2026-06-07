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
    for session_name in sessions:
        try:
            session = fastf1.get_session(year, race_number, session_name)
        except ValueError:
            continue
        session.load(weather=False, messages=False, telemetry=False)
        if datetime.datetime.now() < session.date:
            continue
        for driver in session.drivers:
            driver_laps = session.laps.pick_drivers(driver)
            session_names = []
            bg_colors = []
            stints = set()
            for i in range(0, len(driver_laps)):
                lap = driver_laps.iloc[i]
                if not lap.FreshTyre:
                    continue
                if lap.Stint in stints:
                    continue
                session_names.append(session_name)
                compound = lap.Compound
                bg_colors.append(constants.compound_color.get(compound, "#dddddd"))
                stints.add(lap.Stint)
            driver_name = session.get_driver(driver)['Abbreviation']
            if len(session_names) > 0:
                if driver_name in drivers:
                    drivers[driver_name]['Sessions'].extend(session_names)
                    drivers[driver_name]['Colors'].extend(bg_colors)
                else:
                    drivers[driver_name] = {'Sessions': session_names, 'Colors': bg_colors}

    if session is None:
        return

    max_rows = max(len(d["Sessions"]) for d in drivers.values())
    table_columns = [v["Sessions"] + [""] * (max_rows - len(v["Sessions"])) for v in drivers.values()]
    table_colors = [v["Colors"] + ["white"] * (max_rows - len(v["Colors"])) for v in drivers.values()]

    fig = graph_objects.Figure(data=[graph_objects.Table(
        header={'values': list(drivers.keys()), 'fill_color': 'lightgrey', 'align': 'center'},
        cells={'values': table_columns, 'fill_color': table_colors, 'align': 'center'}
    )])

    session = fastf1.get_session(year, race_number, 'FP1')
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/tyres.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.write_image(output_path, width=1920, height=1080)
    log.info(f"Saved plot to {output_path}")
