import json
import logging
from logging import Logger
from typing import Any

import fastf1


def load_config() -> Any | None:
    config = None
    with open('./config.json', 'r', encoding='utf-8') as file:
        config = json.load(file)
    return config


def fast_f1():
    fastf1.Cache.enable_cache('./cache')
    fastf1.logger.LoggingManager.debug = False
    fastf1.logger.LoggingManager.set_level(logging.WARNING)
    fastf1.logger.set_log_level(logging.WARNING)


def log() -> Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",  # Log format
        handlers=[
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger(__name__)
