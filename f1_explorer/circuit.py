"""Optional circuit metadata for report charts."""

import structlog


def circuit_info_or_none(session, log=None):
    """Treat metadata retrieval failures as missing optional circuit data."""
    if log is None:
        log = structlog.get_logger(__name__)
    try:
        return getattr(session, "get_circuit_info", lambda: None)()
    except Exception as exception:
        log.warning("circuit info unavailable; continuing without circuit metadata",
                    error=str(exception))
        return None
