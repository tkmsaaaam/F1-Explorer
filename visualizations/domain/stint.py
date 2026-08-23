"""A run of laps on one tyre compound."""

from dataclasses import dataclass, field
from typing import Mapping

from visualizations.domain.driver import Driver


@dataclass(slots=True, eq=False)
class Stint:
    """Mutable aggregate of lap times.

    ``laps`` is intentionally mutable because long-run filtering appends and
    removes observations while constructing a stint.  ``eq=False`` preserves
    identity hashing for the legacy set-based plotting code without claiming
    that a mutable dictionary has a stable value hash.
    """

    compound: str
    laps: dict[int, float] = field(default_factory=dict)
    driver: Driver = field(init=False)

    def __init__(self, compound: str, laps: Mapping[int, float], driver: Driver):
        self.compound = compound
        self.laps = dict(laps)
        self.driver = driver

    def get_compound(self) -> str:
        return self.compound

    def get_laps(self) -> dict[int, float]:
        return self.laps

    def get_driver(self) -> Driver:
        return self.driver
