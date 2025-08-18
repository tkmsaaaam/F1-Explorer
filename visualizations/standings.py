import os

import fastf1.plotting
from matplotlib import pyplot as plt

season = 2025
schedule = fastf1.get_event_schedule(season, include_testing=False)

standings = {}
short_event_names = []
colors = {}

for _, event in schedule.iterrows():
    event_name, round_number = event["EventName"], event["RoundNumber"]
    short_event_names.append(event_name.replace("Grand Prix", "").strip())

    race = fastf1.get_session(season, event_name, "R")
    race.load(laps=False, telemetry=False, weather=False, messages=False)

    sprint = None
    if event["EventFormat"] == "sprint_qualifying":
        sprint = fastf1.get_session(season, event_name, "S")
        sprint.load(laps=False, telemetry=False, weather=False, messages=False)

    for _, driver_row in race.results.iterrows():
        abbreviation, race_points, race_position, driver_number = (
            driver_row["Abbreviation"],
            driver_row["Points"],
            driver_row["Position"],
            driver_row["DriverNumber"],
        )

        if driver_number not in colors:
            colors[driver_number] = race.get_driver(abbreviation).TeamColor

        sprint_points = 0
        if sprint is not None:
            driver_row = sprint.results[
                sprint.results["Abbreviation"] == abbreviation
                ]
            if not driver_row.empty:
                sprint_points = driver_row["Points"].values[0]

        if driver_number not in standings:
            standings[driver_number] = [0 for i in range(0, round_number - 1)]
        standings[driver_number].append(race_points + sprint_points)
    for k, v in standings.items():
        if len(v) != round_number:
            v.append(0)

fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
for k, v in standings.items():
    x = [i for i in range(1, len(v) + 1)]
    y = []
    total = 0
    for n in v:
        total += n
        y.append(total)
    ax.plot(x, y, label=k, color='#' + colors.get(k, '000000'), linewidth=1)
ax.legend(fontsize='small')
ax.grid(True)
output_path = f"../images/{season}/standings.png"
os.makedirs(os.path.dirname(output_path), exist_ok=True)
fig.savefig(output_path, bbox_inches='tight')
plt.close(fig)
print(f"Saved plot to {output_path}")
fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
for k, v in standings.items():
    x = [i for i in range(1, len(v) + 1)]
    ax.plot(x, v, label=k, color='#' + colors.get(k, '000000'), linewidth=1)
ax.legend(fontsize='small')
ax.grid(True)
output_path = f"../images/{season}/results.png"
os.makedirs(os.path.dirname(output_path), exist_ok=True)
fig.savefig(output_path, bbox_inches='tight')
plt.close(fig)
print(f"Saved plot to {output_path}")
