"""Scenario execution utilities for PARE benchmark pipeline."""

from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING

from are.simulation.utils.countable_iterator import CountableIterator

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pare.scenarios import PAREScenario

logger = logging.getLogger(__name__)


def multiply_scenarios_iterator(
    scenarios_iterator: CountableIterator[PAREScenario],
    num_runs: int,
) -> CountableIterator[PAREScenario]:
    """Multiply the scenarios iterator to run each scenario N times.

    This function creates multiple copies of each scenario with different run numbers
    to improve variance in the results.

    Args:
        scenarios_iterator: CountableIterator of scenarios to multiply.
        num_runs: Number of times to run each scenario.

    Returns:
        CountableIterator with each scenario repeated num_runs times.
    """

    def iterator() -> Iterator[PAREScenario]:
        # Collect all scenarios to avoid iterator exhaustion
        scenarios_list = list(scenarios_iterator)

        for scenario in scenarios_list:
            for run_num in range(num_runs):
                # Create a deep copy of the scenario for each run
                scenario_copy = copy.deepcopy(scenario)
                # Set the run number (1-indexed)
                scenario_copy.run_number = run_num + 1
                yield scenario_copy

    # Calculate new total count
    new_total_count = scenarios_iterator.total_count * num_runs if scenarios_iterator.total_count is not None else None

    return CountableIterator(iterator(), new_total_count)


# ! TODO: Implement preprocess_scenarios_iterator() to apply config to scenarios
#         (e.g., set metadata, apply augmentation configs)

# ! TODO: Implement run_scenarios() that calls PAREMultiScenarioRunner.run_with_scenarios()
#         - Caching and parallel execution handled by the runner (pare/multi_scenario_runner.py)

# ! TODO: Implement run_benchmark() as main entry point (like meta-ARE's run_dataset):
#         1. Load scenarios via load_scenarios_from_registry()
#         2. Multiply scenarios if num_runs > 1
#         3. Preprocess scenarios with config
#         4. Call run_scenarios() with MultiScenarioRunnerConfig
#         5. Return PAREMultiScenarioValidationResult
