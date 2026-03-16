#!/usr/bin/env python3
"""Fix cached acceptance counts by recomputing from trace files.

The old get_acceptance_count() counted all accept_proposal calls, including responses
to execute-mode send_message_to_user messages. This script recomputes acceptance_count
from trace completed_events, only counting acceptances that follow observe-mode proposals.

After running this script, re-run `pas benchmark sweep` with the same config to
regenerate result JSONs and reports from corrected cache entries.

Usage:
    uv run python scripts/fix_cached_acceptance_counts.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def count_observe_mode_acceptances_from_trace(completed_events: list[dict]) -> int:
    """Count accept_proposal calls that follow observe-mode proposals only.

    Walks completed events chronologically. Tracks the proactive_mode of the most recent
    send_message_to_user call. Only counts accept_proposal when the preceding proposal
    was made in observe mode (not execute mode).

    Args:
        completed_events: List of completed event dicts from a trace file.

    Returns:
        Number of acceptances that correspond to observe-mode proposals.
    """
    last_proposal_mode: str | None = None
    count = 0
    for event in completed_events:
        action = event.get("action", {})
        func_name = action.get("function", "")
        app_class = action.get("app", "")
        if "PASAgentUserInterface" not in str(app_class):
            continue
        metadata = event.get("metadata", {})
        if func_name == "send_message_to_user":
            last_proposal_mode = metadata.get("proactive_mode")
        elif func_name == "accept_proposal" and last_proposal_mode == "observe":
            count += 1
            last_proposal_mode = None  # consume the proposal
    return count


def fix_cache_files(cache_dir: Path, dry_run: bool = False) -> None:
    """Fix acceptance counts in all cache files.

    Args:
        cache_dir: Path to the cache directory.
        dry_run: If True, print changes without writing.
    """
    cache_files = sorted(cache_dir.glob("*.json"))
    if not cache_files:
        logger.info(f"No cache files found in {cache_dir}")
        return

    logger.info(f"Found {len(cache_files)} cache files in {cache_dir}")

    updated = 0
    skipped_no_trace = 0
    skipped_no_change = 0
    errors = 0

    for cache_file in cache_files:
        try:
            with open(cache_file) as f:
                cached = json.load(f)

            export_path = cached.get("export_path")
            if not export_path or not Path(export_path).exists():
                skipped_no_trace += 1
                continue

            with open(export_path) as f:
                trace = json.load(f)

            completed_events = trace.get("completed_events", [])
            new_acceptance_count = count_observe_mode_acceptances_from_trace(completed_events)
            old_acceptance_count = cached.get("acceptance_count", 0)

            if new_acceptance_count == old_acceptance_count:
                skipped_no_change += 1
                continue

            scenario_id = cached.get("scenario_id", "unknown")
            run_number = cached.get("run_number", "?")
            logger.info(
                f"{scenario_id}_run_{run_number}: acceptance_count {old_acceptance_count} -> {new_acceptance_count}"
            )

            if not dry_run:
                cached["acceptance_count"] = new_acceptance_count
                with open(cache_file, "w") as f:
                    json.dump(cached, f, indent=2)

            updated += 1

        except Exception:
            logger.exception(f"Error processing {cache_file.name}")
            errors += 1

    prefix = "[DRY RUN] " if dry_run else ""
    logger.info(f"\n{prefix}Summary:")
    logger.info(f"  Updated: {updated}")
    logger.info(f"  No change needed: {skipped_no_change}")
    logger.info(f"  No trace file: {skipped_no_trace}")
    logger.info(f"  Errors: {errors}")
    logger.info(f"  Total: {len(cache_files)}")


def main() -> None:
    """Entry point for the script."""
    parser = argparse.ArgumentParser(description="Fix cached acceptance counts by recomputing from trace files.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print changes without writing to cache files.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Override cache directory (default: auto-detect from PAS config).",
    )
    args = parser.parse_args()

    if args.cache_dir:
        cache_dir = args.cache_dir
    else:
        try:
            from pas.scenarios.utils.caching import _get_cache_dir

            cache_dir = _get_cache_dir()
        except ImportError:
            cache_dir = Path.home() / ".cache" / "pas" / "scenario_results"
            logger.warning(f"Could not import PAS caching module, using default: {cache_dir}")

    if not cache_dir.exists():
        logger.error(f"Cache directory does not exist: {cache_dir}")
        sys.exit(1)

    logger.info(f"Cache directory: {cache_dir}")
    if args.dry_run:
        logger.info("DRY RUN mode - no files will be modified")

    fix_cache_files(cache_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
