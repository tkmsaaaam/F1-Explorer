"""Selected long-run phases, independent of FastF1 input objects."""
from dataclasses import dataclass
from typing import Literal

from f1_explorer.visualizations.domain.driver import Driver

LongRunScope = Literal["lap", "phase"]


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


@dataclass(frozen=True, slots=True)
class LongRunDecision:
    driver: Driver
    stint_id: int | None
    compound: str
    lap_numbers: tuple[int | None, ...]
    start_time: str | None
    scope: LongRunScope
    accepted: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LongRunSelection:
    runs: tuple[LongRun, ...]
    decisions: tuple[LongRunDecision, ...]
