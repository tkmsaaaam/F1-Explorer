import json
import logging

import fastf1.plotting

from visualizations import run_volume, short_runs, weather, weekend

with open('./config.json', 'r', encoding='utf-8') as file:
    config = json.load(file)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

if config['Session'] == 'Q' or config['Session'] == 'SQ':
    fastf1.Cache.enable_cache('./cache')
    session = fastf1.get_session(config['Year'], config['Round'], config['Session'])
    session.load()

    log.info(f"{config['Year']} Race {config['Round']} {session.event.EventName} {config['Session']}")

    drivers = list(map(int, session.drivers))

    weekend.plot_tyre(config['Year'], config['Round'], log)

    run_volume.plot_lap_number_by_timing(session, log)
    run_volume.plot_laptime(session, log)
    run_volume.plot_laptime_by_timing(session, log)
    run_volume.plot_laptime_by_lap_number(session, log)

    short_runs.plot_best_laptime(session, drivers, log, 'Sector1Time')
    short_runs.plot_best_laptime(session, drivers, log, 'Sector2Time')
    short_runs.plot_best_laptime(session, drivers, log, 'Sector3Time')
    short_runs.plot_best_laptime(session, drivers, log, 'LapTime')

    short_runs.plot_best_speed(session, drivers, log, 'SpeedFL')
    short_runs.plot_best_speed(session, drivers, log, 'SpeedI1')
    short_runs.plot_best_speed(session, drivers, log, 'SpeedI2')
    short_runs.plot_best_speed(session, drivers, log, 'SpeedST')

    n = [1, 4, 16, 81]
    short_runs.compute_and_save_corner_tables_plotly(session,
                                                     f"./images/{session.event.year}/{session.event['RoundNumber']}_{session.event.Location}/{session.name.replace(' ', '')}/corner_table",
                                                     log)

    short_runs.plot_flat_out(session, log)
    short_runs.plot_ideal_best(session, drivers, log)
    short_runs.plot_ideal_best_diff(session, drivers, log)
    short_runs.plot_gear_shift_on_track(session, session.drivers, log)
    short_runs.plot_speed_and_laptime(session, drivers, log)
    short_runs.plot_speed_distance(session, session.drivers, session.get_circuit_info(), log)
    short_runs.plot_speed_distance_comparison(session, session.drivers, session.get_circuit_info(), log)
    short_runs.plot_speed_on_track(session, session.drivers, log)
    short_runs.plot_tyre_age_and_laptime(session, drivers, log)
    short_runs.plot_drs(session, log)
    short_runs.plot_brake(session, log)
    short_runs.plot_throttle(session, log)
    short_runs.plot_telemetry(session, log,
                              n,
                              key='drs',
                              label='DRS',
                              value_func=lambda data: data.DRS.astype(float)
                              )
    short_runs.plot_telemetry(session, log,
                              n,
                              key='brake',
                              label='Brake',
                              value_func=lambda data: data.Brake.astype(float)
                              )
    short_runs.plot_telemetry(session, log,
                              n,
                              key='throttle',
                              label='Throttle [%]',
                              value_func=lambda data: data.Throttle
                              )

    weather.execute(session, log,
                    f"./images/{session.event.year}/{session.event['RoundNumber']}_{session.event.Location}/{session.name.replace(' ', '')}")
