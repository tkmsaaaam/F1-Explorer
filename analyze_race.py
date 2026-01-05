import fastf1
from opentelemetry import trace

import setup
from visualizations import weekend, run_volume, weather, race

tracer = trace.get_tracer(__name__)


@tracer.start_as_current_span("main")
def main():
    config = setup.load_config()

    log = setup.log()
    if config is None:
        log.warning("no config")
        return

    if config.get_session() != 'R' and 'SR':
        log.warning(f"{config.get_session()} is not R or SR. \"Session\" needs to be set to S or SR.")
        return
    trace.get_current_span().set_attributes(
        {"year": config.get_year(), "round": config.get_round(), "session": config.get_session()})
    setup.fast_f1()
    session = fastf1.get_session(config.get_year(), config.get_round(), config.get_session())
    session.load(telemetry=False)

    log.info(f"{session.event.year} Race {session.event.RoundNumber} {session.event.EventName} Race")

    weekend.plot_tyre(config.get_year(), config.get_round(), log)

    run_volume.plot_laptime(session, log)
    run_volume.plot_laptime_by_timing(session, log)
    run_volume.plot_laptime_by_lap_number(session, log)

    path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}"
    race.execute(session, log, path, path, None, None, None)

    weather.execute(session, log, path)


if __name__ == "__main__":
    main()
