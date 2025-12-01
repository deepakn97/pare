"""Standalone scenario registry for PAS.

This module provides PAS's own scenario registry that is completely independent
of Meta-ARE's scenario registry. PAS scenarios are registered exclusively here.
"""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import logging
from typing import TYPE_CHECKING, TypeVar

from are.simulation.scenarios.utils.registry import (
    ScenarioRegistry as BaseScenarioRegistry,
)
from are.simulation.scenarios.utils.registry import (
    register_scenario as meta_register_scenario,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from are.simulation.scenarios.scenario import Scenario

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="Scenario")

# Entry point group name for PAS scenarios
SCENARIO_ENTRY_POINT_GROUP = "pas.scenarios"


class ScenarioRegistry(BaseScenarioRegistry):
    """Standalone scenario registry for PAS.

    This registry extends Meta-ARE's ScenarioRegistry but operates completely independently.
    It only registers PAS scenarios and never loads Meta-ARE's built-in scenarios.
    """

    def _discover_and_import_scenarios(self) -> None:
        """Discover and import PAS scenario modules using entry points.

        This method overrides the parent to skip Meta-ARE's built-in scenarios entirely.
        Only PAS scenarios from entry points are loaded.
        """
        if self._scenarios_discovered:  # type: ignore[has-type]
            return

        # Count how many entry points we've loaded
        loaded_entry_points = 0

        # Discover scenarios via entry points (PAS scenarios only)
        for entry_point in importlib_metadata.entry_points(group=SCENARIO_ENTRY_POINT_GROUP):
            try:
                logger.info(f"Loading scenario entry point: {entry_point.name} from {entry_point.dist}")

                # Load the entry point
                scenario_loader = entry_point.load()

                # If it's a callable, call it with this registry
                if callable(scenario_loader):
                    scenario_loader(self)
                    loaded_entry_points += 1
                else:
                    logger.warning(f"Entry point {entry_point.name} is not callable, skipping")
            except Exception as e:
                logger.warning(
                    f"Failed to load scenario entry point {entry_point.name}: {e}",
                    exc_info=True,
                )

        self._scenarios_discovered = True
        logger.info(f"Discovered and loaded {loaded_entry_points} PAS scenario entry points")


# Create a singleton instance of the PAS registry
registry = ScenarioRegistry()


def register_scenario(scenario_id: str) -> Callable[[type[T]], type[T]]:
    """Decorator to register scenarios with both PAS and Meta-ARE registries.

    This keeps PAS's standalone registry in sync with Meta-ARE's global registry so
    scenarios can be discovered by either runtime.
    """
    pas_register = registry.register(scenario_id)
    meta_register = meta_register_scenario(scenario_id)

    def decorator(cls: type[T]) -> type[T]:
        cls = pas_register(cls)
        cls = meta_register(cls)
        return cls

    return decorator
