import datetime
from pathlib import Path
from typing import Final

import fastf1
import plotly.graph_objects as go
import structlog
# noinspection PyPackageRequirements
from opentelemetry import trace

import constants
from visualizations.output import save_plotly

tracer = trace.get_tracer(__name__)


@tracer.start_as_current_span("plot_tyre")
def plot_tyre(
        year: int,
        race_number: int,
        log: structlog.stdlib.BoundLogger,
        *,
        output_dir: str | Path | None = None,
):
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
            if laps.empty:
                continue
            d = session.get_driver(driver).Abbreviation
            if d not in drivers:
                drivers[d] = {'Sessions': [], 'Compounds': []}
            drivers[d]['Sessions'].extend([session_name for _ in range(len(laps))])
            drivers[d]['Compounds'].extend([lap.Compound for lap in laps.itertuples()])

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
        table_columns.append(col_counts + session_list + [""] * padding_len)
        compound_colors = [constants.compound_color.get(name, "white") for name in compounds]
        table_colors.append(list(constants.compound_color.values()) + compound_colors + ["white"] * padding_len)

    fig = go.Figure(
        data=[go.Table(
            header=go.table.Header(
                values=names, fill=go.table.header.Fill(color='lightgrey'), align='center'),
            cells=go.table.Cells(
                values=table_columns, fill=go.table.cells.Fill(color=table_colors), align='center'))])

    base_dir = Path(output_dir) if output_dir is not None else Path("images") / str(session.event.year) / f"{session.event.RoundNumber}_{session.event.Location}"
    save_plotly(fig, base_dir / "tyres.png", log, width=1920, height=1080)
