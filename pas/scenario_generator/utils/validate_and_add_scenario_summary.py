#!/usr/bin/env python3
"""Script to generate a summary for a scenario file, validate it against existing summaries, and add it to scenario_summaries.json if it passes deduplication checks."""

import argparse
import difflib
import json
import logging
import os
import re
import sys
from collections import Counter
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


def tokens_from_text(text: str) -> list[str]:
    """Extract identifiers and keywords from text.

    - identifiers & keywords only (ignore numbers and punctuation)
    """
    return re.findall(r"[A-Za-z_][A-Za-z_0-9]*", text)


def shingles(tokens: list[str], k: int = 3) -> set[str]:
    """Generate k-gram token shingles from a list of tokens."""
    if len(tokens) < k:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[i : i + k]) for i in range(len(tokens) - k + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    """Calculate Jaccard similarity between two sets."""
    if not a and not b:
        return 1.0
    inter = len(a & b)
    union = len(a | b) or 1
    return inter / union


def cosine_counter(ca: Counter[str], cb: Counter[str]) -> float:
    """Calculate cosine similarity between two Counter objects."""
    if not ca and not cb:
        return 1.0
    keys = set(ca) | set(cb)
    dot = sum(ca[k] * cb[k] for k in keys)
    na = sum(v * v for v in ca.values()) ** 0.5
    nb = sum(v * v for v in cb.values()) ** 0.5
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)


def difflib_ratio(a: str, b: str) -> float:
    """Calculate edit similarity ratio using difflib."""
    return difflib.SequenceMatcher(a=a, b=b, autojunk=False).ratio()


def normalize_text(text: str) -> str:
    """Normalize text by collapsing whitespace."""
    return re.sub(r"\s+", " ", text).strip()


def compare_summaries(summary1: str, summary2: str, k: int = 3) -> dict[str, float | int]:
    """Compare two summaries using multiple similarity metrics.

    Args:
        summary1: First summary text
        summary2: Second summary text
        k: Shingle size for Jaccard (default: 3)

    Returns:
        Dictionary with similarity scores and token lengths
    """
    # Normalize summaries
    s1 = normalize_text(summary1)
    s2 = normalize_text(summary2)

    # Metric 1: difflib (good general-purpose edit similarity)
    sm_ratio = difflib_ratio(s1, s2)

    # Metric 2: Jaccard over token shingles (robust to minor edits)
    toks1, toks2 = tokens_from_text(s1), tokens_from_text(s2)
    sh1, sh2 = shingles(toks1, k=k), shingles(toks2, k=k)
    jac = jaccard(sh1, sh2)

    # Metric 3: Cosine over token frequency (bag-of-words style)
    c1, c2 = Counter(toks1), Counter(toks2)
    cos = cosine_counter(c1, c2)

    return {
        "difflib_ratio": sm_ratio,
        "jaccard_shingles": jac,
        "cosine_tokens": cos,
        "len_tokens_1": len(toks1),
        "len_tokens_2": len(toks2),
    }


def validate_against_existing_summaries(
    new_summary: str,
    existing_summaries: dict[str, str],
    difflib_threshold: float = 0.8,
    jaccard_threshold: float = 0.8,
    cosine_threshold: float = 0.94,
    k: int = 3,
) -> tuple[bool, list[dict[str, str | float]]]:
    """Validate that a new summary is not too similar to existing summaries.

    Args:
        new_summary: The new summary to validate
        existing_summaries: Dictionary of existing scenario IDs to summaries
        difflib_threshold: Threshold for difflib_ratio (default: 0.8)
        jaccard_threshold: Threshold for jaccard_shingles (default: 0.8)
        cosine_threshold: Threshold for cosine_tokens (default: 0.94)
        k: Shingle size for Jaccard (default: 3)

    Returns:
        Tuple of (is_valid, list_of_violations) where:
        - is_valid: True if all metrics are below thresholds for all existing summaries
        - list_of_violations: List of dicts with scenario_id and similarity scores for violations
    """
    violations = []

    for scenario_id, existing_summary in existing_summaries.items():
        scores = compare_summaries(new_summary, existing_summary, k=k)

        # Log comparison metrics for all scenarios
        logger.info(
            f"Comparing with '{scenario_id}': "
            f"difflib_ratio={scores['difflib_ratio']:.4f}, "
            f"jaccard_shingles={scores['jaccard_shingles']:.4f}, "
            f"cosine_tokens={scores['cosine_tokens']:.4f}"
        )

        # Check if any metric exceeds its threshold
        is_duplicate = (
            scores["difflib_ratio"] >= difflib_threshold
            or scores["jaccard_shingles"] >= jaccard_threshold
            or scores["cosine_tokens"] >= cosine_threshold
        )

        if is_duplicate:
            violations.append({
                "scenario_id": scenario_id,
                "difflib_ratio": scores["difflib_ratio"],
                "jaccard_shingles": scores["jaccard_shingles"],
                "cosine_tokens": scores["cosine_tokens"],
            })
            logger.warning(
                f"  ⚠️  VIOLATION: Summary too similar to existing scenario '{scenario_id}' "
                f"(exceeds thresholds: difflib≥{difflib_threshold}, jaccard≥{jaccard_threshold}, cosine≥{cosine_threshold})"
            )

    is_valid = len(violations) == 0
    return is_valid, violations


def main() -> None:
    """Main function to validate and add scenario summary."""
    parser = argparse.ArgumentParser(
        description="Generate summary for a scenario file, validate against existing summaries, "
        "and add to scenario_summaries.json if it passes deduplication checks.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate and add a scenario summary
  python validate_and_add_scenario_summary.py --file pas/scenarios/generated_scenarios/meeting_invite_coordination.py

  # Use custom thresholds
  python validate_and_add_scenario_summary.py --file scenario.py --difflib-threshold 0.75 --jaccard-threshold 0.75
        """,
    )

    # Required arguments
    parser.add_argument(
        "--file", dest="file_path", type=str, required=True, help="Path to the scenario file to validate and add"
    )

    # Threshold arguments
    parser.add_argument(
        "--difflib-threshold", type=float, default=0.8, help="Threshold for difflib_ratio (default: 0.8)"
    )
    parser.add_argument(
        "--jaccard-threshold", type=float, default=0.8, help="Threshold for jaccard_shingles (default: 0.8)"
    )
    parser.add_argument(
        "--cosine-threshold", type=float, default=0.94, help="Threshold for cosine_tokens (default: 0.94)"
    )
    parser.add_argument("--k", type=int, default=3, help="Shingle size for Jaccard similarity (default: 3)")

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

    # Determine output file path
    if args.output_file:
        output_path = Path(args.output_file)
    else:
        output_path = get_generated_scenarios_dir() / "scenario_summaries.json"

    # Load existing summaries
    existing_summaries = load_existing_summaries(output_path)
    logger.info(f"Loaded {len(existing_summaries)} existing summaries")

    # Check if file exists
    file_path = Path(args.file_path)
    if not file_path.exists():
        logger.error(f"Scenario file not found: {file_path}")
        sys.exit(1)

    # Create LLM engine
    config = LLMEngineConfig(model_name=args.model, provider=args.provider, endpoint=args.endpoint)
    engine = LLMEngineBuilder().create_engine(engine_config=config)

    # Create summary generating agent
    agent = SummaryGeneratingAgent(engine)

    # Generate summary for the scenario file
    logger.info(f"Generating summary for {file_path}...")
    scenario_id, summary = agent.generate_summary_from_file(file_path)

    if not scenario_id:
        logger.error(f"Could not extract scenario ID from {file_path}")
        sys.exit(1)

    if not summary:
        logger.error(f"Failed to generate summary for {file_path}")
        sys.exit(1)

    logger.info(f"Generated summary for scenario '{scenario_id}': {summary[:100]}...")

    # Check if summary already exists
    if scenario_id in existing_summaries:
        logger.warning(f"Summary already exists for scenario '{scenario_id}'. Skipping validation.")
        logger.info("Summary already in JSON file. Returning True.")
        print("True")
        sys.exit(0)

    # Validate against existing summaries
    logger.info("Validating summary against existing summaries...")
    is_valid, violations = validate_against_existing_summaries(
        new_summary=summary,
        existing_summaries=existing_summaries,
        difflib_threshold=args.difflib_threshold,
        jaccard_threshold=args.jaccard_threshold,
        cosine_threshold=args.cosine_threshold,
        k=args.k,
    )

    if is_valid:
        # All metrics are below thresholds - add to JSON
        logger.info("✓ All similarity metrics are below thresholds. Adding summary to JSON file.")
        existing_summaries[scenario_id] = summary
        save_summaries(existing_summaries, output_path)
        logger.info(f"Successfully added summary for scenario '{scenario_id}' to {output_path}")
        print("True")
        sys.exit(0)
    else:
        # Some metrics exceeded thresholds
        logger.error(f"✗ Summary is too similar to {len(violations)} existing scenario(s).")
        logger.error("Similarity violations:")
        for violation in violations:
            logger.error(
                f"  - {violation['scenario_id']}: "
                f"difflib={violation['difflib_ratio']:.4f} "
                f"(threshold: {args.difflib_threshold}), "
                f"jaccard={violation['jaccard_shingles']:.4f} "
                f"(threshold: {args.jaccard_threshold}), "
                f"cosine={violation['cosine_tokens']:.4f} "
                f"(threshold: {args.cosine_threshold})"
            )
        print("False")
        sys.exit(1)


if __name__ == "__main__":
    main()
