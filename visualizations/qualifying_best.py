"""Offline qualifying best-time comparison, including independent sector bests."""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def _bar_range(values):
    if not values:
        return None
    low, high = min(values), max(values)
    pad = max((high - low) * 0.08, high * 0.01)
    return [max(0, low - pad), high + pad]


def _team_colors(drivers, teams, session):
    if not teams:
        return ["gray"] * len(drivers)
    import fastf1.plotting
    return [fastf1.plotting.get_team_color(teams.get(driver, ""), session)
            if teams.get(driver, "") else "gray" for driver in drivers]


def make_qualifying_best(session):
    parts = session.laps.split_qualifying_sessions()
    prefix = "SQ" if session.name.startswith("Sprint") else "Q"
    scopes = [("予選全体", session.laps)] + [
        (f"{prefix}{i}", parts[i - 1] if len(parts) >= i else None)
        for i in range(1, 4)
    ]
    combinations = []
    for scope, laps in scopes:
        for key, metric in (("LapTime", "ラップ"), ("Sector1Time", "S1"),
                            ("Sector2Time", "S2"), ("Sector3Time", "S3")):
            best = pd.Series(dtype=float)
            teams = {}
            if laps is not None and not laps.empty:
                valid = laps.loc[laps["IsAccurate"].fillna(False).astype(bool)]
                if "Deleted" in valid:
                    valid = valid.loc[~valid["Deleted"].fillna(False).astype(bool)]
                seconds = valid[key].dt.total_seconds()
                timed = valid.assign(seconds=seconds).loc[seconds > 0]
                best = timed.groupby("Driver")["seconds"].min().sort_values()
                if "Team" in timed:
                    fastest = timed.sort_values("seconds").drop_duplicates("Driver")
                    teams = fastest.set_index("Driver")["Team"].to_dict()
            drivers, times = best.index.tolist(), best.tolist()
            ratios = (best / best.min() * 100).tolist() if len(best) else []
            colors = _team_colors(drivers, teams, session)
            cells = [list(range(1, len(drivers) + 1)), drivers, [f"{t:.3f}" for t in times],
                     [f"{r:.3f}%" for r in ratios]]
            combinations.append((f"{scope} · {metric}", drivers, times, ratios, cells, colors))

    initial_label, initial_drivers, initial_times, initial_ratios, initial_cells, initial_colors = combinations[0]
    fig = make_subplots(
        rows=2, cols=1, specs=[[{"type": "xy"}], [{"type": "table"}]],
        row_heights=[0.48, 0.52], vertical_spacing=0.04,
    )
    fig.add_trace(go.Bar(
        x=initial_drivers, y=initial_times, name="タイム", visible=True, marker_color=initial_colors,
        text=[f"{t:.3f} s<br>{r:.3f}%" for t, r in zip(initial_times, initial_ratios)],
        textposition="inside", textangle=0, insidetextanchor="end",
        hovertemplate="%{x}: %{y:.3f} s<extra></extra>"), row=1, col=1)
    fig.add_trace(go.Bar(
        x=initial_drivers, y=initial_ratios, name="最速比率", visible=False, marker_color=initial_colors,
        text=[f"{t:.3f} s<br>{r:.3f}%" for t, r in zip(initial_times, initial_ratios)],
        textposition="inside", textangle=0, insidetextanchor="end",
        hovertemplate="%{x}: %{y:.3f}%<extra></extra>"), row=1, col=1)
    fig.add_trace(go.Table(
        visible=True, header=dict(values=["順位", "ドライバー", "タイム [s]", "最速比率 [%]"]),
        cells=dict(values=initial_cells, height=28)), row=2, col=1)
    combinations_menu = []
    for label, drivers, times, ratios, cells, colors in combinations:
        combinations_menu.append(dict(label=label, method="update", args=[
            {"x": [drivers, drivers, None], "y": [times, ratios, None],
             "marker.color": [colors, colors, None],
             "text": [[f"{t:.3f} s<br>{r:.3f}%" for t, r in zip(times, ratios)],
                      [f"{t:.3f} s<br>{r:.3f}%" for t, r in zip(times, ratios)], None],
             # Scope and metric changes update the graph and table together.
             "visible": [True, False, True],
             "cells.values": [None, None, cells]},
            {"title.text": label + ("（有効なタイムなし）" if not times else ""),
             "yaxis.autorange": False,
             "yaxis.range": _bar_range(times),
             "xaxis.categoryarray": drivers},
        ]))
    views = []
    for i, (name, axis) in enumerate((("タイム", "Time [s]"),
                                      ("最速比率", "Best time ratio [%]"))):
        views.append(dict(label=name, method="update", execute=False, args=[
            {"visible": [j == i for j in range(2)] + [True]},
            {"yaxis.title.text": axis,
             "xaxis.visible": True, "yaxis.visible": True},
        ]))
    fig.update_layout(
        title=initial_label, height=1500, margin=dict(t=160, b=40), showlegend=False,
        meta=dict(f1ExplorerKind="qualifyingBest"),
        xaxis=dict(title="Driver", categoryorder="array", categoryarray=initial_drivers),
        yaxis=dict(title="Time [s]", tickformat=".3f", range=_bar_range(initial_times)),
        updatemenus=[dict(buttons=combinations_menu, x=0, y=1.14, xanchor="left"),
                     dict(buttons=views, type="buttons", direction="right", x=0.55, y=1.14)],
    )
    return fig
