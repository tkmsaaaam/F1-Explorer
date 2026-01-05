import json
import logging
from logging import Logger

import fastf1
from opentelemetry import trace

tracer = trace.get_tracer(__name__)


class Config:
    def __init__(self, year: int, round: int, session: str, corners: dict[str, list[float]], separator: list[int]):
        self.year = year
        self.round = round
        self.session = session
        self.corners = corners
        self.separator = separator

    def get_year(self):
        return self.year

    def get_round(self):
        return self.round

    def get_session(self):
        return self.session

    def get_corners(self):
        return self.corners

    def get_separator(self):
        return self.separator


@tracer.start_as_current_span("load_config")
def load_config() -> Config | None:
    config = None
    with open('./config.json', 'r', encoding='utf-8') as file:
        config = json.load(file)
    if config is None:
        return None
    return Config(config['Year'], config['Round'], config['Session'], config['Corners'], config['Separator'])


@tracer.start_as_current_span("fast_f1")
def fast_f1():
    fastf1.Cache.enable_cache('./cache')
    fastf1.logger.LoggingManager.debug = False
    fastf1.logger.LoggingManager.set_level(logging.WARNING)
    fastf1.logger.set_log_level(logging.WARNING)


@tracer.start_as_current_span("log")
def log() -> Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(pathname)s:%(lineno)d --- %(message)s",  # Log format
        handlers=[
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger(__name__)
