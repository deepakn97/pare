"""Registration module for PAS user scenarios.

This module follows Meta-ARE's pattern for auto-registering scenarios.
It is loaded via the entry point system when the scenario registry is initialized.

The scenarios directory can be configured via the PAS_SCENARIOS_DIR environment variable.
"""

from __future__ import annotations

import importlib
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from are.simulation.scenarios.utils.registry import ScenarioRegistry

logger = logging.getLogger(__name__)


def register_pas_scenarios(registry: ScenarioRegistry) -> None:
    """Register all PAS user scenarios with the provided registry.

    This function is called by Meta-ARE's scenario registry when it discovers
    the PAS scenarios entry point. It imports all scenario modules from the
    configured scenarios directory (or user_scenarios by default).

    The scenarios directory can be configured via PAS_SCENARIOS_DIR environment variable:
    - Relative path (e.g., "user_scenarios", "generated_scenarios/3apps_group")
    - Multiple directories separated by commas (e.g., "user_scenarios,generated_scenarios/3apps_group")

    Args:
        registry: The ScenarioRegistry instance to register with.
    """
    logger.info("Registering PAS scenarios")

    # Get the base scenarios directory (parent of this file)
    base_scenarios_dir = Path(__file__).parent

    # Get scenarios directory from environment variable or use default
    scenarios_dirs_config = os.getenv("PAS_SCENARIOS_DIR", "benchmark")

    # Support multiple directories separated by commas
    scenarios_dirs = [d.strip() for d in scenarios_dirs_config.split(",")]

    total_imported = 0

    for dir_name in scenarios_dirs:
        # Resolve relative path from base scenarios directory
        scenarios_dir = base_scenarios_dir / dir_name

        if not scenarios_dir.exists():
            logger.warning(f"Scenarios directory not found: {scenarios_dir} (from PAS_SCENARIOS_DIR={dir_name})")
            continue

        logger.info(f"Discovering scenarios in: {scenarios_dir}")

        # Import all Python files in the scenarios directory
        imported_count = 0
        for file_path in scenarios_dir.glob("*.py"):
            # Skip __init__.py
            if file_path.name == "__init__.py":
                continue

            # Get module name - construct full import path
            # Convert path relative to pas/scenarios to module path
            rel_path = file_path.relative_to(base_scenarios_dir)
            module_parts = [*list(rel_path.parts[:-1]), rel_path.stem]
            module_name = f"pas.scenarios.{'.'.join(module_parts)}"

            try:
                # Import the module (triggers @register_scenario decorator)
                importlib.import_module(module_name)
                imported_count += 1
                logger.debug(f"Imported PAS scenario module: {module_name}")
            except Exception as e:
                logger.warning(f"Failed to import PAS scenario module {module_name}: {e}", exc_info=True)

        logger.info(f"Registered {imported_count} scenarios from {scenarios_dir}")
        total_imported += imported_count

    logger.info(f"Total PAS scenarios registered: {total_imported}")
