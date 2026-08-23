from dataclasses import dataclass
from pathlib import Path
from typing import cast

import fastf1
import fastf1.plotting
import matplotlib.pyplot as plt
import pandas
import structlog
from fastf1.core import Session, Laps
from opentelemetry import trace

from visualizations.domain.driver import Driver
from visualizations.domain.stint import Stint
from visualizations.output import resolve_output_dir, save_matplotlib
from visualizations.style import driver_linestyle

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
    stint_id: object
    compound: str
    laps: dict[int, float]
    median: float
    starts_stint: bool
    preceded_by_slow_lap: bool


def _present_and_true(row: pandas.Series, column: str) -> bool:
    value = row.get(column)
    return column in row.index and pandas.notna(value) and bool(value)


def _is_usable_lap(row: pandas.Series) -> bool:
    if pandas.isna(row.get("LapTime")):
        return False
    if _present_and_true(row, "Deleted"):
        return False
    if "IsAccurate" in row.index and pandas.notna(row["IsAccurate"]) and not bool(row["IsAccurate"]):
        return False
    if _present_and_true(row, "PitInTime") or _present_and_true(row, "PitOutTime"):
        return False
    if "TrackStatus" in row.index and pandas.notna(row["TrackStatus"]):
        if str(row["TrackStatus"]) not in {"1", "1.0"}:
            return False
    return True


def _lap_number(row: pandas.Series) -> int:
    return int(row.get("LapNumber", row.get("TyreLife")))


def _slow_lap_indexes(rows: list[tuple[int, pandas.Series]], criteria: LongRunCriteria) -> set[int]:
    """Find obvious interior cooldown/traffic blocks conservatively."""
    if len(rows) < 3:
        return set()
    times = [cast(pandas.Timedelta, row[1]["LapTime"]).total_seconds() for row in rows]
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


def _make_phases(stint_laps: pandas.DataFrame, driver: Driver, stint_id: object,
                 compound: str, criteria: LongRunCriteria) -> tuple[list[_Phase], list[float]]:
    order_column = "LapNumber" if "LapNumber" in stint_laps.columns else "TyreLife"
    ordered = stint_laps.sort_values(by=order_column).reset_index(drop=True)
    usable = [(index, row) for index, row in ordered.iterrows() if _is_usable_lap(row)]
    slow_indexes = _slow_lap_indexes(usable, criteria)
    clean = [(original_index, row) for clean_index, (original_index, row) in enumerate(usable)
             if clean_index not in slow_indexes]
    clean_times = [cast(pandas.Timedelta, row["LapTime"]).total_seconds() for _, row in clean]

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
            continue
        lap_map = {
            int(row.get("TyreLife", _lap_number(row))): cast(pandas.Timedelta, row["LapTime"]).total_seconds()
            for _, row in rows
        }
        phases.append(_Phase(
            driver, stint_id, compound, lap_map,
            float(pandas.Series(list(lap_map.values())).median()),
            bool(usable) and rows[0][0] == usable[0][0],
            rows[0][0] - 1 in removed_original_indexes,
        ))
    return phases, clean_times


def make_stint_set(min_consecutive_laps: int, all_laps: Laps, compound: str,
                   criteria: LongRunCriteria | None = None) -> list[Stint]:
    """Return independently drawable long-run phases for a compound."""
    base = criteria or LongRunCriteria()
    criteria = LongRunCriteria(
        min_consecutive_clean_laps=min_consecutive_laps,
        automatic_long_run_laps=base.automatic_long_run_laps,
        traffic_absolute_margin=base.traffic_absolute_margin,
        traffic_relative_margin=base.traffic_relative_margin,
        qualifying_max_laps=base.qualifying_max_laps,
        qualifying_absolute_margin=base.qualifying_absolute_margin,
        qualifying_relative_margin=base.qualifying_relative_margin,
    )
    laps = all_laps[all_laps.Compound == compound]
    phases: list[_Phase] = []
    clean_times_by_stint: dict[tuple[int, object], list[float]] = {}
    grouped = laps.groupby(["DriverNumber", "Stint", "Compound"], dropna=False, sort=False)
    for (driver_number_value, stint_id, phase_compound), stint_laps in grouped:
        first_lap = stint_laps.iloc[0]
        driver_number = int(cast(str, driver_number_value))
        driver = Driver(driver_number, first_lap.Driver, first_lap.Team)
        stint_phases, clean_times = _make_phases(
            stint_laps, driver, stint_id, cast(str, phase_compound), criteria
        )
        phases.extend(stint_phases)
        clean_times_by_stint[(driver_number, stint_id)] = clean_times

    retained: list[_Phase] = []
    for phase in phases:
        if len(phase.laps) >= criteria.automatic_long_run_laps:
            retained.append(phase)
            continue
        same_stint = [item for item in phases
                      if item.driver.number == phase.driver.number and item.stint_id == phase.stint_id]
        later = [item for item in same_stint
                 if min(item.laps) > max(phase.laps)
                 and len(item.laps) >= criteria.min_consecutive_clean_laps]
        margin = max(criteria.qualifying_absolute_margin,
                     phase.median * criteria.qualifying_relative_margin)
        if (phase.starts_stint and len(phase.laps) <= criteria.qualifying_max_laps
                and any(item.preceded_by_slow_lap and phase.median + margin < item.median
                        for item in later)):
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
                continue
        retained.append(phase)

    result = [Stint(item.compound, item.laps, item.driver) for item in retained]
    return sorted(result, key=lambda item: (item.driver.number, min(item.laps, default=0)))


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
        minimum_laps = criteria.min_consecutive_clean_laps if criteria else 2
        stint_set = make_stint_set(minimum_laps, session.laps, compound, criteria)
        legends = set()
        for stint in stint_set:
            team = stint.driver.team_name
            color = fastf1.plotting.get_team_color(team, session) if team != '' else 'white'
            x = sorted(stint.laps.keys())
            y = [stint.laps[i] for i in x]
            line_style = driver_linestyle(session.event.year, stint.driver.number)
            if stint.driver.number in legends:
                ax.plot(x, y, linewidth=0.5, color=color, linestyle=line_style)
            else:
                ax.plot(x, y, linewidth=0.5, color=color, linestyle=line_style, label=stint.driver.name)
                legends.add(stint.driver.number)
        ax.legend(fontsize='small')
        ax.invert_yaxis()
        ax.grid(True)
        output_path = resolve_output_dir(session, output_dir) / "long_runs" / f"{compound}.png"
        save_matplotlib(fig, output_path, log)
