"""Interactive telemetry comparison used by qualifying reports."""

from __future__ import annotations

from typing import Any

import numpy as np
import plotly.graph_objects as go

from visualizations.short_runs import _plotly_driver_dash, _ordered_quicklap_drivers
from visualizations.short_runs import _gear_colorscale


def _finite_series(data: Any, key: str) -> tuple[np.ndarray, np.ndarray] | None:
    if not hasattr(data, "Distance") or not hasattr(data, key):
        return None
    x = np.asarray(data.Distance, dtype=float)
    y = np.asarray(getattr(data, key), dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    if not valid.any():
        return None
    return x[valid], y[valid]


def _lap_data(lap: Any, key: str) -> tuple[np.ndarray, np.ndarray] | None:
    try:
        return _finite_series(lap.get_car_data().add_distance(), key)
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def _distance_time(lap: Any) -> tuple[np.ndarray, np.ndarray] | None:
    try:
        data = lap.get_car_data().add_distance()
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
    return (distance, times) if len(distance) >= 2 else None


def make_telemetry_comparison(session: Any) -> go.Figure:
    """Build one five-tab telemetry chart for short-session reports."""
    driver_numbers = _ordered_quicklap_drivers(session)
    laps = {}
    for number in driver_numbers:
        try:
            lap = session.laps.pick_drivers(number).pick_fastest()
        except (AttributeError, KeyError, TypeError, ValueError):
            lap = None
        if lap is not None:
            laps[str(number)] = lap

    time_data = {number: _distance_time(lap) for number, lap in laps.items()}
    time_data = {number: value for number, value in time_data.items() if value is not None}
    reference_number = min(
        laps,
        key=lambda number: laps[number].LapTime.total_seconds(),
        default=None,
    )
    common_distance = np.array([], dtype=float)
    if reference_number in time_data:
        reference_distance, reference_time = time_data[reference_number]
        common_distance = np.arange(0.0, reference_distance.max(), 5.0)
        if len(common_distance) >= 2:
            reference_values = np.interp(common_distance, reference_distance, reference_time)
        else:
            common_distance = np.array([], dtype=float)
            reference_values = np.array([], dtype=float)
    else:
        reference_values = np.array([], dtype=float)

    tabs = (
        ("タイム差", "Delta Time [s]", "delta", False),
        ("速度", "Speed [km/h]", "Speed", False),
        ("スロットル", "Throttle [%]", "Throttle", False),
        ("ブレーキ", "Brake", "Brake", False),
        ("ギア", "Gear", "nGear", True),
    )
    figure = go.Figure()
    trace_groups: list[list[int]] = [[] for _ in tabs]
    values_by_tab: list[list[float]] = [[] for _ in tabs]

    for number in driver_numbers:
        lap = laps.get(str(number))
        if lap is None:
            continue
        try:
            color = __import__("fastf1").plotting.get_team_color(lap.Team, session)
        except (AttributeError, KeyError, ValueError):
            color = "gray"
        try:
            dash = _plotly_driver_dash(session.event.year, int(number))
        except (TypeError, ValueError):
            dash = "solid"

        if len(common_distance) >= 2 and str(number) in time_data:
            distance, times = time_data[str(number)]
            delta = np.interp(common_distance, distance, times) - reference_values
            index = len(figure.data)
            figure.add_trace(go.Scatter(
                x=common_distance, y=delta, mode="lines", name=str(lap.Driver),
                line={"color": color, "dash": dash},
                hovertemplate=f"{lap.Driver}<br>Distance: %{{x:.1f}} m<br>Delta: %{{y:.3f}} s<extra></extra>",
                visible=True,
            ))
            trace_groups[0].append(index)
            values_by_tab[0].extend(delta.tolist())

        for tab_index, (_, label, key, step) in enumerate(tabs[1:], start=1):
            series = _lap_data(lap, key)
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

    labels = [tab[0] for tab in tabs]
    axis_labels = [tab[1] for tab in tabs]
    buttons = []
    for tab_index, label in enumerate(labels):
        visible = [False] * len(figure.data)
        for index in trace_groups[tab_index]:
            visible[index] = True
        values = values_by_tab[tab_index]
        layout_update = {"title.text": label, "yaxis.title.text": axis_labels[tab_index]}
        if label == "スロットル":
            layout_update["yaxis.range"] = [0, 100]
        elif label == "ブレーキ":
            layout_update.update({"yaxis.range": [-0.05, 1.05], "yaxis.tickvals": [0, 1]})
        elif label == "ギア":
            maximum = int(max(values, default=0))
            layout_update.update({"yaxis.range": [-0.5, maximum + 0.5], "yaxis.tickvals": list(range(maximum + 1))})
        elif values:
            low, high = min(values), max(values)
            padding = max((high - low) * 0.02, abs(high) * 0.01, 0.01)
            layout_update["yaxis.range"] = [low - padding, high + padding]
        buttons.append(dict(label=label, method="update", args=[{"visible": visible}, layout_update]))

    figure.update_layout(
        title=labels[0] if figure.data else "有効なテレメトリーデータなし",
        hovermode="x unified", template="plotly_white",
        meta={"f1ExplorerKind": "telemetryComparison"},
        updatemenus=[dict(buttons=buttons, type="buttons", direction="right", x=0, y=1.16, xanchor="left")],
        margin={"l": 70, "r": 30, "t": 110, "b": 70},
    )
    figure.update_xaxes(title="Distance [m]")
    figure.update_yaxes(title=axis_labels[0])
    if reference_number is not None:
        figure.add_hline(y=0, line_dash="dash", line_color="grey")
    circuit_info = getattr(session, "get_circuit_info", lambda: None)()
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
    drivers = _ordered_quicklap_drivers(session)
    entries: list[tuple[str, Any, np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
    for number in drivers:
        try:
            lap = session.laps.pick_drivers(number).pick_fastest()
            telemetry = lap.get_telemetry() if lap is not None else None
            x = np.asarray(telemetry.X, dtype=float)
            y = np.asarray(telemetry.Y, dtype=float)
            speed = np.asarray(telemetry.Speed, dtype=float)
            gear = np.asarray(telemetry.nGear, dtype=float)
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
        valid = np.isfinite(x) & np.isfinite(y)
        if not valid.any():
            continue
        entries.append((str(number), lap, x[valid], y[valid], speed[valid], gear[valid]))

    figure = go.Figure()
    groups: dict[str, list[int]] = {"速度": [], "ギア": []}
    driver_indices: dict[str, list[int]] = {}
    all_speed = np.concatenate([entry[4] for entry in entries]) if entries else np.array([])
    speed_min = float(np.nanmin(all_speed)) if all_speed.size else 0.0
    speed_max = float(np.nanmax(all_speed)) if all_speed.size else 1.0
    if speed_min == speed_max:
        speed_min, speed_max = speed_min - 0.5, speed_max + 0.5

    for number, lap, x, y, speed, gear in entries:
        try:
            color = __import__("fastf1").plotting.get_team_color(lap.Team, session)
        except (AttributeError, KeyError, ValueError):
            color = "gray"
        driver_indices[number] = []
        for label, values, colorscale, cmin, cmax, unit, hover_format in (
            ("速度", speed, "Plasma", speed_min, speed_max, "Speed [km/h]", ".1f"),
            ("ギア", gear, _gear_colorscale(), 0.5, max(8.5, float(np.nanmax(gear, initial=1) + 0.5)), "Gear", ".0f"),
        ):
            valid = np.isfinite(values)
            idx = len(figure.data)
            figure.add_trace(go.Scattergl(
                x=x[valid], y=y[valid], customdata=values[valid], mode="lines+markers",
                name=str(lap.Driver), visible=label == "速度" and not driver_indices[number],
                showlegend=False, line={"color": color, "width": 1},
                marker={"color": values[valid], "colorscale": colorscale,
                        "cmin": cmin, "cmax": cmax, "size": 5, "showscale": True,
                        "colorbar": {"title": {"text": unit},
                                     **({"tickvals": list(range(1, 9)), "ticktext": [str(i) for i in range(1, 9)]} if label == "ギア" else {})}},
                hovertemplate=f"{lap.Driver}<br>{unit}: %{{customdata:{hover_format}}}<extra></extra>",
            ))
            driver_indices[number].append(idx)
            groups[label].append(idx)

    driver_labels = [number for number, *_ in entries]
    buttons = []
    for label in ("速度", "ギア"):
        for number in driver_labels:
            visible = [False] * len(figure.data)
            metric_index = 0 if label == "速度" else 1
            selected = driver_indices[number][metric_index]
            visible[selected] = True
            buttons.append({"label": f"{label} — {next(lap.Driver for n, lap, *_ in entries if n == number)}",
                            "method": "update", "args": [{"visible": visible}, {"title.text": f"{label} — {next(lap.Driver for n, lap, *_ in entries if n == number)}"}]})
    driver_buttons = []
    for number in driver_labels:
        driver_name = next(lap.Driver for n, lap, *_ in entries if n == number)
        visible = [False] * len(figure.data)
        visible[driver_indices[number][0]] = True
        driver_buttons.append({"label": str(driver_name), "method": "update", "args": [{"visible": visible}, {"title.text": f"速度 — {driver_name}"}]})
    figure.update_layout(
        title="速度 — " + (str(entries[0][1].Driver) if entries else "有効なテレメトリーデータなし"),
        template="plotly_white", meta={"f1ExplorerKind": "trackMapComparison"},
        updatemenus=[
            {"buttons": [{"label": label, "method": "update", "args": [{"visible": [i in groups[label] and i == driver_indices[driver_labels[0]][0 if label == '速度' else 1] for i in range(len(figure.data))]}, {"title.text": label}]} for label in ("速度", "ギア")], "type": "buttons", "direction": "right", "x": 0, "y": 1.16},
            {"buttons": driver_buttons, "type": "dropdown", "x": 0.28, "y": 1.16},
        ],
        margin={"l": 30, "r": 90, "t": 110, "b": 30},
    )
    figure.update_xaxes(visible=False)
    figure.update_yaxes(visible=False, scaleanchor="x", scaleratio=1)
    return figure


# Backward-compatible names used by the qualifying entry point.
make_qualifying_telemetry = make_telemetry_comparison
make_qualifying_track_map = make_track_map_comparison
