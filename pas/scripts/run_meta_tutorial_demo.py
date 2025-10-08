from are.simulation.scenarios.scenario_tutorial.scenario import ScenarioTutorial

from pas.meta_adapter import build_meta_scenario_components
from pas.scripts.run_demo import run_proactive_demo

# Equivalent CLI: python -m pas.scripts.run_demo \
#   --builder pas.meta_adapter.build_meta_scenario_components \
#   --scenario-class are.simulation.scenarios.scenario_tutorial.scenario.ScenarioTutorial
if __name__ == "__main__":
    run_proactive_demo(build_meta_scenario_components, scenario_factory=ScenarioTutorial)
