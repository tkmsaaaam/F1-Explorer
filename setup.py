import json
import logging
from logging import Logger
from typing import Any

import fastf1
from opentelemetry import trace

tracer = trace.get_tracer(__name__)


@tracer.start_as_current_span("load_config")
def load_config() -> Any | None:
    config = None
    with open('./config.json', 'r', encoding='utf-8') as file:
        config = json.load(file)
    return config


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
