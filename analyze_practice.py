import datetime
import argparse
from pathlib import Path

import fastf1
# noinspection PyPackageRequirements
from opentelemetry import trace

from f1_explorer.circuit import circuit_info_or_none as _circuit_info_or_none
from f1_explorer import config as config_module
from f1_explorer.visualizations import run_volume, long_runs, short_runs, weather, weekend
from f1_explorer.visualizations.output import session_output_dir, session_report_dir
from f1_explorer.visualizations.report import SessionReport
from f1_explorer.visualizations.practice_comparison import make_practice_best, make_practice_speed
from f1_explorer.visualizations.qualifying_telemetry import make_telemetry_comparison, make_track_map_comparison
from f1_explorer.telemetry import lap_telemetry_without_driver_ahead
from f1_explorer.visualizations.output import save_plotly
from f1_explorer.analysis_state import build_fingerprint, manifest_path, should_skip, write_success_manifest
from f1_explorer.separator_estimator import persist_resolution, resolve_separators

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
def main(*, force: bool = False, refresh_separators: bool = False):
    log = config_module.log()
    try:
        config = config_module.load_config()
    except Exception as exception:
        log.warning('setup is failed', args=exception.args)
        return

    if config.get_session_category() != config_module.SessionCategory.FreePractice:
        log.warning(f"{config.get_session()} is not FP. \"Session\" needs to be set to FP.")
        return
    config_module.fast_f1()
    try:
        session = fastf1.get_session(config.get_year(), config.get_round(), config.get_session())
    except Exception as exception:
        log.warning('setup is failed', args=exception.args)
        return

    output_dir = session_output_dir(session)
    report_dir = session_report_dir(session)
    # Load before deciding whether the report can be skipped: an unsaved
    # circuit separator is an input to this report and may need estimating.
    with tracer.start_as_current_span("session.load"):
        session.load(messages=False)
    start = start_at(session)
    if start is None:
        log.warning(f"{session.name} is not Practice 1 or Practice 2 or Practice 3.")
        return
    if datetime.datetime.now().astimezone() < start:
        log.warning(
            f"{session.event.year} Race {session.event.RoundNumber} {session.event.EventName} Practice is not started."
        )
        return
    with tracer.start_as_current_span("resolve_separators"):
        separator_resolution = resolve_separators(
            session,
            Path("config.json"),
            refresh=refresh_separators,
            log=log,
        )
    config.set_separator(separator_resolution.separators, separator_resolution.boundaries)
    log.info("mini segment separator source", source=separator_resolution.source,
             separators=separator_resolution.separators)
    identity = {
        "year": int(config.get_year()),
        "round": int(config.get_round()),
        "session": session.name,
        "entrypoint": Path(__file__).name,
    }
    fingerprint = build_fingerprint(
        Path(__file__), Path(__file__).resolve().parent, Path("config.json")
    )
    if not separator_resolution.pending_save and should_skip(
        manifest_path(report_dir), fingerprint, identity, force=force or refresh_separators
    ):
        log.info("Analysis skipped; source and environment fingerprint unchanged")
        return
    report = SessionReport(session, output_dir, report_dir=report_dir)
    report.activate()

    config.set_attribute_to_span()
    log.info(
        f"{session.event.year} Race {session.event['RoundNumber']} {session.event.EventName} {config.get_session()}")

    run_volume.plot_lap_number_by_timing(session, log)
    run_volume.plot_laptime(session, log)
    run_volume.plot_laptime_by_timing(session, log)
    run_volume.plot_laptime_by_lap_number(session, log)

    long_runs.plot_by_tyre_age_and_tyre(session, log)

    with tracer.start_as_current_span("make_practice_best"):
        best_figure = make_practice_best(session)
    save_plotly(best_figure, output_dir / 'LapTime.png', log, width=1920, height=1080)
    with tracer.start_as_current_span("make_practice_speed"):
        speed_figure = make_practice_speed(session)
    save_plotly(speed_figure, output_dir / 'SpeedFL.png', log, width=1920, height=1080)

    base_path = f"./images/{session.event.year}/{session.event['RoundNumber']}_{session.event.Location}/{session.name.replace(' ', '')}"
    circuit = _circuit_info_or_none(session, log)
    fastest = session.laps.pick_fastest()
    if circuit is not None and fastest is not None:
        fastest_telemetry = lap_telemetry_without_driver_ahead(fastest, add_distance=True)
        corners = [0] + list(circuit.corners['Distance']) + [fastest_telemetry['Distance'].iloc[-1]]
        short_runs.plot_mini_segment_on_circuit(
            session, log, corners, 'corners',
            fastest_lap=fastest, telemetry=fastest_telemetry,
        )
        segment_car_data = short_runs.prepare_segment_car_data(session)
        short_runs.compute_and_save_segment_tables_plotly(
            session, base_path + "/corners", corners, log, car_data_by_driver=segment_car_data,
        )
        corner_map = config.get_corners()
        segment_layout = short_runs.make_mini_segment_layout(
            session, log, corner_map,
            config.get_separator_boundaries() or config.get_separator(),
            fastest_lap=fastest,
            telemetry=fastest_telemetry,
        )
        short_runs.plot_mini_segment_on_circuit(
            session, log, segment_layout, 'mini_segments',
            show_sector_boundaries=True,
            fastest_lap=fastest,
            telemetry=fastest_telemetry,
        )
        short_runs.compute_and_save_segment_tables_plotly(
            session, base_path + "/mini_segments", segment_layout, log, car_data_by_driver=segment_car_data,
        )
    elif fastest is None:
        log.info("fastest info is None; skipping circuit-dependent analysis")
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

    weekend.plot_tyre(config.get_year(), config.get_round(), log, current_session=session)
    report.deactivate()
    report.write(scan_existing=False)
    try:
        persist_resolution(separator_resolution, Path("config.json"), session, refresh=refresh_separators)
    except Exception as exception:
        log.warning("automatic separators were not saved", error=str(exception))
    fingerprint = build_fingerprint(
        Path(__file__), Path(__file__).resolve().parent, Path("config.json")
    )
    write_success_manifest(
        report_dir,
        fingerprint,
        identity,
        extra_output_paths=report.image_paths(),
        extra_output_dirs=(output_dir,),
        exclude_extra_suffixes=(".png",),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze a Formula 1 practice session")
    parser.add_argument("--force", action="store_true", help="rerun even when the analysis is unchanged")
    parser.add_argument(
        "--refresh-separators",
        action="store_true",
        help="re-estimate saved circuit separators (does not change them on failure)",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    main(force=args.force, refresh_separators=args.refresh_separators)
