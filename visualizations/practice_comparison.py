"""Interactive result comparisons for practice reports."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from visualizations.chart_ranges import bar_range


def _colors(drivers, teams, session):
    import fastf1.plotting
    return [fastf1.plotting.get_team_color(teams.get(d, ""), session)
            if teams.get(d, "") else "gray" for d in drivers]


def _speed_range(values):
    if not values:
        return None
    return [max(0, min(values) - 5), max(values) + 5]


def _valid(laps):
    result = laps.loc[laps["IsAccurate"].fillna(False).astype(bool)]
    return result.loc[~result["Deleted"].fillna(False).astype(bool)] if "Deleted" in result else result


def _best(session, key):
    laps = _valid(session.laps)
    if laps.empty:
        return [], [], {}, []
    values = laps[key].dt.total_seconds()
    valid = laps.loc[values.notna() & (values > 0)].assign(_value=values)
    if valid.empty:
        return [], [], {}, []
    best = valid.groupby("Driver")["_value"].min().sort_values()
    teams = (valid.sort_values("_value").drop_duplicates("Driver").set_index("Driver")["Team"].to_dict()
             if "Team" in valid else {})
    drivers, values = best.index.tolist(), best.tolist()
    ratios = (best / best.min() * 100).tolist()
    return drivers, values, teams, ratios


def make_practice_best(session):
    combinations = []
    for key, label in (("LapTime", "ラップ"), ("Sector1Time", "S1"),
                       ("Sector2Time", "S2"), ("Sector3Time", "S3")):
        drivers, values, teams, ratios = _best(session, key)
        cells = [list(range(1, len(drivers) + 1)), drivers,
                 [f"{v:.3f}" for v in values], [f"{r:.3f}%" for r in ratios]]
        combinations.append((label, drivers, values, ratios, cells, _colors(drivers, teams, session)))
    fig = make_subplots(rows=2, cols=1, specs=[[{"type": "xy"}], [{"type": "table"}]],
                        row_heights=[0.48, 0.52], vertical_spacing=0.04)
    first = combinations[0]
    for index, (_, drivers, values, ratios, cells, colors) in enumerate(combinations[:1]):
        fig.add_trace(go.Bar(x=drivers, y=values, marker_color=colors, name="タイム", visible=True,
                             text=[f"{v:.3f} s<br>{r:.3f}%" for v, r in zip(values, ratios)],
                             textposition="inside", textangle=0, insidetextanchor="end",
                             hovertemplate="%{x}: %{y:.3f} s<extra></extra>"), row=1, col=1)
        fig.add_trace(go.Bar(x=drivers, y=ratios, marker_color=colors, name="最速比率", visible=False,
                             text=[f"{v:.3f} s<br>{r:.3f}%" for v, r in zip(values, ratios)],
                             textposition="inside", textangle=0, insidetextanchor="end",
                             hovertemplate="%{x}: %{y:.3f}%<extra></extra>"), row=1, col=1)
        fig.add_trace(go.Table(visible=True, header={"values": ["順位", "ドライバー", "タイム [s]", "最速比率 [%]"]},
                               cells={"values": cells, "height": 28}), row=2, col=1)
    buttons = []
    for label, drivers, values, ratios, cells, colors in combinations:
        buttons.append(dict(label=label, method="update", args=[
            {"x": [drivers, drivers, None], "y": [values, ratios, None],
             "marker.color": [colors, colors, None], "text": [
                 [f"{v:.3f} s<br>{r:.3f}%" for v, r in zip(values, ratios)],
                 [f"{v:.3f} s<br>{r:.3f}%" for v, r in zip(values, ratios)], None],
             "visible": [True, False, True], "cells.values": [None, None, cells]},
            {"title.text": f"{label}（Practice）", "yaxis.autorange": False,
             "yaxis.range": bar_range(values),
             "xaxis.categoryarray": drivers}]))
    views = [dict(label="タイム", method="update", args=[{"visible": [True, False, True]}, {"yaxis.title.text": "Time [s]"}]),
             dict(label="最速比率", method="update", args=[{"visible": [False, True, True]}, {"yaxis.title.text": "Best time ratio [%]"}])]
    fig.update_layout(title="ラップ（Practice）", height=1500, showlegend=False, meta={"f1ExplorerKind": "practiceBest"},
                      xaxis={"title": "Driver", "categoryorder": "array", "categoryarray": first[1]},
                      yaxis={"title": "Time [s]", "tickformat": ".3f", "range": bar_range(first[2]), "autorange": False},
                      updatemenus=[{"buttons": buttons, "x": 0, "y": 1.14}, {"buttons": views, "x": .55, "y": 1.14, "direction": "right"}])
    return fig


def make_practice_speed(session):
    metrics = (("SpeedFL", "フィニッシュライン"), ("SpeedI1", "第1中間計測地点"),
               ("SpeedI2", "第2中間計測地点"), ("SpeedST", "スピードトラップ"))
    laps = _valid(session.laps)
    fig = go.Figure()
    choices = []
    for key, label in metrics:
        values = pd.to_numeric(laps[key], errors="coerce") if key in laps else pd.Series(dtype=float)
        valid = laps.loc[values.notna() & (values > 0)].assign(_value=values)
        best = valid.groupby("Driver")["_value"].max().sort_values(ascending=False) if not valid.empty else pd.Series(dtype=float)
        drivers = best.index.tolist()
        teams = (valid.sort_values("_value").drop_duplicates("Driver").set_index("Driver")["Team"].to_dict()
                 if not valid.empty and "Team" in valid else {})
        choices.append((label, drivers, best.tolist(), _colors(drivers, teams, session)))
    for index, (label, drivers, values, colors) in enumerate(choices):
        fig.add_trace(go.Bar(x=drivers, y=values, name=label, visible=index == 0, marker_color=colors,
                             text=[f"{v:.1f}" for v in values], textposition="inside",
                             hovertemplate="%{x}: %{y:.1f} km/h<extra></extra>"))
    buttons = [dict(label=label, method="update", args=[{"visible": [i == index for i in range(4)],
                    "x": [drivers if i == index else None for i in range(4)],
                    "y": [values if i == index else None for i in range(4)]},
                    {"title.text": label + "（Practice）", "yaxis.title.text": "Speed [km/h]",
                     "yaxis.autorange": False, "yaxis.range": _speed_range(values),
                     "xaxis.categoryarray": drivers}]) for index, (label, drivers, values, _) in enumerate(choices)]
    fig.update_layout(title="フィニッシュライン（Practice）", meta={"f1ExplorerKind": "practiceSpeed"},
                      showlegend=False, xaxis={"title": "Driver"},
                      yaxis={"title": "Speed [km/h]", "range": _speed_range(choices[0][2]), "autorange": False},
                      updatemenus=[{"buttons": buttons, "x": 0, "y": 1.14}])
    return fig
