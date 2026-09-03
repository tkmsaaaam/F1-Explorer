from pathlib import Path
from typing import cast

import fastf1.plotting
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy
import pandas
import plotly.graph_objects as go
import structlog
from fastf1.core import Laps, Session
from plotly.subplots import make_subplots
# noinspection PyPackageRequirements
from opentelemetry import trace

import constants
from visualizations.output import resolve_output_dir, save_matplotlib, save_plotly
from visualizations.report import current_report
from visualizations.session_order import driver_order, driver_sort_key
from visualizations.style import driver_linestyle

tracer = trace.get_tracer(__name__)


@tracer.start_as_current_span("plot_lap_number_by_timing")
def plot_lap_number_by_timing(session: Session, log: structlog.stdlib.BoundLogger, *, output_dir: str | Path | None = None):
    """y = ラップ番号
    x = 時間
    Args:
        session: 分析対象のセッション
        log: ロガー
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    grouped = session.laps.groupby(['Stint', 'DriverNumber'])
    for (stint_num, driver_number), stint_laps in grouped:
        if stint_laps.empty:
            continue
        team = stint_laps.Team.iloc[0]
        color = 'white' if team == '' else fastf1.plotting.get_team_color(team, session)
        stint_laps = stint_laps.sort_values(by='LapNumber')
        lap_numbers = stint_laps.LapNumber
        lap_starts = stint_laps.LapStartDate
        if stint_num == 1:
            ax.plot(lap_starts, lap_numbers, color=color,
                    linestyle=driver_linestyle(session.event.year, int(cast(str, driver_number))),
                    label=stint_laps.Driver.iloc[0])
        else:
            ax.plot(lap_starts, lap_numbers, color=color,
                    linestyle=driver_linestyle(session.event.year, int(cast(str, driver_number))))
    ax.legend(fontsize='small')
    ax.grid(True)
    output_path = resolve_output_dir(session, output_dir) / "lap_number_by_timing.png"
    save_matplotlib(fig, output_path, log)


@tracer.start_as_current_span("plot_laptime")
def plot_laptime(
        session: Session,
        log: structlog.stdlib.BoundLogger,
        *,
        output_dir: str | Path | None = None,
        split_qualifying: bool = False,
):
    """ラップごとのタイムの一覧を作成する
    Args:
        session: セッション
        log: ロガー
    """
    if split_qualifying:
        try:
            qualifying_laps = session.laps.split_qualifying_sessions()
        except ValueError as exception:
            log.warning("Could not split qualifying sessions; using one table", reason=str(exception))
        else:
            prefix = "SQ" if session.name.startswith("Sprint") else "Q"
            sections = [
                (f"{prefix}{index}", laps)
                for index, laps in enumerate(qualifying_laps, start=1)
                if laps is not None and not laps.empty
            ]
            if sections:
                _save_laptime_sections(session, log, sections, output_dir)
                return

    table, heights = _make_laptime_table(
        session,
        session.laps,
        "Lap",
        exclude_pit_laps=split_qualifying,
    )
    fig = go.Figure(
        data=[table],
        layout=go.Layout(autosize=True, margin=go.layout.Margin(l=10, r=10, t=20, b=20, autoexpand=True)),
    )
    image_height = max(1200, sum(heights) + 80)
    save_plotly(fig, resolve_output_dir(session, output_dir) / "laptime_table.png", log,
                width=1920, height=image_height)


def _make_laptime_table(
        session: Session,
        laps: Laps,
        section_label: str,
        *,
        exclude_pit_laps: bool = False,
) -> tuple[go.Table, list[int]]:
    if exclude_pit_laps:
        laps = _laps_without_pit_laps(laps)

    present_drivers = {str(driver_number) for driver_number in laps.DriverNumber.unique()}
    driver_numbers = [driver_number for driver_number in session.drivers if str(driver_number) in present_drivers]
    header = [f"{section_label} Lap"] + [
        session.get_driver(driver_number).Abbreviation for driver_number in driver_numbers
    ]
    max_laps = max((
        len(laps[laps.DriverNumber.astype(str) == str(driver_number)])
        for driver_number in driver_numbers
    ), default=0)
    lap_numbers = [str(i) for i in range(1, max_laps + 1)]
    cells: list[list[str]] = [lap_numbers]
    colors = [["#f0f0f0"] * max_laps]

    for driver_number in driver_numbers:
        driver_laps = laps[laps.DriverNumber.astype(str) == str(driver_number)].sort_values(by='LapNumber')
        values = []
        lap_colors = []
        for row_index in range(len(driver_laps)):
            lap = driver_laps.iloc[row_index]
            lap_colors.append(constants.compound_color.get(lap.Compound, "#dddddd"))
            stint_label = ""
            if exclude_pit_laps:
                stint_number = int(lap.Stint) if pandas.notna(lap.Stint) else "?"
                stint_label = f"<br>(S{stint_number})"
            if pandas.isna(lap.LapTime):
                values.append("")
                continue
            if pandas.isna(lap.PitInTime) and pandas.isna(lap.PitOutTime):
                values.append(str(lap.LapTime.total_seconds()) + stint_label)
            elif pandas.isna(lap.PitOutTime):
                pit_in = lap.LapStartTime.total_seconds() + lap.LapTime.total_seconds() - lap.PitInTime.total_seconds()
                values.append(
                    f"{lap.LapTime.total_seconds()}<br>({pit_in:.3f}<br>{lap.LapTime.total_seconds() - pit_in:.3f})"
                    + stint_label)
            elif pandas.isna(lap.PitInTime):
                pit_out = lap.PitOutTime.total_seconds() - lap.LapStartTime.total_seconds()
                values.append(
                    f"{lap.LapTime.total_seconds()}<br>({pit_out:.3f}<br>{lap.LapTime.total_seconds() - pit_out:.3f})"
                    + stint_label)
            else:
                pit_in = lap.LapStartTime.total_seconds() + lap.LapTime.total_seconds() - lap.PitInTime.total_seconds()
                pit_out = lap.PitOutTime.total_seconds() - lap.LapStartTime.total_seconds()
                values.append(
                    f"{lap.LapTime.total_seconds()}<br>({pit_in:.3f}<br>/{pit_out:.3f})"
                    + stint_label)
        cells.append(values)
        colors.append(lap_colors)

    for i in range(len(cells)):
        if len(cells[i]) < max_laps:
            cells[i].extend([""] * (max_laps - len(cells[i])))
        if len(colors[i]) < max_laps:
            colors[i].extend(["#f0f0f0"] * (max_laps - len(colors[i])))

    heights = [26] * max_laps
    for rows in cells:
        for i, row in enumerate(rows):
            if '<br>' in row:
                heights[i] = 65

    return go.Table(
        header=go.table.Header(values=header, fill=go.table.header.Fill(color='lightgrey'), align='center'),
        cells=go.table.Cells(values=cells, fill=go.table.cells.Fill(color=colors), align='center'),
    ), heights


def _laps_without_pit_laps(laps: Laps) -> Laps:
    """Return the timed laps shown in qualifying lap-time visualizations."""

    return laps[laps.PitOutTime.isna() & laps.PitInTime.isna()]


def _lap_start_dates(session: Session, laps: Laps) -> pandas.Series:
    """Return absolute lap-start timestamps, filling from session time when needed."""

    starts = pandas.to_datetime(laps["LapStartDate"], errors="coerce")
    session_start = getattr(session, "t0_date", pandas.NaT)
    if pandas.notna(session_start):
        fallback = pandas.Timestamp(session_start) + laps["LapStartTime"]
        starts = starts.fillna(fallback)
    return starts


def _save_laptime_sections(session: Session, log: structlog.stdlib.BoundLogger, sections: list[tuple[str, Laps]],
                            output_dir: str | Path | None) -> None:
    prepared = [
        (label, *_make_laptime_table(session, laps, label, exclude_pit_laps=True))
        for label, laps in sections
    ]
    row_heights = [max(320, sum(heights) + 100) for _, _, heights in prepared]
    fig = make_subplots(
        rows=len(sections), cols=1,
        specs=[[{"type": "table"}] for _ in sections],
        subplot_titles=[label for label, _ in sections],
        row_heights=row_heights,
        vertical_spacing=0.04,
    )
    for row, (_, table, _) in enumerate(prepared, start=1):
        fig.add_trace(table, row=row, col=1)
    fig.update_layout(autosize=True, margin=go.layout.Margin(l=10, r=10, t=40, b=20, autoexpand=True))
    save_plotly(fig, resolve_output_dir(session, output_dir) / "laptime_table.png", log,
                width=1920, height=max(1200, sum(row_heights)))


@tracer.start_as_current_span("plot_pit_time")
def plot_pit_time(session: Session, log: structlog.stdlib.BoundLogger, *, output_dir: str | Path | None = None):
    """pitのタイムの一覧を作成する
    Args:
        session: セッション
        log: ロガー
    """
    header = [""]
    data_rows = [["No<br>pit<br>in<br>out<br>in<br>out<br>sum"]]
    pits = []
    for n in session.drivers:
        driver_laps = session.laps.pick_drivers(n).sort_values(by='LapNumber')
        if driver_laps is None:
            continue
        lap_times = []
        for i in range(len(driver_laps)):
            outLap = driver_laps.iloc[i]
            if pandas.isna(outLap.PitOutTime):
                continue
            j = i - 1
            if j < 1:
                continue
            inLap = driver_laps.iloc[j]
            pitInTime = (outLap.LapStartTime - inLap.PitInTime).total_seconds()
            pitOutTime = (outLap.PitOutTime - outLap.LapStartTime).total_seconds()
            pit = pitInTime + pitOutTime
            lap_times.append(
                f"{outLap.LapNumber}"
                f"<br>{"{:.3f}".format(pit)}"
                f"<br>{"{:.3f}".format(pitInTime)}"
                f"<br>{"{:.3f}".format(pitOutTime)}"
                f"<br>{"{:.3f}".format(inLap.LapTime.total_seconds())}"
                f"<br>{"{:.3f}".format(outLap.LapTime.total_seconds())}"
                f"<br>{(inLap.LapTime + outLap.LapTime).total_seconds()}"
            )
            pits.append(pit)
        if not lap_times:
            continue
        header.append(session.get_driver(n).Abbreviation)
        data_rows.append(lap_times)

    header.append('avg')
    data_rows.append([
        f"{len(pits)}"
        f"<br>{"{:.3f}".format(numpy.mean(pits))}"
        f"<br>{"{:.3f}".format(min(pits))}"
        f"<br>{"{:.3f}".format(max(pits))}"
    ])

    fig = go.Figure(
        data=[go.Table(
            header=go.table.Header(
                values=header, fill=go.table.header.Fill(color='lightgrey'), align='center'),
            cells=go.table.Cells(values=data_rows, align='center'))],
        layout=go.Layout(autosize=True, margin=go.layout.Margin(autoexpand=True)))

    output_path = resolve_output_dir(session, output_dir) / "pittime_table.png"
    save_plotly(fig, output_path, log, width=1920, height=2160)


@tracer.start_as_current_span("plot_laptime_by_lap_number")
def plot_laptime_by_lap_number(session: Session, log: structlog.stdlib.BoundLogger, *, output_dir: str | Path | None = None):
    """
    y = ラップタイム
    x = ラップ番号
    Args:
        session: 分析対象のセッション
        log: ロガー
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    grouped = session.laps.groupby(['DriverNumber'])
    for _, stint_laps in grouped:
        if stint_laps.empty:
            continue
        team = stint_laps.Team.iloc[0]
        color = 'white' if team == '' else fastf1.plotting.get_team_color(team, session)
        stint_laps = stint_laps.sort_values(by='LapNumber')
        lap_times = stint_laps.LapTime.dt.total_seconds().tolist()
        lap_numbers = stint_laps.LapNumber
        ax.plot(lap_numbers, lap_times, color=color,
                linestyle=driver_linestyle(session.event.year, int(stint_laps.DriverNumber.iloc[0])),
                label=stint_laps.Driver.iloc[0])
    # noinspection PyUnresolvedReferences
    minimum = session.laps.LapTime.min().total_seconds()
    ax.set_ylim(top=minimum, bottom=minimum * 1.25)
    ax.legend(fontsize='small')
    ax.grid(True)
    output_path = resolve_output_dir(session, output_dir) / "laptime_by_lap_number.png"
    save_matplotlib(fig, output_path, log)
    report = current_report()
    if report is not None:
        report.register_plotly(_make_interactive_laptime_by_lap_number(session), output_path)


def _is_race_session(session: Session) -> bool:
    """Return whether the session is a race, including a sprint race."""

    return str(getattr(session, "name", "")).strip().lower() in {
        "race", "sprint", "sprint race",
    }


def _interactive_race_laptime_range(session: Session) -> list[float] | None:
    """Calculate the narrower of the race graph and fixed fastest-lap ranges."""

    if not _is_race_session(session):
        return None
    seconds = session.laps["LapTime"].dt.total_seconds().dropna()
    if seconds.empty:
        return None
    fastest = float(seconds.min())
    fixed_range = [fastest + 14.5, fastest - 0.5]

    # Match visualizations.race.laptime(), which produces laptime_graph.png.
    # The Plotly graph retains every lap; these values only set its viewport.
    graph_clean = session.laps[
        session.laps["IsAccurate"].fillna(False).astype(bool)
        & ~session.laps["Deleted"].fillna(False).astype(bool)
        & session.laps["TrackStatus"].astype(str).isin({"1", "1.0"})
    ]["LapTime"].dt.total_seconds().dropna()
    graph_max = float(graph_clean.max()) if not graph_clean.empty else float(seconds.max())
    graph_range = [graph_max + 0.1, fastest - 0.1]
    return min((fixed_range, graph_range), key=lambda item: item[0] - item[1])


def _make_interactive_laptime_by_lap_number(session: Session) -> go.Figure:
    """Build an interactive counterpart to the legacy static lap-time plot."""
    fig = go.Figure()
    ranks = driver_order(session)
    groups = sorted(session.laps.groupby("DriverNumber"), key=lambda item: driver_sort_key(item[0], ranks))
    for driver_number, driver_laps in groups:
        driver_laps = driver_laps.sort_values("LapNumber").dropna(subset=["LapTime"])
        if driver_laps.empty:
            continue
        driver = str(driver_laps.Driver.iloc[0])
        customdata = [
            [str(row.Compound), row.TyreLife, row.Stint]
            for row in driver_laps.itertuples()
        ]
        fig.add_trace(go.Scatter(
            x=driver_laps.LapNumber.tolist(),
            y=driver_laps.LapTime.dt.total_seconds().tolist(),
            mode="lines+markers",
            name=driver,
            legendrank=ranks.get(str(driver_number), 1_000_000),
            customdata=customdata,
            hovertemplate=(
                "Driver: %{fullData.name}<br>Lap: %{x}<br>Time: %{y:.3f}s"
                "<br>Compound: %{customdata[0]}<br>Tyre life: %{customdata[1]}"
                "<br>Stint: %{customdata[2]}<extra></extra>"
            ),
        ))
    y_range = _interactive_race_laptime_range(session)
    yaxis = dict(title="Lap Time [s]")
    if y_range is None:
        yaxis["autorange"] = "reversed"
    else:
        yaxis.update(autorange=False, range=y_range)
    fig.update_layout(
        title="Lap Time by Lap Number (interactive)",
        xaxis_title="Lap Number",
        yaxis=yaxis,
        xaxis=dict(rangeslider=dict(visible=True)),
        hovermode="closest",
        legend_title="Driver (click to toggle)",
        margin=dict(l=60, r=20, t=60, b=50),
    )
    return fig


@tracer.start_as_current_span("plot_laptime_by_timing")
def plot_laptime_by_timing(
        session: Session,
        log: structlog.stdlib.BoundLogger,
        *,
        output_dir: str | Path | None = None,
        exclude_pit_laps: bool = False,
):
    """
    y = ラップタイム
    x = 時間
    Args:
        session: 分析対象のセッション
        log: ロガー
    """
    laps = _laps_without_pit_laps(session.laps) if exclude_pit_laps else session.laps
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    grouped = laps.groupby(['DriverNumber'])
    for _, driver_laps in grouped:
        if driver_laps.empty:
            continue
        team = driver_laps.Team.iloc[0]
        color = 'white' if team == '' else fastf1.plotting.get_team_color(team, session)
        driver_laps = driver_laps.sort_values(by='LapNumber').copy()
        driver_laps['_LapStartDate'] = _lap_start_dates(session, driver_laps)
        show_label = True
        for _, stint_laps in driver_laps.groupby('Stint', sort=False, dropna=False):
            lap_times = stint_laps.LapTime.dt.total_seconds().tolist()
            lap_starts = stint_laps['_LapStartDate'].values
            if not lap_times or not lap_starts.size:
                continue
            ax.plot(
                lap_starts,
                lap_times,
                color=color,
                linestyle=driver_linestyle(session.event.year, int(stint_laps.DriverNumber.iloc[0])),
                label=stint_laps.Driver.iloc[0] if show_label else None,
            )
            show_label = False
    # noinspection PyUnresolvedReferences
    minimum = laps.LapTime.min().seconds
    ax.set_ylim(top=minimum, bottom=minimum * 1.25)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    output_path = resolve_output_dir(session, output_dir) / "laptime_by_timing.png"
    ax.legend(fontsize='small')
    ax.grid(True)
    save_matplotlib(fig, output_path, log)
    report = current_report()
    if report is not None:
        report.register_plotly(_make_interactive_laptime_by_timing(session, laps), output_path)


def _make_interactive_laptime_by_timing(session: Session, laps: Laps | None = None) -> go.Figure:
    """Build an interactive time-axis counterpart to the static plot."""
    if laps is None:
        laps = session.laps
    fig = go.Figure()
    ranks = driver_order(session)
    groups = sorted(laps.groupby("DriverNumber"), key=lambda item: driver_sort_key(item[0], ranks))
    for driver_number, driver_laps in groups:
        driver_laps = driver_laps.sort_values("LapNumber").dropna(subset=["LapTime"])
        if driver_laps.empty:
            continue
        starts = _lap_start_dates(session, driver_laps).tolist()
        driver = str(driver_laps.Driver.iloc[0])
        x = []
        y = []
        customdata = []
        previous_stint = object()
        for lap_start, row in zip(starts, driver_laps.itertuples()):
            stint = None if pandas.isna(row.Stint) else row.Stint
            if x and stint != previous_stint:
                x.append(None)
                y.append(None)
                customdata.append([None, None, None, None])
            x.append(lap_start)
            y.append(row.LapTime.total_seconds())
            customdata.append([int(row.LapNumber), str(row.Compound), row.TyreLife, row.Stint])
            previous_stint = stint
        fig.add_trace(go.Scatter(
            x=x,
            y=y,
            mode="lines+markers",
            name=driver,
            legendrank=ranks.get(str(driver_number), 1_000_000),
            customdata=customdata,
            hovertemplate=(
                "Driver: %{fullData.name}<br>Start: %{x|%H:%M}<br>Time: %{y:.3f}s"
                "<br>Lap: %{customdata[0]}<br>Compound: %{customdata[1]}"
                "<br>Tyre life: %{customdata[2]}<br>Stint: %{customdata[3]}<extra></extra>"
            ),
        ))
    fig.update_layout(
        title="Lap Time by Session Time (interactive)",
        xaxis_title="Time",
        yaxis_title="Lap Time [s]",
        yaxis_autorange="reversed",
        xaxis=dict(tickformat="%H:%M", rangeslider=dict(visible=True)),
        hovermode="closest",
        legend_title="Driver (click to toggle)",
        margin=dict(l=60, r=20, t=60, b=50),
    )
    return fig
