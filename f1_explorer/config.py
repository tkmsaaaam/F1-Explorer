from __future__ import annotations

import json
import logging
import os
from enum import Enum
from logging import Logger
from typing import Any, Mapping, Sequence, TYPE_CHECKING

import fastf1
import structlog
# noinspection PyPackageRequirements
from opentelemetry import trace

if TYPE_CHECKING:
    from f1_explorer.separator_estimator import SeparatorBoundary

tracer = trace.get_tracer(__name__)


class SessionCategory(Enum):
    FreePractice = "FreePractice"
    Qualifying = "Qualifying"
    Race = "Race"


class Config:
    def __init__(self, year: int, race_number: int, session: str, corners: dict[str, list[float]],
                 separator: list[float], comparison: list[list[dict[str, Any]]],
                 separator_boundaries: Sequence[SeparatorBoundary | Mapping[str, float | int]] | None = None):
        self.year = year
        self.round = race_number
        self.session = session
        self.corners = corners
        self.separator = separator
        self.separator_boundaries = list(separator_boundaries or [])
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

    def get_separator_boundaries(self):
        return self.separator_boundaries

    def set_separator(
        self,
        separator: list[float],
        boundaries: Sequence[SeparatorBoundary | Mapping[str, float | int]] | None = None,
    ) -> None:
        """Replace the active separator list after session-specific loading."""
        self.separator = list(separator)
        self.separator_boundaries = list(boundaries or [])

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
    # Older sample files use lower-case keys while the original loader only
    # accepted the title-cased spelling.  Accept both spellings so a config
    # can be migrated incrementally without losing user settings.
    separator = config.get('Separator', config.get('separator', []))
    corners = config.get('Corners', config.get('corners', {}))
    comparison = config.get('Comparison', config.get('comparison', []))
    if not isinstance(separator, list):
        # A scoped map belongs to the automatic estimator, not the active
        # legacy fallback list.
        separator = []
    if not isinstance(corners, dict):
        corners = {}
    if not isinstance(comparison, list):
        comparison = []
    return Config(config['Year'], config['Round'], config['Session'], corners, separator, comparison)


@tracer.start_as_current_span("fast_f1")
def fast_f1():
    fastf1.Cache.enable_cache('./cache')


@tracer.start_as_current_span("log")
def log() -> structlog.stdlib.BoundLogger:
    level_name = os.environ.get('F1_LOG_LEVEL', '').upper()
    level = logging.getLevelNamesMapping().get(level_name)
    if level_name and level is None:
        raise ValueError(f'Invalid F1_LOG_LEVEL: {level_name}')
    if level is not None:
        logging.basicConfig(level=level)
        logging.getLogger().setLevel(level)
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    )
    logging.getLogger('choreographer').setLevel(level if level is not None else logging.WARNING)
    # noinspection SpellCheckingInspection
    logging.getLogger('fastf1').setLevel(level if level is not None else logging.WARNING)
    logging.getLogger('kaleido').setLevel(level if level is not None else logging.WARNING)
    return structlog.get_logger(__name__)
