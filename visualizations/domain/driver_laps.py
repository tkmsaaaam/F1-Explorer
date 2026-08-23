"""Typed collection of a driver's race laps."""

from dataclasses import dataclass
from typing import Mapping

from visualizations.domain.driver import Driver
from visualizations.domain.lap import Lap


@dataclass(slots=True, eq=False)
class DriverLaps:
    """Laps indexed by their race lap number.

    The mapping is copied at construction so callers can safely reuse their
    input mapping.  It remains mutable to support incomplete live timing data,
    and is deliberately not hashable (a mutable mapping must not participate
    in a hash).
    """

    driver: Driver
    laps: dict[int, Lap]

    def __init__(self, driver: Driver, laps: Mapping[int, Lap]):
        self.driver = driver
        self.laps = {int(number): lap for number, lap in laps.items()}

    def get_driver(self) -> Driver:
        return self.driver

    def get_laps(self) -> dict[int, Lap]:
        return self.laps

