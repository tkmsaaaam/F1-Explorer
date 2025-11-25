import datetime


class Lap:
    def __init__(self):
        self.time = 0
        self.position = 0
        self.gap_to_ahead = 0
        self.gap_to_top = 0
        self.at = datetime.datetime.now()

    def set_time(self, time: float):
        self.time = time

    def set_at(self, at: datetime.datetime):
        self.at = at

    def set_position(self, position: int):
        self.position = position

    def set_gap_to_ahead(self, gap_to_ahead: float):
        self.gap_to_ahead = gap_to_ahead

    def set_gap_to_top(self, gap_to_top: float):
        self.gap_to_top = gap_to_top
