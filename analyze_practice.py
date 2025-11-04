import fastf1
from opentelemetry import trace

import setup
from visualizations import run_volume, long_runs, short_runs, weather, weekend

tracer = trace.get_tracer(__name__)


@tracer.start_as_current_span("main")
def main():
    config = setup.load_config()

    log = setup.log()
    if config is None:
        log.warning("no config")
        return

    if not config['Session'].startswith('FP'):
        log.warning(f"{config['Session']} is not FP.  \"Session\" needs to be set to FP.")
        return
    setup.fast_f1()
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
    corner_map = config["corners"]
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


if __name__ == "__main__":
    main()
