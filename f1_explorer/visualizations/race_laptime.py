from typing import NamedTuple

from fastf1.core import Laps


class RaceLapTimes(NamedTuple):
    fastest: float
    slowest: float

    @property
    def axis_range(self) -> tuple[float, float]:
        return self.slowest + 0.1, self.fastest - 0.1


def race_lap_times(laps: Laps) -> RaceLapTimes | None:
    """Return axis reference times in seconds, before display padding."""
    seconds = laps["LapTime"].dt.total_seconds()
    if not seconds.notna().any():
        return None
    clean = (
        laps["IsAccurate"].eq(True)
        & laps["Deleted"].eq(False)
        & laps["TrackStatus"].astype(str).isin({"1", "1.0"})
    )
    clean_seconds = seconds[clean].dropna()
    slowest = clean_seconds.max() if not clean_seconds.empty else seconds.max()
    return RaceLapTimes(float(seconds.min()), float(slowest))
