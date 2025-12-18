from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from pytz import timezone

from pas.logging_config import configure_logging, suppress_noisy_are_loggers, suppress_noisy_loggers


def get_pst_time() -> str:
    """Get the current time in PST."""
    date_format = "%Y%m%d_%H%M%S"
    date = datetime.now(tz=UTC)
    date = date.astimezone(timezone("US/Pacific"))
    return date.strftime(date_format)


def setup_logging(
    scenario_id: str,
    level: str = "INFO",
    log_dir: str | Path = "logs",
    experiment_name: str = "demo",
    use_tqdm: bool = True,
    log_to_file: bool = False,
    verbose: bool = False,
) -> None:
    """Configure logging for PAS."""
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise TypeError(f"Invalid log level: {level}")

    if isinstance(log_dir, str):
        log_dir = Path(log_dir)

    # Configure logging with the specified level
    configure_logging(level=numeric_level, use_tqdm=use_tqdm, log_dir=log_dir)
    suppress_noisy_loggers()
    if not verbose:
        suppress_noisy_are_loggers()
