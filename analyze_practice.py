import datetime
import argparse
from pathlib import Path

import fastf1
# noinspection PyPackageRequirements
from opentelemetry import trace

import setup
from visualizations import run_volume, long_runs, short_runs, weather, weekend
from visualizations.output import session_output_dir, session_report_dir
from visualizations.report import SessionReport
from visualizations.practice_comparison import make_practice_best, make_practice_speed
from visualizations.qualifying_telemetry import make_telemetry_comparison, make_track_map_comparison
from visualizations.output import save_plotly
from analysis_state import build_fingerprint, manifest_path, should_skip, write_success_manifest

tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("start_at")
def start_at(session: fastf1.core.Session) -> None | datetime.datetime:
    if session.name == 'Practice 1':
        return session.event.Session1Date
    elif session.name == 'Practice 2':
        return session.event.Session2Date
    elif session.name == 'Practice 3':
        return session.event.Session3Date
    return None


@tracer.start_as_current_span("main")
def main(*, force: bool = False):
    log = setup.log()
    try:
        config = setup.load_config()
    except Exception as exception:
        log.warning('setup is failed', args=exception.args)
        return

    if config.get_session_category() != setup.SessionCategory.FreePractice:
        log.warning(f"{config.get_session()} is not FP. \"Session\" needs to be set to FP.")
        return
    setup.fast_f1()
    try:
        session = fastf1.get_session(config.get_year(), config.get_round(), config.get_session())
    except Exception as exception:
        log.warning('setup is failed', args=exception.args)
        return

    output_dir = session_output_dir(session)
    report_dir = session_report_dir(session)
    identity = {
        "year": int(config.get_year()),
        "round": int(config.get_round()),
        "session": session.name,
        "entrypoint": Path(__file__).name,
    }
    fingerprint = build_fingerprint(Path(__file__), Path(__file__).resolve().parent)
    if should_skip(manifest_path(report_dir), fingerprint, identity, force=force):
        log.info("Analysis skipped; source and environment fingerprint unchanged")
        return
    session.load(messages=False)
    report = SessionReport(session, output_dir, report_dir=report_dir)
    report.activate()

    start = start_at(session)
    if start is None:
        report.deactivate()
        log.warning(f"{session.name} is not Practice 1 or Practice 2 or Practice 3.")
        return
    if datetime.datetime.now().astimezone() < start:
        report.deactivate()
        log.warning(
            f"{session.event.year} Race {session.event.RoundNumber} {session.event.EventName} Practice is not started.")
        return
    config.set_attribute_to_span()
    log.info(
        f"{session.event.year} Race {session.event['RoundNumber']} {session.event.EventName} {config.get_session()}")

    run_volume.plot_lap_number_by_timing(session, log)
    run_volume.plot_laptime(session, log)
    run_volume.plot_laptime_by_timing(session, log)
    run_volume.plot_laptime_by_lap_number(session, log)

    long_runs.plot_by_tyre_age_and_tyre(session, log)

    save_plotly(make_practice_best(session), output_dir / 'LapTime.png', log, width=1920, height=1080)
    save_plotly(make_practice_speed(session), output_dir / 'SpeedFL.png', log, width=1920, height=1080)

    circuit = session.get_circuit_info()
    fastest = session.laps.pick_fastest()

    if circuit is None:
        report.deactivate()
        log.info("circuit info is None")
        return
    if fastest is None:
        report.deactivate()
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
    short_runs.plot_speed_and_laptime(session, log)
    short_runs.plot_tyre_age_and_laptime(session, log)

    save_plotly(
        make_telemetry_comparison(session),
        output_dir / "time_distance_delta.png",
        log,
        width=1920,
        height=1080,
    )
    save_plotly(
        make_track_map_comparison(session),
        output_dir / "speed_on_track.png",
        log,
        width=1920,
        height=1080,
    )

    weather.execute(session, log, base_path)

    weekend.plot_tyre(config.get_year(), config.get_round(), log)
    report.deactivate()
    report.write(scan_existing=False)
    write_success_manifest(
        report_dir,
        fingerprint,
        identity,
        extra_output_paths=(output_dir.parent / "tyres.png",),
        extra_output_dirs=(output_dir,),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze a Formula 1 practice session")
    parser.add_argument("--force", action="store_true", help="rerun even when the analysis is unchanged")
    return parser.parse_args(argv)


if __name__ == "__main__":
    main(force=parse_args().force)
