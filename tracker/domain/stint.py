class Stint:
    def __init__(self):
        self.__compound = 'UNKNOWN'
        self.__is_new = False
        self.__start_laps = 0
        self.__total_laps = 0

    def get_compound(self) -> str:
        return self.__compound

    def get_is_new(self) -> bool:
        return self.__is_new

    def get_start_laps(self) -> int:
        return self.__start_laps

    def get_total_laps(self) -> int:
        return self.__total_laps

    def set_compound(self, value: str):
        self.__compound = value

    def set_is_new(self, value: bool):
        self.__is_new = value

    def set_start_laps(self, value: int):
        self.__start_laps = value

    def set_total_laps(self, value: int):
        self.__total_laps = value
