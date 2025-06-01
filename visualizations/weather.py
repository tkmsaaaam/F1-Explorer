from logging import Logger

from fastf1.core import Session
from matplotlib import pyplot as plt

import util


def execute(session: Session, log: Logger, dir_path: str):
    plot_weather(session, log, 'AirTemp', f"{dir_path}/air_temp.png")
    plot_weather(session, log, 'TrackTemp', f"{dir_path}/track_temp.png")
    plot_weather(session, log, 'WindSpeed', f"{dir_path}/wind_speed.png")
    plot_weather(session, log, 'Rainfall', f"{dir_path}/rainfall.png")


def plot_weather(session: Session, log: Logger, key: str, filepath: str):
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150)
    plt.tight_layout()
    weather = session.weather_data.sort_values('Time')

    x = list((session.date + weather.Time).values)
    y = weather[key].to_list()
    ax.plot(x, y)
    plt.gcf().autofmt_xdate()
    util.save(fig, ax, filepath, log)
