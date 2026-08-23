"""A timed, positioned lap."""

from dataclasses import dataclass
from datetime import datetime

from visualizations.domain.tyre import Tyre


@dataclass(frozen=True, slots=True, init=False)
class Lap:
    time: float
    at: datetime
    position: int
    is_pit_out_lap: bool
    tyre: Tyre

    def __init__(
        self,
        time: float,
        at: datetime,
        position: int,
        is_pit_out_lap: bool | None = None,
        tyre: Tyre | None = None,
        *,
        pit_out: bool | None = None,
    ) -> None:
        """Create a lap.

        ``pit_out`` is accepted as a keyword for old callers.  The explicit
        ``is_pit_out_lap`` attribute avoids the historical ambiguity around
        whether ``pit_out`` represented a pit-in or pit-out event.
        """
        if is_pit_out_lap is None:
            is_pit_out_lap = pit_out if pit_out is not None else False
        elif pit_out is not None and pit_out != is_pit_out_lap:
            raise ValueError("pit_out and is_pit_out_lap disagree")
        if tyre is None:
            raise TypeError("tyre must be provided")
        object.__setattr__(self, "time", float(time))
        object.__setattr__(self, "at", at)
        object.__setattr__(self, "position", int(position))
        object.__setattr__(self, "is_pit_out_lap", bool(is_pit_out_lap))
        object.__setattr__(self, "tyre", tyre)

    def get_time(self) -> float:
        return self.time

    def get_at(self) -> datetime:
        return self.at

    def get_position(self) -> int:
        return self.position

    def get_pit_out(self) -> bool:
        return self.is_pit_out_lap

    def get_tyre(self) -> Tyre:
        return self.tyre
