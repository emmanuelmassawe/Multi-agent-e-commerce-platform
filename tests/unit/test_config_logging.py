"""Settings and structured logging smoke tests."""

import logging

from clos.config import Settings
from clos.logging import configure_logging


def test_settings_defaults() -> None:
    settings = Settings()
    assert settings.app_env == "local"
    assert settings.log_level == "INFO"


def test_configure_logging_accepts_level() -> None:
    configure_logging("DEBUG")
    assert logging.getLogger().level == logging.DEBUG
