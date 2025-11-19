from datetime import datetime


class Lap:
    def __init__(self, time: float, at: datetime):
        self.time = time
        self.at = at
