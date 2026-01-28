from visualizations.domain.driver import Driver


class Stint:
    def __init__(self, compound: str, laps: dict[int, float], driver: Driver):
        self.__compound: str = compound
        self.__laps: dict[int, float] = laps
        self.__driver: Driver = driver

    def get_compound(self) -> str:
        return self.__compound

    def get_laps(self) -> dict[int, float]:
        return self.__laps

    def get_driver(self) -> Driver:
        return self.__driver
