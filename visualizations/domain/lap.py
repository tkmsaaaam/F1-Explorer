from datetime import datetime

from visualizations.domain.tyre import Tyre


class Lap:
    def __init__(self, time: float, at: datetime, position: int, pit_out: bool, tyre: Tyre):
        self.time = time
        self.at = at
        self.position = position
        self.pit_out = pit_out
        self.tyre = tyre
