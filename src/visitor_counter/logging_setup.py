from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    app_handler = RotatingFileHandler(log_dir / "application.log", maxBytes=5_000_000, backupCount=5)
    app_handler.setFormatter(formatter)
    app_handler.setLevel(logging.INFO)

    error_handler = RotatingFileHandler(log_dir / "errors.log", maxBytes=2_000_000, backupCount=5)
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.INFO)

    root.addHandler(app_handler)
    root.addHandler(error_handler)
    root.addHandler(stream_handler)
