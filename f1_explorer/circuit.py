"""Optional circuit metadata for report charts."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from f1_explorer.scalars import call_dynamic

if TYPE_CHECKING:
    from fastf1.mvapi import CircuitInfo


def circuit_info_or_none(session, log=None) -> CircuitInfo | None:
    """Treat metadata retrieval failures as missing optional circuit data."""
    if log is None:
        log = structlog.get_logger(__name__)
    try:
        loader: object = getattr(session, "get_circuit_info", None)
        if loader is None:
            return None
        return call_dynamic(loader)
    except Exception as exception:
        log.warning("circuit info unavailable; continuing without circuit metadata",
                    error=str(exception))
        return None
