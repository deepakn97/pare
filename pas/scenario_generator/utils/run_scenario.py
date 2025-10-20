#!/usr/bin/env python3
"""Wrapper script to run custom scenarios with meta-ARE."""

import importlib.util
import os
import sys

from are.simulation.main import main

# Add the project root directory to Python path so our custom scenarios can be imported
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

# Check if our custom scenario modules are available and import them to register scenarios
if importlib.util.find_spec("pas.scenario_generator.example_proactive_scenarios.scenario"):
    try:
        import pas.scenario_generator.example_proactive_scenarios.scenario  # noqa: F401

        print("Imported custom scenario module")
    except ImportError as e:
        print(f"Warning: Could not import custom scenario module: {e}")

# Import generated scenario files
generated_scenario_files = [
    "pas.scenarios.generated_scenarios.scenario_tutorial_schedule_meeting_scenario",
    "pas.scenarios.generated_scenarios.scenario_tutorial_task_from_message_scenario",
]

for scenario_file in generated_scenario_files:
    if importlib.util.find_spec(scenario_file):
        try:
            importlib.import_module(scenario_file)
            print(f"Imported generated scenario file: {scenario_file}")
        except ImportError as e:
            print(f"Warning: Could not import generated scenario file {scenario_file}: {e}")

if __name__ == "__main__":
    # Get the command line arguments (excluding the script name)
    args = sys.argv[1:]

    # Set the arguments for are-run
    sys.argv = ["are-run", *args]

    # Run are-run
    main()
