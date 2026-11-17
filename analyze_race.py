import datetime
import argparse
from pathlib import Path

import fastf1
# noinspection PyPackageRequirements
from opentelemetry import trace

from f1_explorer import config as config_module
from f1_explorer.visualizations import weekend, run_volume, weather, race
from f1_explorer.session_pipeline import run_session
from f1_explorer.sessions import session_start_at

tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("start_at")
def start_at(session: fastf1.core.Session) -> None | datetime.datetime:
    return session_start_at(session, config_module.SessionCategory.Race)


@tracer.start_as_current_span("main")
def main(*, force: bool = False) -> int:
    return run_session(
        config_module.SessionCategory.Race,
        entrypoint=Path(__file__), start_at=start_at, figures=_figures,
        force=force,
    )


def _figures(session, config, log, output_dir) -> tuple[Path, ...]:
    log.info(f"{session.event.year} Race {session.event.RoundNumber} {session.event.EventName} Race")

    weekend.plot_tyre(config.get_year(), config.get_round(), log, current_session=session)

    run_volume.plot_laptime(session, log)
    run_volume.plot_laptime_by_lap_number(session, log)
    run_volume.plot_pit_time(session, log)

    path = str(output_dir)
    race.execute(session, log, path, path, None, None, None)

    weather.execute(session, log, path)
    return (Path(path) / "timestamp.txt", Path(path) / "race_control.txt",
            Path(path) / "track_status.txt")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze a Formula 1 race session")
    parser.add_argument("--force", action="store_true", help="re-analyze loaded data; does not refresh FastF1 upstream cache")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main(force=parse_args().force))
