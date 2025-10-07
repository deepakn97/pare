"""Run the Meta ARE tutorial scenario through the unified demo runner."""

from __future__ import annotations

from are.simulation.scenarios.scenario_tutorial.scenario import ScenarioTutorial

from pas.meta_adapter import build_meta_scenario_components
from pas.scripts.run_demo import run_proactive_demo


def run_demo() -> None:
    """Run the Meta tutorial scenario once and print a summary."""
    run_proactive_demo(build_meta_scenario_components, scenario_factory=ScenarioTutorial, primary_app="contacts")


if __name__ == "__main__":
    run_demo()
