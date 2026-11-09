"""Selected long-run phases, independent of FastF1 input objects."""
from dataclasses import dataclass

from f1_explorer.visualizations.domain.driver import Driver


@dataclass(frozen=True, slots=True)
class LongRunPoint:
    lap_number: int
    tyre_age: float | None
    lap_time_seconds: float


@dataclass(frozen=True, slots=True)
class LongRun:
    driver: Driver
    stint_id: int | None
    phase_index: int
    compound: str
    # Non-empty by construction: a retained interval always holds at least one
    # lap, so drawing code may index points[0]/points[-1] without a guard.
    points: tuple[LongRunPoint, ...]
