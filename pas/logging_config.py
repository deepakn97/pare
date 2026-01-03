"""Utilities for configuring PAS logging."""

from __future__ import annotations

import logging
import sys
import typing
from pathlib import Path

from are.simulation.logging_config import (
    ScenarioAwareFormatter,
    TqdmLoggingHandler,
    get_logger_run_number,
    get_logger_scenario_id,
)


class PASFormatter(ScenarioAwareFormatter):
    """Formatter with optional color support for file and console handlers."""

    def __init__(self, use_colors: bool = True) -> None:
        """Initialize formatter."""
        super().__init__()
        self.use_colors = use_colors

    def format(self, record: logging.LogRecord) -> str:
        """Format the record with Scenario ID and optionally color support."""
        scenario_id = get_logger_scenario_id()
        run_number = get_logger_run_number()

        # Add scenario ID and run number to the record if available
        if scenario_id and not hasattr(record, "scenario_id"):
            record.scenario_id = scenario_id

            if run_number is not None:
                prefix = f"[Scenario = {scenario_id}, Run = {run_number}]"
            else:
                prefix = f"[Scenario = {scenario_id}]"

            # Only add the prefix if the message doesn't already have it
            # Convert message to string first to handle non-string types (e.g., exceptions)
            msg_str = str(record.msg)
            if not msg_str.startswith(prefix):
                record.msg = f"{prefix} {msg_str}"

        # Optional Colored support
        log_fmt = self.FORMATS.get(record.levelno, self.base_format) if self.use_colors else self.base_format

        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def configure_logging(level: int = logging.INFO, use_tqdm: bool = False, log_dir: Path | None = None) -> None:
    """Configure logging for PAS application.

    This configures the root logger, which all other loggers propogate to.
    Uses ARE's formatter and handler for consistent formatting.

    Args:
        level: The logging level (default: logging.INFO)
        use_tqdm: Whether to use tqdm-compatible logging (for progress bars)
        log_dir: The directory to log to (default: None)
    """
    standard_formatter = PASFormatter()
    console_handler = TqdmLoggingHandler() if use_tqdm else logging.StreamHandler(stream=sys.stdout)

    console_handler.setLevel(level)
    console_handler.setFormatter(standard_formatter)

    root_logger = logging.getLogger()
    # Allow all logging at root level. Handlers set their own levels.
    root_logger.setLevel(logging.DEBUG)

    # Clear any existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    root_logger.addHandler(console_handler)

    if log_dir is not None:
        file_formatter = PASFormatter(use_colors=False)

        # Any logs other than Agents
        pas_file_handler = logging.FileHandler(log_dir / "pas.log", encoding="utf-8")
        pas_file_handler.setLevel(logging.DEBUG)
        pas_file_handler.setFormatter(file_formatter)
        pas_file_handler.addFilter(_ExcludeAgentLogsFilter())
        root_logger.addHandler(pas_file_handler)

        # Agent logs only
        agent_file_handler = logging.FileHandler(log_dir / "agent.log", encoding="utf-8")
        agent_file_handler.setLevel(logging.DEBUG)
        agent_file_handler.setFormatter(file_formatter)

        for logger_name in ["are.simulation.agents", "pas.agents"]:
            agent_logger = logging.getLogger(logger_name)
            for handler in agent_logger.handlers[:]:
                agent_logger.removeHandler(handler)
            agent_logger.addHandler(agent_file_handler)


class _ExcludeAgentLogsFilter(logging.Filter):
    """Filter to exclude agent logs from being logged to the PAS log file."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not (record.name.startswith("are.simulation.agents") or record.name.startswith("pas.agents"))


def suppress_noisy_loggers() -> None:
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("are.simulation.apps").setLevel(logging.WARNING)
    logging.getLogger("are.simulation.environment").setLevel(logging.WARNING)
    logging.getLogger("are.simulation.validation.judge").setLevel(logging.WARNING)


def suppress_noisy_are_loggers() -> None:
    logger_names = [
        "are.simulation.agents",
        "are.simulation.agents.default_agent",
        "are.simulation.agents.default_agent.base_agent",
    ]
    for name in logger_names:
        lg = logging.getLogger(name)
        for handler in lg.handlers[:]:
            lg.removeHandler(handler)
        lg.setLevel(logging.WARNING)


def initialise_pas_logs(*, clear_existing: bool, log_paths: typing.Sequence[Path]) -> None:
    """Prepare PAS log files, optionally clearing previous runs before logging."""
    for path in log_paths:
        resolved = path if path.is_absolute() else (Path.cwd() / path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        if clear_existing and resolved.exists():
            resolved.unlink()


def get_pas_file_logger(name: str, log_path: Path, level: int = logging.INFO) -> logging.Logger:
    """Return a logger writing to ``log_path`` without duplicating handlers."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    log_path = log_path if log_path.is_absolute() else (Path.cwd() / log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if not _has_handler(logger.handlers, log_path):
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        logger.addHandler(file_handler)
    else:
        for existing_handler in logger.handlers:
            if (
                isinstance(existing_handler, logging.FileHandler)
                and Path(existing_handler.baseFilename).resolve() == log_path.resolve()
            ):
                existing_handler.setLevel(level)
    logger.propagate = False
    return logger


def _has_handler(handlers: typing.Sequence[logging.Handler], log_path: Path) -> bool:
    resolved = log_path.resolve()
    for handler in handlers:
        if isinstance(handler, logging.FileHandler) and Path(handler.baseFilename).resolve() == resolved:
            return True
    return False


__all__ = ["get_pas_file_logger", "initialise_pas_logs"]
