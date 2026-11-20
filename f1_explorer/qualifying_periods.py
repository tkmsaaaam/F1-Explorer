"""FastF1 qualifying periods in report order, including unheld periods."""

import structlog
from fastf1.core import Laps, Session
from fastf1.exceptions import DataNotLoadedError

from f1_explorer.sessions import session_code

QualifyingPeriods = list[tuple[str, Laps | None]]


def qualifying_periods(
        session: Session,
        *,
        log: structlog.stdlib.BoundLogger | None = None,
) -> QualifyingPeriods:
    """Return Q1-Q3 (or SQ1-SQ3) periods, using None for unheld periods.

    FastF1 needs loaded status data and a final timestamp to split the session.
    When it cannot split, every period is missing so callers can fall back to
    the whole session instead of dropping the report.
    """

    try:
        parts = session.laps.split_qualifying_sessions()
    except (DataNotLoadedError, ValueError, IndexError, KeyError) as exception:
        if log is not None:
            log.warning("Could not split qualifying sessions; using session laps", reason=str(exception))
        parts = []
    prefix = "SQ" if session_code(getattr(session, "name", "")) == "SQ" else "Q"
    return [(f"{prefix}{index + 1}", parts[index] if index < len(parts) else None) for index in range(3)]


def available_periods(periods: QualifyingPeriods) -> list[tuple[str, Laps]]:
    """Return only the periods that hold laps, keeping their labels."""

    return [(label, laps) for label, laps in periods if laps is not None and not laps.empty]
