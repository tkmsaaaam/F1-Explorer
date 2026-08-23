"""Shared visual styling rules."""

from __future__ import annotations

import constants


def driver_linestyle(year: int, driver_number: int) -> str:
    """Return a driver's camera-based line style, defaulting safely to solid."""
    camera_color = constants.camera.get(year, {}).get(driver_number, "black")
    return "solid" if camera_color == "black" else "dashed"
