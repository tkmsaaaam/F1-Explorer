import datetime

import fastf1
# noinspection PyPackageRequirements
from opentelemetry import trace

import setup
from visualizations import run_volume, long_runs, short_runs, weather, weekend

tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("start_at")
def start_at(session: fastf1.core.Session) -> None | datetime.datetime:
    if session.name == 'Practice 1':
        return session.event.Sessio13Date
    elif session.name == 'Practice 2':
        return session.event.Session2Date
    elif session.name == 'Practice 3':
        return session.event.Session3Date
    return None


@tracer.start_as_current_span("main")
def __main():
    log = setup.log()
    try:
        config = setup.load_config()
    except Exception as exception:
        log.warning(exception.args)
        return

    if config.get_session_category() != setup.SessionCategory.FreePractice:
        log.warning(f"{config.get_session()} is not FP. \"Session\" needs to be set to FP.")
        return
    config.set_attribute_to_span()
    setup.fast_f1()
    try:
        session = fastf1.get_session(config.get_year(), config.get_round(), config.get_session())
    except Exception as exception:
        log.warning(exception.args)
        return
    session.load(messages=False)

    start = start_at(session)
    now = datetime.datetime.now().astimezone()
    if start is not None and now < start:
        log.info(
            f"{session.event.year} Race {session.event.RoundNumber} {session.event.EventName} Practice is not started.")
        return

    log.info(
        f"{session.event.year} Race {session.event['RoundNumber']} {session.event.EventName} {config.get_session()}")

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
    # noinspection SpellCheckingInspection
    short_runs.plot_best_speed(session, log, 'SpeedI1')
    # noinspection SpellCheckingInspection
    short_runs.plot_best_speed(session, log, 'SpeedI2')
    short_runs.plot_best_speed(session, log, 'SpeedST')

    circuit = session.get_circuit_info()
    fastest = session.laps.pick_fastest()

    if circuit is None:
        log.info("circuit info is None")
        return
    if fastest is None:
        log.info("fastest info is None")
        return

    base_path = f"./images/{session.event.year}/{session.event['RoundNumber']}_{session.event.Location}/{session.name.replace(' ', '')}"
    corners = [0] + list(circuit.corners['Distance']) + [fastest.get_telemetry().add_distance()['Distance'].iloc[-1]]
    short_runs.plot_mini_segment_on_circuit(session, log, corners, 'corners')
    short_runs.compute_and_save_segment_tables_plotly(session, base_path + "/corners", corners, log)
    corner_map = config.get_corners()
    segments = short_runs.make_mini_segment(session, log, corner_map, config.get_separator())
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

    weekend.plot_tyre(config.get_year(), config.get_round(), log)


if __name__ == "__main__":
    __main()
