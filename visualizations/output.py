"""Shared output-path and figure-saving helpers for visualizations."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Protocol

import matplotlib.pyplot as plt

from visualizations.report import current_report


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
    **savefig_kwargs: Any,
) -> Path:
    """Save a Matplotlib figure and close it exactly once, including on failure."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    savefig_kwargs.setdefault("bbox_inches", "tight")
    try:
        fig.savefig(output_path, **savefig_kwargs)
        report = current_report()
        if report is not None:
            report.register_image(output_path)
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
    """Save a Plotly figure at the requested dimensions."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_image(output_path, width=width, height=height)
    report = current_report()
    if report is not None:
        report.register_plotly(fig, output_path)
    log.info(f"Saved plot to {output_path}")
    return output_path
