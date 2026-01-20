from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.contacts import Contact
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
    StatefulContactsApp,
)
from pas.apps.shopping import StatefulShoppingApp
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("group_gift_contribution_coordination")
class GroupGiftContributionCoordination(PASScenario):
    """Agent coordinates a group gift purchase based on calendar event and incoming shopping cart share.

    The user has a calendar event "Team Retirement Party for Robert Lee" scheduled for Friday at 3:00 PM with multiple attendees (Sarah Park, James Liu, Maria Garcia). The user receives a shopping app notification that Sarah Park has shared a cart containing a "Professional Camera Kit" with a note "Let's chip in for Robert's retirement gift - $240 total, $60 each if 4 people contribute." The agent must:
    1. Detect the shared cart notification and examine the cart contents using `view_cart()` or `list_cart()`
    2. Search the calendar using `search_events()` to find Robert Lee's retirement party and retrieve attendee names via `list_attendees()`
    3. Cross-reference attendees from the calendar with contacts using `search_contacts()` to verify Sarah Park is an attendee
    4. Infer that this is a coordinated group gift purchase for the retirement party
    5. Propose joining the group gift by adding the camera kit to the user's cart with quantity 1 (representing the user's $60 contribution share)
    6. After user acceptance, complete checkout with any discount code mentioned in the shared cart notification

    This scenario exercises cross-app social coordination (shared shopping cart → calendar event → contact verification), multi-party event reasoning, proportional contribution inference, and collaborative purchase completion..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Contacts App
        self.contacts = StatefulContactsApp(name="Contacts")

        # Populate contacts with all attendees and Robert Lee
        sarah_park = Contact(first_name="Sarah", last_name="Park", email="sarah.park@company.com", phone="+1-555-0101")
        james_liu = Contact(first_name="James", last_name="Liu", email="james.liu@company.com", phone="+1-555-0102")
        maria_garcia = Contact(
            first_name="Maria", last_name="Garcia", email="maria.garcia@company.com", phone="+1-555-0103"
        )
        robert_lee = Contact(
            first_name="Robert",
            last_name="Lee",
            email="robert.lee@company.com",
            phone="+1-555-0104",
            status="Employed",
            job="Senior Engineer",
        )

        self.contacts.add_contact(sarah_park)
        self.contacts.add_contact(james_liu)
        self.contacts.add_contact(maria_garcia)
        self.contacts.add_contact(robert_lee)

        # Initialize Calendar App
        self.calendar = StatefulCalendarApp(name="Calendar")

        # Add the retirement party event scheduled for Friday Nov 22, 2025 at 3:00 PM (5 days after start_time)
        self.retirement_party_event_id = self.calendar.add_calendar_event(
            title="Team Retirement Party for Robert Lee",
            start_datetime="2025-11-21 15:00:00",
            end_datetime="2025-11-21 17:00:00",
            location="Conference Room B",
            description="Farewell celebration for Robert's retirement after 20 years of service",
            tag="Work",
            attendees=["Sarah Park", "James Liu", "Maria Garcia"],
        )

        # Initialize Shopping App
        self.shopping = StatefulShoppingApp(name="Shopping")

        # Add Professional Camera Kit product with discount code GROUPGIFT20
        self.camera_product_id = self.shopping.add_product("Professional Camera Kit")
        self.camera_item_id = self.shopping.add_item_to_product(
            product_id=self.camera_product_id,
            price=240.0,
            options={"brand": "Canon", "model": "EOS R6", "includes": "Body + 24-105mm lens"},
            available=True,
        )

        # Add discount code that will be mentioned in the shared cart notification
        self.shopping.add_discount_code(self.camera_item_id, {"GROUPGIFT20": 20.0})

        # Register all apps here in self.apps
        self.apps = [self.agent_ui, self.system_app, self.contacts, self.calendar, self.shopping]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")
        shopping_app = self.get_typed_app(StatefulShoppingApp, "Shopping")

        with EventRegisterer.capture_mode():
            # Environment event: Sarah Park adds a calendar reminder about the group gift contribution
            # This serves as the exogenous trigger that the agent can observe
            gift_reminder_event = calendar_app.add_calendar_event_by_attendee(
                who_add="Sarah Park",
                title="Group Gift Contribution Reminder - Robert's Retirement",
                start_datetime="2025-11-19 14:00:00",
                end_datetime="2025-11-19 14:30:00",
                description=(
                    "Reminder: Robert Lee retirement group gift.\n"
                    "Professional Camera Kit (Canon EOS R6) — $240 total, split 4 ways ($60 each).\n"
                    "Sarah Park: Can you handle checkout for the group? I'll collect reimbursements.\n"
                    "Use discount code GROUPGIFT20 at checkout."
                ),
                location="",
                tag="Personal",
                attendees=[],
            ).delayed(15)

            # Oracle: Agent searches calendar to find events related to Robert/retirement
            # Motivation: gift reminder event mentions "Robert's retirement", agent searches to understand context
            calendar_search_event = (
                calendar_app.search_events(query="Robert").oracle().depends_on(gift_reminder_event, delay_seconds=3)
            )

            # Oracle: Agent gets calendar events to find the retirement party and attendees
            # Motivation: after finding Robert-related events, agent needs to retrieve attendee list to understand group coordination
            get_events_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-21 00:00:00", end_datetime="2025-11-21 23:59:59"
                )
                .oracle()
                .depends_on(calendar_search_event, delay_seconds=2)
            )

            # Oracle: Agent searches contacts for Sarah Park to verify she's a legitimate attendee
            # Motivation: gift reminder was added by Sarah Park; agent verifies she's a known contact and retirement party attendee
            contact_search_event = (
                contacts_app.search_contacts(query="Sarah Park").oracle().depends_on(get_events_event, delay_seconds=2)
            )

            # Oracle: Agent searches shopping catalog for the Professional Camera Kit mentioned in the reminder
            # Motivation: gift reminder explicitly mentions "Professional Camera Kit", agent searches to find the product
            product_search_event = (
                shopping_app.search_product(product_name="Professional Camera Kit")
                .oracle()
                .depends_on(contact_search_event, delay_seconds=2)
            )

            # Oracle: Agent gets product details to verify item_id and price match the reminder
            # Motivation: search returned product(s), agent needs to get details to confirm the product and $240 price
            product_details_event = (
                shopping_app.get_product_details(product_id=self.camera_product_id)
                .oracle()
                .depends_on(product_search_event, delay_seconds=2)
            )

            # Oracle: Agent proposes to the user to join the group gift by adding the camera to cart and checking out
            # Motivation: agent has verified the gift context (retirement party, attendees, product, pricing, discount code)
            proposal_event = (
                aui.send_message_to_user(
                    content="I noticed a group gift reminder for Robert Lee's retirement party. The reminder says Sarah Park asked you to handle checkout for the group's Professional Camera Kit purchase ($240 total, $60 per person split 4 ways). The retirement party is on Nov 21 at 3:00 PM with Sarah, James, and Maria attending. Would you like me to add the camera kit to your cart and complete checkout using the GROUPGIFT20 discount code?"
                )
                .oracle()
                .depends_on(product_details_event, delay_seconds=3)
            )

            # Oracle: User accepts the proposal
            # Motivation: user agrees to participate in the group gift
            acceptance_event = (
                aui.accept_proposal(content="Yes, please go ahead and complete the purchase.")
                .oracle()
                .depends_on(proposal_event, delay_seconds=5)
            )

            # Oracle: Agent adds the camera kit item to the cart with quantity 1
            # Motivation: user accepted, agent adds the specific camera item identified earlier
            add_to_cart_event = (
                shopping_app.add_to_cart(item_id=self.camera_item_id, quantity=1)
                .oracle()
                .depends_on(acceptance_event, delay_seconds=2)
            )

            # Oracle: Agent completes checkout with the GROUPGIFT20 discount code
            # Motivation: user accepted and item is in cart, agent uses the discount code from the gift reminder
            checkout_event = (
                shopping_app.checkout(discount_code="GROUPGIFT20")
                .oracle()
                .depends_on(add_to_cart_event, delay_seconds=2)
            )

            # Oracle: Agent confirms completion to the user
            # Motivation: checkout completed successfully, agent provides confirmation with order details
            confirmation_event = (
                aui.send_message_to_user(
                    content="Done! I've completed the purchase for Robert's group gift. The Professional Camera Kit has been ordered with the group discount applied."
                )
                .oracle()
                .depends_on(checkout_event, delay_seconds=2)
            )

        # Register ALL events here in self.events
        self.events = [
            gift_reminder_event,
            calendar_search_event,
            get_events_event,
            contact_search_event,
            product_search_event,
            product_details_event,
            proposal_event,
            acceptance_event,
            add_to_cart_event,
            checkout_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent sent proposal to user about group gift
            # Must reference retirement party, Robert Lee, and group contribution
            proposal_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(
                    keyword in e.action.args.get("content", "").lower() for keyword in ["gift", "retirement", "robert"]
                )
                for e in agent_events
            )

            # STRICT Check 2: Agent searched calendar for Robert-related events
            # Accept either search_events or get_calendar_events_from_to
            calendar_search_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name in ["search_events", "get_calendar_events_from_to"]
                for e in agent_events
            )

            # STRICT Check 3: Agent searched contacts for Sarah Park
            contact_search_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "search_contacts"
                and "sarah" in e.action.args.get("query", "").lower()
                for e in agent_events
            )

            # STRICT Check 4: Agent searched shopping for camera product
            product_search_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name in ["search_product", "get_product_details"]
                for e in agent_events
            )

            # STRICT Check 5: Agent added correct item to cart
            add_to_cart_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "add_to_cart"
                and e.action.args.get("item_id") == self.camera_item_id
                and e.action.args.get("quantity") == 1
                for e in agent_events
            )

            # STRICT Check 6: Agent completed checkout with group discount code
            checkout_found = any(
                isinstance(e.action, Action)
                and e.action.class_name == "StatefulShoppingApp"
                and e.action.function_name == "checkout"
                and e.action.args.get("discount_code") == "GROUPGIFT20"
                for e in agent_events
            )

            # All STRICT checks must pass
            success = (
                proposal_found
                and calendar_search_found
                and contact_search_found
                and product_search_found
                and add_to_cart_found
                and checkout_found
            )

            if not success:
                missing_checks = []
                if not proposal_found:
                    missing_checks.append("agent proposal about group gift")
                if not calendar_search_found:
                    missing_checks.append("calendar search for Robert events")
                if not contact_search_found:
                    missing_checks.append("contact search for Sarah Park")
                if not product_search_found:
                    missing_checks.append("product search for camera")
                if not add_to_cart_found:
                    missing_checks.append("add camera item to cart")
                if not checkout_found:
                    missing_checks.append("checkout with GROUPGIFT20 discount")

                rationale = f"Missing required actions: {', '.join(missing_checks)}"
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
