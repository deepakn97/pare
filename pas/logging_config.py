"""Utilities for configuring PAS logging."""

from __future__ import annotations

import logging
import sys
from pathlib import Path  # noqa: TC003 - used at runtime for directory operations

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


def configure_logging(
    level: int = logging.INFO,
    use_tqdm: bool = False,
    log_dir: Path | None = None,
    scenario_id: str | None = None,
    run_number: int | None = None,
) -> None:
    """Configure logging for PAS application.

    This configures the root logger, which all other loggers propogate to.
    Uses ARE's formatter and handler for consistent formatting.

    Args:
        level: The logging level (default: logging.INFO)
        use_tqdm: Whether to use tqdm-compatible logging (for progress bars)
        log_dir: The directory to log to (default: None)
        scenario_id: The scenario ID to log to (default: None)
        run_number: The run number to log to (default: None)
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
        if scenario_id is None:
            import warnings

            warnings.warn("log_dir provided but scenario_id is None - skipping file logging", stacklevel=2)
        else:
            file_formatter = PASFormatter(use_colors=False)
            run_suffix = run_number if run_number is not None else 0

            # Build per-scenario log directories
            pas_log_dir = log_dir / f"{scenario_id}" / "pas"
            agent_log_dir = log_dir / f"{scenario_id}" / "agent"

            # Create directories if they don't exist
            pas_log_dir.mkdir(parents=True, exist_ok=True)
            agent_log_dir.mkdir(parents=True, exist_ok=True)

            # Any logs other than Agents
            pas_file_handler = logging.FileHandler(pas_log_dir / f"run_{run_suffix}.log", encoding="utf-8")
            pas_file_handler.setLevel(logging.DEBUG)
            pas_file_handler.setFormatter(file_formatter)
            pas_file_handler.addFilter(_ExcludeAgentLogsFilter())
            root_logger.addHandler(pas_file_handler)

            # Agent logs only
            agent_file_handler = logging.FileHandler(agent_log_dir / f"run_{run_suffix}.log", encoding="utf-8")
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
    """Suppress noisy loggers from third-party libraries and ARE simulation module."""
    import litellm

    # Suppress litellm's "Give Feedback" messages printed during retries
    litellm.suppress_debug_info = True

    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("are.simulation.apps").setLevel(logging.WARNING)
    logging.getLogger("are.simulation.environment").setLevel(logging.WARNING)
    logging.getLogger("are.simulation.validation.judge").setLevel(logging.WARNING)


def suppress_noisy_are_loggers() -> None:
    """Suppress noisy loggers from the ARE simulation module."""
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
