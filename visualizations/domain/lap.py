from datetime import datetime


class Lap:
    def __init__(self, time: float, at: datetime, position: int):
        self.time = time
        self.at = at
        self.position = position
