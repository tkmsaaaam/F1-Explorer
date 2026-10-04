"""Shared output-path and figure-saving helpers for f1_explorer.visualizations."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import matplotlib.pyplot as plt
import plotly.io as pio
from opentelemetry import trace

from f1_explorer.visualizations.report import current_report

tracer = trace.get_tracer(__name__)


class _EventLike(Protocol):
    """The event fields used to build a session output directory."""

    year: int
    RoundNumber: int
    Location: str


class SessionLike(Protocol):
    """The subset of a FastF1 session needed by this module."""

    event: _EventLike
    name: str


class MatplotlibFigure(Protocol):
    """Protocol for figures accepted by :func:`save_matplotlib`."""

    def savefig(self, fname: str | Path, **kwargs: Any) -> Any:
        """Save the figure."""


class PlotlyFigure(Protocol):
    """Protocol for figures accepted by :func:`save_plotly`."""

    def write_image(self, file: str | Path, *, width: int, height: int) -> Any:
        """Write a static image."""


class LoggerLike(Protocol):
    """Minimal logger interface used by the save helpers."""

    def info(self, message: str, **kwargs: Any) -> Any:
        """Log an informational message."""


def _value(source: object, key: str) -> object:
    """Read a field from either an object or a mapping."""
    if isinstance(source, Mapping):
        return source[key]
    return getattr(source, key)


def session_output_dir(session: SessionLike, root: str | Path = "images") -> Path:
    """Return the relative directory used for one FastF1 session's plots."""
    event = _value(session, "event")
    year = _value(event, "year")
    round_number = _value(event, "RoundNumber")
    location = _value(event, "Location")
    session_name = _value(session, "name")
    return (
        Path(root)
        / str(year)
        / f"{round_number}_{location}"
        / str(session_name).replace(" ", "")
    )


def session_report_dir(session: SessionLike, root: str | Path = "reports") -> Path:
    """Return the directory for a session's HTML report and metadata."""

    return session_output_dir(session, root)


def resolve_output_dir(session: SessionLike, output_dir: str | Path | None) -> Path:
    """Normalize an explicit output directory, or derive the session directory."""
    return session_output_dir(session) if output_dir is None else Path(output_dir)


def save_matplotlib(
    fig: MatplotlibFigure,
    path: str | Path,
    log: LoggerLike,
    *,
    report_interactive: bool = False,
    **savefig_kwargs: Any,
) -> Path:
    """Embed chart data, retain requested PNGs, and close the source figure."""
    output_path = Path(path)
    report = current_report()
    if report is not None and (report_interactive or not report.accepts_output(output_path)):
        plt.close(fig)
        return output_path
    if report is not None and not report.requires_png(output_path):
        from f1_explorer.visualizations.embedded_matplotlib import embed_matplotlib

        try:
            report.register_plotly(embed_matplotlib(fig), output_path)
            return output_path
        finally:
            plt.close(fig)
    if report is not None:
        output_path = report.png_output_path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    savefig_kwargs.setdefault("bbox_inches", "tight")
    try:
        fig.savefig(output_path, **savefig_kwargs)
        report = current_report()
        if report is not None:
            from f1_explorer.visualizations.embedded_matplotlib import embed_matplotlib

            report.register_plotly(embed_matplotlib(fig), output_path)
        log.info(f"Saved plot to {output_path}")
        return output_path
    finally:
        plt.close(fig)


def save_plotly(
    fig: PlotlyFigure,
    path: str | Path,
    log: LoggerLike,
    *,
    width: int,
    height: int,
) -> Path:
    """Embed report figure data; export PNGs only when independently needed."""
    output_path = Path(path)
    report = current_report()
    if report is not None and not report.accepts_output(output_path):
        return output_path
    if report is None or report.requires_png(output_path):
        if report is not None:
            output_path = report.png_output_path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tracer.start_as_current_span("plotly.write_image") as span:
            span.set_attribute("plot.name", output_path.name)
            span.set_attribute("plot.width", width)
            span.set_attribute("plot.height", height)
            fig.write_image(output_path, width=width, height=height)
        log.info(f"Saved plot to {output_path}")
    report = current_report()
    if report is not None:
        with tracer.start_as_current_span("plotly.register_report") as span:
            span.set_attribute("plot.name", output_path.name)
            report.register_plotly(fig, output_path)
    return output_path


def save_plotly_batch(
    figures: Sequence[PlotlyFigure],
    paths: Sequence[str | Path],
    log: LoggerLike,
    *,
    width: int,
    height: int,
) -> list[Path]:
    """Register related figures and batch export their required PNG artifacts."""
    if len(figures) != len(paths):
        raise ValueError("figures and paths must have the same length")
    report = current_report()
    accepted = [
        (fig, Path(path)) for fig, path in zip(figures, paths)
        if report is None or report.accepts_output(path)
    ]
    if not accepted:
        return []
    static = [(fig, path) for fig, path in accepted
              if report is None or report.requires_png(path)]
    if report is not None:
        static = [(fig, report.png_output_path(path)) for fig, path in static]
    for _, path in static:
        path.parent.mkdir(parents=True, exist_ok=True)
    if static:
        with tracer.start_as_current_span("plotly.write_images") as span:
            span.set_attribute("plot.count", len(static))
            span.set_attribute("plot.width", width)
            span.set_attribute("plot.height", height)
            pio.write_images(
                fig=[fig for fig, _ in static],
                file=[path for _, path in static],
                width=width,
                height=height,
            )
        for _, path in static:
            log.info(f"Saved plot to {path}")
    for fig, path in accepted:
        if report is not None and report.requires_png(path):
            path = report.png_output_path(path)
        if report is not None:
            with tracer.start_as_current_span("plotly.register_report") as span:
                span.set_attribute("plot.name", path.name)
                report.register_plotly(fig, path)
    return [report.png_output_path(path) if report is not None and report.requires_png(path) else path
            for _, path in accepted]
