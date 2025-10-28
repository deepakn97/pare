"""Scenario generator module for registering custom scenarios."""

import importlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from are.simulation.scenarios.utils.registry import ScenarioRegistry

logger = logging.getLogger(__name__)


def register_custom_scenarios(registry: "ScenarioRegistry") -> None:
    """Register all custom scenarios from this project with the provided registry.

    This function is called by the meta-ARE framework when it discovers the
    custom scenarios entry point. It imports all custom scenario modules,
    which triggers the @register_scenario decorators.

    Args:
        registry: The ScenarioRegistry instance to register with
    """
    logger.info("Registering custom scenarios from ProactiveAgentSandbox")

    # Import modules containing custom scenarios
    custom_scenario_modules = [
        "pas.scenario_generator.example_proactive_scenarios.scenario",
        "pas.scenario_generator.example_proactive_scenarios.scenario_with_all_apps_init",
        # Add other custom scenario modules here as needed
    ]

    # Import individual generated scenario files (since generated_scenarios is not a package)
    generated_scenario_files = [
        "pas.scenarios.generated_scenarios.budget_summary_creation",
        "pas.scenarios.generated_scenarios.contact_update_notify",
        "pas.scenarios.generated_scenarios.customer_feedback_analysis_workflow",
        "pas.scenarios.generated_scenarios.document_reminder",
        "pas.scenarios.generated_scenarios.file_cleanup",
        "pas.scenarios.generated_scenarios.file_summary_share",
        "pas.scenarios.generated_scenarios.financial_report_planning",
        "pas.scenarios.generated_scenarios.followup_contact_update",
        "pas.scenarios.generated_scenarios.followup_documents",
        "pas.scenarios.generated_scenarios.generate_project_kickoff_meetings",
        "pas.scenarios.generated_scenarios.invoice_organizer",
        "pas.scenarios.generated_scenarios.meeting_note_proposal",
        "pas.scenarios.generated_scenarios.personal_travel_itinerary_manager",
        "pas.scenarios.generated_scenarios.proactive_file_summary",
        "pas.scenarios.generated_scenarios.project_migration_support",
        "pas.scenarios.generated_scenarios.reminder_deadline_followup",
        "pas.scenarios.generated_scenarios.remote_training_workshop_assistant",
        "pas.scenarios.generated_scenarios.schedule_meeting",
        "pas.scenarios.generated_scenarios.supplier_contract_update_workflow",
        "pas.scenarios.generated_scenarios.task_digest_and_summary_suggestion",
        "pas.scenarios.generated_scenarios.team_event_gallery_preparation",
    ]

    imported_count = 0
    for module_name in custom_scenario_modules:
        try:
            importlib.import_module(module_name)
            imported_count += 1
            logger.debug(f"Imported custom scenario module: {module_name}")
        except Exception as e:
            logger.warning(f"Failed to import custom scenario module {module_name}: {e}", exc_info=True)

    # Import generated scenario files
    for scenario_file in generated_scenario_files:
        try:
            importlib.import_module(scenario_file)
            imported_count += 1
            logger.debug(f"Imported generated scenario file: {scenario_file}")
        except Exception as e:
            logger.warning(f"Failed to import generated scenario file {scenario_file}: {e}", exc_info=True)

    logger.info(f"Registered custom scenarios from {imported_count} modules")
