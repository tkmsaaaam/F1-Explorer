"""Backward-compatible Qualifying report layout exports."""

from visualizations.report_layout import (
    QUALIFYING_SECTIONS as _QUALIFYING_LAYOUT,
    organize_session_report_html,
)

# Keep the tuple-shaped export used by older callers and tests.
QUALIFYING_SECTIONS = tuple(
    (section.anchor, section.title, tuple((item.key, item.title) for item in section.items))
    for section in _QUALIFYING_LAYOUT
)


def organize_qualifying_report_html(html: str) -> str:
    """Reorder and number a Qualifying report using the shared layout."""

    return organize_session_report_html(html, "Qualifying")
