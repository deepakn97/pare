from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from are.simulation.agents.llm.llm_engine import LLMEngine
from are.simulation.tool_utils import AppTool

from pas.scenario_generator.prompt.app_combination_prompts import create_app_combination_prompt

if TYPE_CHECKING:
    from are.simulation.scenarios import Scenario

logger = logging.getLogger(__name__)


class AppCombinationAgent:
    """Agent responsible for intelligently selecting app combinations for scenario generation."""

    def __init__(self, llm_engine: LLMEngine) -> None:
        """Initialize the app combination agent.

        Args:
            llm_engine: The LLM engine to use for reasoning about app combinations
        """
        self.llm_engine = llm_engine

    def generate_all_app_combinations(
        self,
        available_apps: list[str],
        total_scenarios: int,
        apps_per_scenario: int,
        app_tools_info: dict[str, list[AppTool]],
        example_scenarios: list[Scenario] | None = None,
    ) -> tuple[list[frozenset[str]], list[str]]:
        """Generate all app combinations for scenario generation at once.

        This method generates a complete set of distinct app combinations that will be used
        for generating multiple scenarios. It ensures all combinations are unique and well-distributed.

        Args:
            available_apps: List of available app names
            total_scenarios: Total number of scenarios to generate (number of combinations needed)
            apps_per_scenario: Number of apps per combination (excluding AgentUserInterface)
            app_tools_info: Dictionary mapping app names to their tools
            example_scenarios: Optional list of example scenarios for context

        Returns:
            Tuple of (list of frozensets containing unique app combinations, list of scenario summaries)
        """
        # Validate inputs
        if len(available_apps) < apps_per_scenario:
            logger.warning(
                f"Not enough apps available ({len(available_apps)}) for requested apps_per_scenario ({apps_per_scenario})"
            )
            apps_per_scenario = len(available_apps)

        if total_scenarios <= 0:
            logger.warning("Total scenarios must be positive")
            return [], []

        logger.info(f"Generating {total_scenarios} distinct app combinations with {apps_per_scenario} apps each")
        logger.info(f"Available apps: {available_apps}")

        # Generate intelligent combinations using LLM reasoning
        intelligent_combinations, intelligent_summaries = self._generate_intelligent_combinations(
            available_apps, total_scenarios, apps_per_scenario, app_tools_info, example_scenarios
        )

        if len(intelligent_combinations) >= total_scenarios:
            logger.info(f"Successfully generated {len(intelligent_combinations)} intelligent combinations")
            return intelligent_combinations[:total_scenarios], intelligent_summaries[:total_scenarios]

        # If we don't have enough intelligent combinations, supplement with algorithmic ones
        logger.warning(
            f"Only generated {len(intelligent_combinations)} intelligent combinations, supplementing with algorithmic ones"
        )
        remaining_needed = total_scenarios - len(intelligent_combinations)

        algorithmic_combinations = self._generate_algorithmic_combinations(
            available_apps, remaining_needed, apps_per_scenario, intelligent_combinations
        )

        all_combinations = intelligent_combinations + algorithmic_combinations
        # For algorithmic combinations, create generic summaries
        algorithmic_summaries = [
            f"Algorithmic combination {i + 1} with apps: {sorted(combo)}"
            for i, combo in enumerate(algorithmic_combinations)
        ]
        all_summaries = intelligent_summaries + algorithmic_summaries

        logger.info(
            f"Generated total of {len(all_combinations)} combinations: {len(intelligent_combinations)} intelligent + {len(algorithmic_combinations)} algorithmic"
        )

        return all_combinations[:total_scenarios], all_summaries[:total_scenarios]

    def _generate_intelligent_combinations(
        self,
        available_apps: list[str],
        total_scenarios: int,
        apps_per_scenario: int,
        app_tools_info: dict[str, list[AppTool]],
        example_scenarios: list[Scenario] | None = None,
    ) -> tuple[list[frozenset[str]], list[str]]:
        """Generate intelligent app combinations using LLM reasoning.

        Args:
            available_apps: List of available app names
            total_scenarios: Total number of combinations needed
            apps_per_scenario: Number of apps per combination
            app_tools_info: Dictionary mapping app names to their tools
            example_scenarios: Optional example scenarios for context

        Returns:
            Tuple of (list of intelligent app combinations, list of scenario summaries)
        """
        try:
            # Create the prompt
            system_prompt, user_prompt = create_app_combination_prompt(
                total_scenarios=total_scenarios,
                apps_per_scenario=apps_per_scenario,
                available_apps=available_apps,
                app_tools_info=app_tools_info,
                example_scenarios=example_scenarios or [],
            )

            # Create messages for LLM
            messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]

            # Get LLM response
            llm_output = self.llm_engine(
                messages, stop_sequences=[], additional_trace_tags=["app_combination_batch_generation"]
            )
            if isinstance(llm_output, tuple) and len(llm_output) == 2:
                llm_output, _ = llm_output
            else:
                llm_output = llm_output

            # Parse LLM response
            combinations, summaries = self._parse_llm_combinations(str(llm_output), available_apps, apps_per_scenario)

            # Validate and filter combinations
            valid_combinations = []
            valid_summaries = []
            seen = set()
            for i, combo in enumerate(combinations):
                if len(combo) == apps_per_scenario and combo not in seen:
                    valid_combinations.append(combo)
                    seen.add(combo)
                    # Include corresponding summary if available
                    if i < len(summaries):
                        valid_summaries.append(summaries[i])
                    else:
                        valid_summaries.append("No summary provided")

            # Log the scenario summaries for debugging
            logger.info(
                f"LLM generated {len(combinations)} combinations, {len(valid_combinations)} are valid and unique"
            )
            for i, (combo, summary) in enumerate(zip(valid_combinations, valid_summaries, strict=False)):
                combo_list = sorted(combo)
                logger.info(f"  Combination {i + 1}: {combo_list}")
                logger.info(f"    Scenario: {summary}")

            return valid_combinations, valid_summaries  # noqa: TRY300

        except Exception as e:
            logger.warning(f"Failed to generate intelligent combinations: {e}")
            return [], []

    def _generate_algorithmic_combinations(
        self,
        available_apps: list[str],
        needed_combinations: int,
        apps_per_scenario: int,
        existing_combinations: list[frozenset[str]],
    ) -> list[frozenset[str]]:
        """Generate algorithmic app combinations to supplement intelligent ones.

        Args:
            available_apps: List of available app names
            needed_combinations: Number of additional combinations needed
            apps_per_scenario: Number of apps per combination
            existing_combinations: Already generated combinations to avoid

        Returns:
            List of algorithmic app combinations
        """
        combinations = []
        used_combinations = set(existing_combinations)

        # Generate diverse random combinations
        random_combinations = self._generate_diverse_random_combinations(
            available_apps, needed_combinations, apps_per_scenario, used_combinations
        )
        combinations.extend(random_combinations)

        # Remove duplicates and limit to needed amount
        unique_combinations = []
        seen = set()
        for combo in combinations:
            if combo not in seen and combo not in used_combinations:
                unique_combinations.append(combo)
                seen.add(combo)
                if len(unique_combinations) >= needed_combinations:
                    break

        logger.info(f"Generated {len(unique_combinations)} algorithmic combinations")
        return unique_combinations

    def _generate_diverse_random_combinations(
        self,
        available_apps: list[str],
        needed_combinations: int,
        apps_per_scenario: int,
        used_combinations: set[frozenset[str]],
    ) -> list[frozenset[str]]:
        """Generate diverse random combinations.

        Args:
            available_apps: List of available app names
            needed_combinations: Number of combinations needed
            apps_per_scenario: Number of apps per combination
            used_combinations: Already used combinations to avoid

        Returns:
            List of diverse random combinations
        """
        import random

        combinations: list[frozenset[str]] = []
        seen = set(used_combinations)
        max_attempts = needed_combinations * 10  # Try many times to find unique combinations

        for _ in range(max_attempts):
            if len(combinations) >= needed_combinations:
                break

            selected_apps = random.sample(available_apps, apps_per_scenario)
            combo = frozenset(selected_apps)

            if combo not in seen:
                combinations.append(combo)
                seen.add(combo)

        return combinations

    def _parse_llm_combinations(  # noqa: C901
        self, llm_output: str, available_apps: list[str], apps_per_scenario: int
    ) -> tuple[list[frozenset[str]], list[str]]:
        """Parse LLM output to extract app combinations and summaries.

        Args:
            llm_output: Raw LLM output
            available_apps: List of valid app names
            apps_per_scenario: Expected number of apps per combination

        Returns:
            Tuple of (list of parsed app combinations, list of scenario summaries)
        """
        import json
        import re

        combinations = []
        summaries = []

        try:
            # Try to extract JSON object from the output - use greedy matching to get the full object
            json_match = re.search(r"\{.*\}", llm_output, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                parsed_data = json.loads(json_str)

                # Handle new format with combinations and summaries
                if isinstance(parsed_data, dict) and "combinations" in parsed_data and "summaries" in parsed_data:
                    parsed_combinations = parsed_data["combinations"]
                    parsed_summaries = parsed_data["summaries"]

                    for combo in parsed_combinations:
                        if isinstance(combo, list):
                            # Validate that all apps in combination are available
                            valid_combo = [app for app in combo if app in available_apps]
                            if len(valid_combo) == apps_per_scenario:
                                combinations.append(frozenset(valid_combo))

                    # Extract summaries
                    if isinstance(parsed_summaries, list):
                        summaries = [str(summary) for summary in parsed_summaries if isinstance(summary, str)]

                # Handle legacy format (just array of combinations)
                elif isinstance(parsed_data, list):
                    for combo in parsed_data:
                        if isinstance(combo, list):
                            valid_combo = [app for app in combo if app in available_apps]
                            if len(valid_combo) == apps_per_scenario:
                                combinations.append(frozenset(valid_combo))
                    # No summaries in legacy format
                    summaries = []

            else:
                # If no JSON object found, try to parse as array (legacy format)
                json_match = re.search(r"\[.*\]", llm_output, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    parsed_combinations = json.loads(json_str)

                    for combo in parsed_combinations:
                        if isinstance(combo, list):
                            valid_combo = [app for app in combo if app in available_apps]
                            if len(valid_combo) == apps_per_scenario:
                                combinations.append(frozenset(valid_combo))
                    # No summaries in legacy format
                    summaries = []
                else:
                    # Try to parse the entire output as JSON
                    try:
                        parsed_data = json.loads(llm_output.strip())
                        if isinstance(parsed_data, list):
                            for combo in parsed_data:
                                if isinstance(combo, list):
                                    valid_combo = [app for app in combo if app in available_apps]
                                    if len(valid_combo) == apps_per_scenario:
                                        combinations.append(frozenset(valid_combo))
                            summaries = []
                    except json.JSONDecodeError:
                        logger.warning("No valid JSON found in LLM output")

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse LLM JSON output: {e}")

        return combinations, summaries

    # ===== Backward Compatibility Method =====

    def select_app_combination(
        self,
        available_apps: list[str],
        apps_per_scenario: int,
        history_combinations: set[frozenset[str]],
        app_tools_info: dict[str, list[AppTool]],
        example_scenarios: list[Scenario] | None = None,
    ) -> frozenset[str]:
        """Backward compatibility method for single combination selection.

        This method generates all combinations and returns the first one.
        For new code, use generate_all_app_combinations() instead.

        Args:
            available_apps: List of available app names
            apps_per_scenario: Number of apps to select (excluding AgentUserInterface)
            history_combinations: Set of previously used app combinations (ignored in batch mode)
            app_tools_info: Dictionary mapping app names to their tools
            example_scenarios: Optional list of example scenarios for context

        Returns:
            A frozenset of selected app names
        """
        # Generate all combinations and return the first one
        all_combinations, _ = self.generate_all_app_combinations(
            available_apps=available_apps,
            total_scenarios=1,
            apps_per_scenario=apps_per_scenario,
            app_tools_info=app_tools_info,
            example_scenarios=example_scenarios,
        )

        if all_combinations:
            return all_combinations[0]
        else:
            # Fallback to random selection
            import random

            selected_apps = random.sample(available_apps, apps_per_scenario)
            return frozenset(selected_apps)
