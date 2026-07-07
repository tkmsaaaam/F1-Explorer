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
    gp_data_path = "./gp_data.json"
    try:
        with open(gp_data_path, 'w') as f:
            json.dump(gp_data, f, indent=2)
    except Exception as e:
        print(f"Error saving gp_data.json: {e}")


def get_color(v: fastf1.core.DriverResult) -> str:
    """Return hex color string for a driver result.

    Copied from :mod:`analyze_season` so that the winners table cells can be
    shaded by team color.
    """
    if getattr(v, 'TeamColor', 'nan') == 'nan':
        return '808080'
    return v.TeamColor


tracer = trace.get_tracer(__name__)


@tracer.start_as_current_span("main")
def __main():
    log = setup.log()
    setup.fast_f1()
    __save_winners(log)


def __save_winners(log, start_year: int = 2000):
    end_year = datetime.datetime.now().year - 1
    winners: dict[int, dict[int, str]] = {}  # {year: {round: driver}}
    gp_names: dict[int, dict[int, str]] = {}  # {year: {round: GP}}
    color_map: dict[int, dict[int, str]] = {}  # {year: {round: team_color}}
    max_round = 0

    interval = 1

    gp_data = load_gp_data()

    for yr in range(start_year, end_year + 1):
        try:
            sched = fastf1.get_event_schedule(yr, include_testing=False).sort_values(by='RoundNumber')
        except Exception:
            continue
        winners[yr] = {}
        gp_names[yr] = {}
        color_map[yr] = {}
        for _, event in sched.iterrows():
            rnd = event.RoundNumber
            max_round: int = max(max_round, rnd)
            if str(yr) in gp_data and str(rnd) in gp_data[str(yr)]:
                log.info(f"Loading winner from cache for {yr} Round {rnd} {event.EventName}")
                cached_data = gp_data[str(yr)][str(rnd)]
                winners[yr][rnd] = cached_data.get("winner", "")
                gp_names[yr][rnd] = cached_data.get("gp_name", "")
                color_map[yr][rnd] = cached_data.get("color", "white")
                continue
            try:
                log.info(f"collecting winners for {yr} {event.EventName}")
                race = fastf1.get_session(yr, event.EventName, "R", backend="ergast")
                race.load(laps=False, telemetry=False, weather=False, messages=False)
                if len(race.results) > 0:
                    winner_row = race.results.iloc[0]
                    winner_abbr = winner_row.Abbreviation
                    color_hex = '#' + get_color(winner_row)
                    winners[yr][rnd] = winner_abbr
                    gp_names[yr][rnd] = event.EventName
                    color_map[yr][rnd] = color_hex

                    if str(yr) not in gp_data:
                        gp_data[str(yr)] = {}
                    gp_data[str(yr)][str(rnd)] = {
                        "gp_name": event.EventName,
                        "winner": winner_abbr,
                        "color": color_hex
                    }
                    save_gp_data(gp_data)
                else:
                    winners[yr][rnd] = ""
                    gp_names[yr][rnd] = ""
                    color_map[yr][rnd] = "white"
                time.sleep(interval)
            except Exception as exc:
                log.warning(f"could not load winner for {yr} {event.EventName}: {exc}")
                winners[yr][rnd] = ""
                color_map[yr][rnd] = "white"
                return

    if not winners:
        log.warning("no winner data was collected")
        return

    years = sorted(winners.keys())
    rounds = list(range(1, max_round + 1))
    cell_values = [rounds]
    color_matrix = [["lightgrey"] * (len(years) + 1)]

    for yr in years:
        winner_counts = {}
        for rnd in winners[yr]:
            abbr = winners[yr][rnd]
            if abbr:
                winner_counts[abbr] = winner_counts.get(abbr, 0) + 1
        sorted_winners = sorted(winner_counts.items(), key=lambda x: x[1], reverse=True)
        win_list = [f"{abbr}: {count}" for abbr, count in sorted_winners]
        win_list_str = "<br>".join(win_list)

        cols = []
        colors = []
        for r in rounds:
            winner = winners[yr].get(r, "")
            gp_name = gp_names[yr].get(r, "").replace('Grand Prix', '').strip()
            color = color_map.get(yr, {}).get(r, "white")
            if color == '#':
                color = 'lightgrey'
            cell_text = f"{winner} {gp_name}".strip()
            cols.append(cell_text)
            colors.append(color)
        cols.insert(0, win_list_str)
        colors.insert(0, 'lightgrey')
        cell_values.append(cols)
        color_matrix.append(colors)

    cell_values[0].insert(0, "Wins")
    color_matrix[0].insert(0, "lightgrey")

    headers = ["Round"] + [str(y) for y in years]
    fig = go.Figure(data=[go.Table(
        header={"values": headers, "fill_color": "lightgrey", "align": "center"},
        cells={"values": cell_values, "fill_color": color_matrix, "align": "center"}
    )], layout=go.Layout(autosize=True, margin=go.layout.Margin(autoexpand=True)))

    base_dir = f"./images/winners-{start_year}-{end_year}"
    output_path = f"{base_dir}/winners.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.write_image(output_path, width=1920, height=2160)
    log.info(f"Saved winners table to {output_path}")


def __save_count(log, start_year: int = 2000):
    end_year = datetime.datetime.now().year - 1
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


if __name__ == "__main__":
    __main()
