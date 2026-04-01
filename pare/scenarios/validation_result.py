"""PARE-specific validation result classes for scenario execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from pare.scenarios.config import MultiScenarioRunnerConfig

# Schema for PARE result DataFrames - used by to_polars() and combine_results_to_dataframe()
PARE_RESULT_SCHEMA: dict[str, type[pl.DataType]] = {
    "base_scenario_id": pl.Utf8,
    "run_number": pl.Int64,
    "success_numeric": pl.Float64,
    "success_bool": pl.Boolean,
    "status": pl.Utf8,
    "has_exception": pl.Boolean,
    "exception_type": pl.Utf8,
    "exception_message": pl.Utf8,
    "rationale": pl.Utf8,
    "export_path": pl.Utf8,
    "run_duration": pl.Float64,
    "job_duration": pl.Float64,
    "user_model": pl.Utf8,
    "user_provider": pl.Utf8,
    "observe_model": pl.Utf8,
    "observe_provider": pl.Utf8,
    "execute_model": pl.Utf8,
    "execute_provider": pl.Utf8,
    "agent_type": pl.Utf8,
    "proactive_model": pl.Utf8,
    "tool_failure_probability": pl.Float64,
    "num_env_events_per_minute": pl.Int64,
    "proposal_count": pl.Int64,
    "acceptance_count": pl.Int64,
    "read_only_actions": pl.Int64,
    "write_actions": pl.Int64,
    "number_of_turns": pl.Int64,
    "proposal_rate": pl.Float64,
    "acceptance_rate": pl.Float64,
}


@dataclass
class PAREScenarioValidationResult:
    """PARE-specific scenario validation result with proactive agent metrics.

    Standalone dataclass (not extending Meta-ARE's ScenarioValidationResult)
    to avoid dataclass inheritance issues.
    """

    # Base fields (mirrored from Meta-ARE's ScenarioValidationResult)

    # Flag indicating whether the scenario validation was successful.
    # None indicated that the judge or run failed (an exception occurred).
    success: bool | None

    # Optional exception that occured during validation, if any.
    exception: Exception | None = None

    # Optional path to exported traces, if applicable.
    export_path: str | None = None

    # Optional description of the rationale.
    rationale: str | None = None

    # Duration of the run in seconds.
    duration: float | None = None

    # PARE-specific stored fields
    proposal_count: int = 0
    acceptance_count: int = 0
    read_only_actions: int = 0
    write_actions: int = 0
    number_of_turns: int = 0

    @property
    def proposal_rate(self) -> float:
        """Proposals per turn."""
        if self.number_of_turns == 0:
            return 0.0
        return self.proposal_count / self.number_of_turns

    @property
    def acceptance_rate(self) -> float:
        """Accepted proposals / total proposals."""
        if self.proposal_count == 0:
            return 0.0
        return self.acceptance_count / self.proposal_count


@dataclass
class PAREMultiScenarioValidationResult:
    """PARE-specific multi-scenario validation result with proactive agent metrics."""

    run_config: MultiScenarioRunnerConfig

    # Dictionary mapping (base_scenario_id, run_number) tuples to their respective validation results
    scenario_results: dict[tuple[str, int | None], PAREScenarioValidationResult] = field(default_factory=dict)

    # Duration of the entire validation run in seconds
    duration: float = 0.0

    # Counts of different scenario outcomes
    successful_count: int = 0
    failed_count: int = 0
    exception_count: int = 0
    no_validation_count: int = 0

    @property
    def total_proposals(self) -> int:
        """Total number of proposals across all scenarios."""
        return sum(result.proposal_count for result in self.scenario_results.values())

    @property
    def total_acceptances(self) -> int:
        """Total number of accepted proposals across all scenarios."""
        return sum(result.acceptance_count for result in self.scenario_results.values())

    @property
    def total_turns(self) -> int:
        """Total number of turns across all scenarios."""
        return sum(result.number_of_turns for result in self.scenario_results.values())

    @property
    def total_read_only_actions(self) -> int:
        """Total number of read-only actions across all scenarios."""
        return sum(result.read_only_actions for result in self.scenario_results.values())

    @property
    def total_write_actions(self) -> int:
        """Total number of write actions across all scenarios."""
        return sum(result.write_actions for result in self.scenario_results.values())

    @property
    def aggregate_proposal_rate(self) -> float:
        """Overall proposals per turn across all scenarios."""
        if self.total_turns == 0:
            return 0.0
        return self.total_proposals / self.total_turns

    @property
    def aggregate_acceptance_rate(self) -> float:
        """Overall accepted proposals / total proposals across all scenarios."""
        if self.total_proposals == 0:
            return 0.0
        return self.total_acceptances / self.total_proposals

    @property
    def success_rate(self) -> float:
        """Overall success rate across all scenarios."""
        total_validations = self.successful_count + self.failed_count + self.exception_count + self.no_validation_count
        if total_validations == 0:
            return 0.0
        return self.successful_count / total_validations

    def success_rate_updated(self) -> float:
        """Overall success rate across all scenarios."""
        total_validations = self.successful_count + self.failed_count + self.exception_count + self.no_validation_count
        if total_validations == 0:
            return 0.0
        return self.successful_count / total_validations

    def add_result(self, result: PAREScenarioValidationResult, scenario_id: str, run_number: int | None = None) -> None:
        """Add a scenario validation result to the multi-scenario results.

        Args:
            result: The PAREScenarioValidationResult to add.
            scenario_id: The base scenario ID.
            run_number: The run number (optional).
        """
        self.scenario_results[(scenario_id, run_number)] = result

        # Update counts based on the result's success status
        if result.success is True:
            self.successful_count += 1
        elif result.success is False:
            self.failed_count += 1
        elif result.exception is not None:
            self.exception_count += 1
        else:
            self.no_validation_count += 1

    def to_polars(self, extra_columns: dict[str, str] | None = None) -> pl.DataFrame:
        """Convert the multi-scenario validation results to a Polars DataFrame.

        Args:
            extra_columns: Addtional columns to add to each row (e.g., phase_name, config, etc.)

        Returns:
            Polars DataFrame with one row per scenario run.
        """
        rows = []

        for scenario_key, scenario_result in self.scenario_results.items():
            base_scenario_id, run_number = scenario_key

            # Convert success to numeric (1.0 for True, 0.0 for False, None for exception)
            success_numeric = (
                1.0 if scenario_result.success is True else 0.0 if scenario_result.success is False else None
            )

            # Determine status
            if scenario_result.success is True:
                status = "success"
            elif scenario_result.success is False:
                status = "failed"
            elif scenario_result.exception is not None:
                status = "exception"
            else:
                status = "no_validation"

            row = {
                # Scenario identification
                "base_scenario_id": base_scenario_id,
                "run_number": run_number,
                # Success fields
                "success_numeric": success_numeric,
                "success_bool": scenario_result.success,
                "status": status,
                # Exception fields
                "has_exception": scenario_result.exception is not None,
                "exception_type": type(scenario_result.exception).__name__ if scenario_result.exception else None,
                "exception_message": str(scenario_result.exception) if scenario_result.exception else None,
                # Other base fields
                "rationale": scenario_result.rationale,
                "export_path": scenario_result.export_path,
                "run_duration": scenario_result.duration,
                "job_duration": self.duration,
                # Model configuration (PARE has 3 agents) - use aliases for human-readable names
                "user_model": self.run_config.user_model_alias,
                "user_provider": self.run_config.user_engine_config.provider,
                "observe_model": self.run_config.observe_model_alias,
                "observe_provider": self.run_config.observe_engine_config.provider,
                "execute_model": self.run_config.execute_model_alias,
                "execute_provider": self.run_config.execute_engine_config.provider,
                # Agent type and proactive model identifier (for aggregation key)
                "agent_type": self.run_config.agent_type,
                "proactive_model": f"{self.run_config.agent_type}_{self.run_config.observe_model_alias}_{self.run_config.execute_model_alias}",
                # Noise configuration
                "tool_failure_probability": (
                    self.run_config.tool_augmentation_config.tool_failure_probability
                    if self.run_config.tool_augmentation_config is not None
                    else 0.0
                ),
                "num_env_events_per_minute": (
                    self.run_config.env_events_config.num_env_events_per_minute
                    if self.run_config.env_events_config is not None
                    else 0
                ),
                # PARE-specific metrics
                "proposal_count": scenario_result.proposal_count,
                "acceptance_count": scenario_result.acceptance_count,
                "read_only_actions": scenario_result.read_only_actions,
                "write_actions": scenario_result.write_actions,
                "number_of_turns": scenario_result.number_of_turns,
                "proposal_rate": scenario_result.proposal_rate,
                "acceptance_rate": scenario_result.acceptance_rate,
            }

            # Add any extra columns provided (cast all values to string to ensure consistent schema)
            if extra_columns:
                row.update({k: str(v) for k, v in extra_columns.items()})
            rows.append(row)

        # Build schema from the module-level constant, adding any extra columns
        schema = dict(PARE_RESULT_SCHEMA)
        if extra_columns:
            for col_name in extra_columns:
                if col_name not in schema:
                    schema[col_name] = pl.Utf8

        return pl.DataFrame(rows, schema=schema)

    def description(
        self,
        split: str = "unknown",
        weight_per_app_class: dict[str, float] | None = None,
    ) -> str:
        """Generate human-readable summary with PARE metrics.

        Uses the reporting infrastructure for consistency with combined reports.

        Args:
            split: Dataset split name (e.g., "full", "ablation").
            weight_per_app_class: Weight per app class from EnvEventsConfig.

        Returns:
            Formatted report string.
        """
        # Import inside method to avoid circular import
        from pare.benchmark.report_stats import generate_validation_report

        df = self.to_polars()
        return generate_validation_report(df, split, weight_per_app_class)
