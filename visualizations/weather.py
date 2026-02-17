import os
from logging import Logger

from fastf1.core import Session
from matplotlib import pyplot as plt
from opentelemetry import trace

tracer = trace.get_tracer(__name__)


@tracer.start_as_current_span("execute")
def execute(session: Session, log: Logger, dir_path: str):
    plot_weather(session, log, 'AirTemp', f"{dir_path}/air_temp.png")
    plot_weather(session, log, 'TrackTemp', f"{dir_path}/track_temp.png")
    plot_weather(session, log, 'WindSpeed', f"{dir_path}/wind_speed.png")
    plot_weather(session, log, 'Rainfall', f"{dir_path}/rainfall.png")


@tracer.start_as_current_span("plot_weather")
def plot_weather(session: Session, log: Logger, key: str, filepath: str):
    """気象情報をプロット
    Args:
        session: セッション
        log: ロガー
        key: キー
        filepath: 保存先のパス
    """
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=150, layout='tight')
    plt.tight_layout()
    weather = session.weather_data.sort_values('Time')

    x = list((session.date + weather.Time).values)
    y = weather[key].to_list()
    ax.plot(x, y)
    plt.gcf().autofmt_xdate()
    ax.grid(True)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    fig.savefig(filepath, bbox_inches='tight')
    log.info(f"Saved plot to {filepath}")
    plt.close(fig)
