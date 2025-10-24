#!/usr/bin/env python3
"""Simple batch runner for scenario generation using subprocess.

This script runs the scenario_generator.py command multiple times with the same parameters,
providing a reliable way to generate multiple scenario variations.
"""

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path


def run_scenario_generation(
    scenarios: list[str],
    model: str = "gpt-5-chat-latest",
    provider: str = "openai",
    endpoint: str | None = None,
    max_turns: int | None = None,
    sim_mode: str = "measured",
) -> subprocess.CompletedProcess[str]:
    """Run a single scenario generation using subprocess."""
    # Get the absolute path to the scenario_generator.py script
    script_path = Path(__file__).parent.parent / "scenario_generator.py"

    cmd = [
        sys.executable,
        str(script_path),
        "-s",
        *scenarios,
        "--model",
        model,
        "--provider",
        provider,
        "--simulated_generation_time_mode",
        sim_mode,
    ]

    if endpoint:
        cmd.extend(["--endpoint", endpoint])
    if max_turns:
        cmd.extend(["--max_turns", str(max_turns)])

    print(f"Running: {' '.join(cmd)}")

    # Check if the script exists
    if not script_path.exists():
        print(f"❌ Error: Scenario generator script not found at: {script_path}")
        print("Make sure you're in the project root directory.")
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="Script not found")

    return subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603


def main() -> None:  # noqa: C901
    """Main function to run scenario generation multiple times."""
    parser = argparse.ArgumentParser(
        description="Run scenario generation multiple times using subprocess",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_scenario_generator_simple.py -s scenario1 scenario2 --num-runs 5
  python run_scenario_generator_simple.py -s scenario1 --num-runs 10 --save-results
  python run_scenario_generator_simple.py -s scenario1 scenario2 --num-runs 3 --model gpt-4

Note: This script uses subprocess to call the original scenario_generator.py script.
        """,
    )

    parser.add_argument(
        "-s",
        "--scenario",
        dest="scenario_list",
        nargs="+",
        required=True,
        help="List of scenario IDs to generate (required)",
    )

    parser.add_argument(
        "--num-runs", type=int, default=1, help="Number of times to run scenario generation (default: 1)"
    )

    parser.add_argument("--model", default="gpt-5-chat-latest", help="LLM model to use (default: gpt-5-chat-latest)")

    parser.add_argument("--provider", default="openai", help="LLM provider to use (default: openai)")

    parser.add_argument("--endpoint", help="Custom endpoint URL (optional)")

    parser.add_argument("--max-turns", type=int, help="Maximum turns for generation (optional)")

    parser.add_argument(
        "--sim-mode", choices=["measured", "fixed"], default="measured", help="Simulation time mode (default: measured)"
    )

    parser.add_argument("--save-results", action="store_true", help="Save results to timestamped files")

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("scenario_generator/generated_scenarios"),
        help="Output directory for saved results (default: scenario_generator/generated_scenarios)",
    )

    parser.add_argument("--delay", type=float, default=0.0, help="Delay between runs in seconds (default: 0.0)")

    parser.add_argument("--json-summary", type=Path, help="Save JSON summary of all runs to specified file")

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logger = logging.getLogger(__name__)

    # Create output directory if saving results
    if args.save_results:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Starting scenario generation: {args.num_runs} runs")
    logger.info(f"Scenarios: {', '.join(args.scenario_list)}")
    logger.info(f"Model: {args.model}, Provider: {args.provider}")

    results = {
        "total_runs": args.num_runs,
        "successful_runs": 0,
        "failed_runs": 0,
        "runs": [],
        "scenarios": args.scenario_list,
        "model": args.model,
        "provider": args.provider,
    }

    for run_num in range(1, args.num_runs + 1):
        logger.info(f"=== Run {run_num}/{args.num_runs} ===")

        try:
            # Run the scenario generation
            result = run_scenario_generation(
                scenarios=args.scenario_list,
                model=args.model,
                provider=args.provider,
                endpoint=args.endpoint,
                max_turns=args.max_turns,
                sim_mode=args.sim_mode,
            )

            run_result = {
                "run_number": run_num,
                "success": result.returncode == 0,
                "return_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

            if result.returncode == 0:
                results["successful_runs"] += 1
                logger.info(f"✅ Run {run_num} completed successfully")

                # Save results if requested
                if args.save_results:
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    output_file = args.output_dir / f"simple_run_{run_num}_{timestamp}.json"

                    with open(output_file, "w") as f:
                        json.dump(run_result, f, indent=2)

                    logger.info(f"📄 Results saved to: {output_file}")

                # Print output if not saving to file and there's output
                if not args.save_results and result.stdout.strip():
                    print("Generated scenario:")
                    print("=" * 50)
                    print(result.stdout.strip())
                    print("=" * 50)

            else:
                results["failed_runs"] += 1
                logger.error(f"❌ Run {run_num} failed with return code {result.returncode}")
                if result.stderr.strip():
                    logger.error(f"STDERR: {result.stderr}")
                    # Check for common dependency issues
                    if "ModuleNotFoundError" in result.stderr and "are" in result.stderr:
                        print("\n" + "=" * 60)
                        print("MISSING DEPENDENCIES DETECTED!")
                        print("=" * 60)
                        print("The 'are' module (meta-agents-research-environments) is not installed.")
                        print("Make sure you're in a virtual environment with dependencies installed:")
                        print("")
                        print("Option 1 - Using venv:")
                        print("  source .venv/bin/activate")
                        print("")
                        print("Option 2 - Using uv:")
                        print("  uv sync")
                        print("")
                        print("Then verify: python -c \"import are; print('are module available')\"")
                        print("=" * 60)

        except Exception as e:
            results["failed_runs"] += 1
            logger.exception(f"❌ Run {run_num} failed with exception")
            run_result = {
                "run_number": run_num,
                "success": False,
                "return_code": -1,
                "stdout": "",
                "stderr": str(e),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

        results["runs"].append(run_result)

        # Delay between runs if specified
        if run_num < args.num_runs and args.delay > 0:
            logger.info(f"⏳ Waiting {args.delay} seconds before next run...")
            time.sleep(args.delay)

    # Save JSON summary if requested
    if args.json_summary:
        with open(args.json_summary, "w") as f:
            json.dump(results, f, indent=2)
        print(f"📊 Summary saved to: {args.json_summary}")

    # Print final summary
    print("\n" + "=" * 60)
    print("BATCH GENERATION COMPLETE")
    print("=" * 60)
    print(f"Total runs: {results['total_runs']}")
    print(f"Successful: {results['successful_runs']}")
    print(f"Failed: {results['failed_runs']}")
    print(f"Success rate: {results['successful_runs'] / results['total_runs'] * 100:.1f}%")
    if results["failed_runs"] > 0:
        print(f"\n⚠️  {results['failed_runs']} runs failed:")
        for run in results["runs"]:
            if not run["success"]:
                print(f"  Run {run['run_number']}: Return code {run['return_code']}")
                if run["stderr"].strip():
                    print(f"    Error: {run['stderr'].strip()}")
        sys.exit(1)
    else:
        print("\n🎉 All runs completed successfully!")


if __name__ == "__main__":
    main()
