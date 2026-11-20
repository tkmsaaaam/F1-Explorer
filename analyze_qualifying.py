import datetime
import argparse
from pathlib import Path

import fastf1
# noinspection PyPackageRequirements
from opentelemetry import trace

from f1_explorer.circuit import circuit_info_or_none as _circuit_info_or_none
from f1_explorer import config as config_module
from f1_explorer.visualizations import run_volume, segment_analysis, short_runs, weather, weekend
from f1_explorer.visualizations.qualifying_telemetry import make_qualifying_telemetry, make_qualifying_track_map
from f1_explorer.visualizations.output import save_plotly
from f1_explorer.visualizations.qualifying_best import make_qualifying_best
from f1_explorer.visualizations.qualifying_speed import make_qualifying_speed
from f1_explorer.qualifying_periods import qualifying_periods
from f1_explorer.session_pipeline import run_session
from f1_explorer.sessions import session_start_at
from f1_explorer.telemetry import last_valid_distance, lap_telemetry_without_driver_ahead

tracer = trace.get_tracer(__name__)


def _fastest_distance_or_none(telemetry, log):
    distance = last_valid_distance(telemetry)
    if distance is None:
        log.warning("Skipping circuit-dependent analysis without valid fastest-lap distances")
    return distance


@tracer.start_as_current_span("start_at")
def start_at(session: fastf1.core.Session) -> None | datetime.datetime:
    return session_start_at(session, config_module.SessionCategory.Qualifying)

@tracer.start_as_current_span("main")
def main(*, force: bool = False, refresh_separators: bool = False) -> int:
    return run_session(
        config_module.SessionCategory.Qualifying,
        entrypoint=Path(__file__), start_at=start_at, figures=_figures,
        force=force, refresh_separators=refresh_separators,
    )


def _figures(session, config, log, output_dir) -> tuple[Path, ...]:
    log.info(f"{config.get_year()} Race {config.get_round()} {session.event.EventName} {config.get_session()}")

    run_volume.plot_lap_number_by_timing(session, log)
    periods = qualifying_periods(session, log=log)
    run_volume.plot_laptime(session, log, periods=periods, exclude_pit_laps=True)
    run_volume.plot_laptime_by_timing(session, log, periods=periods, exclude_pit_laps=True)
    run_volume.plot_laptime_by_lap_number(session, log)

    with tracer.start_as_current_span("make_qualifying_best"):
        best_figure = make_qualifying_best(session, periods=periods)
    save_plotly(best_figure, output_dir / 'LapTime.png', log, width=1920, height=1500)
    with tracer.start_as_current_span("make_qualifying_speed"):
        speed_figure = make_qualifying_speed(session, periods=periods)
    save_plotly(speed_figure, output_dir / 'SpeedFL.png', log, width=1920, height=1080)

    base_path = str(output_dir)
    circuit = _circuit_info_or_none(session, log)
    fastest = session.laps.pick_fastest()
    if circuit is not None and fastest is not None:
        fastest_telemetry = lap_telemetry_without_driver_ahead(fastest, add_distance=True)
        last_distance = _fastest_distance_or_none(fastest_telemetry, log)
        if last_distance is not None:
            corners = [0] + list(circuit.corners['Distance']) + [last_distance]
            segment_analysis.plot_mini_segment_on_circuit(
                session, log, corners, 'corners',
                fastest_lap=fastest, telemetry=fastest_telemetry,
            )
            segment_car_data = segment_analysis.prepare_segment_car_data(session)
            segment_analysis.compute_and_save_segment_tables_plotly(
                session, base_path + "/corners", corners, log,
                color_by_corner_speed=True, car_data_by_driver=segment_car_data,
            )

            corner_map = config.get_corners()
            segment_layout = segment_analysis.make_mini_segment_layout(
                session, log, corner_map,
                config.get_separator_boundaries() or config.get_separator(),
                fastest_lap=fastest,
                telemetry=fastest_telemetry,
            )
            segment_analysis.plot_mini_segment_on_circuit(
                session, log, segment_layout, 'mini_segments',
                show_sector_boundaries=True,
                fastest_lap=fastest,
                telemetry=fastest_telemetry,
            )
            segment_analysis.compute_and_save_segment_tables_plotly(
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
        make_qualifying_telemetry(session),
        output_dir / "time_distance_delta.png",
        log,
        width=1920,
        height=1080,
    )
    save_plotly(
        make_qualifying_track_map(session),
        output_dir / "speed_on_track.png",
        log,
        width=1920,
        height=1080,
    )

    weather.execute(session, log, base_path)
    weekend.plot_tyre(config.get_year(), config.get_round(), log, current_session=session)
    return ()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze a Formula 1 qualifying session")
    parser.add_argument("--force", action="store_true", help="re-analyze loaded data; does not refresh FastF1 upstream cache")
    parser.add_argument(
        "--refresh-separators",
        action="store_true",
        help="re-estimate saved circuit separators (does not change them on failure)",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(main(force=args.force, refresh_separators=args.refresh_separators))
