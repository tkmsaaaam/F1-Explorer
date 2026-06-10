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
        if session is None:
            continue
        if datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) < session.date:
            continue
        order = [d for d in session.results.Abbreviation]
        for driver in session.drivers:
            driver_laps = session.laps.pick_drivers(driver)
            laps = driver_laps[driver_laps.FreshTyre].drop_duplicates(subset=['Stint'], keep='first')
            session_names = [session_name for _ in range(len(laps))]
            compounds = [lap.Compound for lap in laps.itertuples()]
            driver_name = session.get_driver(driver).Abbreviation
            if len(session_names) > 0:
                if driver_name in drivers:
                    drivers[driver_name]['Sessions'].extend(session_names)
                    drivers[driver_name]['Compounds'].extend(compounds)
                else:
                    drivers[driver_name] = {'Sessions': session_names, 'Compounds': compounds}

    if session is None:
        return
    sprint = session.event.EventFormat == 'sprint_qualifying'
    max_rows = max(len(d["Sessions"]) for d in drivers.values())
    names = order + list(set(drivers.keys()) - set(order))
    table_columns = []
    table_colors = []
    for v in names:
        driver_data = drivers.get(v, {'Compounds': [], 'Sessions': []})
        compounds = driver_data.get('Compounds', [])
        col_counts = [
            f"{compounds.count(name)}({constants.compound_counts_sprint.get(name, 0) if sprint
            else constants.compound_counts.get(name, 0)})" for name in constants.compound_color.keys()
        ]
        session_list = driver_data.get('Sessions', [])
        padding_len = max_rows - len(session_list)
        driver_column = col_counts + session_list + [""] * padding_len
        table_columns.append(driver_column)
        compound_colors = [constants.compound_color.get(name, "white") for name in compounds]
        driver_color = list(constants.compound_color.values()) + compound_colors + ["white"] * padding_len
        table_colors.append(driver_color)

    fig = graph_objects.Figure(data=[graph_objects.Table(
        header={'values': names, 'fill_color': 'lightgrey', 'align': 'center'},
        cells={'values': table_columns, 'fill_color': table_colors, 'align': 'center'}
    )])

    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/tyres.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.write_image(output_path, width=1920, height=1080)
    log.info(f"Saved plot to {output_path}")
