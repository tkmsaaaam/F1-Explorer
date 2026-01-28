from datetime import datetime

from visualizations.domain.tyre import Tyre


class Lap:
    def __init__(self, time: float, at: datetime, position: int, pit_out: bool, tyre: Tyre):
        self.__time = time
        self.__at = at
        self.__position = position
        self.__pit_out = pit_out
        self.__tyre = tyre

    def get_time(self) -> float:
        return self.__time

    def get_at(self) -> datetime:
        return self.__at

    def get_position(self) -> int:
        return self.__position

    def get_pit_out(self) -> bool:
        return self.__pit_out

    def get_tyre(self) -> Tyre:
        return self.__tyre
