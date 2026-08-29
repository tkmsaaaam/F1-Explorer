import datetime
import argparse
from pathlib import Path

import fastf1
# noinspection PyPackageRequirements
from opentelemetry import trace

import setup
from visualizations import weekend, run_volume, weather, race
from visualizations.output import session_output_dir
from visualizations.report import SessionReport
from analysis_state import build_fingerprint, manifest_path, should_skip, write_success_manifest

tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("start_at")
def start_at(session: fastf1.core.Session) -> None | datetime.datetime:
    if session.name == 'Sprint':
        return session.event.Session3Date
    elif session.name == 'Race':
        return session.event.Session5Date
    return None


@tracer.start_as_current_span("main")
def main(*, force: bool = False):
    log = setup.log()
    try:
        config = setup.load_config()
    except Exception as exception:
        log.warning('setup is failed', args=exception.args)
        return

    if config.get_session_category() != setup.SessionCategory.Race:
        log.warning(f"{config.get_session()} is not R or S. \"Session\" needs to be set to R or S.")
        return
    setup.fast_f1()
    try:
        session = fastf1.get_session(config.get_year(), config.get_round(), config.get_session())
    except Exception as exception:
        log.warning('setup is failed', args=exception.args)
        return

    output_dir = session_output_dir(session)
    identity = {
        "year": int(config.get_year()),
        "round": int(config.get_round()),
        "session": session.name,
        "entrypoint": Path(__file__).name,
    }
    fingerprint = build_fingerprint(Path(__file__), Path(__file__).resolve().parent)
    if should_skip(manifest_path(output_dir), fingerprint, identity, force=force):
        log.info("Analysis skipped; source and environment fingerprint unchanged")
        return
    session.load()
    report = SessionReport(session, output_dir)
    report.activate()

    start = start_at(session)
    if start is None:
        report.deactivate()
        log.warning(f"{session.name} is not Sprint or Race.")
        return
    if datetime.datetime.now().astimezone() < start:
        report.deactivate()
        log.warning(
            f"{session.event.year} Race {session.event.RoundNumber} {session.event.EventName} Race is not started.")
        return
    config.set_attribute_to_span()
    log.info(f"{session.event.year} Race {session.event.RoundNumber} {session.event.EventName} Race")

    weekend.plot_tyre(config.get_year(), config.get_round(), log)

    run_volume.plot_laptime(session, log)
    run_volume.plot_laptime_by_timing(session, log)
    run_volume.plot_laptime_by_lap_number(session, log)
    run_volume.plot_pit_time(session, log)

    path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}"
    race.execute(session, log, path, path, None, None, None)

    weather.execute(session, log, path)
    report.deactivate()
    report.write(extra_paths=(output_dir.parent / "tyres.png",))
    write_success_manifest(output_dir, fingerprint, identity,
                           extra_output_paths=(output_dir.parent / "tyres.png",))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze a Formula 1 race session")
    parser.add_argument("--force", action="store_true", help="rerun even when the analysis is unchanged")
    return parser.parse_args(argv)


if __name__ == "__main__":
    main(force=parse_args().force)
