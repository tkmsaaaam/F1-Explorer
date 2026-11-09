"""Interactive telemetry comparison used by qualifying reports."""

from __future__ import annotations

from typing import Any

from f1_explorer.circuit import circuit_info_or_none

from fastf1.core import Telemetry
import fastf1.plotting
import numpy as np
import plotly.graph_objects as go

from f1_explorer.visualizations.lap_selection import fastest_laps_by_driver
from f1_explorer.visualizations.short_runs import _plotly_driver_dash
from f1_explorer.visualizations.short_runs import _gear_colorscale
from f1_explorer.telemetry import lap_telemetry_without_driver_ahead


# Tab definitions for make_telemetry_comparison:
# (label, y-axis title, car-data key, step line, axis spec).
# Axis spec keys:
#   "range": fixed y-axis range, used with or without data;
#   "ticks": fixed explicit tick values rendered as array-mode ticks;
#   "empty": y-axis range shown when the tab has no data;
#   "fallback": gear maximum assumed when the tab has no data.
TELEMETRY_TABS = (
    ("タイム差", "Delta Time [s]", "delta", False, {"empty": [-1, 1]}),
    ("速度", "Speed [km/h]", "Speed", False, {"empty": [0, 300]}),
    ("スロットル", "Throttle [%]", "Throttle", False, {"range": [0, 100]}),
    ("ブレーキ", "Brake", "Brake", False, {"range": [-0.05, 1.05], "ticks": [0, 1]}),
    ("ギア", "Gear", "nGear", True, {"fallback": 8}),
)


def _finite_series(data: Any, key: str) -> tuple[np.ndarray, np.ndarray] | None:
    if not hasattr(data, "Distance") or not hasattr(data, key):
        return None
    x = np.asarray(data.Distance, dtype=float)
    y = np.asarray(getattr(data, key), dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    if not valid.any():
        return None
    return x[valid], y[valid]


def _lap_data(data: Any, key: str) -> tuple[np.ndarray, np.ndarray] | None:
    try:
        return _finite_series(data, key)
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def _distance_time(data: Any) -> tuple[np.ndarray, np.ndarray] | None:
    """Keep finite samples in acquisition order, rejecting backward progress."""
    try:
        distance = np.asarray(data.Distance, dtype=float)
        times = np.asarray([value.total_seconds() for value in data.Time], dtype=float)
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
    valid = np.isfinite(distance) & np.isfinite(times)
    distance, times = distance[valid], times[valid]
    if len(distance) < 2:
        return None
    indices = np.unique(distance, return_index=True)[1]
    indices = np.sort(indices)
    distance, times = distance[indices], times[indices]
    if len(distance) < 2 or np.any(np.diff(distance) < 0) or np.any(np.diff(times) < 0):
        return None
    return distance, times


def make_telemetry_comparison(session: Any) -> go.Figure:
    """Build one five-tab telemetry chart for short-session reports."""
    laps = fastest_laps_by_driver(session)

    # Scope reuse to this figure: car data and merged position telemetry differ.
    car_data: dict[str, Telemetry | None] = {}
    for number, driver_lap in laps.items():
        try:
            car_data[number] = driver_lap.get_car_data().add_distance()
        except (AttributeError, KeyError, TypeError, ValueError):
            car_data[number] = None
    time_data = {number: _distance_time(data) for number, data in car_data.items()}
    time_data = {number: value for number, value in time_data.items() if value is not None}
    reference_number = next(iter(laps), None)
    common_distance = np.array([], dtype=float)
    if reference_number is not None and reference_number in time_data:
        reference_distance, reference_time = time_data[reference_number]
        common_distance = np.arange(0.0, reference_distance.max(), 5.0)
        if len(common_distance) >= 2:
            reference_values = np.interp(
                common_distance, reference_distance, reference_time, left=np.nan, right=np.nan,
            )
        else:
            common_distance = np.array([], dtype=float)
            reference_values = np.array([], dtype=float)
    else:
        reference_values = np.array([], dtype=float)

    tabs = TELEMETRY_TABS
    figure = go.Figure()
    trace_groups: list[list[int]] = [[] for _ in tabs]
    values_by_tab: list[list[float]] = [[] for _ in tabs]

    for number, lap in laps.items():
        try:
            color = fastf1.plotting.get_team_color(lap.Team, session)
        except (AttributeError, KeyError, ValueError):
            color = "gray"
        try:
            dash = _plotly_driver_dash(session.event.year, int(number))
        except (TypeError, ValueError):
            dash = "solid"

        if len(common_distance) >= 2 and str(number) in time_data:
            distance, times = time_data[str(number)]
            valid = (np.isfinite(reference_values)
                     & (common_distance >= distance[0]) & (common_distance <= distance[-1]))
            if np.count_nonzero(valid) >= 2:
                delta = np.interp(common_distance[valid], distance, times) - reference_values[valid]
                delta_values: list[float | None] = [None] * len(common_distance)
                for sample_index, value in zip(np.flatnonzero(valid), delta):
                    delta_values[sample_index] = float(value)
                index = len(figure.data)
                figure.add_trace(go.Scatter(
                    x=common_distance, y=delta_values, mode="lines", name=str(lap.Driver),
                    line={"color": color, "dash": dash}, connectgaps=False,
                    hovertemplate=f"{lap.Driver}<br>Distance: %{{x:.1f}} m<br>Delta: %{{y:.3f}} s<extra></extra>",
                    visible=True,
                ))
                trace_groups[0].append(index)
                values_by_tab[0].extend(delta.tolist())

        for tab_index, (_, label, key, step, _axis) in enumerate(tabs[1:], start=1):
            series = _lap_data(car_data[str(number)], key)
            if series is None:
                continue
            distance, values = series
            index = len(figure.data)
            figure.add_trace(go.Scatter(
                x=distance, y=values, mode="lines", name=str(lap.Driver),
                line={"color": color, "dash": dash, **({"shape": "hv"} if step else {})},
                hovertemplate=f"{lap.Driver}<br>Distance: %{{x:.1f}} m<br>{label}: %{{y:.2f}}<extra></extra>",
                visible=False,
            ))
            trace_groups[tab_index].append(index)
            values_by_tab[tab_index].extend(values.tolist())

    # When no delta series exists, show the first tab that still has traces.
    initial_tab = next((index for index, group in enumerate(trace_groups) if group), 0)
    if figure.data:
        for index in trace_groups[initial_tab]:
            figure.data[index].visible = True

    buttons = []
    initial_layout: dict[str, Any] | None = None
    for tab_index, (label, axis_label, _, step, axis) in enumerate(tabs):
        visible = [False] * len(figure.data)
        for index in trace_groups[tab_index]:
            visible[index] = True
        values = values_by_tab[tab_index]
        if step:  # Gear: one integer tick per gear up to the observed maximum.
            maximum = int(max(values, default=axis["fallback"]))
            axis_range, ticks = [-0.5, maximum + 0.5], list(range(maximum + 1))
        elif "range" in axis:  # Fixed axes: throttle and brake.
            axis_range, ticks = axis["range"], axis.get("ticks")
        elif values:  # Data-driven axes wrap the observed values with padding.
            low, high = min(values), max(values)
            padding = max((high - low) * 0.02, abs(high) * 0.01, 0.01)
            axis_range, ticks = [low - padding, high + padding], None
        else:  # Missing data: show the tab's placeholder range.
            axis_range, ticks = axis["empty"], None
        # Reset the whole axis state on every switch: "auto" plus the null
        # tick properties undo the array ticks of the previously shown tab.
        layout_update = {
            "title.text": label if values else f"{label}（欠測）",
            "yaxis.title.text": axis_label,
            "yaxis.tickmode": "auto" if ticks is None else "array",
            "yaxis.tickvals": ticks,
            "yaxis.ticktext": None,
            "yaxis.range": axis_range,
            "yaxis.autorange": False,
        }
        buttons.append(dict(label=label, method="update", args=[{"visible": visible}, layout_update]))
        if tab_index == initial_tab:
            initial_layout = layout_update

    figure.update_layout(
        hovermode="x unified", template="plotly_white",
        meta={"f1ExplorerKind": "telemetryComparison"},
        updatemenus=[dict(buttons=buttons, type="buttons", direction="right", x=0, y=1.16, xanchor="left")],
        margin={"l": 70, "r": 30, "t": 110, "b": 70},
    )
    figure.update_xaxes(title="Distance [m]")
    figure.update_layout(initial_layout)
    if reference_number is not None:
        figure.add_hline(y=0, line_dash="dash", line_color="grey")
    circuit_info = circuit_info_or_none(session)
    if circuit_info is not None:
        for _, corner in circuit_info.corners.iterrows():
            distance = float(corner.Distance)
            figure.add_vline(x=distance, line_dash="dot", line_color="grey", opacity=0.6)
            figure.add_annotation(x=distance, y=0, yref="paper", yshift=-12,
                                  text=f"{corner.Number}{corner.Letter}", showarrow=False,
                                  font={"size": 9, "color": "grey"})
    return figure


def make_track_map_comparison(session: Any) -> go.Figure:
    """Build one driver-selectable speed/gear track map for short-session reports."""
    entries: list[tuple[str, Any, str, np.ndarray, np.ndarray, np.ndarray]] = []
    for number, lap in fastest_laps_by_driver(session).items():
        try:
            telemetry: Telemetry = lap_telemetry_without_driver_ahead(lap)
            x = np.asarray(telemetry.X, dtype=float)
            y = np.asarray(telemetry.Y, dtype=float)
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
        for metric in ("Speed", "nGear"):
            try:
                values = np.asarray(telemetry[metric], dtype=float)
                valid = np.isfinite(x) & np.isfinite(y) & np.isfinite(values)
            except (AttributeError, KeyError, TypeError, ValueError):
                continue
            if valid.any():
                entries.append((str(number), lap, metric, x[valid], y[valid], values[valid]))

    figure = go.Figure()
    speed_values = [values for _, _, metric, _, _, values in entries if metric == "Speed"]
    all_speed = np.concatenate(speed_values) if speed_values else np.array([])
    speed_min = float(all_speed.min()) if all_speed.size else 0.0
    speed_max = float(all_speed.max()) if all_speed.size else 1.0
    if speed_min == speed_max:
        speed_min, speed_max = speed_min - 0.5, speed_max + 0.5
    selected_driver = next((number for number, _, metric, *_ in entries if metric == "Speed"), None)
    driver_labels: dict[str, str] = {}
    for number, lap, metric, x, y, values in entries:
        driver_labels[number] = str(lap.Driver)
        try:
            color = fastf1.plotting.get_team_color(lap.Team, session)
        except (AttributeError, KeyError, ValueError):
            color = "gray"
        is_speed = metric == "Speed"
        unit, hover_format = ("Speed [km/h]", ".1f") if is_speed else ("Gear", ".0f")
        figure.add_trace(go.Scattergl(
            x=x, y=y, customdata=values, mode="lines+markers",
            name=str(lap.Driver), visible=is_speed and number == selected_driver,
            meta={"driverNumber": number, "metric": metric},
            showlegend=False, line={"color": color, "width": 1},
            marker={"color": values, "colorscale": "Plasma" if is_speed else _gear_colorscale(),
                    "cmin": speed_min if is_speed else 0.5,
                    "cmax": speed_max if is_speed else max(8.5, float(values.max() + 0.5)),
                    "size": 5, "showscale": True,
                    "colorbar": {"title": {"text": unit},
                                 **({"tickvals": list(range(1, 9)), "ticktext": [str(i) for i in range(1, 9)]} if not is_speed else {})}},
            hovertemplate=f"{lap.Driver}<br>{unit}: %{{customdata:{hover_format}}}<extra></extra>",
        ))
    speed_drivers = [number for number, _, metric, *_ in entries if metric == "Speed"]
    driver_buttons = [
        {"label": driver_labels[number], "method": "update", "execute": False,
         "args": [{"driverNumber": number}]} for number in speed_drivers
    ]
    figure.update_layout(
        title={"text": "速度 — " + (driver_labels[selected_driver] if selected_driver else "有効なデータなし"),
               "x": 0.5, "xanchor": "center", "y": 0.98, "yanchor": "top"},
        template="plotly_white",
        meta={"f1ExplorerKind": "trackMapComparison",
              "drivers": [{"number": number, "label": label} for number, label in driver_labels.items()],
              "selectedDriver": selected_driver, "selectedMetric": "Speed"},
        updatemenus=[
            {"buttons": [{"label": label, "method": "update", "execute": False,
                          "args": [{"metric": metric}]} for label, metric in (("速度", "Speed"), ("ギア", "nGear"))],
             "type": "buttons", "direction": "right", "x": 0, "y": 1.16, "active": 0},
            {"buttons": driver_buttons, "type": "dropdown", "x": 0.28, "y": 1.16,
             "active": 0 if driver_buttons else -1},
        ],
        margin={"l": 30, "r": 90, "t": 110, "b": 30},
    )
    figure.update_xaxes(visible=False)
    figure.update_yaxes(visible=False, scaleanchor="x", scaleratio=1)
    return figure


# Backward-compatible names used by the qualifying entry point.
make_qualifying_telemetry = make_telemetry_comparison
make_qualifying_track_map = make_track_map_comparison
