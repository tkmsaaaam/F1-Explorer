"""Offline qualifying speed comparison by lap selection and measurement point."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from opentelemetry import trace

tracer = trace.get_tracer(__name__)


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


def _truthy(values):
    """Convert nullable object values without pandas' deprecated fillna downcast."""
    return values.map(lambda value: False if pd.isna(value) else bool(value))


def _valid_laps(laps):
    valid = laps.loc[_truthy(laps["IsAccurate"])]
    if "Deleted" in valid:
        valid = valid.loc[~_truthy(valid["Deleted"])]
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


@tracer.start_as_current_span("speed.telemetry_cache")
def _telemetry_cache(laps):
    trace.get_current_span().set_attribute("speed.valid_lap_count", len(laps))
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


def _indexed_laps(laps):
    """Build a first-row lookup, matching the first-duplicate behavior of iteration."""
    rows = {}
    for lap_index, lap in _iter_laps(laps):
        rows.setdefault(lap_index, lap)
    return rows


def _prepared_telemetry(telemetry_cache):
    """Cache numeric distance and nanosecond timestamp arrays for one figure build."""
    prepared = {}
    for lap_index, (driver, telemetry) in telemetry_cache.items():
        prepared[lap_index] = (
            driver,
            telemetry,
            telemetry["Distance"].to_numpy(dtype=float),
            telemetry["Date"].astype("int64").to_numpy(dtype=float),
        )
    return prepared


class _TowContext:
    """Per-figure lookups and lazy tow decisions shared by all measurements."""

    def __init__(self, laps, telemetry_cache, row_source=None):
        self.lap_rows = _indexed_laps(laps if row_source is None else row_source)
        self.prepared = _prepared_telemetry(telemetry_cache)
        self.measurements = {}
        self.masks = {}

    def mask(self, lap_index):
        if lap_index not in self.masks:
            self.masks[lap_index] = _tow_mask_prepared(lap_index, self.prepared)
        return self.masks[lap_index]

    def at_measurement(self, lap_index, key, telemetry_cache, session):
        cache_key = (lap_index, key)
        if cache_key not in self.measurements:
            self.measurements[cache_key] = _tow_at_measurement(
                lap_index, key, telemetry_cache, session,
                lap_rows=self.lap_rows, prepared=self.prepared,
            )
        return self.measurements[cache_key]


def _tow_mask_prepared(lap_index, prepared):
    """Classify samples using prebuilt distance/time arrays."""
    driver, telemetry, target_distance, target_time = prepared[lap_index]
    tow = np.zeros(len(telemetry), dtype=bool)
    threshold_ns = _TOW_THRESHOLD_SECONDS * 1_000_000_000
    for other_index, (other_driver, _, other_distance, other_time) in prepared.items():
        if other_index == lap_index or other_driver == driver or len(other_distance) < 2:
            continue
        overlap = ((target_distance >= other_distance[0]) &
                   (target_distance <= other_distance[-1]))
        if not overlap.any():
            continue
        passage_time = np.interp(target_distance[overlap], other_distance, other_time)
        gap = target_time[overlap] - passage_time
        tow[overlap] |= (gap > 0) & (gap <= threshold_ns)
    return tow


def _tow_at_measurement(lap_index, key, telemetry_cache, session, lap_rows=None,
                        prepared=None):
    """Return tow context at FL/I1/I2; SpeedST intentionally has no context."""
    if key == "SpeedST" or lap_index not in telemetry_cache:
        return None
    _, telemetry = telemetry_cache[lap_index]
    lap = (lap_rows or _indexed_laps(session.laps)).get(lap_index)
    if lap is None:
        return None
    if key == "SpeedFL":
        sample = telemetry.iloc[-1]
    else:
        field = {"SpeedI1": "Sector1SessionTime", "SpeedI2": "Sector2SessionTime"}[key]
        when = lap.get(field)
        if pd.isna(when) or not hasattr(session, "t0_date"):
            return None
        target = session.t0_date + when
        sample = telemetry.iloc[(telemetry["Date"] - target).abs().argmin()]
    if prepared is None:
        prepared = _prepared_telemetry(telemetry_cache)
    best = None
    for other_index, (other_driver, other) in telemetry_cache.items():
        _, _, other_distances, other_times = prepared[other_index]
        if other_index == lap_index or other_driver == lap.get("Driver") or len(other_distances) < 2:
            continue
        distance = float(sample["Distance"])
        if distance < other_distances[0] or distance > other_distances[-1]:
            continue
        other_time = np.interp(distance, other_distances, other_times)
        gap = (float(sample["Date"].value) - other_time) / 1_000_000_000
        if 0 < gap <= _TOW_THRESHOLD_SECONDS and (best is None or gap < best[1]):
            best = (other_driver, gap)
    return best


@tracer.start_as_current_span("speed.measurement_values")
def _measurement_values(laps, key, telemetry_cache, session=None, tow_context=None):
    span = trace.get_current_span()
    span.set_attribute("speed.measurement", key)
    span.set_attribute("speed.lap_count", len(laps))
    rows = []
    context = tow_context or _TowContext(laps, telemetry_cache)
    if key.startswith("Telemetry"):
        wants_tow = key == "TelemetryTow"
        for lap_index, lap in _iter_laps(laps):
            if lap_index not in telemetry_cache:
                continue
            _, telemetry, _, _ = context.prepared[lap_index]
            mask = context.mask(lap_index)
            selected = telemetry.loc[mask if wants_tow else ~mask, "Speed"]
            maximum = selected.max()
            if pd.notna(maximum) and maximum > 0:
                rows.append((lap.get("Driver"), lap.get("Team", ""), float(maximum), lap_index, wants_tow))
    else:
        for lap_index, lap in _iter_laps(laps):
            speed = pd.to_numeric(pd.Series([lap.get(key)]), errors="coerce").iloc[0]
            if pd.notna(speed) and speed > 0:
                tow = None
                if session is not None:
                    tow = context.at_measurement(lap_index, key, telemetry_cache, session)
                rows.append((lap.get("Driver"), lap.get("Team", ""), float(speed), lap_index, tow is not None))

    if not rows:
        return [], [], {}, {}
    measured = pd.DataFrame(rows, columns=["Driver", "Team", "Speed", "LapIndex", "Tow"])
    fastest = measured.sort_values("Speed", ascending=False).drop_duplicates("Driver")
    return (fastest["Driver"].tolist(), fastest["Speed"].tolist(),
            fastest.set_index("Driver")["Team"].to_dict(),
            fastest.set_index("Driver")["Tow"].to_dict())


def make_qualifying_speed(session):
    """Build the 4 lap selections × 6 speed measurements comparison."""

    valid = _valid_laps(session.laps)
    telemetry_cache = _telemetry_cache(valid)
    tow_context = _TowContext(valid, telemetry_cache, row_source=session.laps)
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
            drivers, speeds, teams, tow = _measurement_values(
                laps, key, telemetry_cache, session, tow_context=tow_context,
            )
            label = f"{scope_label} · {measurement_label}"
            combinations.append((label, key, drivers, speeds, _team_colors(drivers, teams, session), tow))

    fig = go.Figure()
    for index, (label, key, drivers, speeds, colors, tow) in enumerate(combinations):
        text = [f"<b>{speed:.1f}</b>" if tow.get(driver, False) and key != "SpeedST" else f"{speed:.1f}" for driver, speed in zip(drivers, speeds)]
        fig.add_trace(go.Bar(
            x=drivers, y=speeds, name=label, visible=index == 0,
            marker_color=colors, text=text,
            textposition="inside", textangle=0, insidetextanchor="end",
            hovertemplate="%{x}: %{y:.1f} km/h<extra></extra>",
        ))

    buttons = []
    for index, (label, _, drivers, speeds, _, _) in enumerate(combinations):
        buttons.append(dict(label=label, method="update", args=[
            {"visible": [trace_index == index for trace_index in range(len(combinations))]},
            {"title.text": label + ("（有効な速度なし）" if not speeds else ""),
             "yaxis.range": _speed_range(speeds), "yaxis.autorange": False,
             "xaxis.categoryarray": drivers},
        ]))

    initial_label, _, initial_drivers, initial_speeds, _, _ = combinations[0]
    fig.update_layout(
        title=dict(text=initial_label, x=0, xanchor="left", y=0.98),
        height=640, margin=dict(t=150), showlegend=False,
        meta=dict(f1ExplorerKind="qualifyingSpeed"),
        xaxis=dict(title="Driver", categoryorder="array", categoryarray=initial_drivers),
        yaxis=dict(title="Speed [km/h]", tickformat=".1f", range=_speed_range(initial_speeds)),
        updatemenus=[dict(buttons=buttons, x=0, xanchor="left", y=1.18, yanchor="top")],
    )
    return fig
