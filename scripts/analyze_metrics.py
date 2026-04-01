#!/usr/bin/env python3
"""Analyze PARE traces and compute metrics per model and per scenario.

Metrics computed:
1. Proposal Rate: proposals / total tool calls in observe mode
2. Proposal Acceptance Rate: accepted proposals / total proposals
3. Average read-only tool calls in observe mode (per scenario)
4. Average read-only tool calls per proposal
5. Average tool calls in execute mode (per scenario)
6. Scenario pass/fail accuracy

Usage:
    python scripts/analyze_metrics.py <traces_dir> [--output <output_file>]
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

# Scenarios to exclude from analysis
EXCLUDED_SCENARIOS = {"original_seed_id", "adjust_ride_for_late_friends"}


@dataclass
class ScenarioMetrics:
    """Metrics for a single scenario run."""

    scenario_name: str
    model: str
    success: bool = False
    # Observe mode metrics
    observe_tool_calls: int = 0
    observe_proposals: int = 0  # send_message_to_user in observe mode
    observe_wait: int = 0  # wait calls in observe mode
    # Execute mode metrics
    execute_tool_calls: int = 0
    # User metrics
    user_accepts: int = 0
    user_rejects: int = 0

    @property
    def observe_read_only_calls(self) -> int:
        """Read-only calls = total observe calls - proposals - wait."""
        return self.observe_tool_calls - self.observe_proposals - self.observe_wait


@dataclass
class ModelMetrics:
    """Aggregated metrics for a model across all scenarios."""

    model: str
    total_scenarios: int = 0
    passed_scenarios: int = 0
    failed_scenarios: int = 0
    # Aggregated counts
    total_observe_tool_calls: int = 0
    total_observe_proposals: int = 0
    total_observe_wait: int = 0
    total_execute_tool_calls: int = 0
    total_user_accepts: int = 0
    total_user_rejects: int = 0
    # Per-scenario data
    scenario_metrics: list[ScenarioMetrics] = field(default_factory=list)

    @property
    def total_observe_read_only_calls(self) -> int:
        """Total read-only calls in observe mode."""
        return self.total_observe_tool_calls - self.total_observe_proposals - self.total_observe_wait

    @property
    def accuracy(self) -> float:
        """Pass/fail accuracy."""
        if self.total_scenarios == 0:
            return 0.0
        return self.passed_scenarios / self.total_scenarios

    @property
    def proposal_rate(self) -> float:
        """Proposals / total observe tool calls."""
        if self.total_observe_tool_calls == 0:
            return 0.0
        return self.total_observe_proposals / self.total_observe_tool_calls

    @property
    def acceptance_rate(self) -> float:
        """Accepted proposals / total proposals."""
        if self.total_observe_proposals == 0:
            return 0.0
        return self.total_user_accepts / self.total_observe_proposals

    @property
    def avg_observe_read_only_calls(self) -> float:
        """Average read-only tool calls in observe mode per scenario."""
        if self.total_scenarios == 0:
            return 0.0
        return self.total_observe_read_only_calls / self.total_scenarios

    @property
    def avg_read_only_per_proposal(self) -> float:
        """Average read-only tool calls per proposal."""
        if self.total_observe_proposals == 0:
            return 0.0
        return self.total_observe_read_only_calls / self.total_observe_proposals

    @property
    def avg_execute_tool_calls(self) -> float:
        """Average tool calls in execute mode per scenario."""
        if self.total_scenarios == 0:
            return 0.0
        return self.total_execute_tool_calls / self.total_scenarios


@dataclass
class ScenarioAggregateMetrics:
    """Aggregated metrics for a scenario across all models."""

    scenario_name: str
    total_runs: int = 0
    passed_runs: int = 0
    # Aggregated counts
    total_observe_tool_calls: int = 0
    total_observe_proposals: int = 0
    total_observe_wait: int = 0
    total_execute_tool_calls: int = 0
    total_user_accepts: int = 0

    @property
    def total_observe_read_only_calls(self) -> int:
        return self.total_observe_tool_calls - self.total_observe_proposals - self.total_observe_wait

    @property
    def accuracy(self) -> float:
        if self.total_runs == 0:
            return 0.0
        return self.passed_runs / self.total_runs

    @property
    def proposal_rate(self) -> float:
        if self.total_observe_tool_calls == 0:
            return 0.0
        return self.total_observe_proposals / self.total_observe_tool_calls

    @property
    def acceptance_rate(self) -> float:
        if self.total_observe_proposals == 0:
            return 0.0
        return self.total_user_accepts / self.total_observe_proposals

    @property
    def avg_observe_read_only_calls(self) -> float:
        if self.total_runs == 0:
            return 0.0
        return self.total_observe_read_only_calls / self.total_runs

    @property
    def avg_read_only_per_proposal(self) -> float:
        if self.total_observe_proposals == 0:
            return 0.0
        return self.total_observe_read_only_calls / self.total_observe_proposals

    @property
    def avg_execute_tool_calls(self) -> float:
        if self.total_runs == 0:
            return 0.0
        return self.total_execute_tool_calls / self.total_runs


def analyze_trace(trace_path: Path, model: str, scenarios_filter: set[str] | None = None) -> ScenarioMetrics | None:
    """Analyze a single trace file using completed_events."""
    scenario_name = trace_path.stem

    # Skip excluded scenarios
    if scenario_name in EXCLUDED_SCENARIOS:
        return None

    # Apply scenarios filter if provided
    if scenarios_filter is not None and scenario_name not in scenarios_filter:
        return None

    with open(trace_path) as f:
        data = json.load(f)

    completed_events = data.get("completed_events", [])

    metrics = ScenarioMetrics(scenario_name=scenario_name, model=model)

    for event in completed_events:
        event_type = event.get("event_type", "")
        action = event.get("action", {})
        metadata = event.get("metadata", {})
        function_name = action.get("function", "")

        if event_type == "AGENT":
            proactive_mode = metadata.get("proactive_mode", "")

            if proactive_mode == "observe":
                metrics.observe_tool_calls += 1
                if function_name == "send_message_to_user":
                    metrics.observe_proposals += 1
                elif function_name == "wait":
                    metrics.observe_wait += 1

            elif proactive_mode == "execute":
                metrics.execute_tool_calls += 1
                # Execute mode proposals also count as proposals
                if function_name == "send_message_to_user":
                    metrics.observe_proposals += 1

        elif event_type == "USER":
            if function_name == "accept_proposal":
                metrics.user_accepts += 1
            elif function_name == "reject_proposal":
                metrics.user_rejects += 1

    return metrics


def analyze_model_directory(model_dir: Path, scenarios_filter: set[str] | None = None) -> ModelMetrics | None:
    """Analyze all traces for a single model."""
    model = model_dir.name

    # Read result summary
    result_summary_path = model_dir / "result_summary.json"
    if not result_summary_path.exists():
        print(f"  Warning: No result_summary.json found for {model}")
        return None

    with open(result_summary_path) as f:
        result_summary = json.load(f)

    model_metrics = ModelMetrics(model=model)

    # Build a map of scenario -> success from result summary
    scenario_success = {}
    for result in result_summary.get("results", []):
        scenario_name = result.get("scenario_name", "")
        if scenario_name in EXCLUDED_SCENARIOS:
            continue
        # Apply scenarios filter if provided
        if scenarios_filter is not None and scenario_name not in scenarios_filter:
            continue
        scenario_success[scenario_name] = result.get("success", False)
        model_metrics.total_scenarios += 1
        if result.get("success"):
            model_metrics.passed_scenarios += 1
        else:
            model_metrics.failed_scenarios += 1

    # Analyze each trace file
    for trace_file in model_dir.glob("*.json"):
        if trace_file.name == "result_summary.json":
            continue

        scenario_metrics = analyze_trace(trace_file, model, scenarios_filter)
        if scenario_metrics is None:
            continue

        # Update success from result summary
        scenario_metrics.success = scenario_success.get(scenario_metrics.scenario_name, False)

        model_metrics.scenario_metrics.append(scenario_metrics)

        # Aggregate counts
        model_metrics.total_observe_tool_calls += scenario_metrics.observe_tool_calls
        model_metrics.total_observe_proposals += scenario_metrics.observe_proposals
        model_metrics.total_observe_wait += scenario_metrics.observe_wait
        model_metrics.total_execute_tool_calls += scenario_metrics.execute_tool_calls
        model_metrics.total_user_accepts += scenario_metrics.user_accepts
        model_metrics.total_user_rejects += scenario_metrics.user_rejects

    return model_metrics


def aggregate_by_scenario(all_model_metrics: list[ModelMetrics]) -> dict[str, ScenarioAggregateMetrics]:
    """Aggregate metrics by scenario across all models."""
    scenario_aggregates: dict[str, ScenarioAggregateMetrics] = {}

    for model_metrics in all_model_metrics:
        for sm in model_metrics.scenario_metrics:
            if sm.scenario_name not in scenario_aggregates:
                scenario_aggregates[sm.scenario_name] = ScenarioAggregateMetrics(scenario_name=sm.scenario_name)

            agg = scenario_aggregates[sm.scenario_name]
            agg.total_runs += 1
            if sm.success:
                agg.passed_runs += 1
            agg.total_observe_tool_calls += sm.observe_tool_calls
            agg.total_observe_proposals += sm.observe_proposals
            agg.total_observe_wait += sm.observe_wait
            agg.total_execute_tool_calls += sm.execute_tool_calls
            agg.total_user_accepts += sm.user_accepts

    return scenario_aggregates


def print_model_metrics_table(all_metrics: list[ModelMetrics]) -> None:
    """Print model metrics as a formatted table."""
    print("\n" + "=" * 120)
    print("MODEL METRICS (aggregated across all scenarios)")
    print("=" * 120)

    # Header
    print(
        f"{'Model':<20} {'Accuracy':>8} {'PropRate':>9} {'AcceptRate':>10} "
        f"{'AvgObsRO':>9} {'RO/Prop':>8} {'AvgExec':>8} {'Pass/Total':>10}"
    )
    print("-" * 120)

    for m in sorted(all_metrics, key=lambda x: x.accuracy, reverse=True):
        print(
            f"{m.model:<20} {m.accuracy:>8.1%} {m.proposal_rate:>9.2%} {m.acceptance_rate:>10.1%} "
            f"{m.avg_observe_read_only_calls:>9.1f} {m.avg_read_only_per_proposal:>8.1f} "
            f"{m.avg_execute_tool_calls:>8.1f} {m.passed_scenarios:>4}/{m.total_scenarios:<5}"
        )

    print("-" * 120)


def print_scenario_metrics_table(scenario_metrics: dict[str, ScenarioAggregateMetrics]) -> None:
    """Print scenario metrics as a formatted table."""
    print("\n" + "=" * 130)
    print("SCENARIO METRICS (aggregated across all models)")
    print("=" * 130)

    # Header
    print(
        f"{'Scenario':<45} {'Accuracy':>8} {'PropRate':>9} {'AcceptRate':>10} "
        f"{'AvgObsRO':>9} {'RO/Prop':>8} {'AvgExec':>8} {'Pass/Total':>10}"
    )
    print("-" * 130)

    for name in sorted(scenario_metrics.keys()):
        s = scenario_metrics[name]
        print(
            f"{name:<45} {s.accuracy:>8.1%} {s.proposal_rate:>9.2%} {s.acceptance_rate:>10.1%} "
            f"{s.avg_observe_read_only_calls:>9.1f} {s.avg_read_only_per_proposal:>8.1f} "
            f"{s.avg_execute_tool_calls:>8.1f} {s.passed_runs:>4}/{s.total_runs:<5}"
        )

    print("-" * 130)


def save_results_json(
    all_metrics: list[ModelMetrics],
    scenario_metrics: dict[str, ScenarioAggregateMetrics],
    output_path: Path,
) -> None:
    """Save results to JSON file."""
    results = {
        "model_metrics": [
            {
                "model": m.model,
                "total_scenarios": m.total_scenarios,
                "passed_scenarios": m.passed_scenarios,
                "failed_scenarios": m.failed_scenarios,
                "accuracy": m.accuracy,
                "proposal_rate": m.proposal_rate,
                "acceptance_rate": m.acceptance_rate,
                "avg_observe_read_only_calls": m.avg_observe_read_only_calls,
                "avg_read_only_per_proposal": m.avg_read_only_per_proposal,
                "avg_execute_tool_calls": m.avg_execute_tool_calls,
                "raw_counts": {
                    "total_observe_tool_calls": m.total_observe_tool_calls,
                    "total_observe_proposals": m.total_observe_proposals,
                    "total_observe_wait": m.total_observe_wait,
                    "total_observe_read_only_calls": m.total_observe_read_only_calls,
                    "total_execute_tool_calls": m.total_execute_tool_calls,
                    "total_user_accepts": m.total_user_accepts,
                    "total_user_rejects": m.total_user_rejects,
                },
            }
            for m in all_metrics
        ],
        "scenario_metrics": [
            {
                "scenario_name": s.scenario_name,
                "total_runs": s.total_runs,
                "passed_runs": s.passed_runs,
                "accuracy": s.accuracy,
                "proposal_rate": s.proposal_rate,
                "acceptance_rate": s.acceptance_rate,
                "avg_observe_read_only_calls": s.avg_observe_read_only_calls,
                "avg_read_only_per_proposal": s.avg_read_only_per_proposal,
                "avg_execute_tool_calls": s.avg_execute_tool_calls,
            }
            for s in scenario_metrics.values()
        ],
    }

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to: {output_path}")


def load_scenarios_filter(scenarios_arg: list[str] | None) -> set[str] | None:
    """Load scenarios filter from file or space-separated list.

    Args:
        scenarios_arg: List containing either a single file path or multiple scenario names.

    Returns:
        Set of scenario names to include, or None if no filter specified.
    """
    if not scenarios_arg:
        return None

    # Check if first argument is a file
    if len(scenarios_arg) == 1:
        scenarios_path = Path(scenarios_arg[0])
        if scenarios_path.exists():
            # Load from file
            scenarios = set()
            with open(scenarios_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        scenarios.add(line)
            return scenarios

    # Treat as space-separated list of scenario names
    return {s.strip() for s in scenarios_arg if s.strip()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze PARE traces and compute metrics.")
    parser.add_argument(
        "--traces",
        "-t",
        type=Path,
        required=True,
        help="Path to traces directory",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output JSON file path (default: <traces_dir>/metrics.json)",
    )
    parser.add_argument(
        "--scenarios",
        "-s",
        nargs="*",
        default=None,
        help="Filter to specific scenarios: path to file (one per line) or space-separated list",
    )
    args = parser.parse_args()

    traces_dir = args.traces
    if not traces_dir.exists():
        print(f"Error: Traces directory not found: {traces_dir}")
        return

    # Load scenarios filter
    scenarios_filter = load_scenarios_filter(args.scenarios)

    print(f"Analyzing traces in: {traces_dir}")
    print(f"Excluding scenarios: {EXCLUDED_SCENARIOS}")
    if scenarios_filter:
        print(f"Filtering to scenarios: {scenarios_filter}")

    # Find all model directories
    model_dirs = [d for d in traces_dir.iterdir() if d.is_dir()]

    if not model_dirs:
        print("Error: No model directories found")
        return

    print(f"Found {len(model_dirs)} model directories")

    # Analyze each model
    all_metrics: list[ModelMetrics] = []
    for model_dir in sorted(model_dirs):
        print(f"  Analyzing {model_dir.name}...")
        metrics = analyze_model_directory(model_dir, scenarios_filter)
        if metrics:
            all_metrics.append(metrics)

    if not all_metrics:
        print("Error: No metrics collected")
        return

    # Aggregate by scenario
    scenario_metrics = aggregate_by_scenario(all_metrics)

    # Print tables
    print_model_metrics_table(all_metrics)
    print_scenario_metrics_table(scenario_metrics)

    # Save to JSON
    if args.output:
        output_path = args.output
    else:
        # Default: results/<traces_dir_name>[_<scenario_file_name>].json
        output_name = traces_dir.name
        if args.scenarios and len(args.scenarios) == 1:
            scenario_file = Path(args.scenarios[0])
            if scenario_file.exists():
                output_name = f"{output_name}_{scenario_file.stem}"
        output_path = Path("results") / f"{output_name}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

    save_results_json(all_metrics, scenario_metrics, output_path)


if __name__ == "__main__":
    main()
