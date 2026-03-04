import datetime
import os
import time

import fastf1
from opentelemetry import trace
from plotly import graph_objects


def get_color(v: fastf1.core.DriverResult) -> str:
    """Return hex color string for a driver result.

    Copied from :mod:`analyze_season` so that the winners table cells can be
    shaded by team color.
    """
    if getattr(v, 'TeamColor', 'nan') == 'nan':
        return '808080'
    return v.TeamColor


import setup

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

    end_year = datetime.datetime.now().year
    winners: dict[int, dict[int, str]] = {}
    color_map: dict[int, dict[int, str]] = {}
    max_round = 0

    for yr in range(start_year, end_year + 1):
        try:
            sched = fastf1.get_event_schedule(yr, include_testing=False).sort_values(by='RoundNumber')
        except Exception:
            # some very early years may not be available via fastf1
            continue
        winners[yr] = {}
        color_map[yr] = {}
        for _, event in sched.iterrows():
            rnd = event.RoundNumber
            max_round = max(max_round, rnd)
            try:
                log.info(f"collecting winners for {yr} {event.EventName}")
                race = fastf1.get_session(yr, event.EventName, "R")
                race.load(laps=False, telemetry=False, weather=False, messages=False)
                if len(race.results) > 0:
                    winner_row = race.results.iloc[0]
                    winners[yr][rnd] = winner_row.Abbreviation
                    color_map[yr][rnd] = '#' + get_color(winner_row)
                else:
                    winners[yr][rnd] = ""
                    color_map[yr][rnd] = "white"
                time.sleep(3)
            except Exception as exc:
                log.warning(f"could not load winner for {yr} {event.EventName}: {exc}")
                winners[yr][rnd] = ""
                color_map[yr][rnd] = "white"
                time.sleep(3)

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
            cols.append(winners[yr].get(r, ""))
            colors.append(color_map.get(yr, {}).get(r, "white"))
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
