from pathlib import Path
from typing import cast

import fastf1.plotting
import matplotlib.pyplot as plt
import numpy
import pandas
import plotly.graph_objects as go
import structlog
from fastf1.core import Session
from numpy import datetime64
# noinspection PyPackageRequirements
from opentelemetry import trace

import constants
from visualizations.output import resolve_output_dir, save_matplotlib, save_plotly
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
def plot_laptime(session: Session, log: structlog.stdlib.BoundLogger, *, output_dir: str | Path | None = None):
    """ラップごとのタイムの一覧を作成する
    Args:
        session: セッション
        log: ロガー
    """
    header = ["Lap"] + [session.get_driver(driver_number).Abbreviation for driver_number in session.drivers]

    laps = session.laps
    max_laps = max(len(laps[laps.DriverNumber == d]) for d in session.drivers)
    lap_numbers = [str(i) for i in range(1, max_laps + 1)]
    cells: list[list[str]] = [lap_numbers]
    colors = [["#f0f0f0"] * max_laps]

    for driver in header:
        if driver == 'Lap':
            continue
        driver_laps = session.laps.pick_drivers(driver).sort_values(by='LapNumber')
        values = []
        lap_colors = []
        for i in range(len(driver_laps)):
            lap = driver_laps.iloc[i]
            lap_colors.append(constants.compound_color.get(lap.Compound, "#dddddd"))
            if pandas.isna(lap.PitInTime) and pandas.isna(lap.PitOutTime):
                values.append(str(lap.LapTime.total_seconds()))
            elif pandas.isna(lap.PitOutTime):
                i = lap.LapStartTime.total_seconds() + lap.LapTime.total_seconds() - lap.PitInTime.total_seconds()
                values.append(
                    f"{lap.LapTime.total_seconds()}<br>({"{:.3f}".format(i)}<br>{"{:.3f}".format(lap.LapTime.total_seconds() - i)})")
            elif pandas.isna(lap.PitInTime):
                o = lap.PitOutTime.total_seconds() - lap.LapStartTime.total_seconds()
                values.append(
                    f"{lap.LapTime.total_seconds()}<br>({"{:.3f}".format(o)}<br>{"{:.3f}".format(lap.LapTime.total_seconds() - o)})")
            else:
                i = lap.LapStartTime.total_seconds() + lap.LapTime.total_seconds() - lap.PitInTime.total_seconds()
                o = lap.PitOutTime.total_seconds() - lap.LapStartTime.total_seconds()
                values.append(f"{lap.LapTime.total_seconds()}<br>({"{:.3f}".format(i)}<br>/{"{:.3f}".format(o)})")
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

    fig = go.Figure(
        data=[go.Table(
            header=go.table.Header(
                values=header, fill=go.table.header.Fill(color='lightgrey'), align='center'),
            cells=go.table.Cells(
                values=cells, fill=go.table.cells.Fill(color=colors), align='center'))],
        layout=go.Layout(autosize=True, margin=go.layout.Margin(l=10, r=10, t=20, b=20, autoexpand=True)))

    image_height = max(1200, sum(heights) + 40 + 40)  # header & bottom = 40

    output_path = resolve_output_dir(session, output_dir) / "laptime_table.png"
    save_plotly(fig, output_path, log, width=1920, height=image_height)


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


@tracer.start_as_current_span("plot_laptime_by_timing")
def plot_laptime_by_timing(session: Session, log: structlog.stdlib.BoundLogger, *, output_dir: str | Path | None = None):
    """
    y = ラップタイム
    x = 時間
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
        if not stint_laps.LapStartDate.values.size:
            continue
        d: datetime64 = stint_laps.LapStartDate.values[0]
        if not pandas.isna(d):
            lap_starts = stint_laps.LapStartDate.values
        else:
            lap_starts = stint_laps.LapStartTime.values
        if not lap_times or not lap_starts.size:
            continue
        ax.plot(lap_starts, lap_times, color=color,
                linestyle=driver_linestyle(session.event.year, int(stint_laps.DriverNumber.iloc[0])),
                label=stint_laps.Driver.iloc[0])
    # noinspection PyUnresolvedReferences
    minimum = session.laps.LapTime.min().seconds
    ax.set_ylim(top=minimum, bottom=minimum * 1.25)
    output_path = resolve_output_dir(session, output_dir) / "laptime_by_timing.png"
    ax.legend(fontsize='small')
    ax.grid(True)
    save_matplotlib(fig, output_path, log)
