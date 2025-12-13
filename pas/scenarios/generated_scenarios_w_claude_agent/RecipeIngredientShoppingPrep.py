"""start of the template to build scenario for Proactive Agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# TODO: import all Apps that will be used in this scenario
# WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
from are.simulation.apps.calendar import CalendarEvent
from are.simulation.apps.contacts import Contact
from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, Action, Event, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCalendarApp,
    StatefulContactsApp,
    StatefulEmailApp,
    StatefulMessagingApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("recipe_ingredient_shopping_prep")
class RecipeIngredientShoppingPrep(PASScenario):
    """The user receives a message from a friend confirming they're coming over for dinner on Saturday evening at 6 PM, expressing excitement about trying the user's homemade pasta dish. The user's calendar shows the Saturday dinner event already exists with the friend as an attendee, tagged as "Social." Several days before Saturday, the user receives an email newsletter from their favorite cooking blog featuring a new authentic carbonara recipe with a detailed ingredient list and preparation timeline. The user's contacts app contains details for their local Italian grocery store that closes at 5 PM on Saturdays, plus their regular supermarket's information.

    The proactive agent identifies the approaching dinner commitment in the calendar and correlates it with the cooking context established in the messaging thread. When the recipe email arrives mid-week, the agent reasons that the user will need to acquire specialty ingredients (guanciale, Pecorero Romano, fresh pasta) before Saturday. By checking the calendar, it recognizes that the Italian market's 5 PM Saturday closing time conflicts with the 6 PM dinner start, meaning grocery shopping must happen earlier in the week or Saturday morning. The agent notes the recipe's two-hour preparation timeline also requires the user to start cooking by 4 PM.

    The agent proactively offers to create a shopping checklist from the recipe email's ingredient list, suggest adding a Friday evening or Saturday morning shopping time block to the calendar with the Italian market's contact details attached, and calculate when to add a Saturday afternoon cooking reminder that accounts for the two-hour prep window before the friend's arrival. The user accepts, appreciating that the agent connected their social commitment, culinary interest, store hours, and realistic cooking timeline into a coordinated preparation plan..
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with baseline data for recipe shopping preparation scenario."""
        # Initialize all required apps
        self.messaging = StatefulMessagingApp(name="Messages")
        self.contacts = StatefulContactsApp(name="Contacts")
        self.calendar = StatefulCalendarApp(name="Calendar")
        self.email = StatefulEmailApp(name="Emails")
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Populate Contacts App
        # Add friend who's coming to dinner
        self.contacts.add_contact(
            Contact(
                first_name="Alex",
                last_name="Chen",
                contact_id="contact-alex-chen",
                email="alex.chen@email.com",
                phone="555-234-5678",
            )
        )

        # Add Italian grocery store contact with hours
        self.contacts.add_contact(
            Contact(
                first_name="Bella",
                last_name="Italia Market",
                contact_id="contact-bella-italia",
                email="orders@bellaitalia.com",
                phone="555-876-5432",
                address="456 Market Street",
                description="Italian specialty grocery store. Hours: Mon-Fri 8AM-8PM, Sat 9AM-5PM, Sun Closed",
            )
        )

        # Add regular supermarket contact
        self.contacts.add_contact(
            Contact(
                first_name="Fresh",
                last_name="Foods Market",
                contact_id="contact-fresh-foods",
                email="info@freshfoods.com",
                phone="555-111-2222",
                address="123 Main Street",
                description="Full-service supermarket. Hours: Mon-Sun 7AM-11PM",
            )
        )

        # Populate Calendar App
        # Saturday dinner event at 6 PM (November 23, 2025)
        saturday_dinner_timestamp = datetime(2025, 11, 23, 18, 0, 0, tzinfo=UTC).timestamp()
        saturday_dinner_end = datetime(2025, 11, 23, 21, 0, 0, tzinfo=UTC).timestamp()

        self.calendar.events["event-saturday-dinner"] = CalendarEvent(
            event_id="event-saturday-dinner",
            title="Dinner with Alex - Homemade Pasta Night",
            start_datetime=saturday_dinner_timestamp,
            end_datetime=saturday_dinner_end,
            tag="Social",
            description="Cooking homemade pasta for Alex",
            location="Home",
            attendees=["Alex Chen"],
        )

        # Populate Messaging App
        # Create conversation with Alex Chen about the dinner
        self.messaging.add_users(["Alex Chen"])
        alex_id = self.messaging.name_to_id["Alex Chen"]

        # Earlier conversation thread about dinner plans (from a few days ago)
        conversation_timestamp_1 = datetime(2025, 11, 15, 14, 30, 0, tzinfo=UTC).timestamp()
        conversation_timestamp_2 = datetime(2025, 11, 15, 14, 35, 0, tzinfo=UTC).timestamp()
        conversation_timestamp_3 = datetime(2025, 11, 15, 14, 40, 0, tzinfo=UTC).timestamp()

        conversation = ConversationV2(
            conversation_id="conv-alex-dinner",
            participant_ids=[alex_id],
            title="Alex Chen",
            messages=[
                MessageV2(
                    message_id="msg-1",
                    sender_id=alex_id,
                    content="Hey! Are we still on for dinner this Saturday?",
                    timestamp=conversation_timestamp_1,
                ),
                MessageV2(
                    message_id="msg-2",
                    sender_id="user",
                    content="Yes! I'm planning to make homemade pasta. Sound good?",
                    timestamp=conversation_timestamp_2,
                ),
                MessageV2(
                    message_id="msg-3",
                    sender_id=alex_id,
                    content="That sounds amazing! I can't wait to try your cooking. See you at 6 PM!",
                    timestamp=conversation_timestamp_3,
                ),
            ],
            last_updated=conversation_timestamp_3,
        )

        self.messaging.conversations["conv-alex-dinner"] = conversation

        # Email app starts empty (recipe newsletter arrives as event in build_events_flow)

        # Register all apps
        self.apps = [
            self.messaging,
            self.contacts,
            self.calendar,
            self.email,
            self.agent_ui,
            self.system_app,
        ]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # Initialize all apps
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")
        contacts_app = self.get_typed_app(StatefulContactsApp, "Contacts")

        with EventRegisterer.capture_mode():
            # Event 1: Recipe newsletter email arrives mid-week (environment event)
            recipe_email_event = email_app.send_email_to_user_with_id(
                email_id="email-recipe-newsletter",
                sender="newsletter@authenticitalian.com",
                subject="This Week's Recipe: Authentic Roman Carbonara",
                content="""Buongiorno food lovers!

This week we're featuring the classic Roman Carbonara - a deceptively simple dish that relies on perfect technique and quality ingredients.

**Ingredients (serves 2):**
- 200g guanciale (cured pork jowl), cut into small strips
- 300g fresh egg pasta (or dried spaghetti)
- 4 large egg yolks
- 100g Pecorino Romano, finely grated
- Freshly ground black pepper
- Salt for pasta water

**Preparation Timeline: 2 hours**
- 30 minutes: Prep ingredients (grate cheese, separate eggs, slice guanciale)
- 45 minutes: Render guanciale slowly at low heat to extract maximum flavor
- 30 minutes: Cook pasta, temper eggs with pasta water, combine everything
- 15 minutes: Rest and serve

**Chef's Notes:**
The key is finding authentic guanciale - regular bacon won't give you the same depth. Look for specialty Italian markets that import it directly from Rome. Pecorino Romano should be aged at least 8 months for proper sharpness.

The two-hour timeline accounts for the slow rendering of guanciale fat, which is what makes the sauce truly silky. Don't rush this step!

Buon appetito!
- Chef Marco, Authentic Italian Cooking""",
            ).delayed(5)

            # Event 2: Agent sends proposal after correlating recipe with dinner plans (oracle)
            proposal_event = (
                aui.send_message_to_user(
                    content="""I noticed you received a carbonara recipe email and you have dinner with Alex this Saturday at 6 PM. The recipe requires specialty ingredients like guanciale and Pecorino Romano, plus a 2-hour prep timeline.

I checked your contacts and found that Bella Italia Market (456 Market Street) carries authentic Italian ingredients, but they close at 5 PM on Saturday - which conflicts with your 6 PM dinner start.

Would you like me to:
1. Create a shopping list from the recipe ingredients
2. Add a Friday evening (5-7 PM) or Saturday morning (10 AM-12 PM) shopping reminder for Bella Italia Market
3. Add a Saturday afternoon cooking reminder at 4 PM (2 hours before dinner) with the prep timeline

This way you'll have time to shop before they close and start cooking with enough buffer before Alex arrives."""
                )
                .oracle()
                .depends_on(recipe_email_event, delay_seconds=3)
            )

            # Event 3: User accepts the proposal (oracle)
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, that sounds perfect! Friday evening shopping would work better for me. Please set everything up."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=2)
            )

            # Event 4: Agent checks calendar to verify Friday evening availability (oracle)
            calendar_check_event = (
                calendar_app.get_calendar_events_from_to(
                    start_datetime="2025-11-21 17:00:00",  # Friday 5 PM
                    end_datetime="2025-11-21 19:00:00",  # Friday 7 PM
                )
                .oracle()
                .depends_on(acceptance_event, delay_seconds=1)
            )

            # Event 5: Agent retrieves Bella Italia contact details for calendar event (oracle)
            contacts_check_event = (
                contacts_app.search_contacts(query="Bella Italia")
                .oracle()
                .depends_on(calendar_check_event, delay_seconds=1)
            )

            # Event 6: Agent creates Friday evening shopping reminder in calendar (oracle)
            shopping_reminder_event = (
                calendar_app.add_calendar_event(
                    title="Shopping at Bella Italia Market - Carbonara Ingredients",
                    start_datetime="2025-11-21 17:00:00",  # Friday 5 PM
                    end_datetime="2025-11-21 19:00:00",  # Friday 7 PM
                    location="Bella Italia Market - 456 Market Street",
                    description="""Shopping list for Authentic Roman Carbonara:
- 200g guanciale (cured pork jowl)
- 300g fresh egg pasta
- 4 large egg yolks (check freshness)
- 100g Pecorino Romano (aged 8+ months)
- Black pepper
- Salt

Store closes at 8 PM weekdays. Phone: 555-876-5432""",
                    tag="Personal",
                )
                .oracle()
                .depends_on(contacts_check_event, delay_seconds=1)
            )

            # Event 7: Agent creates Saturday cooking reminder in calendar (oracle)
            cooking_reminder_event = (
                calendar_app.add_calendar_event(
                    title="Start Cooking - Carbonara for Alex (2hr prep time)",
                    start_datetime="2025-11-23 16:00:00",  # Saturday 4 PM (2 hours before dinner)
                    end_datetime="2025-11-23 18:00:00",  # Saturday 6 PM (when dinner starts)
                    location="Home",
                    description="""Recipe prep timeline (2 hours total):
1. 4:00-4:30 PM: Prep ingredients (grate cheese, separate eggs, slice guanciale)
2. 4:30-5:15 PM: Render guanciale slowly at low heat
3. 5:15-5:45 PM: Cook pasta, temper eggs with pasta water, combine
4. 5:45-6:00 PM: Rest and plate
5. 6:00 PM: Alex arrives for dinner

Chef's tip: Don't rush the guanciale rendering - that's the secret to silky sauce!""",
                    tag="Personal",
                )
                .oracle()
                .depends_on(shopping_reminder_event, delay_seconds=1)
            )

            # Event 8: Agent confirms successful completion (oracle)
            confirmation_event = (
                aui.send_message_to_user(
                    content="""Perfect! I've set everything up for your Saturday dinner with Alex:

✓ **Friday 5-7 PM**: Shopping at Bella Italia Market (456 Market Street, closes at 8 PM)
  Shopping list includes: guanciale, fresh pasta, egg yolks, Pecorino Romano, pepper, salt

✓ **Saturday 4:00 PM**: Start cooking reminder with full 2-hour prep timeline
  You'll finish right when Alex arrives at 6 PM

Your Friday evening is free, so you'll have plenty of time to shop for the specialty ingredients before the weekend. The cooking reminder breaks down each prep step so you can follow Chef Marco's technique for that authentic silky carbonara sauce."""
                )
                .oracle()
                .depends_on(cooking_reminder_event, delay_seconds=2)
            )

        # Register ALL events
        self.events: list[Event] = [
            recipe_email_event,
            proposal_event,
            acceptance_event,
            calendar_check_event,
            contacts_check_event,
            shopping_reminder_event,
            cooking_reminder_event,
            confirmation_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1: Agent sent proposal correlating recipe with dinner plans
            proposal_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and "carbonara" in e.action.args.get("content", "").lower()
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["saturday", "alex", "dinner", "6 pm"]
                )
                and any(
                    store_keyword in e.action.args.get("content", "")
                    for store_keyword in ["Bella Italia", "bella italia"]
                )
                for e in log_entries
            )

            # Check Step 2a: Agent checked calendar availability for shopping window
            calendar_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "get_calendar_events_from_to"
                for e in log_entries
            )

            # Check Step 2b: Agent searched contacts for store information
            contacts_check_found = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulContactsApp"
                and e.action.function_name == "search_contacts"
                and "bella italia" in e.action.args.get("query", "").lower()
                for e in log_entries
            )

            # Check Step 3a: Agent created shopping reminder with ingredient list
            shopping_reminder_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "2025-11-21" in e.action.args.get("start_datetime", "")  # Friday
                and any(
                    ingredient in e.action.args.get("description", "").lower()
                    for ingredient in ["guanciale", "pecorino"]
                )
                and "Bella Italia" in e.action.args.get("location", "")
                for e in log_entries
            )

            # Check Step 3b: Agent created cooking reminder accounting for 2-hour prep
            cooking_reminder_created = any(
                e.event_type == EventType.AGENT
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "add_calendar_event"
                and "2025-11-23 16:00:00" in e.action.args.get("start_datetime", "")  # Saturday 4 PM
                and any(
                    keyword in e.action.args.get("description", "").lower()
                    for keyword in ["prep", "render", "guanciale"]
                )
                for e in log_entries
            )

            # Strict checks: proposal, both calendar events created
            success = proposal_found and shopping_reminder_created and cooking_reminder_created

            # Flexible checks: calendar/contacts detection (agent may use different strategies)
            # If agent succeeded without explicit checks, that's acceptable
            return ScenarioValidationResult(success=success)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
