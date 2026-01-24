from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.email_client import Email, EmailFolderName
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulEmailApp,
)
from pas.apps.cab import StatefulCabApp
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("order_failure_store_visit_suggestion")
class OrderFailureStoreVisitSuggestion(PASScenario):
    """Agent detects shopping order failure and proactively suggests a cab ride for urgent in-store pickup.

    The user has placed an online shopping order for in-store pickup or delivery. They receive a notification that the order has failed due to payment issues, item unavailability, or address problems. The agent must:
    1. Parse the order failure notification containing the order details and failure reason using view_order() or list_orders()
    2. Identify the merchant or store location associated with the failed order
    3. Recognize that the user may need to visit the store in person to resolve the issue or complete the purchase
    4. Propose booking a cab ride to the store location using get_quotation() for the user's current location to the store
    5. Execute order_ride() to book the ride upon user acceptance

    This scenario exercises failure recovery through cross-app coordination (shopping failure → mobility solution), proactive problem-solving that bridges digital and physical shopping channels, and service recovery assistance by facilitating in-person resolution when online processes fail..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")
        self.email = StatefulEmailApp(name="Email")

        # Initialize shopping app
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Add a product representing an electronics item at TechMart store
        product_id = self.shopping.add_product(name="Wireless Headphones")
        self.shopping.add_item_to_product(
            product_id=product_id,
            price=79.99,
            options={"color": "black", "brand": "AudioPro", "store": "TechMart Downtown"},
            available=True,
        )

        # Initialize cab app with store location for distance calculation
        self.cab = StatefulCabApp(name="Cab")

        # Seed a previous ride to TechMart so the distance is known
        self.cab.add_new_ride(
            service_type="Default",
            start_location="456 Oak Avenue",
            end_location="TechMart Downtown, 789 Main Street",
            price=12.50,
            duration=15.0,
            time_stamp=self.start_time - 86400,  # 1 day ago
            distance_km=8.5,
        )

        # Seed a prior email thread that creates urgency: user needs wireless headphones TODAY for an afternoon test.
        # This grounds why booking a cab for quick in-store pickup makes sense.
        teacher_email = Email(
            email_id="email-teacher-headphones-required",
            sender="prof.lee@university.edu",
            recipients=[self.email.user_email],
            subject="Reminder: Listening section requires headphones (today)",
            content=(
                "Hi,\n\n"
                "Reminder: today's assessment has a listening section. Please bring wired/wireless headphones.\n"
                "If you don't have a working pair, please get one before the test this afternoon.\n\n"
                "Best,\n"
                "Prof. Lee"
            ),
            timestamp=self.start_time - 3600,  # 1 hour before scenario start
            is_read=True,
        )
        user_reply = Email(
            email_id="sent-teacher-headphones-ack",
            sender=self.email.user_email,
            recipients=["prof.lee@university.edu"],
            subject="Re: Reminder: Listening section requires headphones (today)",
            content="Thanks — I'll pick up wireless headphones today so I'm ready for the test this afternoon.\n\n— John",
            timestamp=self.start_time - 3300,
            is_read=True,
            parent_id=teacher_email.email_id,
        )
        self.email.folders[EmailFolderName.INBOX].add_email(teacher_email)
        self.email.folders[EmailFolderName.SENT].add_email(user_reply)

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.email, self.shopping, self.cab]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps from self.apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Email")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        with EventRegisterer.capture_mode():
            # Environment Event 1: Order failure notification
            # User receives notification that their shopping order has been cancelled
            order_failure_event = shopping_app.update_order_status(
                order_id="test-order-001", status="cancelled"
            ).delayed(5)

            # Environment Event 1.5: Teacher replies to the user's email, reinforcing the urgency (time-driven trigger).
            # We use send_email_to_user_with_id so it shows up as an incoming email event in the log/notifications.
            teacher_reply_event = email_app.send_email_to_user_with_id(
                sender="prof.lee@university.edu",
                email_id="sent-teacher-headphones-ack",
                content="Thanks for confirming. See you this afternoon — please bring headphones for the listening section.",
            ).delayed(3)

            # Environment Event 2: Retailer follow-up recommends an in-person store visit (grounds the cab idea + store address)
            techmart_followup_email_event = email_app.send_email_to_user_with_id(
                email_id="email-techmart-cancelled-001",
                sender="support@techmart.example",
                subject="Your TechMart order was cancelled — in-store pickup available today",
                content=(
                    "Hi,\n\n"
                    "We weren't able to ship your order (ID: test-order-001), so it was cancelled.\n\n"
                    "If you still want the item today, you can purchase it in person or set up in-store pickup at:\n"
                    "TechMart Downtown, 789 Main Street\n\n"
                    "If you need it urgently, visiting the store is the fastest option.\n\n"
                    "Best,\n"
                    "TechMart Support"
                ),
            ).delayed(70)

            # Oracle Event 0: Agent notices the new teacher reply in INBOX (strong trigger).
            list_inbox_after_teacher_reply_event = (
                email_app.list_emails(folder_name="INBOX", offset=0, limit=5)
                .oracle()
                .depends_on(teacher_reply_event, delay_seconds=1)
            )
            read_teacher_reply_event = (
                email_app.get_email_by_index(idx=0, folder_name="INBOX")
                .oracle()
                .depends_on(list_inbox_after_teacher_reply_event, delay_seconds=1)
            )

            # Oracle Event 0.5: Agent also reads the original teacher reminder email for full details.
            read_teacher_email_event = (
                email_app.get_email_by_id(email_id="email-teacher-headphones-required", folder_name="INBOX")
                .oracle()
                .depends_on(read_teacher_reply_event, delay_seconds=1)
            )

            # Oracle Event 1: Agent lists orders to understand the failure details
            # Motivated by: order failure notification from environment event
            list_orders_event = (
                shopping_app.list_orders()
                .oracle()
                .depends_on([order_failure_event, read_teacher_email_event], delay_seconds=1)
            )

            # Oracle Event 2: Agent gets order details to extract store location
            # Motivated by: need to understand which store/merchant the failed order is associated with
            get_order_event = (
                shopping_app.get_order_details(order_id="test-order-001")
                .oracle()
                .depends_on(list_orders_event, delay_seconds=1)
            )

            # Oracle Event 3: Agent gets cab quotation to the store location
            # Motivated by: TechMart support email explicitly recommends visiting "TechMart Downtown, 789 Main Street"
            # and states the user's address on file is "456 Oak Avenue", so agent checks ride feasibility.
            get_quotation_event = (
                cab_app.get_quotation(
                    start_location="456 Oak Avenue",
                    end_location="TechMart Downtown, 789 Main Street",
                    service_type="Default",
                )
                .oracle()
                .depends_on([get_order_event, techmart_followup_email_event], delay_seconds=2)
            )

            # Oracle Event 4: Agent proposes ride booking to resolve order issue
            # Motivated by: detected order failure + confirmed ride availability from quotation
            proposal_event = (
                aui.send_message_to_user(
                    content=(
                        "I noticed your order (test-order-001) was cancelled. TechMart support emailed that the fastest "
                        "way to get the item today is an in-person visit to TechMart Downtown (789 Main Street). "
                        "I also saw your email about needing headphones for the test this afternoon, so time is tight. "
                        "Would you like me to book a cab from 456 Oak Avenue to the store for a quick pickup?"
                    )
                )
                .oracle()
                .depends_on(get_quotation_event, delay_seconds=2)
            )

            # Oracle Event 5: User accepts the proposal
            # Motivated by: user responds affirmatively to agent's ride booking proposal
            acceptance_event = (
                aui.accept_proposal(content="Yes, please proceed.").oracle().depends_on(proposal_event, delay_seconds=2)
            )

            # Oracle Event 6: Agent books the cab ride to the store
            # Motivated by: user acceptance from previous event
            book_ride_event = (
                cab_app.order_ride(
                    start_location="456 Oak Avenue",
                    end_location="TechMart Downtown, 789 Main Street",
                    service_type="Default",
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

        # Register ALL events
        self.events = [
            order_failure_event,
            teacher_reply_event,
            techmart_followup_email_event,
            list_inbox_after_teacher_reply_event,
            read_teacher_reply_event,
            read_teacher_email_event,
            list_orders_event,
            get_order_event,
            get_quotation_event,
            proposal_event,
            acceptance_event,
            book_ride_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check 1 (STRICT): Agent sent proposal to the user suggesting a cab ride to the store
            # The agent must propose a ride to TechMart after detecting the order failure
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 2 (STRICT): Agent got cab quotation to the store location
            # The agent must check ride availability using get_quotation with correct endpoints
            quotation_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "get_quotation"
                for e in log_entries
            )

            # Check 3 (STRICT): Agent booked the cab ride after user acceptance
            # The agent must complete the ride booking using order_ride
            ride_booked = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "order_ride"
                for e in log_entries
            )

            # Build success result and rationale
            missing_checks = []
            if not proposal_found:
                missing_checks.append("agent proposal message to user not found")
            if not quotation_found:
                missing_checks.append("cab quotation to TechMart not found")
            if not ride_booked:
                missing_checks.append("cab ride booking to TechMart not found")

            success = proposal_found and quotation_found and ride_booked

            if not success:
                rationale = "; ".join(missing_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
