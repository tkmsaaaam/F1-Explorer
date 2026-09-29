import logging

import pytest

from f1_explorer.config import log


@pytest.fixture
def restore_logger_levels():
    loggers = [logging.getLogger(), logging.getLogger("fastf1"),
               logging.getLogger("kaleido"), logging.getLogger("choreographer")]
    original_levels = [logger.level for logger in loggers]
    original_handlers = logging.getLogger().handlers[:]
    yield original_levels[0]
    for logger, level in zip(loggers, original_levels):
        logger.setLevel(level)
    logging.getLogger().handlers[:] = original_handlers


def test_log_uses_warning_defaults_without_environment_override(monkeypatch, restore_logger_levels):
    monkeypatch.delenv("F1_LOG_LEVEL", raising=False)

    log()

    assert logging.getLogger().level == restore_logger_levels
    for name in ("fastf1", "kaleido", "choreographer"):
        assert logging.getLogger(name).level == logging.WARNING


def test_log_applies_debug_environment_override(monkeypatch, restore_logger_levels):
    monkeypatch.setenv("F1_LOG_LEVEL", "DEBUG")

    log()

    assert logging.getLogger().level == logging.DEBUG
    for name in ("fastf1", "kaleido", "choreographer"):
        assert logging.getLogger(name).level == logging.DEBUG


def test_log_rejects_invalid_environment_override(monkeypatch, restore_logger_levels):
    monkeypatch.setenv("F1_LOG_LEVEL", "verbose")

    with pytest.raises(ValueError, match="Invalid F1_LOG_LEVEL: VERBOSE"):
        log()
