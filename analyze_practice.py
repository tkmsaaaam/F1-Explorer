import json
import logging

import fastf1

from visualizations import run_volume, long_runs, short_runs, weather, weekend

with open('./config.json', 'r', encoding='utf-8') as file:
    config = json.load(file)

fastf1.Cache.enable_cache('./cache')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",  # Log format
    handlers=[
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

if config['Session'].startswith('FP'):
    fastf1.logger.LoggingManager.debug = False
    fastf1.logger.LoggingManager.set_level(logging.WARNING)
    fastf1.logger.set_log_level(logging.WARNING)
    session = fastf1.get_session(config['Year'], config['Round'], config['Session'])
    session.load(messages=False)

    log.info(f"{session.event.year} Race {session.event['RoundNumber']} {session.event.EventName} {config['Session']}")

    weekend.plot_tyre(config['Year'], config['Round'], log)

    run_volume.plot_lap_number_by_timing(session, log)
    run_volume.plot_laptime(session, log)
    run_volume.plot_laptime_by_timing(session, log)
    run_volume.plot_laptime_by_lap_number(session, log)

    long_runs.plot_by_tyre_age_and_tyre(session, log)

    short_runs.plot_best_laptime(session, log, 'Sector1Time')
    short_runs.plot_best_laptime(session, log, 'Sector2Time')
    short_runs.plot_best_laptime(session, log, 'Sector3Time')
    short_runs.plot_best_laptime(session, log, 'LapTime')

    short_runs.plot_best_speed(session, log, 'SpeedFL')
    short_runs.plot_best_speed(session, log, 'SpeedI1')
    short_runs.plot_best_speed(session, log, 'SpeedI2')
    short_runs.plot_best_speed(session, log, 'SpeedST')

    base_path = f"./images/{session.event.year}/{session.event['RoundNumber']}_{session.event.Location}/{session.name.replace(' ', '')}"
    corners = [0] + list(
        session.get_circuit_info().corners['Distance']
    ) + [session.laps.pick_fastest().get_telemetry().add_distance()['Distance'].iloc[-1]]
    short_runs.plot_mini_segment_on_circuit(session, log, corners, 'corners')
    short_runs.compute_and_save_segment_tables_plotly(session, base_path + "/corners", corners, log)
    corner_map: dict[str: list[int]] = config["corners"]
    segments = short_runs.make_mini_segment(session, log, corner_map, config["separator"])
    short_runs.plot_mini_segment_on_circuit(session, log, segments, 'mini_segments')
    short_runs.compute_and_save_segment_tables_plotly(session, base_path + "/mini_segments", segments, log)
    short_runs.plot_flat_out(session, log)
    short_runs.plot_ideal_best(session, log)
    short_runs.plot_ideal_best_diff(session, log)
    short_runs.plot_gear_shift_on_track(session, log)
    short_runs.plot_speed_and_laptime(session, log)
    short_runs.plot_speed_distance(session, log)
    short_runs.plot_speed_distance_comparison(session, log)
    short_runs.plot_speed_on_track(session, log)
    short_runs.plot_time_distance_comparison(session, log)
    short_runs.plot_tyre_age_and_laptime(session, log)
    short_runs.plot_drs(session, log)
    short_runs.plot_brake(session, log)
    short_runs.plot_throttle(session, log)

    weather.execute(session, log, base_path)
else:
    log.warning(f"{config['Session']} is not FP")
