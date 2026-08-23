"""Driver value object used by the race visualizations."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Driver:
    """The identity of a driver in a session.

    Driver objects are immutable values.  The ``get_*`` methods are retained
    for callers in the original plotting code; new code can use the public
    attributes directly.
    """

    number: int
    name: str
    team_name: str

    def get_number(self) -> int:
        return self.number

    def get_name(self) -> str:
        return self.name

    def get_team_name(self) -> str:
        return self.team_name
