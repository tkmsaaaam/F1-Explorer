"""Offline qualifying speed comparison by lap selection and measurement point."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go


_MEASUREMENTS = (
    ("SpeedFL", "フィニッシュライン"),
    ("SpeedI1", "第1中間計測地点"),
    ("SpeedI2", "第2中間計測地点"),
    ("SpeedST", "スピードトラップ"),
    ("TelemetryTow", "ラップ中の最高速（トウあり）"),
    ("TelemetryNoTow", "ラップ中の最高速（トウなし）"),
)
_TOW_THRESHOLD_SECONDS = 2.0


def _speed_range(values):
    if not values:
        return None
    return [max(0, min(values) - 5), max(values) + 5]


def _team_colors(drivers, teams, session):
    if not teams:
        return ["gray"] * len(drivers)
    import fastf1.plotting
    return [fastf1.plotting.get_team_color(teams.get(driver, ""), session)
            if teams.get(driver, "") else "gray" for driver in drivers]


def _valid_laps(laps):
    valid = laps.loc[laps["IsAccurate"].fillna(False).astype(bool)]
    if "Deleted" in valid:
        valid = valid.loc[~valid["Deleted"].fillna(False).astype(bool)]
    return valid


def _best_laps(laps):
    seconds = laps["LapTime"].dt.total_seconds()
    timed = laps.loc[seconds.notna() & (seconds > 0)]
    if timed.empty:
        return timed
    indices = timed.assign(_seconds=seconds.loc[timed.index]).groupby("Driver")["_seconds"].idxmin()
    return timed.loc[indices.tolist()]


def _iter_laps(laps):
    if hasattr(laps, "iterlaps"):
        yield from laps.iterlaps(require=())
    else:
        yield from laps.iterrows()


def _lap_telemetry(lap):
    try:
        telemetry = lap.get_car_data()
        if "Distance" not in telemetry:
            telemetry = telemetry.add_distance()
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
    required = {"Date", "Distance", "Speed"}
    if not required.issubset(telemetry.columns):
        return None
    data = telemetry.loc[:, ["Date", "Distance", "Speed"]].copy()
    data["Distance"] = pd.to_numeric(data["Distance"], errors="coerce")
    data["Speed"] = pd.to_numeric(data["Speed"], errors="coerce")
    data = data.dropna().sort_values("Distance").drop_duplicates("Distance")
    return data if not data.empty else None


def _telemetry_cache(laps):
    cache = {}
    for lap_index, lap in _iter_laps(laps):
        telemetry = _lap_telemetry(lap)
        if telemetry is not None:
            cache[lap_index] = (lap.get("Driver"), telemetry)
    return cache


def _tow_mask(lap_index, telemetry_cache):
    """Classify each sample from another car's interpolated passage time at that distance."""

    driver, target = telemetry_cache[lap_index]
    target_distance = target["Distance"].to_numpy(dtype=float)
    target_time = target["Date"].astype("int64").to_numpy(dtype=float)
    tow = np.zeros(len(target), dtype=bool)
    threshold_ns = _TOW_THRESHOLD_SECONDS * 1_000_000_000
    for other_index, (other_driver, other) in telemetry_cache.items():
        if other_index == lap_index or other_driver == driver or len(other) < 2:
            continue
        other_distance = other["Distance"].to_numpy(dtype=float)
        overlap = ((target_distance >= other_distance[0]) &
                   (target_distance <= other_distance[-1]))
        if not overlap.any():
            continue
        other_time = other["Date"].astype("int64").to_numpy(dtype=float)
        passage_time = np.interp(target_distance[overlap], other_distance, other_time)
        gap = target_time[overlap] - passage_time
        tow[overlap] |= (gap > 0) & (gap <= threshold_ns)
    return tow


def _measurement_values(laps, key, telemetry_cache):
    rows = []
    if key.startswith("Telemetry"):
        wants_tow = key == "TelemetryTow"
        for lap_index, lap in _iter_laps(laps):
            if lap_index not in telemetry_cache:
                continue
            _, telemetry = telemetry_cache[lap_index]
            mask = _tow_mask(lap_index, telemetry_cache)
            selected = telemetry.loc[mask if wants_tow else ~mask, "Speed"]
            maximum = selected.max()
            if pd.notna(maximum) and maximum > 0:
                rows.append((lap.get("Driver"), lap.get("Team", ""), float(maximum)))
    else:
        for _, lap in _iter_laps(laps):
            speed = pd.to_numeric(pd.Series([lap.get(key)]), errors="coerce").iloc[0]
            if pd.notna(speed) and speed > 0:
                rows.append((lap.get("Driver"), lap.get("Team", ""), float(speed)))

    if not rows:
        return [], [], {}
    measured = pd.DataFrame(rows, columns=["Driver", "Team", "Speed"])
    fastest = measured.sort_values("Speed", ascending=False).drop_duplicates("Driver")
    return (fastest["Driver"].tolist(), fastest["Speed"].tolist(),
            fastest.set_index("Driver")["Team"].to_dict())


def make_qualifying_speed(session):
    """Build the 4 lap selections × 6 speed measurements comparison."""

    valid = _valid_laps(session.laps)
    telemetry_cache = _telemetry_cache(valid)
    parts = session.laps.split_qualifying_sessions()
    prefix = "SQ" if session.name.startswith("Sprint") else "Q"
    scopes = [("全有効ラップ", valid)]
    for index in range(3):
        part = parts[index] if len(parts) > index else None
        part = _valid_laps(part) if part is not None and not part.empty else valid.iloc[0:0]
        scopes.append((f"{prefix}{index + 1}ベストラップ", _best_laps(part)))

    combinations = []
    for scope_label, laps in scopes:
        for key, measurement_label in _MEASUREMENTS:
            drivers, speeds, teams = _measurement_values(laps, key, telemetry_cache)
            label = f"{scope_label} · {measurement_label}"
            combinations.append((label, drivers, speeds, _team_colors(drivers, teams, session)))

    fig = go.Figure()
    for index, (label, drivers, speeds, colors) in enumerate(combinations):
        fig.add_trace(go.Bar(
            x=drivers, y=speeds, name=label, visible=index == 0,
            marker_color=colors, text=[f"{speed:.1f}" for speed in speeds],
            textposition="inside", textangle=0, insidetextanchor="end",
            hovertemplate="%{x}: %{y:.1f} km/h<extra></extra>",
        ))

    buttons = []
    for index, (label, drivers, speeds, _) in enumerate(combinations):
        buttons.append(dict(label=label, method="update", args=[
            {"visible": [trace_index == index for trace_index in range(len(combinations))]},
            {"title.text": label + ("（有効な速度なし）" if not speeds else ""),
             "yaxis.range": _speed_range(speeds), "yaxis.autorange": False,
             "xaxis.categoryarray": drivers},
        ]))

    initial_label, initial_drivers, initial_speeds, _ = combinations[0]
    fig.update_layout(
        title=dict(text=initial_label, x=0, xanchor="left", y=0.98),
        height=640, margin=dict(t=150), showlegend=False,
        meta=dict(f1ExplorerKind="qualifyingSpeed"),
        xaxis=dict(title="Driver", categoryorder="array", categoryarray=initial_drivers),
        yaxis=dict(title="Speed [km/h]", tickformat=".1f", range=_speed_range(initial_speeds)),
        updatemenus=[dict(buttons=buttons, x=0, xanchor="left", y=1.18, yanchor="top")],
    )
    return fig
