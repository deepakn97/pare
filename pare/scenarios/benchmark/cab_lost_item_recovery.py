"""Scenario for lost item recovery after cab ride."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pare.apps import (
    HomeScreenSystemApp,
    PAREAgentUserInterface,
    StatefulCabApp,
    StatefulContactsApp,
    StatefulEmailApp,
    StatefulMessagingApp,
    StatefulShoppingApp,
)
from pare.scenarios import PAREScenario
from pare.scenarios.utils.registry import register_scenario


@register_scenario("cab_lost_item_recovery")
class CabLostItemRecovery(PAREScenario):
    """Agent helps recover lost item after friend suggests checking the cab.

    Story:
    1. User ordered Wireless Noise Cancelling Headphones online
    2. User received email that order is ready for pickup at "123 Tech Plaza" on Nov 17
    3. On Nov 17, user took cab from home to pickup location, picked up headphones
    4. User then took cab to friend Sarah's house to show off the new headphones
    5. User took cab from Sarah's house back home in the evening
    6. On Nov 18 morning, user realizes headphones are missing and messages Sarah
    7. Sarah replies that user had the headphones when leaving, suggests checking the cab

    Agent detects Sarah's suggestion, correlates with cab ride history and shopping order,
    and proposes to contact the cab company's lost and found service.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with data for cab lost item recovery scenario."""
        # Required infrastructure apps
        self.agent_ui = PAREAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize apps
        self.cab = StatefulCabApp(name="Cab")
        self.shopping = StatefulShoppingApp(name="Shopping")
        self.email = StatefulEmailApp(name="Emails")
        self.contacts = StatefulContactsApp(name="Contacts")
        self.messaging = StatefulMessagingApp(name="Messages")

        # Add contacts
        self.contacts.add_new_contact(
            first_name="Sarah",
            last_name="Chen",
            phone="555-234-5678",
            email="sarah.chen@email.com",
            address="789 Oak Street",
        )
        self.contacts.add_new_contact(
            first_name="Lost and Found",
            last_name="Support",
            phone="555-CAB-LOST",
            email="lostandfound@cabservice.com",
        )

        # Set up shopping: product and completed order
        product_id = self.shopping.add_product(name="Wireless Noise Cancelling Headphones")
        item_id = self.shopping.add_item_to_product(
            product_id=product_id,
            price=299.99,
            options={"color": "Black", "size": "One Size"},
            available=True,
        )
        # Order placed Nov 15, picked up Nov 17
        order_date = datetime(2025, 11, 15, 10, 0, 0, tzinfo=UTC).timestamp()
        self.shopping.add_order(
            order_id="order-headphones-001",
            order_status="completed",
            order_date=order_date,
            order_total=299.99,
            item_id=item_id,
            quantity=1,
        )

        # Email from shopping app about pickup ready (received Nov 16)
        self.email.create_and_add_email_with_time(
            sender="orders@techstore.com",
            recipients=None,  # to user
            subject="Your Order is Ready for Pickup",
            content=(
                "Great news! Your order for Wireless Noise Cancelling Headphones is ready for pickup.\n\n"
                "Order Details:\n"
                "- Item: Wireless Noise Cancelling Headphones (Black)\n"
                "- Price: $299.99\n"
                "- Order ID: order-headphones-001\n\n"
                "Pickup Location: 123 Tech Plaza\n"
                "Pickup Date: November 17, 2025\n"
                "Store Hours: 9:00 AM - 9:00 PM\n\n"
                "Please bring a valid ID and this email confirmation.\n\n"
                "Thank you for shopping with us!\n"
                "Tech Store Team"
            ),
            email_time="2025-11-16 14:00:00",
            folder_name="INBOX",
        )

        # Cab rides on Nov 17
        # Ride 1: Home to Pickup Location (2:00 PM)
        self.cab.add_new_ride(
            service_type="Default",
            start_location="456 Home Avenue",
            end_location="123 Tech Plaza",
            price=15.50,
            duration=720.0,  # 12 minutes
            time_stamp=datetime(2025, 11, 17, 14, 0, 0, tzinfo=UTC).timestamp(),
            distance_km=8.5,
        )

        # Ride 2: Pickup Location to Friend's House (2:30 PM)
        self.cab.add_new_ride(
            service_type="Default",
            start_location="123 Tech Plaza",
            end_location="789 Oak Street",
            price=12.00,
            duration=600.0,  # 10 minutes
            time_stamp=datetime(2025, 11, 17, 14, 30, 0, tzinfo=UTC).timestamp(),
            distance_km=6.0,
        )

        # Ride 3: Friend's House to Home (6:00 PM) - this is where item was left
        self.last_ride_id = self.cab.add_new_ride(
            service_type="Default",
            start_location="789 Oak Street",
            end_location="456 Home Avenue",
            price=18.50,
            duration=900.0,  # 15 minutes
            time_stamp=datetime(2025, 11, 17, 18, 0, 0, tzinfo=UTC).timestamp(),
            distance_km=12.5,
        )

        # Set up messaging: add Sarah as a user and create conversation with user's message
        self.messaging.add_users(["Sarah Chen"])
        sarah_id = self.messaging.name_to_id["Sarah Chen"]
        current_user_id = self.messaging.current_user_id

        # Get or create conversation between user and Sarah
        conv_ids = self.messaging.get_existing_conversation_ids([current_user_id, sarah_id])
        if conv_ids:
            self.sarah_conv_id = conv_ids[0]
        else:
            # Create conversation by sending initial message
            self.sarah_conv_id = self.messaging.send_message(
                user_id=sarah_id,
                content="Hey Sarah, did I leave my new headphones at your place? Can't find them anywhere!",
            )

        # Store Sarah's ID for the trigger event
        self.sarah_id = sarah_id

        # Register all apps
        self.apps = [
            self.agent_ui,
            self.system_app,
            self.cab,
            self.shopping,
            self.email,
            self.contacts,
            self.messaging,
        ]

    def build_events_flow(self) -> None:
        """Build event flow - friend's reply triggers agent to help with lost item recovery."""
        aui = self.get_typed_app(PAREAgentUserInterface)
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")

        with EventRegisterer.capture_mode():
            # ENV Event: Sarah replies suggesting the user check the cab
            # This is the trigger - Sarah confirms user had headphones when leaving her place
            sarah_reply = messaging_app.send_message(
                user_id=self.sarah_id,
                content=(
                    "No, you definitely had them when you left! You were showing them to me "
                    "right before you got in the cab. Maybe you left them in the cab? "
                ),
            ).delayed(30)

            # Oracle: Agent checks cab ride history to find relevant rides
            get_ride_history = (
                cab_app.get_ride_history(offset=0, limit=10).oracle().depends_on(sarah_reply, delay_seconds=2)
            )

            # Oracle: Agent checks shopping orders to identify the item
            list_orders = shopping_app.list_orders().oracle().depends_on(get_ride_history, delay_seconds=1)

            # Oracle: Agent proposes to contact cab company's lost and found
            proposal = (
                aui.send_message_to_user(
                    content=(
                        "I see Sarah mentioned you had your headphones when you left her place "
                        "and took a cab home. Based on your ride history, you took a cab from "
                        "789 Oak Street to 456 Home Avenue yesterday evening. Your shopping order "
                        "shows you recently purchased Wireless Noise Cancelling Headphones. "
                        "Would you like me to contact the cab company's lost and found service "
                        "to report the missing headphones?"
                    )
                )
                .oracle()
                .depends_on(list_orders, delay_seconds=2)
            )

            # Oracle: User accepts the proposal
            acceptance = (
                aui.accept_proposal(content="Yes, please contact them with all the details.")
                .oracle()
                .depends_on(proposal, delay_seconds=2)
            )

            # Oracle: Agent sends email to cab company lost and found
            send_email = (
                email_app.send_email(
                    recipients=["lostandfound@cabservice.com"],
                    subject="Lost Item Report - Ride from 789 Oak Street to 456 Home Avenue",
                    content=(
                        "Hello,\n\n"
                        "I am writing to report a lost item from a recent ride.\n\n"
                        "Ride Details:\n"
                        f"- Ride ID: {self.last_ride_id}\n"
                        "- Date: November 17, 2025, approximately 6:00 PM\n"
                        "- Route: 789 Oak Street to 456 Home Avenue\n"
                        "- Service Type: Default\n\n"
                        "Lost Item:\n"
                        "- Item: Wireless Noise Cancelling Headphones\n"
                        "- Color: Black\n"
                        "- Value: $299.99\n"
                        "- Description: Recently purchased, in original packaging\n\n"
                        "Please contact me if the item is found.\n\n"
                        "Thank you for your assistance."
                    ),
                )
                .oracle()
                .depends_on(acceptance, delay_seconds=2)
            )

            # Oracle: Agent confirms to user that recovery request has been submitted
            confirmation = (
                aui.send_message_to_user(
                    content=(
                        "I've submitted a lost item report to the cab company's lost and found service. "
                        "I included your ride details from yesterday evening and the description of your "
                        "Wireless Noise Cancelling Headphones. They should contact you if the item is found."
                    )
                )
                .oracle()
                .depends_on(send_email, delay_seconds=1)
            )

        self.events = [
            sarah_reply,
            get_ride_history,
            list_orders,
            proposal,
            acceptance,
            send_email,
            confirmation,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent helped with lost item recovery.

        Essential outcomes checked:
        1. Agent sent proposal to user before taking action
        2. Agent sent email to cab company's lost and found with correct ride ID
        """
        try:
            log_entries = env.event_log.list_view()

            # Check 1: Agent sent proposal to user about lost item recovery
            proposal_sent = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PAREAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                for e in log_entries
            )

            # Check 2: Agent sent email to cab company's lost and found with correct ride ID
            # The email must be to lostandfound@cabservice.com and contain the correct ride ID
            email_sent_with_correct_ride = False
            for e in log_entries:
                if (
                    e.event_type == EventType.AGENT
                    and isinstance(e.action, Action)
                    and e.action.class_name == "StatefulEmailApp"
                    and e.action.function_name == "send_email"
                    and "lostandfound@cabservice.com" in e.action.args.get("recipients", [])
                ):
                    # Check if email content contains the correct ride ID
                    email_content = e.action.args.get("content", "")
                    email_subject = e.action.args.get("subject", "")
                    if self.last_ride_id in email_content or self.last_ride_id in email_subject:
                        email_sent_with_correct_ride = True
                        break

            success = proposal_sent and email_sent_with_correct_ride

            if not success:
                missing = []
                if not proposal_sent:
                    missing.append("proposal to user about lost item recovery")
                if not email_sent_with_correct_ride:
                    missing.append(f"email to cab company lost and found with ride ID {self.last_ride_id}")
                return ScenarioValidationResult(
                    success=False,
                    rationale=f"Missing required actions: {', '.join(missing)}",
                )

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
