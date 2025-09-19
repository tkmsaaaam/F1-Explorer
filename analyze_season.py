import datetime
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

drivers = []
standings = {}
colors = {}

# {"round_number": {"name": "Japan", "sprint": true, "sprint_position": {"abbreviation": 1},"grid_position": {"abbreviation": 1}, "position": {"abbreviation": 1}}}
results = {}

schedule = schedule.sort_values(by='RoundNumber')
for _, event in schedule.iterrows():
    event_name, round_number = event.EventName, event.RoundNumber

    if round_number not in results:
        results[round_number] = {}

    gp = results[round_number]
    gp["name"] = event_name
    gp["date"] = event.EventDate

    race = fastf1.get_session(season, event_name, "R")
    race.load(laps=False, telemetry=False, weather=False, messages=False)

    sprint = None
    if event["EventFormat"] == "sprint_qualifying":
        sprint = fastf1.get_session(season, event_name, "S")
        sprint.load(laps=False, telemetry=False, weather=False, messages=False)
        gp["sprint"] = True
        if "sprint_position" not in gp:
            gp["sprint_position"] = {}
        if "sprint_point" not in gp:
            gp["sprint_point"] = {}
        for _, driver_row in sprint.results.iterrows():
            gp["sprint_position"][driver_row.Abbreviation] = driver_row.Position
            gp["sprint_point"][driver_row.Abbreviation] = driver_row.Points
    else:
        gp["sprint"] = False

    if "grid_position" not in gp:
        gp["grid_position"] = {}
    if "position" not in gp:
        gp["position"] = {}
    if "point" not in gp:
        gp["point"] = {}
    for _, driver_row in race.results.iterrows():
        abbreviation = driver_row.Abbreviation
        gp["grid_position"][abbreviation] = driver_row.GridPosition
        gp["position"][abbreviation] = driver_row.Position
        gp["point"][abbreviation] = driver_row.Points

        if abbreviation not in drivers:
            drivers.append(abbreviation)
        if abbreviation not in colors:
            colors[abbreviation] = race.get_driver(abbreviation).TeamColor

now = datetime.datetime.now()
latest = 0

for i in range(1, 53):
    if now < results[i]["date"]:
        break
    latest = i

base_dir = f"./images/{season}"

fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
champion_points = []
for v in drivers:
    y = []
    for i in range(1, latest + 1):
        sum_point = results[i]["point"].get(v, 0)
        if results[i]["sprint"]:
            sum_point += results[i]["sprint_point"].get(v, 0)
        y.append(sum_point)
    if sum(y) > sum(champion_points):
        champion_points = y
    ax.plot([i for i in range(1, latest + 1)], [sum(y[:i + 1]) for i in range(len(y))], label=v,
            color='#' + colors.get(v, '000000'), linewidth=1)
ax.legend(fontsize='small')
ax.grid(True)
output_path = f"{base_dir}/standings.png"
os.makedirs(os.path.dirname(output_path), exist_ok=True)
fig.savefig(output_path, bbox_inches='tight')
plt.close(fig)
log.info(f"Saved plot to {output_path}")

fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
for v in drivers:
    y = []
    for i in range(1, latest + 1):
        p = results[i]["point"].get(v, 0)
        if results[i]["sprint"]:
            p += results[i]["sprint_point"].get(v, 0)
        y.append(p)
    ax.plot([i for i in range(1, latest + 1)], y, label=v, color='#' + colors.get(v, '000000'), linewidth=1)
ax.legend(fontsize='small')
ax.grid(True)
output_path = f"{base_dir}/results.png"
os.makedirs(os.path.dirname(output_path), exist_ok=True)
fig.savefig(output_path, bbox_inches='tight')
plt.close(fig)
log.info(f"Saved plot to {output_path}")

fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout="tight")
for v in drivers:
    y = []
    for i in range(1, latest + 1):
        p = results[i]["point"].get(v, 0)
        if results[i]["sprint"]:
            p += results[i]["sprint_point"].get(v, 0)
        y.append(p)
    diff = [a - b for a, b in zip(accumulate(y), accumulate(champion_points))]
    ax.plot([i for i in range(1, latest + 1)], diff, label=v, color="#" + colors.get(v, "000000"), linewidth=1)
ax.legend(fontsize='small')
ax.grid(True)
output_path = f"{base_dir}/diffs.png"
os.makedirs(os.path.dirname(output_path), exist_ok=True)
fig.savefig(output_path, bbox_inches='tight')
plt.close(fig)
log.info(f"Saved plot to {output_path}")

fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
x = [i for i in range(1, latest + 1)]
for v in drivers:
    y = [results[i]["grid_position"].get(v, 21) for i in range(1, latest + 1)]
    ax.plot(x, y, label=v, color='#' + colors.get(v, '000000'), linewidth=1)
ax.legend(fontsize='small')
ax.grid(True)
ax.invert_yaxis()
output_path = f"{base_dir}/grid_positions.png"
os.makedirs(os.path.dirname(output_path), exist_ok=True)
fig.savefig(output_path, bbox_inches='tight')
plt.close(fig)
log.info(f"Saved plot to {output_path}")

fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
for v in drivers:
    y = [results[i]["grid_position"].get(v, 21) - results[i]["position"].get(v, 21) for i in range(1, latest + 1)]
    ax.plot(x, y, label=v, color='#' + colors.get(v, '000000'), linewidth=1)
ax.legend(fontsize='small')
ax.grid(True)
output_path = f"{base_dir}/grid_to_results.png"
os.makedirs(os.path.dirname(output_path), exist_ok=True)
fig.savefig(output_path, bbox_inches='tight')
plt.close(fig)
log.info(f"Saved plot to {output_path}")
