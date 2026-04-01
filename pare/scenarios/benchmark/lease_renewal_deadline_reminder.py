from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.email_client import Email, EmailFolderName
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulEmailApp,
)
from pare.apps.apartment import StatefulApartmentApp
from pare.apps.reminder import StatefulReminderApp
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("lease_renewal_deadline_reminder")
class LeaseRenewalDeadlineReminder(PAREScenario):
    """Agent manages lease renewal deadline from landlord email notification.

    The user has saved "Riverside Lofts" (managed by Metro Property Group) to their apartment favorites. An email arrives from Metro Property Group's leasing office about the upcoming lease renewal deadline for Riverside Lofts, stating that the current lease expires on March 31st, 2026, and the user must respond by February 15th, 2026 to secure current rates. The email mentions a new monthly rent of $2,100 (up from $2,000) and requests confirmation by the deadline. The agent must:
    1. Parse the renewal deadline, new rent, and apartment name from the email
    2. Search saved apartments to verify this matches one of the user's saved properties
    3. Update the apartment's price to reflect the new rent amount
    4. Create a reminder for February 10th (5 days before deadline) with title "Lease Renewal Decision - Riverside Lofts" and description including the deadline date, new rent, and action required
    5. Reply to the leasing office email acknowledging receipt and confirming the deadline is noted

    This scenario exercises landlord-initiated deadline coordination, cross-app data correlation (email → saved apartment lookup), proactive time management with advance-notice reminders for decision deadlines, apartment price updates, and closed-loop email acknowledgment.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with baseline data for lease renewal scenario."""
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize scenario specific apps
        self.email = StatefulEmailApp(name="Emails")
        self.apartment = StatefulApartmentApp(name="Apartment")
        self.reminder = StatefulReminderApp(name="Reminders")

        # Seed saved apartment: Riverside Lofts (current rent $2,000)
        riverside_apt_id = self.apartment.add_new_apartment(
            name="Riverside Lofts",
            location="Downtown District",
            zip_code="90210",
            price=2000.0,
            number_of_bedrooms=2,
            number_of_bathrooms=2,
            square_footage=1200,
            property_type="Apartment",
            furnished_status="Unfurnished",
            floor_level="Upper floors",
            pet_policy="Cats allowed",
            lease_term="1 year",
            amenities=["Gym", "Pool", "Parking"],
        )
        self.riverside_apt_id = riverside_apt_id
        self.apartment.save_apartment(riverside_apt_id)

        # Seed historical email thread: original lease agreement confirmation from 1 year ago
        original_lease_timestamp = datetime(2024, 11, 18, 10, 0, 0, tzinfo=UTC).timestamp()
        original_lease_email = Email(
            email_id="original_lease_001",
            sender="leasing@metroproperty.com",
            recipients=[self.email.user_email],
            subject="Lease Agreement Confirmation - Riverside Lofts",
            content="Dear Tenant,\n\nThank you for choosing Riverside Lofts! Your lease has been finalized for Unit 203 at $2,000/month, starting December 1, 2024 and ending March 31, 2026.\n\nBest regards,\nMetro Property Group Leasing Team",
            timestamp=original_lease_timestamp,
            is_read=True,
        )
        self.email.add_email(original_lease_email, EmailFolderName.INBOX)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.apartment, self.reminder]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        apartment_app = self.get_typed_app(StatefulApartmentApp, "Apartment")
        reminder_app = self.get_typed_app(StatefulReminderApp, "Reminders")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Incoming lease renewal email from Metro Property Group (triggers workflow)
            renewal_email_event = email_app.send_email_to_user_with_id(
                email_id="renewal_email_001",
                sender="leasing@metroproperty.com",
                subject="Lease Renewal Notice - Riverside Lofts Unit 203",
                content="Dear Tenant,\n\nYour current lease for Riverside Lofts Unit 203 expires on March 31, 2026. We are pleased to offer you a lease renewal at $2,100/month (up from $2,000/month).\n\nTo secure this rate and guarantee your continued residency, please confirm your renewal decision by February 15, 2026. If we do not hear from you by this deadline, the unit will be made available to other prospective tenants.\n\nPlease reply to this email with your decision at your earliest convenience.\n\nBest regards,\nMetro Property Group Leasing Office",
            ).delayed(15)

            # Oracle Event 1: Agent reads the renewal email to extract key details (motivated by env notification)
            # Motivation: renewal email notification arrived, agent needs to read full content to understand context
            read_email_event = (
                email_app.get_email_by_id(
                    email_id="renewal_email_001",
                    folder_name="INBOX",
                )
                .oracle()
                .depends_on(renewal_email_event, delay_seconds=3)
            )

            # Oracle Event 2: Agent searches saved apartments to verify this is a saved property
            # Motivation: email mentions "Riverside Lofts" apartment; agent needs to check if user has saved it
            search_saved_event = (
                apartment_app.list_saved_apartments().oracle().depends_on(read_email_event, delay_seconds=2)
            )

            # Oracle Event 3: Agent proposes to help manage the renewal deadline
            # Motivation: email explicitly states renewal deadline (Feb 15, 2026) and rent increase; saved apartment found
            proposal_event = (
                aui.send_message_to_user(
                    content="I received a lease renewal notice from Metro Property Group for your saved apartment Riverside Lofts. The lease expires March 31, 2026, and you must respond by February 15, 2026 to secure the new rate of $2,100/month (up from $2,000/month). Would you like me to update the apartment price, create a reminder for the deadline, and acknowledge receipt to the leasing office?"
                )
                .oracle()
                .depends_on([renewal_email_event, search_saved_event], delay_seconds=2)
            )

            # Oracle Event 4: User accepts the proposal
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please do all of that. Set the reminder a few days before the deadline so I have time to decide."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 5: Agent gets saved apartments to extract the apartment_id for update
            # Motivation: need to identify which saved apartment is "Riverside Lofts" to update its price
            get_saved_details_event = (
                apartment_app.list_saved_apartments().oracle().depends_on(acceptance_event, delay_seconds=1)
            )

            # Oracle Event 6: Agent updates the apartment price to new rent
            # Motivation: email states new rent ($2,100); user accepted proposal to update price; need apartment_id from search
            # Note: The apartment_id will come from the saved list returned in get_saved_details_event
            # In the real execution, the agent will extract this from the results, but for the scenario definition,
            # we reference the ID seeded in Step 2. The validation should check that update_apartment was called.
            update_price_event = (
                apartment_app.update_apartment(
                    apartment_id=self.riverside_apt_id,
                    new_price=2100.0,
                )
                .oracle()
                .depends_on(get_saved_details_event, delay_seconds=1)
            )

            # Oracle Event 7: Agent creates reminder for 5 days before deadline (Feb 10, 2026)
            # Motivation: email deadline is Feb 15, 2026; user requested reminder "a few days before"
            reminder_event = (
                reminder_app.add_reminder(
                    title="Lease Renewal Decision - Riverside Lofts",
                    due_datetime="2026-02-10 09:00:00",
                    description="Respond to Metro Property Group by February 15, 2026 regarding lease renewal at $2,100/month. Current lease expires March 31, 2026.",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle Event 8: Agent replies to leasing office acknowledging receipt
            # Motivation: email requests reply confirmation; user accepted proposal to acknowledge receipt
            reply_email_event = (
                email_app.reply_to_email(
                    email_id="renewal_email_001",
                    folder_name="INBOX",
                    content="Thank you for the lease renewal notice. I have received the information and noted the February 15, 2026 deadline. I will review the terms and respond with my decision soon.",
                )
                .oracle()
                .depends_on([reminder_event, update_price_event], delay_seconds=3)
            )

        # Register ALL events
        self.events = [
            renewal_email_event,
            read_email_event,
            search_saved_event,
            proposal_event,
            acceptance_event,
            get_saved_details_event,
            update_price_event,
            reminder_event,
            reply_email_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()
            agent_entries = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent created a reminder with appropriate deadline awareness
            # Must create reminder with title mentioning Riverside Lofts and due date before Feb 15
            reminder_created = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulReminderApp"
                and e.action.function_name == "add_reminder"
                and e.action.args.get("due_datetime") is not None
                and "2026-02-10" in e.action.args.get("due_datetime", "")
                and "Riverside Lofts" in e.action.args.get("title", "")
                for e in agent_entries
            )

            # STRICT Check 2: Agent replied to the leasing office email acknowledging receipt
            # Must reply to the renewal email (not create new email)
            reply_sent = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "reply_to_email"
                and e.action.args.get("email_id") == "renewal_email_001"
                for e in agent_entries
            )

            # STRICT Check 3: Agent updated the saved apartment price to the new rent
            price_updated = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulApartmentApp"
                and e.action.function_name == "update_apartment"
                and e.action.args.get("apartment_id") == self.riverside_apt_id
                and e.action.args.get("new_price") == 2100
                for e in agent_entries
            )

            # All checks must pass for success
            success = reminder_created and reply_sent and price_updated

            # Build rationale if validation fails
            if not success:
                missing_checks = []
                if not reminder_created:
                    missing_checks.append("reminder creation for Riverside Lofts")
                if not reply_sent:
                    missing_checks.append("reply to leasing office email")
                if not price_updated:
                    missing_checks.append("update Riverside Lofts price to 2100")

                rationale = f"Missing required agent actions: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
