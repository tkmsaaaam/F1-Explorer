import json
import logging
from enum import Enum
from logging import Logger
from typing import Any

import fastf1
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

class SessionCategory(Enum):
    FreePractice = "FreePractice"
    Qualifying = "Qualifying"
    Race = "Race"

class Config:
    def __init__(self, year: int, round: int, session: str, corners: dict[str, list[float]], separator: list[int]):
        self.year = year
        self.round = round
        self.session = session
        self.corners = corners
        self.separator = separator
        if session == 'FP1' or session == 'FP2' or session == 'FP3':
            self.session_category = SessionCategory.FreePractice
        elif session == 'SQ' or session == 'Q':
            self.session_category = SessionCategory.Qualifying
        elif session == 'SR' or session == 'R':
            self.session_category = SessionCategory.Race
        else:
            raise Exception("Session is invalid")

    def get_year(self):
        return self.year

    def get_round(self):
        return self.round

    def get_session(self):
        return self.session

    def get_session_category(self):
        return self.session_category

    def get_corners(self):
        return self.corners

    def get_separator(self):
        return self.separator

def validate_config(config: dict[str, Any]):
    if 'Year' not in config:
        raise Exception("Year must be provided")
    if 'Round' not in config:
        raise Exception("Round must be provided")
    if 'Session' not in config:
        raise Exception("Session must be provided")
    if not config['Session'] != 'FP1' and 'FP2' and 'FP3' and 'SQ' and 'Q' and 'R' and 'SR':
        raise Exception("Session is invalid")

@tracer.start_as_current_span("load_config")
def load_config() -> Config:
    config = None
    with open('./config.json', 'r', encoding='utf-8') as file:
        config = json.load(file)
    if config is None:
        raise Exception("Config must be provided")
    validate_config(config)
    separator = []
    if 'Separator' in config:
        separator = config['Separator']
    corners = {}
    if 'Corners' in config:
        corners = config['Corners']
    return Config(config['Year'], config['Round'], config['Session'], corners, separator)


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
