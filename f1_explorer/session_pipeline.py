"""Shared lifecycle for the Practice, Qualifying, and Race report entrypoints."""

import datetime
from collections.abc import Callable
from pathlib import Path

import fastf1
import structlog
from opentelemetry import trace

from f1_explorer import config as config_module
from f1_explorer.analysis_state import (
    build_fingerprint, invalidate_success_manifest, manifest_path, should_skip,
    write_success_manifest, session_input_fingerprint, session_is_finished,
)
from f1_explorer.config import CONFIG_PATH
from f1_explorer.separator_estimator import persist_resolution, resolve_separators
from f1_explorer.visualizations.output import session_output_dir, session_report_dir
from f1_explorer.visualizations.report import SessionReport

tracer = trace.get_tracer(__name__)


def run_session(
    category: config_module.SessionCategory,
    *,
    entrypoint: Path,
    start_at: Callable[[fastf1.core.Session], datetime.datetime | None],
    figures: Callable[[fastf1.core.Session, config_module.Config, structlog.stdlib.BoundLogger, Path],
                      tuple[Path, ...]],
    force: bool = False,
    refresh_separators: bool = False,
) -> int:
    """Load and analyze one session and write its report and success manifest.

    The ``figures`` callback runs inside the report context (so ``save_plotly``
    and ``register_plotly`` attach figures to the report), after separators
    have been resolved into ``config``, and before ``report.write``.  Its
    return value lists additional outputs that join the manifest's extra and
    required output paths.
    """
    codes, names, label = {
        config_module.SessionCategory.FreePractice: ("FP", "Practice 1 or Practice 2 or Practice 3", "Practice"),
        config_module.SessionCategory.Qualifying: ("Q or SQ", "Sprint Qualifying or Qualifying", "Qualifying"),
        config_module.SessionCategory.Race: ("R or S", "Sprint or Race", "Race"),
    }[category]
    is_race = category == config_module.SessionCategory.Race
    if is_race and refresh_separators:
        # The CLI cannot reach this, but the API must not pretend to refresh:
        # race skips all separator work, so a "refresh" would only force a
        # regeneration with unchanged separators.
        raise ValueError("refresh_separators is not supported for Race")
    log = config_module.log()
    try:
        config = config_module.load_config()
    except Exception as exception:
        log.warning('setup is failed', args=exception.args)
        return 1

    if config.get_session_category() != category:
        log.warning(f"{config.get_session()} is not {codes}. \"Session\" needs to be set to {codes}.")
        return 1
    config_module.fast_f1()
    try:
        session = fastf1.get_session(config.get_year(), config.get_round(), config.get_session())
    except Exception as exception:
        log.warning('setup is failed', args=exception.args)
        return 1

    start = start_at(session)
    if start is None:
        log.warning(f"{session.name} is not {names}.")
        return 1
    if datetime.datetime.now().astimezone() < start:
        log.warning(
            f"{session.event.year} Race {session.event.RoundNumber} {session.event.EventName} {label} is not started."
        )
        return 0

    output_dir = session_output_dir(session)
    report_dir = session_report_dir(session)
    # Race has no separator/config persistence and retains its pre-load source hash.
    fingerprint = build_fingerprint(entrypoint, entrypoint.resolve().parent) if is_race else None
    with tracer.start_as_current_span("session.load"):
        try:
            if is_race:
                session.load()
            else:
                session.load(messages=False)
        except Exception:
            invalidate_success_manifest(report_dir)
            raise
    session_input = session_input_fingerprint(session, include_messages=is_race)
    complete = session_is_finished(session)
    separator_resolution = None
    if not is_race:
        # Load first: resolve_separators needs loaded laps, and the unsaved
        # separator it estimates is an input to this report, so the reuse
        # check below must come after both.
        with tracer.start_as_current_span("resolve_separators"):
            separator_resolution = resolve_separators(
                session,
                CONFIG_PATH,
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
        "entrypoint": entrypoint.name,
    }
    if not is_race:
        fingerprint = build_fingerprint(entrypoint, entrypoint.resolve().parent, CONFIG_PATH)
    if (separator_resolution is None or not separator_resolution.pending_save) and should_skip(
        manifest_path(report_dir), fingerprint, identity, force=force or refresh_separators,
        session_input=session_input, complete=complete,
    ):
        log.info("Analysis skipped; loaded session inputs and analysis environment match the successful report")
        return 0
    invalidate_success_manifest(report_dir)
    report = SessionReport(session, output_dir, report_dir=report_dir)
    with report:
        config.set_attribute_to_span()
        extra_outputs = figures(session, config, log, output_dir)
        report.write(scan_existing=False)
        if separator_resolution is not None:
            try:
                persist_resolution(separator_resolution, CONFIG_PATH, session,
                                   refresh=refresh_separators)
            except Exception as exception:
                log.warning("automatic separators were not saved", error=str(exception))
            fingerprint = build_fingerprint(entrypoint, entrypoint.resolve().parent, CONFIG_PATH)
        if complete and session_input is not None:
            write_success_manifest(
                report_dir,
                fingerprint,
                identity,
                extra_output_paths=(*report.written_output_paths(), *extra_outputs),
                required_output_paths=(report.report_dir / "report.html", *report.required_png_paths(),
                                       *extra_outputs),
                session_input=session_input,
            )
    return 0
