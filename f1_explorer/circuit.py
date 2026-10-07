"""Optional circuit metadata for report charts."""

from __future__ import annotations

from typing import Callable, TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from fastf1.mvapi import CircuitInfo


def circuit_info_or_none(session, log=None):
    """Treat metadata retrieval failures as missing optional circuit data."""
    if log is None:
        log = structlog.get_logger(__name__)
    try:
        loader: Callable[[], CircuitInfo | None] | None = getattr(session, "get_circuit_info", None)
        if loader is None:
            return None
        return loader()
    except Exception as exception:
        log.warning("circuit info unavailable; continuing without circuit metadata",
                    error=str(exception))
        return None
