"""A single race lap, optionally timed and positioned.

``time`` is the lap time in seconds and ``at`` the session-elapsed time
(FastF1 ``Laps.Time``) at which the lap was completed; both may be
``None`` when the source timing record lacks the value.  ``position``
is the running race position and may be ``None`` as well.  Identity is
the driver plus the lap number, so a lap is kept even when only the lap
number is known.
"""

from dataclasses import dataclass
from datetime import timedelta

from f1_explorer.visualizations.domain.tyre import Tyre


@dataclass(frozen=True, slots=True, init=False)
class Lap:
    time: float | None
    at: timedelta | None
    position: int | None
    is_pit_out_lap: bool
    tyre: Tyre

    def __init__(
        self,
        time: float | None,
        at: timedelta | None,
        position: int | None,
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
        if at is not None and not isinstance(at, timedelta):
            raise TypeError("at must be a datetime.timedelta (including pandas.Timedelta)")
        object.__setattr__(self, "time", None if time is None else float(time))
        object.__setattr__(self, "at", at)
        object.__setattr__(self, "position", None if position is None else int(position))
        object.__setattr__(self, "is_pit_out_lap", bool(is_pit_out_lap))
        object.__setattr__(self, "tyre", tyre)

    def get_time(self) -> float | None:
        return self.time

    def get_at(self) -> timedelta | None:
        return self.at

    def get_position(self) -> int | None:
        return self.position

    def get_pit_out(self) -> bool:
        return self.is_pit_out_lap

    def get_tyre(self) -> Tyre:
        return self.tyre
