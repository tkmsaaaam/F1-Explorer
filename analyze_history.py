import datetime
import json
import os
import time

import fastf1
import plotly.graph_objects as go
# noinspection PyPackageRequirements
from opentelemetry import trace

import setup


def load_gp_data() -> dict:
    """Load GP data from JSON cache file."""
    gp_data_path = "./cache/gp_data.json"
    if os.path.exists(gp_data_path):
        try:
            with open(gp_data_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading gp_data.json: {e}")
            return {}
    return {}


def save_gp_data(gp_data: dict) -> None:
    """Save GP data to JSON cache file."""
    gp_data_path = "./cache/gp_data.json"
    try:
        with open(gp_data_path, 'w') as f:
            json.dump(gp_data, f, indent=2)
    except Exception as e:
        print(f"Error saving gp_data.json: {e}")


def get_name(v: fastf1.core.DriverResult) -> str:
    if getattr(v, 'FullName', 'nan') == 'nan':
        return ''
    return v.FullName


def get_team(v: fastf1.core.DriverResult) -> str:
    if getattr(v, 'TeamName', 'nan') == 'nan':
        return ''
    return v.TeamName


def get_color(v: fastf1.core.DriverResult) -> str:
    if getattr(v, 'TeamColor', 'nan') == 'nan':
        return '808080'
    return v.TeamColor


tracer = trace.get_tracer(__name__)


@tracer.start_as_current_span("main")
def __main():
    log = setup.log()
    setup.fast_f1()
    end_year = datetime.datetime.now().year - 1
    __save_cache(log, False, end_year=end_year, interval=1)
    __save_winners(log, end_year=end_year)
    __save_count(log, end_year=end_year)
    __save_team_count(log, end_year=end_year)


def __save_cache(log, force_reload: bool = False, start_year: int = 2000,
                 end_year: int = datetime.datetime.now().year - 1, interval: int = 1):
    max_round = 0
    gp_data = load_gp_data()
    for yr in range(start_year, end_year + 1):
        try:
            sched = fastf1.get_event_schedule(yr, include_testing=False).sort_values(by='RoundNumber')
        except Exception:
            continue
        for _, event in sched.iterrows():
            rnd = event.RoundNumber
            max_round: int = max(max_round, rnd)
            if not force_reload and str(yr) in gp_data and str(rnd) in gp_data[str(yr)]:
                log.info(f"Loading winner from cache for {yr} Round {rnd} {event.EventName}")
                continue
            try:
                log.info(f"collecting winners for {yr} {event.EventName}")
                race = fastf1.get_session(yr, event.EventName, "R")
                race.load(laps=False, telemetry=False, weather=False, messages=False)
                if len(race.results) <= 0:
                    continue
                winner_row = race.results.iloc[0]
                if str(yr) not in gp_data:
                    gp_data[str(yr)] = {}
                data = {
                    "gp_name": event.EventName,
                    "abbreviation": winner_row.Abbreviation,
                    "winner": get_name(winner_row),
                    "team": get_team(winner_row),
                    "color": '#' + get_color(winner_row)
                }
                gp_data[str(yr)][str(rnd)] = data
                log.info(data)
                save_gp_data(gp_data)
                time.sleep(interval)
            except Exception as exc:
                log.warning(f"could not load winner for {yr} {event.EventName}: {exc}")
                continue


def __save_winners(log, start_year: int = 2000, end_year: int = datetime.datetime.now().year - 1):
    gp_data = load_gp_data()
    season_data: dict[int, dict[int, dict[str, str]]] = {}
    max_round = 0
    for yr in range(start_year, end_year + 1):
        try:
            sched = fastf1.get_event_schedule(yr, include_testing=False).sort_values(by='RoundNumber')
        except Exception:
            continue
        season_data[yr] = {}
        yr_str = str(yr)
        for _, event in sched.iterrows():
            rnd = event.RoundNumber
            rnd_str = str(rnd)
            if yr_str not in gp_data or rnd_str not in gp_data[yr_str]:
                continue
            max_round = max(max_round, rnd)
            log.info(f"Loading winner from cache for {yr} Round {rnd} {event.EventName}")
            cached = gp_data[yr_str][rnd_str]
            color = cached.get("color", "white")
            if color == '#':
                color = 'lightgrey'
            season_data[yr][rnd] = {
                "winner": cached.get("abbreviation", ""),
                "gp_name": cached.get("gp_name", "").replace('Grand Prix', '').strip(),
                "color": color
            }
    if not season_data or all(not rounds for rounds in season_data.values()):
        log.warning("no winner data was collected")
        return
    years = sorted(season_data.keys())
    rounds = list(range(1, max_round + 1))
    headers = ["Round"] + [str(y) for y in years]
    cell_values = [["Wins"] + rounds]
    color_matrix = [["lightgrey"] * (max_round + 1)]
    for yr in years:
        counts = {}
        for rnd_data in season_data[yr].values():
            if abbr := rnd_data["winner"]:
                counts[abbr] = counts.get(abbr, 0) + 1
        win_list_str = "<br>".join(
            f"{abbr}: {count}" for abbr, count in sorted(counts.items(), key=lambda x: x[1], reverse=True))
        cols = [win_list_str]
        colors = ['lightgrey']

        for r in rounds:
            data = season_data[yr].get(r, {})
            winner = data.get("winner", "")
            gp_name = data.get("gp_name", "")
            cols.append(f"{winner} {gp_name}".strip())
            colors.append(data.get("color", "white"))

        cell_values.append(cols)
        color_matrix.append(colors)

    fig = go.Figure(data=[go.Table(
        header={"values": headers, "fill_color": "lightgrey", "align": "center"},
        cells={"values": cell_values, "fill_color": color_matrix, "align": "center"}
    )], layout=go.Layout(autosize=True, margin=go.layout.Margin(autoexpand=True)))

    output_path = f"./images/winners-{start_year}-{end_year}/winners.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.write_image(output_path, width=1920, height=2160)
    log.info(f"Saved winners table to {output_path}")


def __save_count(log, start_year: int = 2000, end_year: int = datetime.datetime.now().year - 1):
    gp_data = load_gp_data()
    w: dict[str, dict[int, int]] = {}  # {winner: {year: count}}
    for year, season_winners in gp_data.items():
        y = int(year)
        for gp in season_winners.values():
            winner = gp.get("winner")
            w.setdefault(winner, {}).setdefault(y, 0)
            w[winner][y] += 1

    all_years = sorted({y for yd in w.values() for y in yd})
    driver_totals = sorted(
        [(driver, sum(yd.values()), yd) for driver, yd in w.items()],
        key=lambda x: x[1],
        reverse=True,
    )
    drivers_col = [d for d, _, _ in driver_totals]
    totals_col = [t for _, t, _ in driver_totals]
    years_cols = [[yd.get(y, 0) for _, _, yd in driver_totals] for y in all_years]
    cell_values = [drivers_col, totals_col] + years_cols
    headers = ["Driver", "Total"] + [str(y) for y in all_years]
    num_rows = len(drivers_col)
    row_colors = ["#ffffff" if i % 2 == 0 else "#f9f9f9" for i in range(num_rows)]
    color_matrix = [row_colors for _ in range(len(headers))]
    fig = go.Figure(
        data=[
            go.Table(
                header={"values": headers, "fill_color": "lightgrey", "align": "center"},
                cells={"values": cell_values, "fill_color": color_matrix, "align": "center"},
            )
        ],
        layout=go.Layout(autosize=True, margin=go.layout.Margin(autoexpand=True)),
    )
    base_dir = f"./images/winners-{start_year}-{end_year}"
    output_path = f"{base_dir}/count.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.write_image(output_path, width=1920, height=2160)
    log.info(f"Saved winners table to {output_path}")


def __save_team_count(log, start_year: int = 2000, end_year: int = datetime.datetime.now().year - 1):
    gp_data = load_gp_data()
    w: dict[str, dict[int, int]] = {}  # {winner: {year: count}}
    for year, season_winners in gp_data.items():
        y = int(year)
        for gp in season_winners.values():
            winner = gp.get("team")
            w.setdefault(winner, {}).setdefault(y, 0)
            w[winner][y] += 1

    all_years = sorted({y for yd in w.values() for y in yd})
    driver_totals = sorted(
        [(driver, sum(yd.values()), yd) for driver, yd in w.items()],
        key=lambda x: x[1],
        reverse=True,
    )
    drivers_col = [d for d, _, _ in driver_totals]
    totals_col = [t for _, t, _ in driver_totals]
    years_cols = [[yd.get(y, 0) for _, _, yd in driver_totals] for y in all_years]
    cell_values = [drivers_col, totals_col] + years_cols
    headers = ["Team", "Total"] + [str(y) for y in all_years]
    num_rows = len(drivers_col)
    row_colors = ["#ffffff" if i % 2 == 0 else "#f9f9f9" for i in range(num_rows)]
    color_matrix = [row_colors for _ in range(len(headers))]
    fig = go.Figure(
        data=[
            go.Table(
                header={"values": headers, "fill_color": "lightgrey", "align": "center"},
                cells={"values": cell_values, "fill_color": color_matrix, "align": "center"},
            )
        ],
        layout=go.Layout(autosize=True, margin=go.layout.Margin(autoexpand=True)),
    )
    base_dir = f"./images/winners-{start_year}-{end_year}"
    output_path = f"{base_dir}/team_count.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.write_image(output_path, width=1920, height=2160)
    log.info(f"Saved constructors table to {output_path}")


if __name__ == "__main__":
    __main()
