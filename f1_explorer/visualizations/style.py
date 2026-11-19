"""Shared visual styling rules."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import fastf1.plotting
import structlog
from fastf1.core import Session

from f1_explorer import constants

logger = structlog.get_logger(__name__)


def driver_linestyle(year: int, driver_number: int) -> str:
    """Return a driver's camera-based line style, defaulting safely to solid."""
    camera_color = constants.camera.get(year, {}).get(driver_number, "black")
    return "solid" if camera_color == "black" else "dashed"


def resolve_team_color(team: object, session: Session, *, empty_color: str = "gray") -> str:
    """Return the team's palette color, falling back safely.

    An empty team name yields ``empty_color``; a non-string team (None or
    NaN, e.g. from lap rows or test stubs lacking ``Team``) yields ``gray``
    so it stays visible.  A team whose palette lookup fails yields ``gray``
    and is logged.
    """
    if not isinstance(team, str):
        return "gray"
    if not team:
        return empty_color
    try:
        return fastf1.plotting.get_team_color(team, session)
    except (AttributeError, KeyError, TypeError, ValueError):
        logger.warning("Team color lookup failed", team=team)
        return "gray"


def driver_team_colors(drivers: Iterable[object], teams: Mapping[object, str], session: Session) -> list[str]:
    """Return each driver's team color, gray when the team is unknown."""
    return [resolve_team_color(teams.get(driver), session) for driver in drivers]


def plotly_driver_dash(session: Session, number: object) -> str:
    """Translate the camera-based line style into Plotly's dash name, defaulting to solid."""
    try:
        style = driver_linestyle(session.event.year, int(number))
    except (AttributeError, TypeError, ValueError):
        return "solid"
    return "dash" if style == "dashed" else "solid"
