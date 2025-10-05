import fastf1

import setup
from visualizations import weekend, run_volume, weather, race


def main():
    config = setup.load_config()

    log = setup.log()
    if config is None:
        log.warning("no config")
        return

    if config['Session'] != 'S' or 'R':
        log.warning(f"{config['Session']} is not S or SR. \"Session\" needs to be set to S or SR.")
        return

    setup.fast_f1()
    session = fastf1.get_session(config['Year'], config['Round'], config['Session'])
    session.load(telemetry=False)

    log.info(f"{session.event.year} Race {session.event.RoundNumber} {session.event.EventName} Race")

    weekend.plot_tyre(config['Year'], config['Round'], log)

    run_volume.plot_laptime(session, log)
    run_volume.plot_laptime_by_timing(session, log)
    run_volume.plot_laptime_by_lap_number(session, log)

    path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}"
    race.execute(session, log, path, path, None, None, None)

    weather.execute(session, log, path)
