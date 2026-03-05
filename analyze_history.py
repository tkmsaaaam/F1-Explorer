import datetime
import json
import os
import time

import fastf1
from opentelemetry import trace
from plotly import graph_objects

import setup


def load_gp_data() -> dict:
    """Load GP data from JSON cache file."""
    gp_data_path = "./gp_data.json"
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
    try:
        config = setup.load_config()
    except Exception as exception:
        log.warning(exception.args)
        return
    config.set_attribute_to_span()
    setup.fast_f1()

    # ----------------------------------------------------------------------
    # save winner table from 2000 through current year
    # ----------------------------------------------------------------------
    __save_winners(log)


def __save_winners(log, start_year: int = 2000):
    """Build and persist a table of race winners from ``start_year`` through this year.

    The table is oriented such that the columns represent years and the rows
    represent the round number within that season (race count).  Each cell
    contains the abbreviation of the driver who won the corresponding race.  An
    image is written under ``./images/winners-<start>-<end>/winners.png``.
    """

    end_year = datetime.datetime.now().year - 1
    winners: dict[int, dict[int, str]] = {}
    gp_names: dict[int, dict[int, str]] = {}
    color_map: dict[int, dict[int, str]] = {}
    max_round = 0

    interval = 1

    # Load GP data from JSON cache
    gp_data = load_gp_data()

    for yr in range(start_year, end_year + 1):
        try:
            sched = fastf1.get_event_schedule(yr, include_testing=False).sort_values(by='RoundNumber')
        except Exception:
            # some very early years may not be available via fastf1
            continue
        winners[yr] = {}
        gp_names[yr] = {}
        color_map[yr] = {}
        for _, event in sched.iterrows():
            rnd = event.RoundNumber
            max_round = max(max_round, rnd)
            # Check if data exists in JSON cache
            if str(yr) in gp_data and str(rnd) in gp_data[str(yr)]:
                log.info(f"Loading winner from cache for {yr} Round {rnd} {event.EventName}")
                cached_data = gp_data[str(yr)][str(rnd)]
                winners[yr][rnd] = cached_data.get("winner", "")
                gp_names[yr][rnd] = cached_data.get("gp_name", "")
                # You would need to compute color from the abbreviation or store it in JSON
                color_map[yr][rnd] = cached_data.get("color", "white")
            else:
                try:
                    log.info(f"collecting winners for {yr} {event.EventName}")
                    race = fastf1.get_session(yr, event.EventName, "R")
                    race.load(laps=False, telemetry=False, weather=False, messages=False)
                    if len(race.results) > 0:
                        winner_row = race.results.iloc[0]
                        winner_abbr = winner_row.Abbreviation
                        color_hex = '#' + get_color(winner_row)
                        winners[yr][rnd] = winner_abbr
                        gp_names[yr][rnd] = event.EventName
                        color_map[yr][rnd] = color_hex

                        # Save to JSON cache
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
    # first column is round numbers
    cell_values = [rounds]

    # color matrix: grey for the round column, and use the precomputed
    # team colour for each winner cell (defaulting to white when missing).
    color_matrix = [["lightgrey"] * (len(years) + 1)]

    for yr in years:
        cols = []
        colors = []
        for r in rounds:
            winner = winners[yr].get(r, "")
            gp_name = gp_names[yr].get(r, "").replace('Grand Prix', '').strip()
            color = color_map.get(yr, {}).get(r, "white")
            if color == '#':
                color = 'lightgrey'
            # Combine winner and GP name with space
            cell_text = f"{winner} {gp_name}".strip()
            cols.append(cell_text)
            colors.append(color)
        cell_values.append(cols)
        color_matrix.append(colors)

    headers = ["Round"] + [str(y) for y in years]
    fig = graph_objects.Figure(data=[graph_objects.Table(
        header={"values": headers, "fill_color": "lightgrey", "align": "center"},
        cells={"values": cell_values, "fill_color": color_matrix, "align": "center"}
    )], layout={"autosize": True, "margin": {"autoexpand": True}})

    base_dir = f"./images/winners-{start_year}-{end_year}"
    output_path = f"{base_dir}/winners.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.write_image(output_path, width=1920, height=2160)
    log.info(f"Saved winners table to {output_path}")


if __name__ == "__main__":
    __main()
