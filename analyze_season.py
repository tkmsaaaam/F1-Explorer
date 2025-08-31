import logging
import os
from itertools import accumulate

import fastf1.plotting
from matplotlib import pyplot as plt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

season = 2025
schedule = fastf1.get_event_schedule(season, include_testing=False)

standings = {}
colors = {}

for _, event in schedule.iterrows():
    event_name, round_number = event["EventName"], event["RoundNumber"]

    race = fastf1.get_session(season, event_name, "R")
    race.load(laps=False, telemetry=False, weather=False, messages=False)

    sprint = None
    if event["EventFormat"] == "sprint_qualifying":
        sprint = fastf1.get_session(season, event_name, "S")
        sprint.load(laps=False, telemetry=False, weather=False, messages=False)

    for _, driver_row in race.results.iterrows():
        driver_number, race_points, abbreviation = (
            driver_row["DriverNumber"],
            driver_row["Points"],
            driver_row["Abbreviation"],
        )

        if abbreviation not in colors:
            colors[abbreviation] = race.get_driver(abbreviation).TeamColor

        sprint_points = 0
        if sprint is not None:
            sprint_points = sprint.results.Points.get(driver_number, 0)

        if abbreviation not in standings:
            standings[abbreviation] = [0] * (round_number - 1)
        standings[abbreviation].append(race_points + sprint_points)
    for v in standings.values():
        v.extend([0] * (round_number - len(v)))

fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
for k, v in standings.items():
    ax.plot([i for i in range(1, len(v) + 1)], [sum(v[:i + 1]) for i in range(len(v))], label=k,
            color='#' + colors.get(k, '000000'), linewidth=1)
ax.legend(fontsize='small')
ax.grid(True)
output_path = f"./images/{season}/standings.png"
os.makedirs(os.path.dirname(output_path), exist_ok=True)
fig.savefig(output_path, bbox_inches='tight')
plt.close(fig)
log.info(f"Saved plot to {output_path}")
fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
for k, v in standings.items():
    x = [i for i in range(1, len(v) + 1)]
    ax.plot(x, v, label=k, color='#' + colors.get(k, '000000'), linewidth=1)
ax.legend(fontsize='small')
ax.grid(True)
output_path = f"./images/{season}/results.png"
os.makedirs(os.path.dirname(output_path), exist_ok=True)
fig.savefig(output_path, bbox_inches='tight')
plt.close(fig)
log.info(f"Saved plot to {output_path}")

champion_number, champion_point = max(
    ((k, sum(v)) for k, v in standings.items()),
    key=lambda item: item[1]
)
fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout="tight")
champion_sum = list(accumulate(standings[champion_number]))
for k, v in standings.items():
    if k == champion_number:
        continue
    x = range(1, len(v) + 1)
    diff = [a - b for a, b in zip(accumulate(v), champion_sum)]
    ax.plot(x, diff, label=k, color="#" + colors.get(k, "000000"), linewidth=1)
ax.legend(fontsize='small')
ax.grid(True)
output_path = f"./images/{season}/diffs.png"
os.makedirs(os.path.dirname(output_path), exist_ok=True)
fig.savefig(output_path, bbox_inches='tight')
plt.close(fig)
log.info(f"Saved plot to {output_path}")
