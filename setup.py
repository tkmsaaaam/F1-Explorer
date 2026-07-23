import json
import logging
from enum import Enum
from logging import Logger
from typing import Any

import fastf1
import structlog
# noinspection PyPackageRequirements
from opentelemetry import trace

tracer = trace.get_tracer(__name__)


class SessionCategory(Enum):
    FreePractice = "FreePractice"
    Qualifying = "Qualifying"
    Race = "Race"


class Config:
    def __init__(self, year: int, race_number: int, session: str, corners: dict[str, list[float]],
                 separator: list[int], comparison: list[list[dict[str, Any]]]):
        self.year = year
        self.round = race_number
        self.session = session
        self.corners = corners
        self.separator = separator
        self.comparison = comparison
        if session in {'FP1', 'FP2', 'FP3'}:
            self.session_category = SessionCategory.FreePractice
        elif session in {'SQ', 'Q'}:
            self.session_category = SessionCategory.Qualifying
        elif session in {'S', 'R'}:
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

    def get_comparison(self):
        return self.comparison

    def set_attribute_to_span(self):
        trace.get_current_span().set_attributes(
            {"year": self.get_year(), "round": self.get_round(), "session": self.get_session()})


def validate_config(config: dict[str, Any]):
    if 'Year' not in config:
        raise Exception("Year must be provided")
    if 'Round' not in config:
        raise Exception("Round must be provided")
    if 'Session' not in config:
        raise Exception("Session must be provided")
    if config['Session'] not in {'FP1', 'FP2', 'FP3', 'SQ', 'S', 'Q', 'R'}:
        raise Exception("Session is invalid")


@tracer.start_as_current_span("load_config")
def load_config() -> Config:
    config = None
    with open('./config.json', 'r', encoding='utf-8') as file:
        config = json.load(file)
    if config is None:
        raise Exception("Config must be provided")
    validate_config(config)
    separator = config['Separator'] if 'Separator' in config else []
    corners = config['Corners'] if 'Corners' in config else {}
    comparison = config['Comparison'] if 'Comparison' in config else []
    return Config(config['Year'], config['Round'], config['Session'], corners, separator, comparison)


@tracer.start_as_current_span("fast_f1")
def fast_f1():
    fastf1.Cache.enable_cache('./cache')


@tracer.start_as_current_span("log")
def log() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    )
    logging.getLogger('choreographer').setLevel(logging.WARNING)
    # noinspection SpellCheckingInspection
    logging.getLogger('fastf1').setLevel(logging.WARNING)
    logging.getLogger('kaleido').setLevel(logging.WARNING)
    return structlog.get_logger(__name__)
