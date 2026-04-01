"""PARE-specific scenario exporter with world_logs and proactive context support."""

from __future__ import annotations

import logging
import os
import tempfile
from typing import TYPE_CHECKING, Any

from are.simulation.data_handler.exporter import JsonScenarioExporter
from are.simulation.scenarios.utils.caching import get_run_id
from are.simulation.types import EventType

from pare.data_handler.models import (
    PAREEventMetadata,
    PAREExportedCompletedEvent,
    PAREExportedEventMetadata,
    PAREExportedTrace,
)

if TYPE_CHECKING:
    from are.simulation.agents.are_simulation_agent import BaseAgentLog
    from are.simulation.data_handler.models import ExportedTraceBase
    from are.simulation.environment import Environment
    from are.simulation.scenarios import Scenario
    from are.simulation.scenarios.config import ScenarioRunnerConfig
    from are.simulation.types import CompletedEvent, EventMetadata

logger = logging.getLogger(__name__)


class PAREJsonScenarioExporter(JsonScenarioExporter):
    """PARE-specific exporter that includes world_logs and proactive context."""

    def _get_trace(
        self,
        env: Environment,
        scenario: Scenario,
        scenario_id: str,
        model_id: str | None,
        agent_id: str | None,
        validation_decision: str | None,
        annotation_id: str | None,
        annotator_name: str | None,
        context: str | None,
        comment: str | None,
        apps_state: dict[str, Any] | None,
        world_logs: list[BaseAgentLog] | None = None,
        export_apps: bool = True,
        scenario_exception: Exception | None = None,
        runner_config: ScenarioRunnerConfig | None = None,
        **kwargs: Any,
    ) -> ExportedTraceBase:
        """Override to use PARE-specific trace conversion.

        Args:
            env: The environment to export the trace from.
            scenario: The scenario to export the trace for.
            scenario_id: The ID of the scenario.
            runner_config: The runner configuration.
            model_id: The model ID.
            agent_id: The agent ID.
            validation_decision: The validation decision.
            annotation_id: The annotation ID.
            annotator_name: The annotator name.
            context: The context.
            comment: The comment.
            apps_state: The apps state.
            world_logs: The world logs.
            export_apps: Whether to export the apps.
            scenario_exception: The scenario exception.
            **kwargs: Additional keyword arguments.

        Returns:
            The PARE-specific trace.
        """
        # ! NOTE: We convert the completed events twice, once inside the super()._get_trace method, and once here. this is necessary to avoid copying boilerplate code.
        trace: ExportedTraceBase = super()._get_trace(
            env,
            scenario,
            scenario_id,
            model_id,
            agent_id,
            validation_decision,
            annotation_id,
            annotator_name,
            context,
            comment,
            apps_state,
            world_logs,
            export_apps,
            scenario_exception,
            runner_config=runner_config,
            **kwargs,
        )
        completed_events = [
            self.convert_completed_pare_event(event)
            for event in env.event_log.list_view()
            if event.event_type
            != EventType.VALIDATION  # Validation events have Python functions that we can't serialize
        ]
        return PAREExportedTrace(
            metadata=trace.metadata,
            world_logs=trace.world_logs,
            events=trace.events,
            completed_events=completed_events,
            apps=trace.apps,
            version=trace.version,
            context=trace.context,
        )

    @staticmethod
    def convert_event_metadata(metadata: EventMetadata) -> PAREExportedEventMetadata:
        """Convert event metadata, extracting PARE-specific fields if present.

        Args:
            metadata: The event metadata to convert.

        Returns:
            The converted event metadata.
        """
        proactive_mode = None
        turn_number = None

        if isinstance(metadata, PAREEventMetadata):
            proactive_mode = metadata.proactive_mode
            turn_number = metadata.turn_number

        return PAREExportedEventMetadata(
            return_value=str(metadata.return_value) if metadata.return_value else None,
            return_value_type=type(metadata.return_value).__name__ if metadata.return_value else None,
            exception=metadata.exception,
            exception_stack_trace=metadata.exception_stack_trace,
            proactive_mode=proactive_mode,
            turn_number=turn_number,
        )

    @staticmethod
    def convert_completed_pare_event(event: CompletedEvent) -> PAREExportedCompletedEvent:
        """Override to use PARE-specific metadata conversion.

        Returns a dict instead of a Pydantic model because ExportedTrace expects
        ExportedCompletedEvent instances, and Pydantic v2 doesn't accept subclasses
        that aren't in the type annotation. Dicts are accepted and validated.

        Args:
            event: The completed event to convert.

        Returns:
            The exported completed event as a dict with PARE metadata fields.
        """
        action = JsonScenarioExporter.convert_action(event.action)

        return PAREExportedCompletedEvent(
            class_name=event.__class__.__name__,
            event_type=event.event_type.name,
            event_time=event.event_time if event.event_time else 0,
            event_id=event.event_id,
            event_relative_time=event.event_relative_time,
            dependencies=[dependency.event_id for dependency in event.dependencies],
            action=action,
            metadata=PAREJsonScenarioExporter.convert_event_metadata(event.metadata),
        )

    def export_to_json_file(
        self,
        env: Environment,
        scenario: Scenario,
        model_id: str | None = None,
        agent_id: str | None = None,
        validation_decision: str | None = None,
        validation_rationale: str | None = None,
        run_duration: float | None = None,
        output_dir: str | None = None,
        export_apps: bool = True,
        trace_dump_format: str = "hf",
        scenario_exception: Exception | None = None,
        runner_config: ScenarioRunnerConfig | None = None,
    ) -> tuple[bool, str | None]:
        """Export trace data with world_logs included.

        Overrides parent to properly pass world_logs for 'hf' format.

        Args:
            env: Environment containing the trace data.
            scenario: The scenario that was run.
            model_id: Model identifier string.
            agent_id: Agent identifier string.
            validation_decision: Validation decision (Valid/Invalid).
            validation_rationale: Rationale for validation decision.
            run_duration: Total run duration in seconds.
            output_dir: Directory to write the trace file.
            export_apps: Whether to include app states in export.
            trace_dump_format: Export format ('hf', 'lite', or 'both').
            scenario_exception: Any exception that occurred during scenario.
            runner_config: Optional runner configuration.

        Returns:
            Tuple of (success: bool, file_path: str | None).
        """
        if output_dir is None:
            output_dir = tempfile.gettempdir()
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        if trace_dump_format not in ["hf", "lite", "both"]:
            raise ValueError(f"{trace_dump_format} is an invalid dump format, must be 'hf', 'lite', or 'both'")

        try:
            if trace_dump_format == "hf":
                json_str = self.export_to_json(
                    env,
                    scenario,
                    scenario.scenario_id,
                    runner_config,
                    model_id,
                    agent_id,
                    validation_decision,
                    export_apps=export_apps,
                    scenario_exception=scenario_exception,
                    world_logs=env.get_world_logs(),  # THE FIX
                )
            elif trace_dump_format == "lite":
                logger.warning("Exporting trace in **lite format**, outputs will not be uploadable to HuggingFace.")
                json_str = self.export_to_json_lite(
                    env,
                    scenario,
                    scenario.scenario_id,
                    model_id,
                    agent_id,
                    validation_decision,
                    validation_rationale,
                    run_duration=run_duration,
                )
            elif trace_dump_format == "both":
                # Generate both formats
                hf_json_str = self.export_to_json(
                    env,
                    scenario,
                    scenario.scenario_id,
                    runner_config,
                    model_id,
                    agent_id,
                    validation_decision,
                    export_apps=export_apps,
                    scenario_exception=scenario_exception,
                    world_logs=env.get_world_logs(),  # THE FIX
                )
                lite_json_str = self.export_to_json_lite(
                    env,
                    scenario,
                    scenario.scenario_id,
                    model_id,
                    agent_id,
                    validation_decision,
                    validation_rationale,
                    run_duration,
                )

                # Create subdirectories and file paths
                hf_dir = os.path.join(output_dir, "hf")
                lite_dir = os.path.join(output_dir, "lite")
                os.makedirs(hf_dir, exist_ok=True)
                os.makedirs(lite_dir, exist_ok=True)

                base_filename = f"{get_run_id(scenario, runner_config)}.json"
                hf_file_path = os.path.join(hf_dir, base_filename)
                lite_file_path = os.path.join(lite_dir, base_filename)

                # Write both files
                with open(hf_file_path, "w", encoding="utf-8") as f:
                    f.write(hf_json_str)
                    f.flush()
                with open(lite_file_path, "w", encoding="utf-8") as f:
                    f.write(lite_json_str)
                    f.flush()

                return True, hf_file_path  # Return HF path for backward compatibility
        except Exception as e:
            logger.exception("Failed to export trace", exc_info=True)
            return False, None

        # Handle file writing for single format (hf or lite)
        base_filename = f"{get_run_id(scenario, runner_config)}.json"
        file_path = os.path.join(output_dir, base_filename)

        try:
            with open(file_path, "w", encoding="utf-8") as file:
                file.write(json_str)
                file.flush()
        except Exception as e:
            logger.exception("Failed to write trace file", exc_info=True)
            return False, None
        else:
            return True, file_path
