"""Segment layouts and tables; numerical metrics remain in segment_metrics."""
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas
import plotly.graph_objects as go
import structlog
from fastf1.core import CircuitInfo, Session, Lap, Telemetry
from opentelemetry import trace

from f1_explorer.circuit import circuit_info_or_none
from f1_explorer.scalars import as_float, as_seconds
from f1_explorer.visualizations.output import resolve_output_dir, save_matplotlib, save_plotly_batch
from f1_explorer.visualizations.segment_metrics import deltas_to_reference, rank_segment_durations, segment_durations
from f1_explorer.visualizations.lap_selection import fastest_laps_by_driver
from f1_explorer.separator_estimator import SeparatorBoundary, coerce_separator_boundary
from f1_explorer.telemetry import lap_telemetry_without_driver_ahead

tracer = trace.get_tracer(__name__)


@dataclass(frozen=True, slots=True)
class MiniSegmentLayout:
    """The single boundary set shared by the map and segment tables."""

    distances: list[float]
    separator_boundaries: list[SeparatorBoundary]


CORNER_SPEED_COLORS = {
    "low": "#f8d7da",
    "medium_low": "#ffe5b4",
    "medium_high": "#fff3b0",
    "high": "#d4edda",
    "unavailable": "white",
}


def _corner_speed_color(speed: float | None) -> str:
    """Return the background color for a corner's passing speed."""
    if speed is None or not math.isfinite(speed):
        return CORNER_SPEED_COLORS["unavailable"]
    if speed <= 100:
        return CORNER_SPEED_COLORS["low"]
    if speed <= 150:
        return CORNER_SPEED_COLORS["medium_low"]
    if speed <= 200:
        return CORNER_SPEED_COLORS["medium_high"]
    return CORNER_SPEED_COLORS["high"]


def _corner_segment_colors(
        fastest_lap: Lap,
        corner_distances: list[float],
        segment_boundaries: list[float],
) -> list[str]:
    """Color each segment by the fastest lap's speed at its end corner."""
    car_data = fastest_lap.get_car_data().add_distance()
    samples = car_data[["Distance", "Speed"]].dropna().sort_values("Distance")
    samples = samples.drop_duplicates(subset="Distance", keep="last")
    if samples.empty:
        return [CORNER_SPEED_COLORS["unavailable"]] * (len(segment_boundaries) - 1)

    colors = []
    for end_distance in segment_boundaries[1:]:
        matching_corner = next(
            (distance for distance in corner_distances if math.isclose(distance, end_distance, abs_tol=0.1)),
            None,
        )
        if matching_corner is None:
            colors.append(CORNER_SPEED_COLORS["unavailable"])
            continue
        speed = float(np.interp(matching_corner, samples.Distance, samples.Speed))
        colors.append(_corner_speed_color(speed))
    return colors


def _table_fill_colors(column_count: int, row_colors: list[str]) -> list[list[str]]:
    """Expand row colors into Plotly's column-major table fill format."""
    return [row_colors] * column_count


@tracer.start_as_current_span("segment_table.prepare_car_data")
def prepare_segment_car_data(session: Session) -> dict[str, Telemetry]:
    """Read each driver's fastest-lap car samples once for both segment tables.

    Preserve sample order, duplicate distances, and missing values. These are
    raw car samples with distance added, rather than merged position telemetry.
    """
    samples: dict[str, Telemetry] = {}
    for driver_number, lap in fastest_laps_by_driver(session).items():
        try:
            samples[driver_number] = lap.get_car_data().add_distance()
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
    return samples


def _segment_descriptor_rows(segment_boundaries: list[float], circuit: CircuitInfo) -> list[list[Any]]:
    """Per-segment [name, distance, corner numbers] prefixes shared by the tables."""
    corners_df = circuit.corners
    rows = []
    for i in range(1, len(segment_boundaries)):
        filtered = corners_df[
            (corners_df.Distance >= segment_boundaries[i - 1]) & (corners_df.Distance <= segment_boundaries[i])
        ]
        rows.append([f"{i}", round(segment_boundaries[i] - segment_boundaries[i - 1], 1),
                     filtered.Number.tolist()])
    return rows


def _rounded_driver_column(
        values_by_driver: Mapping[str, Sequence[float | None]],
        driver_number: str, segment_index: int,
) -> float | None:
    values = values_by_driver.get(driver_number)
    value = values[segment_index] if values is not None and segment_index < len(values) else None
    return round(value, 3) if value is not None else None


def _rank_driver_column(
        ranks_by_driver: Mapping[str, Sequence[int]],
        driver_number: str, segment_index: int,
) -> int | None:
    ranks = ranks_by_driver.get(driver_number)
    return ranks[segment_index] if ranks is not None and segment_index < len(ranks) else None


def _driver_value_rows(
        descriptor_rows: list[list[Any]],
        drivers: list[str],
        values_by_driver: Mapping[str, Sequence[float | None]],
) -> list[list[Any]]:
    """Append one rounded value column per driver to the descriptor prefixes."""
    return [
        descriptor + [_rounded_driver_column(values_by_driver, driver_number, i - 1)
                      for driver_number in drivers]
        for i, descriptor in enumerate(descriptor_rows, start=1)
    ]


def _segment_table(headers: list[Any], rows: list[list[Any]], row_colors: list[str]) -> go.Figure:
    return go.Figure(data=[go.Table(
        header=go.table.Header(
            values=headers,
            fill=go.table.header.Fill(color='lightgrey'),
            align='center'),
        cells=go.table.Cells(
            values=list(zip(*rows)),
            fill=go.table.cells.Fill(
                color=_table_fill_colors(len(headers), row_colors),
            ),
            align='center',
        ),
    )])


@tracer.start_as_current_span("compute_and_save_segment_tables_plotly")
def compute_and_save_segment_tables_plotly(
        session: Session,
        filename_base: str,
        segment_boundaries: list[float] | MiniSegmentLayout,
        log: structlog.stdlib.BoundLogger,
        *,
        color_by_corner_speed: bool = False,
        car_data_by_driver: Mapping[str, Telemetry] | None = None,
):
    """mini segmentごとのタイムをプロットする
    Args:
        session: セッション
        filename_base: ファイル名のprefix
        segment_boundaries: セグメントの境界値一覧
        log: ロガー
        color_by_corner_speed: コーナー通過速度で行を着色する
        car_data_by_driver: 再利用済みの車両サンプル（キーは車番）
    """
    trace.get_current_span().set_attribute("segment.table_kind", Path(filename_base).name)
    if isinstance(segment_boundaries, MiniSegmentLayout):
        segment_boundaries = segment_boundaries.distances
    segment_boundaries = sorted(segment_boundaries)
    driver_times: dict[str, list[float | None]] = {}
    drivers = list(fastest_laps_by_driver(session))

    with tracer.start_as_current_span("segment_table.driver_times") as span:
        span.set_attribute("segment.boundary_count", len(segment_boundaries))
        span.set_attribute("segment.driver_count", len(drivers))
        if car_data_by_driver is None:
            car_data_by_driver = prepare_segment_car_data(session)
        for driver_number in drivers:
            car_data = car_data_by_driver.get(driver_number)
            if car_data is None:
                continue
            if "Distance" not in car_data or "Time" not in car_data:
                continue
            driver_times[driver_number] = [
                None if (last_point := car_data[car_data.Distance < dist]).empty else
                last_point.iloc[-1].Time.total_seconds() for dist in segment_boundaries]

    circuit = circuit_info_or_none(session, log)
    if circuit is None:
        return
    durations_by_driver = segment_durations(driver_times)
    descriptor_rows = _segment_descriptor_rows(segment_boundaries, circuit)
    segment_rows = _driver_value_rows(descriptor_rows, drivers, durations_by_driver)

    abbreviations = [session.get_driver(d).Abbreviation for d in drivers]
    row_colors = [CORNER_SPEED_COLORS["unavailable"]] * len(segment_rows)
    if color_by_corner_speed:
        fastest_lap = session.laps.pick_fastest()
        if fastest_lap is not None and not fastest_lap.empty:
            try:
                row_colors = _corner_segment_colors(
                    fastest_lap,
                    [float(distance) for distance in circuit.corners.Distance],
                    segment_boundaries,
                )
            except (AttributeError, KeyError, TypeError, ValueError):
                log.warning("Fastest lap telemetry unavailable for corner speed colors.")
        else:
            log.warning("Fastest lap telemetry unavailable for corner speed colors.")

    with tracer.start_as_current_span("segment_table.build_figure") as span:
        span.set_attribute("segment.output", "durations")
        fig_segment = _segment_table(
            ["segment", "distance", "corners"] + abbreviations, segment_rows, row_colors)
    table_figures = [fig_segment]
    table_paths = [f"{filename_base}_durations.png"]

    def save_tables():
        save_plotly_batch(table_figures, table_paths, log, width=1920, height=1080)

    ranks_by_driver = rank_segment_durations(durations_by_driver)
    segment_rank_rows = [
        # The ranks table omits the corners column: only name and distance
        # carry over from the descriptor prefix.
        descriptor[:2] + [_rank_driver_column(ranks_by_driver, driver_number, i - 1)
                          for driver_number in drivers]
        for i, descriptor in enumerate(descriptor_rows, start=1)
    ]

    with tracer.start_as_current_span("segment_table.build_figure") as span:
        span.set_attribute("segment.output", "ranks")
        fig_ranks = _segment_table(["segment", "distance"] + abbreviations,
                                   segment_rank_rows, row_colors)
    table_figures.append(fig_ranks)
    table_paths.append(f"{filename_base}_ranks.png")

    best = session.laps.pick_fastest()
    if best is None or best.empty:
        save_tables()
        return
    best_driver_number = str(best.DriverNumber)
    best_durations = durations_by_driver.get(best_driver_number)
    if not best_durations:
        log.warning("Fastest lap driver has insufficient segment data.")
        save_tables()
        return
    deltas_by_driver = deltas_to_reference(durations_by_driver, best_driver_number)
    gap_rows = _driver_value_rows(descriptor_rows, drivers, deltas_by_driver)
    with tracer.start_as_current_span("segment_table.build_figure") as span:
        span.set_attribute("segment.output", "gaps_to_best")
        fig_gap = _segment_table(
            ["segment", "distance", "corners"] + abbreviations, gap_rows, row_colors)
    table_figures.append(fig_gap)
    table_paths.append(f"{filename_base}_gaps_to_best.png")
    save_tables()


@tracer.start_as_current_span("make_mini_segment_layout")
def make_mini_segment_layout(
        session: Session,
        log: structlog.stdlib.BoundLogger,
        corner_map: dict[str, list[float]],
        separators: Sequence[Any],
        *, fastest_lap: Lap | None = None, telemetry: Telemetry | None = None,
) -> MiniSegmentLayout:
    """Build one shared distance/identity definition for mini segments."""
    fastest_lap = fastest_lap if fastest_lap is not None else session.laps.pick_fastest()
    if fastest_lap is None:
        return MiniSegmentLayout([], [])
    car_data = telemetry if telemetry is not None else lap_telemetry_without_driver_ahead(
        fastest_lap, add_distance=True
    )
    if car_data is None or car_data.empty or "Distance" not in car_data:
        return MiniSegmentLayout([], [])

    segment_boundaries = [0.0, float(car_data.iloc[-1].Distance)]
    circuit_info = circuit_info_or_none(session, log)
    if circuit_info is not None:
        corners_df = circuit_info.corners
        for c in range(0, len(corners_df)):
            corner = corners_df.iloc[c]
            if corner is None:
                continue
            i = str(corner.Number)
            if i not in corner_map:
                continue
            for offset in corner_map[i]:
                try:
                    segment_boundaries.append(float(corner.Distance) + float(offset))
                except (TypeError, ValueError):
                    continue

    separator_boundaries: list[SeparatorBoundary] = []
    separator_distances: list[float] = []
    for item in separators:
        if not isinstance(item, (SeparatorBoundary, Mapping)):
            try:
                distance = float(item)
            except (TypeError, ValueError):
                continue
            # Same positive-distance policy as coerce_separator_boundary: a
            # separator at or before the 0.0 start boundary is not a segment.
            if math.isfinite(distance) and distance > 0:
                separator_distances.append(distance)
            continue
        boundary = coerce_separator_boundary(item)
        if boundary is not None:
            separator_boundaries.append(boundary)
            separator_distances.append(float(boundary.distance))

    segment_boundaries.extend(separator_distances)
    distances = sorted({round(distance, 6) for distance in segment_boundaries if math.isfinite(distance)})
    log.info(
        f"{corner_map} {separator_distances} corners_list: "
        f"{list(getattr(circuit_info, 'corners', pandas.DataFrame()).Distance) if circuit_info is not None else []}, "
        f"segment_list: {distances}"
    )
    return MiniSegmentLayout(distances, separator_boundaries)


@tracer.start_as_current_span("plot_mini_segment_on_circuit")
def plot_mini_segment_on_circuit(
        session: Session,
        log: structlog.stdlib.BoundLogger,
        segment_boundaries: list[float] | MiniSegmentLayout,
        image_name: str,
        *, output_dir: str | Path | None = None,
        separator_boundaries: Sequence[Any] | None = None,
        show_sector_boundaries: bool = False,
        fastest_lap: Lap | None = None,
        telemetry: Telemetry | None = None):
    """ミニセグメントをプロットする
    Args:
        session: 分析対象のセッション
        log: ロガー
        segment_boundaries: セグメントの境界
        image_name: 画像名
    """
    if isinstance(segment_boundaries, MiniSegmentLayout):
        if separator_boundaries is None:
            separator_boundaries = segment_boundaries.separator_boundaries
        segment_boundaries = segment_boundaries.distances
    # ベストタイムを記録したドライバーのベストラップを取得
    fastest_lap = fastest_lap if fastest_lap is not None else session.laps.pick_fastest()
    if fastest_lap is None:
        return
    driver = fastest_lap.Driver
    car_data = telemetry if telemetry is not None else lap_telemetry_without_driver_ahead(
        fastest_lap, add_distance=True
    )

    segment_boundaries = sorted(float(distance) for distance in segment_boundaries)
    x = car_data["X"].to_numpy()
    y = car_data["Y"].to_numpy()
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    ax.plot(x, y, color='lightgrey', linewidth=2)

    for i in range(1, len(segment_boundaries)):
        start = segment_boundaries[i - 1]
        end = segment_boundaries[i]
        mask = (car_data.Distance >= start) & (car_data.Distance <= end)
        seg_x = car_data["X"][mask].to_numpy()
        seg_y = car_data["Y"][mask].to_numpy()
        color = 'black' if i % 2 == 0 else 'red'
        ax.plot(seg_x, seg_y, color=color, linewidth=3)

        indices = car_data.index[mask]
        if indices.empty:
            continue
        mid_index = indices[len(indices) // 2]
        mid_x: float = car_data.X.loc[mid_index]
        mid_y: float = car_data.Y.loc[mid_index]
        ax.text(mid_x, mid_y, f"{i}", fontsize=8, color='blue', ha='center', va='center')

    if show_sector_boundaries:
        structured = _structured_sector_boundary_distances(separator_boundaries)
        sector_distances = (
            structured if structured is not None
            else _sector_boundary_distances(fastest_lap, car_data)
        )
        for label, distance in zip(("S1→S2", "S2→S3"), sector_distances):
            point_x = float(np.interp(distance, car_data.Distance, car_data.X))
            point_y = float(np.interp(distance, car_data.Distance, car_data.Y))
            ax.scatter(
                [point_x], [point_y], s=150, marker='o', facecolors='white',
                edgecolors='#00a6ff', linewidths=2.5, zorder=10,
            )
            ax.annotate(
                label, (point_x, point_y), xytext=(7, 7), textcoords='offset points',
                fontsize=9, fontweight='bold', color='#006da8', zorder=11,
            )

    ax.set_aspect('equal')
    ax.set_title(f"Mini Segments of Best Lap - {driver}")
    ax.axis('off')

    save_matplotlib(fig, resolve_output_dir(session, output_dir) / f"{image_name}.png", log)


def _structured_sector_boundary_distances(
        boundaries: Sequence[Any] | None,
) -> list[float] | None:
    """Get S1/S2 ends from stored identities, not from a fastest-lap clock."""
    if boundaries is None:
        return None
    parsed = [boundary for boundary in map(coerce_separator_boundary, boundaries)
              if boundary is not None]
    if not parsed:
        return None
    result = []
    for sector in (0, 1):
        candidates = [item for item in parsed if item.sector == sector]
        if candidates:
            result.append(max(candidates, key=lambda item: (item.segment, item.distance)).distance)
    return result


def _sector_boundary_distances(lap: Lap, telemetry: Telemetry | pandas.DataFrame | None = None) -> list[float]:
    """Return the S1/S2 end positions as distances on the supplied lap."""
    sector_times = []
    for name in ("Sector1Time", "Sector2Time"):
        value = getattr(lap, name, None)
        if value is None or pandas.isna(value):
            return []
        try:
            seconds = as_seconds(value)
        except (AttributeError, TypeError, ValueError):
            return []
        if not math.isfinite(seconds) or seconds <= 0:
            return []
        sector_times.append(seconds)

    data = telemetry if telemetry is not None else lap.get_telemetry().add_distance()
    if data is None:
        return []
    if "Distance" not in data.columns or "Time" not in data.columns:
        return []
    times = np.asarray([
        as_seconds(value) if hasattr(value, "total_seconds") else as_float(value)
        for value in data.Time
    ], dtype=float)
    distances = np.asarray(data.Distance, dtype=float)
    valid = np.isfinite(times) & np.isfinite(distances)
    if valid.sum() < 2:
        return []
    times = times[valid]
    distances = distances[valid]
    order = np.argsort(times)
    times = times[order]
    distances = distances[order]
    targets = [sector_times[0], sector_times[0] + sector_times[1]]
    if targets[-1] > times[-1]:
        return []
    return [float(np.interp(target, times, distances)) for target in targets]

