"""Standalone scenario registry for PARE.

This module provides PARE's own scenario registry that is completely independent
of Meta-ARE's scenario registry. PARE scenarios are registered exclusively here.
"""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import logging
from typing import TYPE_CHECKING, TypeVar

from are.simulation.scenarios.utils.registry import ScenarioRegistry as BaseScenarioRegistry

if TYPE_CHECKING:
    from collections.abc import Callable

    from are.simulation.scenarios.scenario import Scenario

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="Scenario")

# Entry point group name for PARE scenarios
SCENARIO_ENTRY_POINT_GROUP = "pare.scenarios"


class ScenarioRegistry(BaseScenarioRegistry):
    """Standalone scenario registry for PARE.

    This registry extends Meta-ARE's ScenarioRegistry but operates completely independently.
    It only registers PARE scenarios and never loads Meta-ARE's built-in scenarios.
    """

    def _discover_and_import_scenarios(self) -> None:
        """Discover and import PARE scenario modules using entry points.

        This method overrides the parent to skip Meta-ARE's built-in scenarios entirely.
        Only PARE scenarios from entry points are loaded.
        """
        if self._scenarios_discovered:  # type: ignore[has-type]
            return

        # Count how many entry points we've loaded
        loaded_entry_points = 0

        # Discover scenarios via entry points (PARE scenarios only)
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
        logger.info(f"Discovered and loaded {loaded_entry_points} PARE scenario entry points")


# Create a singleton instance of the PARE registry
registry = ScenarioRegistry()


def register_scenario(scenario_id: str) -> Callable[[type[T]], type[T]]:
    """Decorator to register a scenario with PARE registry.

    This decorator is PARE's standalone alternative to Meta-ARE's @register_scenario.
    It registers scenarios exclusively to the PARE registry, keeping it separate from
    Meta-ARE's global registry.

    Usage:
        from pare.scenarios.registry import register_scenario

        @register_scenario('my_scenario_id')
        class MyScenario(Scenario):
            ...

    Args:
        scenario_id: The ID to register the scenario under.

    Returns:
        A decorator function that registers the scenario class.
    """
    return registry.register(scenario_id)
