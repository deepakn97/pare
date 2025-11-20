#!/usr/bin/env python3
"""Wrapper script to run custom scenarios with meta-ARE."""

from __future__ import annotations

import argparse
import glob
import importlib.util
import logging
import os
import sys

from are.simulation.main import main

logger = logging.getLogger(__name__)

# Add the project root directory to Python path so our custom scenarios can be imported
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)


def import_temporary_scenario(temp_file_path: str) -> None:
    """Import a temporary scenario file and register it."""
    if not os.path.exists(temp_file_path):
        print(f"Warning: Temporary file not found: {temp_file_path}")
        return

    try:
        # Create a module spec for the temporary file
        spec = importlib.util.spec_from_file_location("temp_scenario", temp_file_path)
        if spec and spec.loader:
            # Create and execute the module to trigger @register_scenario decorators
            temp_module = importlib.util.module_from_spec(spec)
            temp_module.__name__ = spec.name
            sys.modules[spec.name] = temp_module
            spec.loader.exec_module(temp_module)
            print(f"✅ Successfully imported and registered temporary scenario from: {temp_file_path}")
            logger.info(f"Successfully imported temporary scenario: {temp_file_path}")
        else:
            print(f"❌ Failed to create module spec for temporary file: {temp_file_path}")
    except Exception as e:
        print(f"❌ Error importing temporary scenario: {e}")


# Parse command line arguments
parser = argparse.ArgumentParser(description="Run scenario validation")
parser.add_argument("-s", "--scenario", required=True, help="Scenario ID to run")
parser.add_argument("-a", "--agent", required=True, help="Agent to use")
parser.add_argument("--provider", required=True, help="Provider to use")
parser.add_argument("--temp-file", help="Path to temporary scenario file to import before running")

args = parser.parse_args()

# Check if our custom scenario modules are available and import them to register scenarios
if importlib.util.find_spec("pas.scenario_generator.example_proactive_scenarios.scenario"):
    try:
        import pas.scenario_generator.example_proactive_scenarios.scenario  # noqa: F401

        print("Imported custom scenario module")
    except ImportError as e:
        print(f"Warning: Could not import custom scenario module: {e}")

# Import temporary scenario file if provided (this registers it before main validation)
if args.temp_file:
    import_temporary_scenario(args.temp_file)

# Import generated scenario files dynamically

generated_dir = os.path.join(os.path.dirname(__file__), "..", "..", "scenarios", "generated_scenarios")
if os.path.exists(generated_dir):
    pattern = os.path.join(generated_dir, "*.py")
    generated_files = glob.glob(pattern)
    # Filter out __pycache__ and other non-scenario files
    generated_files = [f for f in generated_files if not os.path.basename(f).startswith("__")]

    for scenario_file_path in generated_files:
        scenario_file = os.path.basename(scenario_file_path)[:-3]  # Remove .py extension
        scenario_module = f"pas.scenarios.generated_scenarios.{scenario_file}"

        if importlib.util.find_spec(scenario_module):
            try:
                importlib.import_module(scenario_module)
                print(f"Imported generated scenario file: {scenario_module}")
            except ImportError as e:
                print(f"Warning: Could not import generated scenario file {scenario_module}: {e}")
            except Exception as e:
                import traceback

                error_details = f"Failed to load scenario from {scenario_module}: {e}"
                error_traceback = traceback.format_exc()
                print(f"❌ {error_details}")
                print(f"Full traceback:\n{error_traceback}")
                # Continue with other scenarios even if one fails
else:
    print(f"Warning: Generated scenarios directory not found: {generated_dir}")


# Verify that scenarios are properly registered
def verify_scenario_registration(requested_scenario: str) -> bool:
    """Verify that expected scenarios are registered in meta-ARE."""
    try:
        from are.simulation.scenarios.utils.constants import ALL_SCENARIOS

        registered_scenarios = set(ALL_SCENARIOS.keys())

        # Check if the requested scenario is registered
        if requested_scenario and requested_scenario in registered_scenarios:
            print(f"✅ Requested scenario '{requested_scenario}' is registered")
        elif requested_scenario:
            print(f"❌ Requested scenario '{requested_scenario}' is NOT registered")

        # For logging purposes, also check for tutorial scenarios
        tutorial_scenarios = {
            sid
            for sid in registered_scenarios
            if "tutorial" in sid or "schedule_meeting" in sid or "proactive_file_summary" in sid
        }
        if tutorial_scenarios:
            print(f"[INFO] Tutorial scenarios found: {sorted(tutorial_scenarios)}")

        # The main requirement is that the requested scenario is registered
        registration_success = requested_scenario in registered_scenarios if requested_scenario else True

        print("\n=== Scenario Registration Verification ===")
        print(f"Total registered scenarios: {len(registered_scenarios)}")

        if not registration_success:
            print(f"❌ Requested scenario '{requested_scenario}' is not registered")
        else:
            print("✅ Scenario registration check passed")

        print("=== End Verification ===\n")

    except Exception as e:
        print(f"❌ Error verifying scenario registration: {e}")
        return False
    else:
        return registration_success


if __name__ == "__main__":
    # Parse command line arguments first
    args = parser.parse_args()

    # Verify scenario registration before running (now we have args available)
    registration_success = verify_scenario_registration(args.scenario)

    # Set the arguments for are-run using parsed arguments
    sys.argv = ["are-run", "-s", args.scenario, "-a", args.agent, "--provider", args.provider, "--oracle"]
    # sys.argv = ["are-run", "-s", args.scenario, "-a", args.agent, "--provider", args.provider]

    # Run are-run only if scenarios are properly registered
    if registration_success:
        print("✅ All scenarios properly registered, proceeding with execution...\n")
        try:
            main()
            print("✅ Scenario execution completed successfully")
            sys.exit(0)  # Success exit code
        except Exception as e:
            # Write error details to a file for the parent process to read
            import os
            import time
            import traceback

            error_details = f"Error during scenario execution: {e}"
            error_traceback = traceback.format_exc()

            # Create runtime_error directory if it doesn't exist
            error_dir = "/Users/jasonz/Projects/ucsb/proactiveGoalInference/runtime_error"
            os.makedirs(error_dir, exist_ok=True)

            # Generate unique filename with timestamp
            timestamp = int(time.time())
            error_filename = f"scenario_error_{timestamp}.txt"
            error_filepath = os.path.join(error_dir, error_filename)

            # Write error details to file
            with open(error_filepath, "w") as f:
                f.write(f"Error Details:\n{error_details}\n\n")
                f.write(f"Full Traceback:\n{error_traceback}\n")
                f.write(f"Error Type: {type(e).__name__}\n")
                f.write(f"Scenario: {args.scenario}\n")

            print(f"❌ Error details written to: {error_filepath}")

            # Use different exit codes for different error types
            if "has no attribute" in str(e):
                print("ERROR_TYPE: METHOD_NOT_FOUND")
                with open(error_filepath, "a") as f:
                    f.write("METHOD_NOT_FOUND")
                sys.exit(2)  # Method not found error
            elif "Failed to load scenario" in str(e):
                print("ERROR_TYPE: SCENARIO_LOAD_FAILED")
                with open(error_filepath, "a") as f:
                    f.write("3")
                sys.exit(3)  # Scenario loading error
            else:
                print("ERROR_TYPE: GENERAL_EXECUTION_ERROR")
                with open(error_filepath, "a") as f:
                    f.write("4")
                sys.exit(4)  # General execution error
    else:
        print("❌ Scenario registration issues detected, please fix before running scenarios.")
        print("ERROR_TYPE: REGISTRATION_FAILED")

        # Write error details to file
        import os
        import time

        error_dir = "/Users/jasonz/Projects/ucsb/proactiveGoalInference/runtime_error"
        os.makedirs(error_dir, exist_ok=True)
        timestamp = int(time.time())
        error_filename = f"scenario_error_{timestamp}.txt"
        error_filepath = os.path.join(error_dir, error_filename)

        with open(error_filepath, "w") as f:
            f.write("Error Details:\nScenario registration issues detected\n\n")
            f.write("Error Type: REGISTRATION_FAILED\n")
            f.write(f"Scenario: {args.scenario}\n")
            f.write("Exit Code: 5")

        print(f"❌ Error details written to: {error_filepath}")
        sys.exit(5)  # Registration error
