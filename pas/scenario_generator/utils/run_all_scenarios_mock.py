#!/usr/bin/env python3
"""Utility to run all scenarios with mock provider and generate status report."""

from __future__ import annotations

import argparse
import glob
import logging
import os
import subprocess
import sys
import time

# Add the project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

logger = logging.getLogger(__name__)


def get_all_scenario_files() -> list[str]:
    """Get all scenario files from the generated_scenarios directory using glob.

    Recursively searches the directory tree so it automatically picks up any
    nested groups (e.g., 3apps_group, 4apps_group, etc.) without hardcoding.
    """
    generated_dir = os.path.join(os.path.dirname(__file__), "..", "..", "scenarios", "generated_scenarios")

    if not os.path.exists(generated_dir):
        print(f"❌ Generated scenarios directory not found: {generated_dir}")
        return []

    # Recursively match all .py files under generated_scenarios
    pattern = os.path.join(generated_dir, "**", "*.py")
    scenario_files = glob.glob(pattern, recursive=True)

    # Filter out dunder files and anything inside __pycache__
    scenario_files = [f for f in scenario_files if not os.path.basename(f).startswith("__") and "__pycache__" not in f]

    return sorted(scenario_files)


def extract_scenario_id(file_path: str) -> str:
    """Extract scenario ID from file path by reading the @register_scenario decorator."""
    try:
        with open(file_path) as f:
            content = f.read()

        # Look for @register_scenario("scenario_id")
        import re

        match = re.search(r'@register_scenario\("([^"]+)"\)', content)
        if match:
            return match.group(1)
        else:
            # Fallback: use filename without extension
            return os.path.basename(file_path)[:-3]  # Remove .py extension
    except Exception as e:
        print(f"⚠️  Warning: Could not extract scenario ID from {file_path}: {e}")
        return os.path.basename(file_path)[:-3]


def run_scenario_mock(scenario_id: str, timeout: int = 60) -> tuple[bool, str]:
    """Run a single scenario with mock provider.

    Returns:
        Tuple of (success: bool, error_message: str)
    """
    try:
        # Run the scenario using the existing run_scenario.py script
        cmd = [
            sys.executable,
            os.path.join(os.path.dirname(__file__), "run_scenario.py"),
            "-s",
            scenario_id,
            "-a",
            "default",
            "--provider",
            "mock",
        ]

        print(f"🔄 Running scenario: {scenario_id}")

        # Run with timeout
        result = subprocess.run(  # noqa: S603 - inputs are controlled (internal script invocation)
            cmd, capture_output=True, text=True, timeout=timeout, cwd=project_root
        )

        if result.returncode == 0:
            print(f"✅ {scenario_id}: PASS")
            return True, ""
        else:
            error_msg = result.stderr.strip() if result.stderr else result.stdout.strip()
            print(f"❌ {scenario_id}: FAIL - {error_msg}")
            return False, error_msg

    except subprocess.TimeoutExpired:
        error_msg = f"Timeout after {timeout} seconds"
        print(f"⏰ {scenario_id}: FAIL - {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = f"Execution error: {e!s}"
        print(f"💥 {scenario_id}: FAIL - {error_msg}")
        return False, error_msg


def run_all_scenarios_mock(timeout: int = 60, output_file: str | None = None) -> dict[str, str]:
    """Run all scenarios with mock provider and return results.

    Args:
        timeout: Timeout in seconds for each scenario
        output_file: Optional file to write results to

    Returns:
        Dictionary mapping scenario_id to status ("PASS" or "FAIL")
    """
    print("🚀 Starting mock run for all scenarios...")
    print(f"⏱️  Timeout per scenario: {timeout} seconds")
    print("=" * 60)

    # Get all scenario files
    scenario_files = get_all_scenario_files()

    if not scenario_files:
        print("❌ No scenario files found!")
        return {}

    print(f"📁 Found {len(scenario_files)} scenario files")
    print()

    results = {}
    start_time = time.time()

    for i, file_path in enumerate(scenario_files, 1):
        scenario_id = extract_scenario_id(file_path)
        print(f"[{i}/{len(scenario_files)}] Testing: {scenario_id}")

        success, error_msg = run_scenario_mock(scenario_id, timeout)
        results[scenario_id] = "PASS" if success else "FAIL"

        if not success and error_msg:
            print(f"   Error: {error_msg}")

        print()  # Add blank line between scenarios

    total_time = time.time() - start_time
    print("=" * 60)
    print(f"🏁 Completed in {total_time:.1f} seconds")

    # Print summary
    pass_count = sum(1 for status in results.values() if status == "PASS")
    fail_count = len(results) - pass_count

    print(f"📊 Results: {pass_count} PASS, {fail_count} FAIL")

    # Write to output file if specified
    if output_file:
        write_results_to_file(results, output_file)
        print(f"📝 Results written to: {output_file}")

    return results


def write_results_to_file(results: dict[str, str], output_file: str) -> None:
    """Write results to a markdown file."""
    try:
        with open(output_file, "w") as f:
            f.write("# Generated Scenarios Mock Test Status\n\n")
            f.write("| Scenario | Mock Run Result |\n")
            f.write("|----------|----------------|\n")

            for scenario_id, status in sorted(results.items()):
                f.write(f"| {scenario_id} | {status} |\n")

        print(f"✅ Results written to {output_file}")
    except Exception as e:
        print(f"❌ Error writing to file {output_file}: {e}")


def main() -> None:
    """Main function for command line usage."""
    parser = argparse.ArgumentParser(description="Run all scenarios with mock provider")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout in seconds for each scenario (default: 60)")
    parser.add_argument(
        "--output", "-o", help="Output file to write results (default: generated_scenarios_mock_status.md)"
    )
    parser.add_argument("--scenario", "-s", help="Run only a specific scenario (for testing)")

    args = parser.parse_args()

    # Set default output file
    if not args.output:
        args.output = os.path.join(
            os.path.dirname(__file__), "..", "..", "scenarios", "generated_scenarios_mock_status.md"
        )

    if args.scenario:
        # Run single scenario
        print(f"🧪 Testing single scenario: {args.scenario}")
        success, error_msg = run_scenario_mock(args.scenario, args.timeout)
        status = "PASS" if success else "FAIL"
        print(f"Result: {status}")
        if error_msg:
            print(f"Error: {error_msg}")
    else:
        # Run all scenarios
        results = run_all_scenarios_mock(args.timeout, args.output)

        # Print final summary
        print("\n" + "=" * 60)
        print("📋 FINAL SUMMARY")
        print("=" * 60)

        for scenario_id, status in sorted(results.items()):
            emoji = "✅" if status == "PASS" else "❌"
            print(f"{emoji} {scenario_id}: {status}")


if __name__ == "__main__":
    main()
