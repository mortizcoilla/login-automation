from __future__ import annotations

import logging
import os
from typing import Final

from src.constants import LOG_FILE

_DEFAULT_LEVEL: Final[str] = os.getenv("LOG_LEVEL", "INFO").upper()
_LOGGER_NAME: Final[str] = "login_automation"
_FORMAT: Final[str] = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
_DATEFMT: Final[str] = "%Y-%m-%d %H:%M:%S"


def _resolve_log_path(log_file: str) -> str:
    if os.path.isabs(log_file):
        return log_file
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), log_file)


def setup_logger(
    log_file: str = LOG_FILE,
    level: str | int | None = None,
) -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level if level is not None else _DEFAULT_LEVEL)
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    file_handler = logging.FileHandler(_resolve_log_path(log_file), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME)
