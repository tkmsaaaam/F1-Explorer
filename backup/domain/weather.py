class Weather:
    def __init__(self):
        self.air_temp = 0
        self.rain_fall = 0
        self.track_temp = 0
        self.wind_speed = 0

    def set_air_temp(self, v: float):
        self.air_temp = v

    def set_rain_fall(self, v: float):
        self.rain_fall = v

    def set_track_temp(self, v: float):
        self.track_temp = v

    def set_wind_speed(self, v: float):
        self.wind_speed = v
