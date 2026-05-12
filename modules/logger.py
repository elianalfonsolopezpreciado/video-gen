"""
modules/logger.py - Logger CLI (sin GUI).
"""

import logging
import os
from datetime import datetime

_loggers: dict = {}


def setup_logger(log_dir: str = "logs") -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"session_{timestamp}.log")

    logger = logging.getLogger("canal")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-7s] %(message)s", datefmt="%H:%M:%S"
    )

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    _loggers["canal"] = logger
    logger.info(f"Logger iniciado -> {log_file}")
    return logger


def get_logger() -> logging.Logger:
    return _loggers.get("canal", logging.getLogger("canal"))
