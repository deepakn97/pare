#!/usr/bin/env python3
"""Script to generate summaries for scenario files and save them to a JSON file."""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Add the project root directory to Python path so modules can be imported
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

from are.simulation.agents.are_simulation_agent_config import LLMEngineConfig  # noqa: E402
from are.simulation.agents.llm.llm_engine_builder import LLMEngineBuilder  # noqa: E402

from pas.scenario_generator.agent.summary_generating_agent import SummaryGeneratingAgent  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_generated_scenarios_dir() -> Path:
    """Get the path to the generated scenarios directory."""
    return Path(__file__).resolve().parents[2] / "scenarios" / "generated_scenarios"


def load_existing_summaries(json_path: Path) -> dict[str, str]:
    """Load existing summaries from JSON file if it exists.

    Args:
        json_path: Path to the JSON file

    Returns:
        Dictionary mapping scenario IDs to summaries
    """
    if json_path.exists():
        try:
            with open(json_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load existing summaries from {json_path}: {e}")
            return {}
    return {}


def save_summaries(summaries: dict[str, str], json_path: Path) -> None:
    """Save summaries to JSON file.

    Args:
        summaries: Dictionary mapping scenario IDs to summaries
        json_path: Path to the JSON file
    """
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summaries, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved {len(summaries)} summaries to {json_path}")


def generate_summary_for_file(
    file_path: Path, agent: SummaryGeneratingAgent, summaries: dict[str, str], force_update: bool = False
) -> bool:
    """Generate summary for a single scenario file.

    Args:
        file_path: Path to the scenario file
        agent: Summary generating agent
        summaries: Dictionary to update with new summaries
        force_update: If True, regenerate summary even if it exists

    Returns:
        True if summary was generated successfully, False otherwise
    """
    scenario_id, summary = agent.generate_summary_from_file(file_path)

    if not scenario_id:
        logger.error(f"Could not extract scenario ID from {file_path}")
        return False

    if not summary:
        logger.error(f"Failed to generate summary for {file_path}")
        return False

    # Check if summary already exists
    if scenario_id in summaries and not force_update:
        logger.info(f"Summary already exists for {scenario_id}, skipping (use --force to update)")
        return True

    summaries[scenario_id] = summary
    logger.info(f"Generated summary for {scenario_id}: {summary[:80]}...")
    return True


def generate_summaries_for_all(
    agent: SummaryGeneratingAgent, summaries: dict[str, str], force_update: bool = False
) -> int:
    """Generate summaries for all scenario files in the generated_scenarios directory and subdirectories.

    Args:
        agent: Summary generating agent
        summaries: Dictionary to update with new summaries
        force_update: If True, regenerate summaries even if they exist

    Returns:
        Number of summaries generated
    """
    scenarios_dir = get_generated_scenarios_dir()
    if not scenarios_dir.exists():
        logger.error(f"Generated scenarios directory does not exist: {scenarios_dir}")
        return 0

    # Get all Python files recursively (including subdirectories)
    # Exclude __pycache__ directories and __init__.py files
    scenario_files = []
    for py_file in scenarios_dir.rglob("*.py"):
        # Skip files in __pycache__ directories
        if "__pycache__" in str(py_file):
            continue
        # Skip __init__.py files
        if py_file.name == "__init__.py":
            continue
        # Skip files starting with __
        if py_file.name.startswith("__"):
            continue
        # Only include actual files (not directories)
        if py_file.is_file():
            scenario_files.append(py_file)

    logger.info(f"Found {len(scenario_files)} scenario files to process (including subdirectories)")

    generated_count = 0
    for scenario_file in scenario_files:
        # Show relative path for files in subdirectories
        rel_path = scenario_file.relative_to(scenarios_dir)
        logger.info(f"Processing {rel_path}...")
        if generate_summary_for_file(scenario_file, agent, summaries, force_update):
            generated_count += 1

    return generated_count


def main() -> None:
    """Main function to run the summary generation script."""
    parser = argparse.ArgumentParser(
        description="Generate summaries for scenario files and save them to a JSON file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate summary for a single file
  python generate_scenario_summaries.py --file pas/scenarios/generated_scenarios/meeting_invite_coordination.py

  # Generate summaries for all scenarios
  python generate_scenario_summaries.py --all

  # Force update existing summaries
  python generate_scenario_summaries.py --all --force
        """,
    )

    # File input option
    parser.add_argument(
        "--file",
        dest="file_path",
        type=str,
        default=None,
        help="Path to a single scenario file to generate summary for",
    )

    # All files option
    parser.add_argument(
        "--all", action="store_true", help="Generate summaries for all scenario files in generated_scenarios/ directory"
    )

    # Force update option
    parser.add_argument(
        "--force", action="store_true", help="Force regeneration of summaries even if they already exist"
    )

    # LLM configuration
    parser.add_argument("--model", dest="model", default="gpt-4o-mini", help="LLM model to use (default: gpt-4o-mini)")
    parser.add_argument("--provider", dest="provider", default="openai", help="LLM provider (default: openai)")
    parser.add_argument("--endpoint", dest="endpoint", default=None, help="Optional endpoint URL")

    # Output file option
    parser.add_argument(
        "--output",
        dest="output_file",
        type=str,
        default=None,
        help="Path to output JSON file (default: generated_scenarios/scenario_summaries.json)",
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.file_path and not args.all:
        parser.error("Either --file or --all must be specified")

    if args.file_path and args.all:
        parser.error("Cannot specify both --file and --all")

    # Determine output file path
    if args.output_file:
        output_path = Path(args.output_file)
    else:
        output_path = get_generated_scenarios_dir() / "scenario_summaries.json"

    # Load existing summaries
    summaries = load_existing_summaries(output_path)
    logger.info(f"Loaded {len(summaries)} existing summaries")

    # Create LLM engine
    config = LLMEngineConfig(model_name=args.model, provider=args.provider, endpoint=args.endpoint)
    engine = LLMEngineBuilder().create_engine(engine_config=config)

    # Create summary generating agent
    agent = SummaryGeneratingAgent(engine)

    # Generate summaries
    if args.file_path:
        # Single file mode
        file_path = Path(args.file_path)
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            sys.exit(1)

        logger.info(f"Generating summary for {file_path}...")
        success = generate_summary_for_file(file_path, agent, summaries, args.force)
        if not success:
            logger.error("Failed to generate summary")
            sys.exit(1)

    else:
        # All files mode
        logger.info("Generating summaries for all scenario files...")
        generated_count = generate_summaries_for_all(agent, summaries, args.force)
        logger.info(f"Generated {generated_count} summaries")

    # Save summaries to JSON file
    save_summaries(summaries, output_path)
    logger.info(f"Summary generation completed. Total summaries: {len(summaries)}")


if __name__ == "__main__":
    main()
