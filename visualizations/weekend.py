import os
from logging import Logger
from typing import Final

import fastf1
from fastf1.core import DataNotLoadedError
from opentelemetry import trace
from plotly import graph_objects

import constants

tracer = trace.get_tracer(__name__)


@tracer.start_as_current_span("plot_tyre")
def plot_tyre(year: int, race_number: int, log: Logger):
    drivers = {}
    sessions: Final[str] = ['FP1', 'FP2', 'FP3', 'SQ', 'SR', 'Q', 'R']
    for session_name in sessions:
        try:
            session = fastf1.get_session(year, race_number, session_name)
        except ValueError:
            continue
        try:
            session.load(weather=False, messages=False, telemetry=False)
            laps = session.laps
        except DataNotLoadedError:
            continue
        for driver in session.drivers:
            driver_laps = laps[laps['DriverNumber'] == driver]
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

    driver_names = list(drivers.keys())
    # データの最大行数を取得
    max_rows = max(len(d["Sessions"]) for d in drivers.values())

    # 各ドライバー列のデータと背景色を作成
    table_columns = []
    table_colors = []

    for name in driver_names:
        s = drivers[name]["Sessions"]
        colors = drivers[name]["Colors"]
        # 足りないところは空白 + 白で埋める
        padded_sessions = s + [""] * (max_rows - len(sessions))
        padded_colors = colors + ["white"] * (max_rows - len(colors))
        table_columns.append(padded_sessions)
        table_colors.append(padded_colors)

    # 表を作成
    fig = graph_objects.Figure(data=[graph_objects.Table(
        header=dict(values=driver_names, fill_color='lightgrey', align='center'),
        cells=dict(values=table_columns, fill_color=table_colors, align='center')
    )])

    session = fastf1.get_session(year, race_number, 'FP1')
    output_path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/tyres.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.write_image(output_path, width=1920, height=1080)
    log.info(f"Saved plot to {output_path}")
