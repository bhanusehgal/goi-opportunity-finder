"""Logging setup for repeatable daily runs."""

from __future__ import annotations

import logging
from pathlib import Path
import time


def setup_logging(level: str = "INFO", log_file: str | Path = "data/finder.log") -> logging.Logger:
    """Configure root logger with console + file handlers."""
    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)

    logging.Formatter.converter = time.gmtime
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    log_level = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(log_level)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    logger = logging.getLogger("goi_finder")
    logger.info("Logging initialized at level %s", level.upper())
    return logger
