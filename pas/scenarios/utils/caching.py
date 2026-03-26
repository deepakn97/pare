"""Adapted caching utilities from meta-are/are/simulation/scenarios/utils/caching.py for PAS scenarios.

The changes are minimal and primarily involve updating imports and type hints to reference PAS-specific classes.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import xxhash
from dotenv import load_dotenv

from pas.scenarios.validation_result import PASScenarioValidationResult

if TYPE_CHECKING:
    from pas.scenarios import PASScenario
    from pas.scenarios.config import ScenarioRunnerConfig

load_dotenv()

logger = logging.getLogger(__name__)


def get_run_id(scenario: PASScenario, runner_config: ScenarioRunnerConfig | None) -> str:
    """Generate a unique run ID for the scenario and configuration.

    Args:
        scenario: The scenario object.
        runner_config: The configuration for the scenario runner.

    Returns:
        A string representing the unique run ID.
    """
    config_hash = ""
    if runner_config is not None:
        config_hash = f"_{runner_config.get_config_hash()}"

    if hasattr(scenario, "run_number") and scenario.run_number is not None:
        return f"{scenario.scenario_id}_run_{scenario.run_number}{config_hash}"
    return f"{scenario.scenario_id}{config_hash}"


@dataclass
class CachedScenarioResult:
    """Cached representation of a scenario result."""

    # Core result data
    success: bool | None
    exception_type: str | None
    exception_message: str | None
    export_path: str | None
    rationale: str | None
    duration: float | None

    # PAS-specific metrics
    proposal_count: int
    acceptance_count: int
    read_only_actions: int
    write_actions: int
    number_of_turns: int

    # Cache metadata
    cache_key: str
    scenario_id: str
    run_number: int | None
    config_hash: str
    scenario_hash: str

    @classmethod
    def from_scenario_result(
        cls,
        scenario_result: PASScenarioValidationResult,
        scenario: PASScenario,
        runner_config: ScenarioRunnerConfig,
    ) -> CachedScenarioResult:
        """Create a cached result from a scenario validation result.

        Args:
            scenario_result: The validation result from running the scenario.
            scenario: The scenario object.
            runner_config: The configuration for the scenario runner.

        Returns:
            A CachedScenarioResult instance.
        """
        cache_key = get_run_id(scenario, runner_config)
        config_hash = _generate_config_hash(runner_config)
        scenario_hash = _generate_scenario_hash(scenario)

        return cls(
            success=scenario_result.success,
            exception_type=(type(scenario_result.exception).__name__ if scenario_result.exception else None),
            exception_message=(str(scenario_result.exception) if scenario_result.exception else None),
            export_path=scenario_result.export_path,
            rationale=scenario_result.rationale,
            duration=scenario_result.duration,
            proposal_count=scenario_result.proposal_count,
            acceptance_count=scenario_result.acceptance_count,
            read_only_actions=scenario_result.read_only_actions,
            write_actions=scenario_result.write_actions,
            number_of_turns=scenario_result.number_of_turns,
            cache_key=cache_key,
            scenario_id=scenario.scenario_id,
            run_number=getattr(scenario, "run_number", None),
            config_hash=config_hash,
            scenario_hash=scenario_hash,
        )

    def to_json(self) -> str:
        """Serialize the cached result to JSON.

        Returns:
            JSON string representation of the cached result.
        """
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> CachedScenarioResult:
        """Deserialize a cached result from JSON.

        Args:
            json_str: JSON string to deserialize.

        Returns:
            A CachedScenarioResult instance.
        """
        data = json.loads(json_str)
        return cls(**data)

    def to_scenario_result(self) -> PASScenarioValidationResult:
        """Convert back to a PASScenarioValidationResult.

        Returns:
            A PASScenarioValidationResult instance.
        """
        exception = None
        if self.exception_type and self.exception_message:
            exception = Exception(f"{self.exception_type}: {self.exception_message}")

        return PASScenarioValidationResult(
            success=self.success,
            exception=exception,
            export_path=self.export_path,
            rationale=self.rationale,
            duration=self.duration,
            proposal_count=self.proposal_count,
            acceptance_count=self.acceptance_count,
            read_only_actions=self.read_only_actions,
            write_actions=self.write_actions,
            number_of_turns=self.number_of_turns,
        )


def _generate_cache_key(runner_config: ScenarioRunnerConfig, scenario: PASScenario) -> str:
    """Generate a unique cache key for the scenario and configuration."""
    return get_run_id(scenario=scenario, runner_config=runner_config)


def _generate_config_hash(runner_config: ScenarioRunnerConfig) -> str:
    """Generate a hash of the runner configuration for cache validation.

    This hash includes only fields that affect scenario execution results.
    It serves as a secondary validation to catch hash collisions in the cache key.

    Uses model aliases if available (canonical identifiers that stay consistent
    even when deployment paths change). Falls back to model_name if no alias set.

    Args:
        runner_config: The configuration for the scenario runner.

    Returns:
        A string representing the hash of the configuration.
    """
    # Use aliases if available, otherwise fall back to model_name
    user_model = runner_config.user_model_alias or runner_config.user_engine_config.model_name
    observe_model = runner_config.observe_model_alias or runner_config.observe_engine_config.model_name
    execute_model = runner_config.execute_model_alias or runner_config.execute_engine_config.model_name

    config_dict = {
        "agent_type": runner_config.agent_type,
        "user_model": user_model,
        "user_max_iterations": runner_config.user_max_iterations,
        "observe_model": observe_model,
        "observe_max_iterations": runner_config.observe_max_iterations,
        "execute_model": execute_model,
        "execute_max_iterations": runner_config.execute_max_iterations,
        "oracle": runner_config.oracle,
        "max_turns": runner_config.max_turns,
        "simulated_generation_time_mode": runner_config.simulated_generation_time_mode,
        "tool_augmentation": asdict(runner_config.tool_augmentation_config)
        if runner_config.tool_augmentation_config
        else None,
        "env_events_config": asdict(runner_config.env_events_config) if runner_config.env_events_config else None,
    }
    config_json = json.dumps(config_dict, sort_keys=True)
    return xxhash.xxh64(config_json.encode()).hexdigest()[:16]


def _generate_scenario_hash(scenario: PASScenario) -> str:
    """Generate a hash of the scenario to detect changes.

    Args:
        scenario: The scenario object.

    Returns:
        A string representing the hash of the scenario.
    """
    scenario_dict = {
        "scenario_id": scenario.scenario_id,
        "seed": scenario.seed,
        "nb_turns": scenario.nb_turns,
        "config": scenario.config,
        "additional_system_prompt": scenario.additional_system_prompt,
        "tags": [str(tag) for tag in scenario.tags],
        "events_count": len(scenario.events) if scenario.events else 0,
        "event_types": ([str(event.event_type) for event in scenario.events] if scenario.events else []),
    }
    scenario_json = json.dumps(scenario_dict, sort_keys=True)
    return xxhash.xxh64(scenario_json.encode()).hexdigest()[:16]


def _get_cache_dir() -> Path:
    """Get the cache directory path.

    Priority:
    1. PAS_CACHE_DIR environment variable
    2. Persistent config file setting (~/.config/pas/config.json)
    3. Default: ~/.cache/pas/scenario_results

    Returns:
        Path to the cache directory.
    """
    # Check environment variable first
    cache_dir = os.environ.get("PAS_CACHE_DIR")
    if cache_dir:
        return Path(cache_dir)

    # Check config file
    config_file = Path.home() / ".config" / "pas" / "config.json"
    if config_file.exists():
        try:
            with open(config_file) as f:
                config = json.load(f)
                if "cache_dir" in config:
                    return Path(config["cache_dir"])
        except (json.JSONDecodeError, OSError):
            pass  # Fall through to default

    # Default
    return Path.home() / ".cache" / "pas" / "scenario_results"


def _get_cache_file_path(cache_key: str) -> Path:
    """Get the full path for a cache file.

    Args:
        cache_key: The cache key for the scenario.

    Returns:
        Path to the cache file.
    """
    cache_dir = _get_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{cache_key}.json"


def maybe_load_cached_result(
    runner_config: ScenarioRunnerConfig,
    scenario: PASScenario,
) -> PASScenarioValidationResult | None:
    """Try to load a cached result for the scenario and configuration."""
    try:
        cache_key = _generate_cache_key(runner_config, scenario)
        cache_file = _get_cache_file_path(cache_key)

        if not cache_file.exists():
            return None

        # Load and validate the cached result
        with open(cache_file) as f:
            cached_result = CachedScenarioResult.from_json(f.read())

        # Validate that the cache is still valid
        current_config_hash = _generate_config_hash(runner_config)
        current_scenario_hash = _generate_scenario_hash(scenario)

        if cached_result.config_hash != current_config_hash or cached_result.scenario_hash != current_scenario_hash:
            logger.debug(f"Cache invalidated for {scenario.scenario_id} due to config/scenario changes")
            return None

        if cached_result.exception_type is not None:
            logger.info(
                f"Ignoring cached result with exception for {scenario.scenario_id}: {cached_result.exception_type}"
            )
            return None

        logger.info(f"Loading cached result for scenario {scenario.scenario_id}")
        return cached_result.to_scenario_result()

    except Exception as e:
        logger.warning(f"Failed to load cached result for {scenario.scenario_id}: {e}")
        return None


def write_cached_result(
    runner_config: ScenarioRunnerConfig,
    scenario: PASScenario,
    result: PASScenarioValidationResult,
) -> None:
    """Write a scenario result to cache."""
    try:
        cached_result = CachedScenarioResult.from_scenario_result(result, scenario, runner_config)

        cache_file = _get_cache_file_path(cached_result.cache_key)

        with open(cache_file, "w") as f:
            f.write(cached_result.to_json())

        logger.debug(f"Cached result for scenario {scenario.scenario_id}")

    except Exception as e:
        logger.warning(f"Failed to cache result for {scenario.scenario_id}: {e}")


def clear_cache() -> None:
    """Clear all cached scenario results."""
    try:
        cache_dir = _get_cache_dir()
        if cache_dir.exists():
            for cache_file in cache_dir.glob("*.json"):
                cache_file.unlink()
            logger.info("Cleared scenario result cache")
    except Exception as e:
        logger.warning(f"Failed to clear cache: {e}")


def get_cache_stats() -> dict[str, Any]:
    """Get statistics about the cache."""
    try:
        cache_dir = _get_cache_dir()
        if not cache_dir.exists():
            return {"cache_dir": str(cache_dir), "file_count": 0, "total_size": 0}

        cache_files = list(cache_dir.glob("*.json"))
        total_size = sum(f.stat().st_size for f in cache_files)

        return {
            "cache_dir": str(cache_dir),
            "file_count": len(cache_files),
            "total_size": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
        }
    except Exception as e:
        logger.warning(f"Failed to get cache stats: {e}")
        return {"error": str(e)}
