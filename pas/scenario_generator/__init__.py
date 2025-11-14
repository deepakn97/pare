"""Scenario generator module for registering custom scenarios."""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from are.simulation.scenarios.utils.registry import ScenarioRegistry

logger = logging.getLogger(__name__)


def register_custom_scenarios(registry: ScenarioRegistry) -> None:  # noqa: C901
    """Register all custom scenarios from this project with the provided registry.

    This function is called by the meta-ARE framework when it discovers the
    custom scenarios entry point. It imports all custom scenario modules,
    which triggers the @register_scenario decorators.

    Args:
        registry: The ScenarioRegistry instance to register with
    """
    logger.info("Registering custom scenarios from ProactiveAgentSandbox")

    # Import modules containing custom scenarios
    custom_scenario_modules = [
        "pas.scenario_generator.example_proactive_scenarios.scenario",
        "pas.scenario_generator.example_proactive_scenarios.scenario_with_all_apps_init",
        "pas.scenario_generator.example_proactive_scenarios.scenario_with_all_pas_apps",
        "pas.scenario_generator.example_proactive_scenarios.very_basic_demo_pas_app",
        # Add other custom scenario modules here as needed
    ]

    # Auto-discover generated scenario files by file path; import by spec (no package required)
    base_dir = Path(__file__).resolve().parents[1] / "scenarios" / "generated_scenarios"
    discovered_files: list[Path] = []
    excluded_filenames = {"meeting_invite_coordination.py", "project_feedback_share.py", "weekend_grocery_pickup.py"}
    if base_dir.exists():
        for p in base_dir.rglob("*.py"):
            if p.name.startswith("__"):
                continue
            if "__pycache__" in str(p):
                continue
            if p.name in excluded_filenames:
                # Skip baseline scenarios that are registered elsewhere to avoid duplicate IDs
                continue
            discovered_files.append(p)
    else:
        logger.warning(f"Generated scenarios directory not found: {base_dir}")

    imported_count = 0
    for module_name in custom_scenario_modules:
        try:
            importlib.import_module(module_name)
            imported_count += 1
            logger.debug(f"Imported custom scenario module: {module_name}")
        except Exception as e:
            logger.warning(f"Failed to import custom scenario module {module_name}: {e}", exc_info=True)

    # Import generated scenario files by file path to support non-package directories
    for idx, file_path in enumerate(sorted(discovered_files)):
        try:
            module_name = f"pas.scenarios.generated_dynamic.module_{idx}"
            spec = importlib.util.spec_from_file_location(module_name, str(file_path))
            if spec is None or spec.loader is None:
                raise ImportError(f"spec_from_file_location failed for {file_path}")  # noqa: TRY301
            module = importlib.util.module_from_spec(spec)
            # Ensure the module is discoverable by dataclasses/ARE during class creation
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            imported_count += 1
            logger.debug(f"Imported generated scenario file by path: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to import generated scenario file {file_path}: {e}", exc_info=True)

    logger.info(f"Registered custom scenarios from {imported_count} modules")
