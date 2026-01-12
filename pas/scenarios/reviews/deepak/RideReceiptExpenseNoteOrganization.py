"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.contacts import Contact
from are.simulation.apps.email_client import Email, EmailFolderName
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulContactsApp,
    StatefulEmailApp,
)
from pas.apps.cab import StatefulCabApp
from pas.apps.note import StatefulNotesApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("ride_receipt_expense_note_organization")
class RideReceiptExpenseNoteOrganization(PASScenario):
    """Agent organizes ride receipts and expense documentation from multiple cab trips into a structured expense note with attachments.

    The user completes three business-related cab rides over two days (conference pickup, client site visit, airport return). After each ride ends, the cab app sends a ride completion notification with fare details and receipt information. Separately, the user receives an email from their finance department with the subject "Expense Report Due: Business Trip Reimbursement" requesting organized documentation of all transportation costs, including: itemized ride details (date, route, fare), receipt file paths for each trip, and total transportation expenses. The agent must: 1. Monitor ride completion events and extract fare, route, and timestamp details from each notification. 2. Search the user's existing notes to check if an expense documentation note already exists in the "Work" folder. 3. If no expense note exists, create a new note titled "Business Trip Transportation Expenses" with structured sections. 4. For each completed ride, append an entry to the note with ride details (pickup/dropoff, date/time, fare). 5. Attach receipt file paths provided in the ride notifications to the expense note using `add_attachment_to_note`. 6. Calculate and add the total transportation cost at the bottom of the note.

    This scenario exercises ride history retrieval and status monitoring (`get_ride_history`, `get_ride`, `get_current_ride_status`), note update operations (`update_note`) and attachment management (`add_attachment_to_note`, `list_attachments`), cross-app synthesis of ride data into financial documentation, and email coordination for expense reporting workflows..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize contacts app
        self.contacts = StatefulContactsApp(name="Contacts")

        # Initialize email app
        self.email = StatefulEmailApp(name="Emails", user_email="user@company.com")

        # Initialize cab app
        self.cab = StatefulCabApp(name="Cab")

        # Initialize notes app
        self.note = StatefulNotesApp(name="Notes")

        # Populate contacts: finance department contact
        finance_contact = Contact(
            first_name="Sarah",
            last_name="Chen",
            email="sarah.chen@company.com",
            phone="+1-555-0198",
            job="Finance Manager",
        )
        self.contacts.add_contact(finance_contact)

        # Populate email: old conference invitation (baseline context)
        conference_email = Email(
            sender="events@techconf2025.org",
            recipients=["user@company.com"],
            subject="Tech Conference 2025 - Registration Confirmed",
            content="Thank you for registering for Tech Conference 2025 on November 18-19. Your badge will be available at the main entrance. Event starts at 10:00 AM.",
            timestamp=datetime(2025, 11, 10, 14, 0, 0, tzinfo=UTC).timestamp(),
            is_read=True,
        )
        self.email.add_email(conference_email, EmailFolderName.INBOX)

        # Populate cab: prior ride history (completed before scenario start)
        self.cab.add_new_ride(
            service_type="Default",
            start_location="Home",
            end_location="Airport",
            price=45.50,
            duration=35.0 * 60,
            time_stamp=datetime(2025, 11, 15, 7, 30, 0, tzinfo=UTC).timestamp(),
            distance_km=22.5,
        )

        # Populate notes: existing work folder with unrelated note
        self.note.create_note_with_time(
            folder="Work",
            title="Q4 Project Milestones",
            content="Key deliverables: Design review (Nov 20), Implementation sprint (Dec 1-15), Final testing (Dec 16-20).",
            created_at="2025-11-12 10:00:00",
            updated_at="2025-11-12 10:00:00",
        )

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.email, self.cab, self.note]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")
        note_app = self.get_typed_app(StatefulNotesApp, "Notes")

        with EventRegisterer.capture_mode():
            # Environment Event 1: First ride completes (Conference venue)
            ride1_end = cab_app.end_ride().delayed(5)

            # Environment Event 2: Second ride completes (Client site visit)
            ride2_end = cab_app.end_ride().delayed(10)

            # Environment Event 3: Third ride completes (Return to airport)
            ride3_end = cab_app.end_ride().delayed(15)

            # Environment Event 4: Finance email requesting expense documentation
            # Trigger: Finance email explicitly requests "itemized ride details (date, route, fare), receipt file paths, and total transportation expenses"
            finance_email_event = email_app.send_email_to_user_with_id(
                email_id="finance-expense-request",
                sender="sarah.chen@company.com",
                subject="Expense Report Due: Business Trip Reimbursement",
                content=(
                    "Hi! Please submit your expense report for the Nov 18-19 business trip by end of week. "
                    "We need: itemized transportation details (date, pickup/dropoff locations, fare amount for each ride), "
                    "receipt file paths, and total transportation cost. "
                    "If possible, keep this expense documentation in a single note in your Work folder so it's easy to reference. "
                    "Let me know once it's ready. Thanks!"
                ),
            ).delayed(20)

            # Oracle Event 1: Agent retrieves ride history to get details of completed rides
            # Motivation: Finance email requests "itemized transportation details (date, pickup/dropoff locations, fare amount)" - need to retrieve ride records
            get_rides = (
                cab_app.get_ride_history(offset=0, limit=10).oracle().depends_on(finance_email_event, delay_seconds=2)
            )

            # Oracle Event 2: Agent searches existing notes in Work folder to check for expense note
            # Motivation: Finance email explicitly asks to keep documentation "in a single note in your Work folder",
            # so the agent searches the Work folder to see if an expense note already exists before creating a new one.
            search_expense_note = (
                note_app.search_notes_in_folder(query="expense", folder_name="Work")
                .oracle()
                .depends_on(get_rides, delay_seconds=1)
            )

            # Oracle Event 3: Agent retrieves details of first ride from history
            # Motivation: Need specific fare, route, and timestamp for first ride to populate note (finance email requires "date, pickup/dropoff, fare")
            get_ride1 = cab_app.get_ride(idx=1).oracle().depends_on(search_expense_note, delay_seconds=1)

            # Oracle Event 4: Agent retrieves details of second ride from history
            # Motivation: Need specific fare, route, and timestamp for second ride to populate note
            get_ride2 = cab_app.get_ride(idx=2).oracle().depends_on(get_ride1, delay_seconds=1)

            # Oracle Event 5: Agent retrieves details of third ride from history
            # Motivation: Need specific fare, route, and timestamp for third ride to populate note
            get_ride3 = cab_app.get_ride(idx=3).oracle().depends_on(get_ride2, delay_seconds=1)

            # Oracle Event 6: Agent sends proposal to user
            # Motivation: Finance email from sarah.chen@company.com requests "expense report for Nov 18-19 business trip" with "itemized transportation details and total cost"
            proposal = (
                aui.send_message_to_user(
                    content="I received an expense report request from Sarah Chen (Finance) for your Nov 18-19 business trip. I've retrieved your ride history showing 3 completed trips. Would you like me to create a structured expense note in your Work folder with itemized ride details (dates, routes, fares) and calculate the total transportation cost?"
                )
                .oracle()
                .depends_on(get_ride3, delay_seconds=2)
            )

            # Oracle Event 7: User accepts proposal
            acceptance = (
                aui.accept_proposal(content="Yes, please organize the ride expenses into a note.")
                .oracle()
                .depends_on(proposal, delay_seconds=2)
            )

            # Oracle Event 8: Agent creates new expense note in Work folder (user-gated write)
            # Motivation: User accepted proposal to create an expense note in Work; finance email requests itemized ride details and totals.
            create_note = (
                note_app.create_note(
                    folder="Work",
                    title="Business Trip Transportation Expenses",
                    content=(
                        "Transportation Expense Summary\n\n"
                        "Ride Details:\n"
                        "1. Date: Nov 18, 2025 | Route: Conference Venue to Hotel | Fare: $28.50\n"
                        "2. Date: Nov 19, 2025 | Route: Hotel to Client Office | Fare: $32.75\n"
                        "3. Date: Nov 19, 2025 | Route: Client Office to Airport | Fare: $41.25\n\n"
                        "Total Transportation Cost: $102.50"
                    ),
                )
                .oracle()
                .depends_on(acceptance, delay_seconds=1)
            )

            # Oracle Event 12: Agent replies to finance email confirming documentation is ready
            # Motivation: User accepted proposal to "reply to Sarah"; finance email requested notification "once documentation is ready"
            reply_to_finance = (
                email_app.reply_to_email(
                    email_id="finance-expense-request",
                    folder_name="INBOX",
                    content="Hi Sarah, I've completed the expense documentation for the Nov 18-19 business trip. All transportation details are organized in the 'Business Trip Transportation Expenses' note in my Work folder, including itemized ride information (dates, routes, fares) and the total cost of $102.50. Let me know if you need any additional details!",
                )
                .oracle()
                .depends_on(create_note, delay_seconds=2)
            )

        # TODO: Register ALL events here in self.events
        self.events = [
            ride1_end,
            ride2_end,
            ride3_end,
            finance_email_event,
            get_rides,
            search_expense_note,
            get_ride1,
            get_ride2,
            get_ride3,
            proposal,
            acceptance,
            create_note,
            reply_to_finance,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # STRICT Check 1: Agent sent proposal to user referencing the finance email and ride data
            # The proposal must reference Sarah Chen (Finance) and mention organizing ride/expense data
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "Sarah" in e.action.args.get("content", "")
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["expense", "ride", "trip", "transportation"]
                )
                for e in log_entries
            )

            # STRICT Check 2: Agent retrieved ride history to gather completed ride data
            # Equivalence: Either get_ride_history or individual get_ride calls are acceptable
            ride_history_retrieved = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name in ["get_ride_history", "get_ride"]
                for e in log_entries
            )

            # STRICT Check 3: Agent searched for existing expense notes in Work folder
            # Ensures agent checks for existing documentation before creating new
            search_performed = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "search_notes_in_folder"
                and e.action.args.get("folder_name") == "Work"
                for e in log_entries
            )

            # STRICT Check 4: Agent created a new note in Work folder for expense tracking
            # The note must be in Work folder and title should reference expenses/transportation
            note_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "create_note"
                and e.action.args.get("folder") == "Work"
                and any(
                    keyword in e.action.args.get("title", "").lower()
                    for keyword in ["expense", "transportation", "trip"]
                )
                for e in log_entries
            )

            # STRICT Check 5: Agent created an expense note whose content contains itemized ride details and a total
            # The scenario can implement this either as multiple update_note calls or a single create_note with full content.
            note_filled = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulNotesApp"
                and e.action.function_name == "create_note"
                and e.action.args.get("content") is not None
                for e in log_entries
            )

            # Overall success: All strict checks must pass
            success = proposal_found and ride_history_retrieved and search_performed and note_created and note_filled

            # Build rationale for failures
            if not success:
                failures = []
                if not proposal_found:
                    failures.append("no proposal to user referencing finance email and rides")
                if not ride_history_retrieved:
                    failures.append("no ride history retrieval")
                if not search_performed:
                    failures.append("no search for existing expense notes in Work folder")
                if not note_created:
                    failures.append("no expense note created in Work folder")
                if not note_filled:
                    failures.append("created note missing ride detail content")

                rationale = f"Validation failed: {'; '.join(failures)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
