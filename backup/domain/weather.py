class Weather:
    def __init__(self):
        self.__air_temp = 0
        self.__rain_fall = 0
        self.__track_temp = 0
        self.__wind_speed = 0

    def get_air_temp(self):
        return self.__air_temp

    def get_rain_fall(self):
        return self.__rain_fall

    def get_track_temp(self):
        return self.__track_temp

    def get_wind_speed(self):
        return self.__wind_speed

    def set_air_temp(self, v: float):
        self.__air_temp = v

    def set_rain_fall(self, v: float):
        self.__rain_fall = v

    def set_track_temp(self, v: float):
        self.__track_temp = v

    def set_wind_speed(self, v: float):
        self.__wind_speed = v
