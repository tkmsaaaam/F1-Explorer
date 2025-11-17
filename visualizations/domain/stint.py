from visualizations.domain.driver import Driver


class Stint:
    def __init__(self, compound: str, laps: dict[int, float], driver: Driver):
        self.compound: str = compound
        self.laps: dict[int, float] = laps
        self.driver: Driver = driver
