"""Scenario loader for PAS benchmark pipeline.

Loads scenarios from the PAS registry. Future versions will support
loading from JSON files and HuggingFace datasets.
"""

from __future__ import annotations

import logging
import os
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from are.simulation.utils.countable_iterator import CountableIterator

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pas.scenarios import PASScenario

logger = logging.getLogger(__name__)

# Default splits directory (relative to this file)
_DEFAULT_SPLITS_DIR = Path(__file__).parent.parent.parent / "data" / "splits"


class Split(str, Enum):
    """Benchmark split types."""

    FULL = "full"
    ABLATION = "ablation"


def get_splits_dir() -> Path:
    """Get the splits directory from environment variable or default.

    Returns:
        Path to the splits directory.
    """
    env_path = os.environ.get("PAS_BENCHMARK_SPLITS_DIR")
    if env_path:
        return Path(env_path)
    return _DEFAULT_SPLITS_DIR


def load_scenario_ids_from_file(file_path: str | Path) -> list[str]:
    """Load scenario IDs from a file (one ID per line).

    Args:
        file_path: Path to file containing scenario IDs.

    Returns:
        List of scenario IDs.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Scenario IDs file not found: {path}")

    scenario_ids = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if line and not line.startswith("#"):
                scenario_ids.append(line)

    logger.info(f"Loaded {len(scenario_ids)} scenario IDs from {path}")
    return scenario_ids


def load_scenarios_from_registry(
    scenario_ids: list[str] | None = None,
    limit: int | None = None,
) -> CountableIterator[PASScenario]:
    """Load scenarios from PAS registry.

    Scenarios are instantiated lazily as the iterator is consumed.

    Args:
        scenario_ids: Specific scenario IDs to load. If None, loads all registered scenarios.
        limit: Maximum number of scenarios to load.

    Returns:
        CountableIterator of PASScenario objects.
    """
    from pas.scenarios import registry

    # Get scenario IDs to load
    if scenario_ids is None:
        all_scenarios = registry.get_all_scenarios()
        scenario_ids = list(all_scenarios.keys())
        logger.info(f"Found {len(scenario_ids)} registered scenarios")

    # Apply limit to scenario IDs before loading
    if limit and len(scenario_ids) > limit:
        logger.info(f"Limiting to {limit} scenarios")
        scenario_ids = scenario_ids[:limit]

    def generator() -> Iterator[PASScenario]:
        for scenario_id in scenario_ids:
            try:
                scenario_class = registry.get_scenario(scenario_id)
                yield scenario_class()
                logger.debug(f"Loaded scenario: {scenario_id}")
            except KeyError:
                logger.warning(f"Scenario not found in registry: {scenario_id}")
            except Exception as e:
                logger.warning(f"Failed to instantiate scenario {scenario_id}: {e}")

    return CountableIterator(generator(), len(scenario_ids))


def load_scenarios_by_split(
    split: Split,
    limit: int | None = None,
) -> CountableIterator[PASScenario]:
    """Load scenarios for a specific benchmark split.

    Args:
        split: The benchmark split to load (full or ablation).
        limit: Maximum number of scenarios to load.

    Returns:
        CountableIterator of PASScenario objects.

    Raises:
        FileNotFoundError: If split file doesn't exist.
    """
    splits_dir = get_splits_dir()
    split_file = splits_dir / f"{split.value}.txt"

    if not split_file.exists():
        raise FileNotFoundError(
            f"Split file not found: {split_file}. "
            f"Create {split_file} with scenario IDs (one per line), "
            f"or set PAS_BENCHMARK_SPLITS_DIR environment variable."
        )

    scenario_ids = load_scenario_ids_from_file(split_file)
    logger.info(f"Loading {len(scenario_ids)} scenarios for split '{split.value}'")

    return load_scenarios_from_registry(scenario_ids=scenario_ids, limit=limit)


# ! TODO: Implement load_scenarios_from_json() for loading from local JSON files
# ! TODO: Implement load_scenarios_from_huggingface() for loading from HuggingFace datasets
# ! TODO: Implement setup_scenarios_iterator() as unified entry point that routes to
#         registry, local JSON, or HuggingFace based on arguments (similar to meta-are)
