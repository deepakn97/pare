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
    # Note: This list is maintained manually and should be updated when new scenarios are added
    generated_scenario_files = [
        "pas.scenarios.generated_scenarios.3apps_group.apartment_search_and_save_proactive",
        "pas.scenarios.generated_scenarios.3apps_group.city_safety_advice",
        "pas.scenarios.generated_scenarios.3apps_group.contact_directory_update",
        "pas.scenarios.generated_scenarios.3apps_group.daily_commute_planning",
        "pas.scenarios.generated_scenarios.3apps_group.daily_task_planner_proactive",
        "pas.scenarios.generated_scenarios.3apps_group.email_cleanup_and_reply",
        "pas.scenarios.generated_scenarios.3apps_group.file_organization_proactive_backup",
        "pas.scenarios.generated_scenarios.3apps_group.office_report_review_and_archive",
        "pas.scenarios.generated_scenarios.3apps_group.online_shopping_discount_checkout",
        "pas.scenarios.generated_scenarios.3apps_group.online_shopping_proactive_checkout",
        "pas.scenarios.generated_scenarios.3apps_group.project_file_organization",
        "pas.scenarios.generated_scenarios.3apps_group.rental_search_assistant",
        "pas.scenarios.generated_scenarios.3apps_group.team_meeting_sync_proactive",
        "pas.scenarios.generated_scenarios.3apps_group.team_update_coordinator",
        "pas.scenarios.generated_scenarios.4apps_group.apartment_safety_check",
        "pas.scenarios.generated_scenarios.4apps_group.apartment_safety_selection",
        "pas.scenarios.generated_scenarios.4apps_group.apartment_viewing_schedule",
        "pas.scenarios.generated_scenarios.4apps_group.auto_meeting_with_cab_booking",
        "pas.scenarios.generated_scenarios.4apps_group.city_safety_apartment_suggestion",
        "pas.scenarios.generated_scenarios.4apps_group.compare_apartment_rentals",
        "pas.scenarios.generated_scenarios.4apps_group.compare_market_inventories",
        "pas.scenarios.generated_scenarios.4apps_group.document_organizer_proactive",
        "pas.scenarios.generated_scenarios.4apps_group.dual_storage_sync_confirmation",
        "pas.scenarios.generated_scenarios.4apps_group.email_to_calendar_confirmation",
        "pas.scenarios.generated_scenarios.4apps_group.email_to_reminder_conversion",
        "pas.scenarios.generated_scenarios.4apps_group.express_gadget_delivery",
        "pas.scenarios.generated_scenarios.4apps_group.online_order_pickup_trip",
        "pas.scenarios.generated_scenarios.4apps_group.project_file_sync_proactive",
        "pas.scenarios.generated_scenarios.4apps_group.project_planning_proactive",
        "pas.scenarios.generated_scenarios.4apps_group.safe_apartment_finder",
        "pas.scenarios.generated_scenarios.4apps_group.sync_contact_from_email_proactive",
        "pas.scenarios.generated_scenarios.4apps_group.sync_contacts_from_chat",
        "pas.scenarios.generated_scenarios.4apps_group.team_file_share_collaboration",
        "pas.scenarios.generated_scenarios.4apps_group.team_meeting_coordination",
        "pas.scenarios.generated_scenarios.4apps_group.team_meeting_from_email",
        "pas.scenarios.generated_scenarios.4apps_group.teamfollowup_with_reminder",
        "pas.scenarios.generated_scenarios.5apps_group.apartment_hunt_transport_and_schedule",
        "pas.scenarios.generated_scenarios.5apps_group.apartment_safety_comparison",
        "pas.scenarios.generated_scenarios.5apps_group.asset_sync_and_share",
        "pas.scenarios.generated_scenarios.5apps_group.business_meeting_coordination",
        "pas.scenarios.generated_scenarios.5apps_group.city_relocation_advisor",
        "pas.scenarios.generated_scenarios.5apps_group.customer_purchase_and_vendor_update",
        "pas.scenarios.generated_scenarios.5apps_group.document_archive_proposal",
        "pas.scenarios.generated_scenarios.5apps_group.influencer_collab_campaign",
        "pas.scenarios.generated_scenarios.5apps_group.inventory_update_and_order_proposal",
        "pas.scenarios.generated_scenarios.5apps_group.productivity_followup_workflow",
        "pas.scenarios.generated_scenarios.5apps_group.productivity_supply_planner",
        "pas.scenarios.generated_scenarios.5apps_group.project_brainstorm_management",
        "pas.scenarios.generated_scenarios.5apps_group.relocation_with_safety_check",
        "pas.scenarios.generated_scenarios.5apps_group.rental_inquiry_proactive_forward",
        "pas.scenarios.generated_scenarios.5apps_group.safety_shopping_and_ride",
        "pas.scenarios.generated_scenarios.5apps_group.social_ride_coordination",
        "pas.scenarios.generated_scenarios.5apps_group.team_collaboration_project_files",
        "pas.scenarios.generated_scenarios.5apps_group.team_project_sync_proposal",
        "pas.scenarios.generated_scenarios.5apps_group.travel_assistant_with_calendar_and_ride",
        "pas.scenarios.generated_scenarios.5apps_group.urban_relocation_day",
        "pas.scenarios.generated_scenarios.6apps_group.apartment_hunt_assistant",
        "pas.scenarios.generated_scenarios.6apps_group.apartment_search_and_share",
        "pas.scenarios.generated_scenarios.6apps_group.apartment_viewing_coordination",
        "pas.scenarios.generated_scenarios.6apps_group.city_living_home_setup_assistant",
        "pas.scenarios.generated_scenarios.6apps_group.city_trip_coordination",
        "pas.scenarios.generated_scenarios.6apps_group.daily_errand_plan_with_city_safety",
        "pas.scenarios.generated_scenarios.6apps_group.ecommerce_followup_workflow",
        "pas.scenarios.generated_scenarios.6apps_group.ecommerce_support_transaction_workflow",
        "pas.scenarios.generated_scenarios.6apps_group.email_to_filesystem_archival",
        "pas.scenarios.generated_scenarios.6apps_group.lifestyle_concierge_apartment_move",
        "pas.scenarios.generated_scenarios.6apps_group.personal_productivity_meeting",
        "pas.scenarios.generated_scenarios.6apps_group.productivity_sync_flow",
        "pas.scenarios.generated_scenarios.6apps_group.project_sync_and_fileshare",
        "pas.scenarios.generated_scenarios.6apps_group.secure_doc_sync",
        "pas.scenarios.generated_scenarios.6apps_group.shopping_delivery_tracking",
        "pas.scenarios.generated_scenarios.6apps_group.storage_backup_proactive",
        "pas.scenarios.generated_scenarios.6apps_group.team_field_meeting_coordination",
        "pas.scenarios.generated_scenarios.6apps_group.team_report_summary_and_meeting",
        "pas.scenarios.generated_scenarios.6apps_group.trip_to_safe_conference",
        "pas.scenarios.generated_scenarios.6apps_group.unified_communication_followup",
        "pas.scenarios.generated_scenarios.7apps_group.budget_summary_creation",
        "pas.scenarios.generated_scenarios.7apps_group.contact_update_notify",
        "pas.scenarios.generated_scenarios.7apps_group.document_reminder",
        "pas.scenarios.generated_scenarios.7apps_group.file_cleanup",
        "pas.scenarios.generated_scenarios.7apps_group.file_summary_share",
        "pas.scenarios.generated_scenarios.7apps_group.financial_report_planning",
        "pas.scenarios.generated_scenarios.7apps_group.followup_contact_update",
        "pas.scenarios.generated_scenarios.7apps_group.followup_documents",
        "pas.scenarios.generated_scenarios.7apps_group.generate_project_kickoff_meetings",
        "pas.scenarios.generated_scenarios.7apps_group.invoice_organizer",
        "pas.scenarios.generated_scenarios.7apps_group.meeting_note_proposal",
        "pas.scenarios.generated_scenarios.7apps_group.personal_travel_itinerary_manager",
        "pas.scenarios.generated_scenarios.7apps_group.proactive_file_summary",
        "pas.scenarios.generated_scenarios.7apps_group.project_migration_support",
        "pas.scenarios.generated_scenarios.7apps_group.reminder_deadline_followup",
        "pas.scenarios.generated_scenarios.7apps_group.remote_training_workshop_assistant",
        "pas.scenarios.generated_scenarios.7apps_group.schedule_meeting",
        "pas.scenarios.generated_scenarios.7apps_group.supplier_contract_update_workflow",
        "pas.scenarios.generated_scenarios.7apps_group.task_digest_and_summary_suggestion",
        "pas.scenarios.generated_scenarios.7apps_group.team_event_gallery_preparation",
        "pas.scenarios.generated_scenarios.meeting_invite_coordination",
        "pas.scenarios.generated_scenarios.project_feedback_share",
        "pas.scenarios.generated_scenarios.weekend_grocery_pickup",
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
