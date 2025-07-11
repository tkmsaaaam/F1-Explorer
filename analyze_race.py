import json
import logging

import fastf1

from visualizations import weekend, run_volume, weather, race

with open('./config.json', 'r', encoding='utf-8') as file:
    config = json.load(file)

fastf1.Cache.enable_cache('./cache')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

if config['Session'] == 'SR' or config['Session'] == 'R':
    session = fastf1.get_session(config['Year'], config['Round'], 'Race')
    session.load(telemetry=False)

    log.info(f"{session.event.year} Race {session.event.RoundNumber} {session.event.EventName} Race")

    drivers = list(map(int, session.drivers))

    weekend.plot_tyre(config['Year'], config['Round'], log)

    run_volume.plot_lap_number_by_timing(session, log)
    run_volume.plot_laptime(session, log)
    run_volume.plot_laptime_by_timing(session, log)
    run_volume.plot_laptime_by_lap_number(session, log)

    path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}"
    race.execute(session, log, path, path, None, None, None)

    weather.execute(session, log, path)
else:
    log.warning(f"{config['Session']} is not R or SR")
