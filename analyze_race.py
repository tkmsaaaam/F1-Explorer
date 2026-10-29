import datetime
import argparse
from pathlib import Path

import fastf1
# noinspection PyPackageRequirements
from opentelemetry import trace

from f1_explorer import config as config_module
from f1_explorer.visualizations import weekend, run_volume, weather, race
from f1_explorer.visualizations.output import session_output_dir, session_report_dir
from f1_explorer.visualizations.report import SessionReport
from f1_explorer.analysis_state import (
    build_fingerprint, invalidate_success_manifest, manifest_path, should_skip, write_success_manifest,
    session_input_fingerprint, session_is_finished,
)

tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("start_at")
def start_at(session: fastf1.core.Session) -> None | datetime.datetime:
    if session.name == 'Sprint':
        return session.event.Session3Date
    elif session.name == 'Race':
        return session.event.Session5Date
    return None


@tracer.start_as_current_span("main")
def main(*, force: bool = False) -> int:
    log = config_module.log()
    try:
        config = config_module.load_config()
    except Exception as exception:
        log.warning('setup is failed', args=exception.args)
        return 1

    if config.get_session_category() != config_module.SessionCategory.Race:
        log.warning(f"{config.get_session()} is not R or S. \"Session\" needs to be set to R or S.")
        return 1
    config_module.fast_f1()
    try:
        session = fastf1.get_session(config.get_year(), config.get_round(), config.get_session())
    except Exception as exception:
        log.warning('setup is failed', args=exception.args)
        return 1

    start = start_at(session)
    if start is None:
        log.warning(f"{session.name} is not Sprint or Race.")
        return 1
    if datetime.datetime.now().astimezone() < start:
        log.warning(
            f"{session.event.year} Race {session.event.RoundNumber} {session.event.EventName} Race is not started.")
        return 0

    output_dir = session_output_dir(session)
    report_dir = session_report_dir(session)
    identity = {
        "year": int(config.get_year()),
        "round": int(config.get_round()),
        "session": session.name,
        "entrypoint": Path(__file__).name,
    }
    fingerprint = build_fingerprint(Path(__file__), Path(__file__).resolve().parent)
    try:
        session.load()
    except Exception:
        invalidate_success_manifest(report_dir)
        raise
    session_input = session_input_fingerprint(session, include_messages=True)
    complete = session_is_finished(session)
    if should_skip(manifest_path(report_dir), fingerprint, identity, force=force,
                   session_input=session_input, complete=complete):
        log.info("Analysis skipped; loaded session inputs and analysis environment match the successful report")
        return 0
    invalidate_success_manifest(report_dir)
    report = SessionReport(session, output_dir, report_dir=report_dir)
    with report:
        _analyze_session(session, config, log, report, output_dir, report_dir, identity, fingerprint, session_input, complete)
    return 0


def _analyze_session(session, config, log, report, output_dir, report_dir, identity, fingerprint, session_input, complete):
    config.set_attribute_to_span()
    log.info(f"{session.event.year} Race {session.event.RoundNumber} {session.event.EventName} Race")

    weekend.plot_tyre(config.get_year(), config.get_round(), log, current_session=session)

    run_volume.plot_laptime(session, log)
    run_volume.plot_laptime_by_lap_number(session, log)
    run_volume.plot_pit_time(session, log)

    path = f"./images/{session.event.year}/{session.event.RoundNumber}_{session.event.Location}/{session.name.replace(' ', '')}"
    race.execute(session, log, path, path, None, None, None)

    weather.execute(session, log, path)
    report.write(scan_existing=False)
    if complete and session_input is not None:
        write_success_manifest(
            report_dir,
            fingerprint,
            identity,
            extra_output_paths=(*report.written_output_paths(),
                                Path(path) / "timestamp.txt", Path(path) / "race_control.txt",
                                Path(path) / "track_status.txt"),
            required_output_paths=(report.report_dir / "report.html", *report.required_png_paths(),
                                   Path(path) / "timestamp.txt", Path(path) / "race_control.txt",
                                   Path(path) / "track_status.txt"),
            session_input=session_input,
        )
    return None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze a Formula 1 race session")
    parser.add_argument("--force", action="store_true", help="re-analyze loaded data; does not refresh FastF1 upstream cache")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main(force=parse_args().force))
