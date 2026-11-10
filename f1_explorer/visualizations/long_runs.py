from dataclasses import asdict, dataclass, replace
import math
from pathlib import Path
from collections.abc import Hashable
from f1_explorer.scalars import as_float, as_int, as_seconds
from typing import cast

import fastf1
import fastf1.plotting
import matplotlib.pyplot as plt
import pandas
import plotly.graph_objects as go
import structlog
from fastf1.core import Session, Laps
from opentelemetry import trace

from f1_explorer.visualizations.domain.driver import Driver
from f1_explorer.visualizations.domain.long_run import (
    LongRun, LongRunPoint, LongRunDecision, LongRunSelection, LongRunScope,
)
from f1_explorer.visualizations.output import resolve_output_dir, save_matplotlib
from f1_explorer.visualizations.report import current_report
from f1_explorer.visualizations.session_order import driver_order, driver_sort_key
from f1_explorer.visualizations.style import driver_linestyle

tracer = trace.get_tracer(__name__)


@dataclass(frozen=True, slots=True)
class LongRunCriteria:
    min_consecutive_clean_laps: int = 2
    automatic_long_run_laps: int = 4
    traffic_absolute_margin: float = 5.0
    traffic_relative_margin: float = 0.07
    qualifying_max_laps: int = 3
    qualifying_absolute_margin: float = 1.5
    qualifying_relative_margin: float = 0.02


@dataclass(slots=True)
class _Phase:
    driver: Driver
    stint_id: int | None
    compound: str
    points: tuple[LongRunPoint, ...]
    median: float
    starts_stint: bool
    preceded_by_slow_lap: bool
    start_time: str | None


def _present_and_true(row: pandas.Series, column: str) -> bool:
    value = row.get(column)
    return column in row.index and pandas.notna(value) and bool(value)


def _lap_exclusion_reasons(row: pandas.Series) -> tuple[str, ...]:
    reasons = []
    if pandas.isna(row.get("LapNumber")) or pandas.isna(row.get("LapTime")):
        reasons.append("missing")
    if _present_and_true(row, "Deleted"):
        reasons.append("deleted")
    if "IsAccurate" in row.index and pandas.notna(row["IsAccurate"]) and not bool(row["IsAccurate"]):
        reasons.append("inaccurate")
    if _present_and_true(row, "PitInTime") or _present_and_true(row, "PitOutTime"):
        reasons.append("pit")
    if pandas.notna(row.get("TrackStatus")) and str(row["TrackStatus"]) not in {"1", "1.0"}:
        reasons.append("track_status")
    return tuple(reasons)


def _start_time(row: pandas.Series) -> str | None:
    """First lap's start instant: absolute date when known, else session-relative time."""
    start = next((row.get(key) for key in ("LapStartDate", "LapStartTime")
                  if pandas.notna(row.get(key))), None)
    return str(start) if start is not None else None


def _decision(driver: Driver, stint_id: int | None, compound: str,
              rows: list[pandas.Series], scope: LongRunScope, accepted: bool,
              reasons: tuple[str, ...]) -> LongRunDecision:
    return LongRunDecision(
        driver, stint_id, compound,
        tuple(as_int(row["LapNumber"]) if pandas.notna(row.get("LapNumber")) else None
              for row in rows),
        _start_time(rows[0]) if rows else None,
        scope, accepted, reasons,
    )


def _lap_number(row: pandas.Series) -> int:
    return as_int(row["LapNumber"])


def _slow_lap_indexes(rows: list[tuple[Hashable, pandas.Series]], criteria: LongRunCriteria) -> set[int]:
    """Find obvious interior cooldown/traffic blocks conservatively."""
    if len(rows) < 3:
        return set()
    times = [as_seconds(row[1]["LapTime"]) for row in rows]
    prefix_min, current = [], float("inf")
    for value in times:
        prefix_min.append(current)
        current = min(current, value)
    suffix_min = [float("inf")] * len(times)
    current = float("inf")
    for index in range(len(times) - 1, -1, -1):
        suffix_min[index] = current
        current = min(current, times[index])

    slow = set()
    for index, value in enumerate(times):
        if prefix_min[index] == float("inf") or suffix_min[index] == float("inf"):
            continue
        local_reference = max(prefix_min[index], suffix_min[index])
        margin = max(criteria.traffic_absolute_margin, local_reference * criteria.traffic_relative_margin)
        if value > local_reference + margin:
            slow.add(index)
    return slow


def _point(lap_number: int, row: pandas.Series) -> LongRunPoint:
    """Convert one lap row into a selection point; a missing tyre age is kept."""
    age = as_float(row.get("TyreLife")) if pandas.notna(row.get("TyreLife")) else None
    if age is not None and not math.isfinite(age):
        age = None
    return LongRunPoint(lap_number, age, as_seconds(row["LapTime"]))


def _make_phases(stint_laps: pandas.DataFrame, driver: Driver, stint_id: int | None,
                 compound: str, criteria: LongRunCriteria,
                 decisions: list[LongRunDecision] | None) -> tuple[list[_Phase], list[float]]:
    order_column = "LapNumber"
    ordered = stint_laps.sort_values(by=order_column).reset_index(drop=True)
    usable: list[tuple[int, pandas.Series]] = []
    for original_index, (_, row) in enumerate(ordered.iterrows()):
        reasons = _lap_exclusion_reasons(row)
        if reasons:
            if decisions is not None:
                decisions.append(_decision(driver, stint_id, compound, [row], "lap", False, reasons))
        else:
            usable.append((original_index, row))
    slow_indexes = _slow_lap_indexes(usable, criteria)
    if decisions is not None:
        for index in sorted(slow_indexes):
            decisions.append(_decision(driver, stint_id, compound, [usable[index][1]],
                                       "lap", False, ("slow_interior",)))

    clean = [(original_index, row) for clean_index, (original_index, row) in enumerate(usable)
             if clean_index not in slow_indexes]
    clean_times = [as_seconds(row["LapTime"]) for _, row in clean]

    phase_rows: list[list[tuple[int, pandas.Series]]] = []
    for original_index, row in clean:
        if (not phase_rows or original_index != phase_rows[-1][-1][0] + 1
                or _lap_number(row) != _lap_number(phase_rows[-1][-1][1]) + 1):
            phase_rows.append([])
        phase_rows[-1].append((original_index, row))

    phases = []
    removed_original_indexes = {
        original_index for clean_index, (original_index, _) in enumerate(usable)
        if clean_index in slow_indexes
    }
    for rows in phase_rows:
        if len(rows) < criteria.min_consecutive_clean_laps:
            if decisions is not None:
                decisions.append(_decision(driver, stint_id, compound,
                                           [row for _, row in rows], "phase", False,
                                           ("insufficient_consecutive",)))
            continue
        points = tuple(_point(_lap_number(row), row) for _, row in rows)
        phases.append(_Phase(
            driver, stint_id, compound, points,
            float(pandas.Series([point.lap_time_seconds for point in points]).median()),
            bool(usable) and rows[0][0] == usable[0][0],
            rows[0][0] - 1 in removed_original_indexes,
            _start_time(rows[0][1]),
        ))
    return phases, clean_times


def _select_long_runs(min_consecutive_laps: int | None, all_laps: Laps, compound: str,
                      criteria: LongRunCriteria | None,
                      decisions: list[LongRunDecision] | None) -> list[LongRun]:
    """Return independently drawable long-run phases for a compound."""
    criteria = criteria or LongRunCriteria()
    if min_consecutive_laps is not None:
        criteria = replace(criteria, min_consecutive_clean_laps=min_consecutive_laps)
    if "LapNumber" not in all_laps.columns:
        all_laps = all_laps.assign(LapNumber=float("nan"))
    laps = all_laps[all_laps.Compound == compound]
    phases: list[_Phase] = []
    clean_times_by_stint: dict[tuple[int, int | None], list[float]] = {}
    grouped = laps.groupby(["DriverNumber", "Stint", "Compound"], dropna=False, sort=False)
    for (driver_number_value, stint_id, phase_compound), stint_laps in grouped:
        stint_id = as_int(stint_id) if pandas.notna(stint_id) else None
        first_lap = stint_laps.iloc[0]
        driver_number = int(cast(str, driver_number_value))
        driver = Driver(driver_number, first_lap.Driver, first_lap.Team)
        stint_phases, clean_times = _make_phases(
            stint_laps, driver, stint_id, cast(str, phase_compound), criteria, decisions
        )
        phases.extend(stint_phases)
        clean_times_by_stint[(driver_number, stint_id)] = clean_times

    def record_phase(phase: _Phase, accepted: bool, reason: str) -> None:
        if decisions is not None:
            decisions.append(LongRunDecision(
                phase.driver, phase.stint_id, phase.compound,
                tuple(point.lap_number for point in phase.points),
                phase.start_time, "phase", accepted, (reason,),
            ))

    retained: list[_Phase] = []
    for phase in phases:
        if len(phase.points) >= criteria.automatic_long_run_laps:
            retained.append(phase)
            record_phase(phase, True, "automatic_long_run")
            continue
        same_stint = [item for item in phases
                      if item.driver.number == phase.driver.number and item.stint_id == phase.stint_id]
        later = [item for item in same_stint
                 if item.points[0].lap_number > phase.points[-1].lap_number
                 and len(item.points) >= criteria.min_consecutive_clean_laps]
        margin = max(criteria.qualifying_absolute_margin,
                     phase.median * criteria.qualifying_relative_margin)
        if (phase.starts_stint and len(phase.points) <= criteria.qualifying_max_laps
                and any(item.preceded_by_slow_lap and phase.median + margin < item.median
                        for item in later)):
            record_phase(phase, False, "qualifying_same_stint")
            continue

        external_times = [
            time for (driver_number, stint_id), times in clean_times_by_stint.items()
            if driver_number == phase.driver.number and stint_id != phase.stint_id
            for time in times
        ]
        if external_times:
            reference = min(external_times)
            margin = max(criteria.qualifying_absolute_margin,
                         reference * criteria.qualifying_relative_margin)
            if phase.median <= reference + margin:
                record_phase(phase, False, "qualifying_other_stint")
                continue
        retained.append(phase)
        record_phase(phase, True, "retained_short_run")

    # Phase indexes number the retained runs, so a dropped early interval
    # leaves no gaps: each stint's runs stay 1-based and contiguous.
    retained_by_key: dict[tuple[int, int | None], int] = {}
    result: list[LongRun] = []
    for item in retained:
        key = (item.driver.number, item.stint_id)
        retained_by_key[key] = retained_by_key.get(key, 0) + 1
        result.append(LongRun(item.driver, item.stint_id, retained_by_key[key],
                              item.compound, item.points))
    return sorted(result, key=lambda item: (item.driver.number, item.points[0].lap_number))


def select_long_run_selection(min_consecutive_laps: int | None = None, all_laps: Laps = None,
                              compound: str = None,
                              criteria: LongRunCriteria | None = None) -> LongRunSelection:
    decisions: list[LongRunDecision] = []
    runs = _select_long_runs(min_consecutive_laps, all_laps, compound, criteria, decisions)
    return LongRunSelection(tuple(runs), tuple(decisions))


def select_long_runs(min_consecutive_laps: int | None = None, all_laps: Laps = None,
                     compound: str = None,
                     criteria: LongRunCriteria | None = None) -> list[LongRun]:
    return list(select_long_run_selection(min_consecutive_laps, all_laps, compound, criteria).runs)


def _displayed_points(run: LongRun) -> tuple[LongRunPoint, ...]:
    """Points with a known tyre age; missing-age laps stay in the result un-drawn."""
    return tuple(point for point in run.points if point.tyre_age is not None)


def _run_label(run: LongRun) -> str:
    stint = run.stint_id if run.stint_id is not None else "?"
    displayed = len(_displayed_points(run))
    return (f"{run.driver.name} / Stint {stint} / "
            f"laps {run.points[0].lap_number}–{run.points[-1].lap_number}"
            f" / selected {len(run.points)}, displayed {displayed}")


@tracer.start_as_current_span("plot_by_tyre_age_and_tyre")
def plot_by_tyre_age_and_tyre(
        session: Session,
        log: structlog.stdlib.BoundLogger,
        *,
        output_dir: str | Path | None = None,
        criteria: LongRunCriteria | None = None,
):
    """Plot clean long-run phases by tyre age and compound."""
    for compound in session.laps.Compound.unique():
        fastf1.plotting.setup_mpl(mpl_timedelta_support=True, color_scheme='light')
        fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
        try:
            selection = select_long_run_selection(None, session.laps, compound, criteria)
            runs = list(selection.runs)
            for run in runs:
                team = run.driver.team_name
                color = fastf1.plotting.get_team_color(team, session) if team != '' else 'white'
                displayed = _displayed_points(run)
                line_style = driver_linestyle(session.event.year, run.driver.number)
                ax.plot([point.tyre_age for point in displayed],
                        [point.lap_time_seconds for point in displayed],
                        linewidth=0.5, marker=".", color=color, linestyle=line_style,
                        label=_run_label(run))
            if runs:
                ax.legend(fontsize='small')
            ax.invert_yaxis()
            ax.set_xlabel("Tyre age [laps]")
            ax.set_ylabel("Lap Time [s]")
            ax.grid(True)
            output_path = resolve_output_dir(session, output_dir) / "long_runs" / f"{compound}.png"
            save_matplotlib(fig, output_path, log, report_interactive=True)
            report = current_report()
            if report is not None:
                figure = _make_interactive_long_run_figure(session, compound, runs)
                # Lap-scope decisions lead so the 採否一覧 can keep the
                # per-lap and per-phase sections apart by order alone.
                figure.update_layout(meta={
                    "f1ExplorerKind": "longRunSelection",
                    "longRunSelection": [
                        asdict(d) for d in sorted(
                            selection.decisions, key=lambda d: d.scope != "lap")
                    ],
                })
                report.register_plotly(figure, output_path)
        finally:
            plt.close(fig)


def _make_interactive_long_run_figure(
        session: Session,
        compound: str,
        runs: list[LongRun],
) -> go.Figure:
    """Build an interactive long-run counterpart while retaining the PNG."""
    fig = go.Figure()
    ranks = driver_order(session)
    ordered_runs = sorted(
        runs,
        key=lambda run: driver_sort_key(run.driver.number, ranks),
    )
    for run in ordered_runs:
        name = _run_label(run)
        customdata = [[run.driver.name, run.driver.team_name, point.lap_number,
                       point.tyre_age] for point in run.points]
        try:
            color = (fastf1.plotting.get_team_color(run.driver.team_name, session)
                     if run.driver.team_name else "gray")
        except (AttributeError, KeyError, TypeError, ValueError):
            color = "gray"
        try:
            line_style = driver_linestyle(session.event.year, run.driver.number)
            dash = "dash" if line_style == "dashed" else "solid"
        except (AttributeError, TypeError, ValueError):
            dash = "solid"
        fig.add_trace(go.Scatter(
            x=[point.tyre_age for point in run.points],
            y=[point.lap_time_seconds if point.tyre_age is not None else None
               for point in run.points],
            connectgaps=False,
            mode="lines+markers",
            name=name,
            line={"color": color, "dash": dash},
            legendrank=ranks.get(str(run.driver.number), 1_000_000),
            customdata=customdata,
            hovertemplate=(
                "Driver: %{customdata[0]}<br>Team: %{customdata[1]}"
                "<br>Lap: %{customdata[2]}<br>Tyre age: %{customdata[3]} laps<br>Lap time: %{y:.3f}s<extra></extra>"
            ),
        ))
    fig.update_layout(
        title=f"Long Runs — {compound} (interactive)",
        xaxis_title="Tyre age [laps]",
        yaxis_title="Lap Time [s]",
        xaxis=dict(rangeslider=dict(visible=True)),
        yaxis_autorange="reversed",
        hovermode="closest",
        legend_title="Driver / stint (click to toggle)",
        margin=dict(l=60, r=20, t=60, b=50),
    )
    return fig
