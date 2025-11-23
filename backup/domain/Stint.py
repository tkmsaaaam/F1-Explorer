class Stint:
    def __init__(self):
        self.compound = 'UNKNOWN'
        self.is_new = False
        self.start_laps = 0
        self.total_laps = 0

    def set_compound(self, value: str):
        self.compound = value

    def set_is_new(self, value: bool):
        self.is_new = value

    def set_start_laps(self, value: int):
        self.start_laps = value

    def set_total_laps(self, value: int):
        self.total_laps = value
