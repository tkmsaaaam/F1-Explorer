import datetime

import fastf1
# noinspection PyPackageRequirements
from opentelemetry import trace

import setup
from visualizations import weekend, run_volume, weather, race

tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("main")
def start_at(session: fastf1.core.Session) -> None | datetime.datetime:
    if session.name == 'Sprint':
        return session.event.Session3Date
    elif session.name == 'Race':
        return session.event.Session5Date
    return None


@tracer.start_as_current_span("main")
def main():
    log = setup.log()
    try:
        config = setup.load_config()
    except Exception as exception:
        log.warning(exception.args)
        return

    if config.get_session_category() != setup.SessionCategory.Race:
        log.warning(f"{config.get_session()} is not R or S. \"Session\" needs to be set to R or S.")
        return
    config.set_attribute_to_span()
    setup.fast_f1()
    try:
        session = fastf1.get_session(config.get_year(), config.get_round(), config.get_session())
    except Exception as exception:
        log.warning(exception.args)
        return
    session.load()

    start = start_at(session)
    now = datetime.datetime.now().astimezone()
    if start is not None and now < start:
        log.info(
            f"{session.event.year} Race {session.event.RoundNumber} {session.event.EventName} Race is not started.")
        return

    log.info(f"{session.event.year} Race {session.event.RoundNumber} {session.event.EventName} Race")

    weekend.plot_tyre(config.get_year(), config.get_round(), log)

    run_volume.plot_laptime(session, log)
    run_volume.plot_laptime_by_timing(session, log)
    run_volume.plot_laptime_by_lap_number(session, log)
    run_volume.plot_pit_time(session, log)

    path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}"
    race.execute(session, log, path, path, None, None, None)

    weather.execute(session, log, path)


if __name__ == "__main__":
    main()
