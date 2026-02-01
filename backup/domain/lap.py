class Lap:
    def __init__(self, time=0):
        self.__time = time
        self.__position = 0
        self.__gap_to_ahead = 0
        self.__gap_to_top = 0

    def get_time(self):
        return self.__time

    def get_position(self):
        return self.__position

    def get_gap_to_ahead(self):
        return self.__gap_to_ahead

    def get_gap_to_top(self):
        return self.__gap_to_top

    def set_position(self, position: int):
        self.__position = position

    def set_gap_to_ahead(self, gap_to_ahead: float):
        self.__gap_to_ahead = gap_to_ahead

    def set_gap_to_top(self, gap_to_top: float):
        self.__gap_to_top = gap_to_top
