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


@register_scenario("volunteer_storm_equipment_relay")
class VolunteerStormEquipmentRelay(PASScenario):
    """The user coordinates a community garden volunteer group and receives an urgent email from the local parks department on Friday afternoon warning that a severe thunderstorm is forecast for Saturday morning with potential hail damage. The user's calendar shows they scheduled a major garden workday for Saturday 9 AM to 3 PM with eight volunteers signed up, and their contacts contain each volunteer's details including who owns pickup trucks, who has tarps and protective equipment stored in their garage, and the garden shed key holder. A messaging thread with the volunteer group from earlier in the week shows enthusiasm about planting new seedlings on Saturday, and one volunteer mentioned they're driving in from an hour away specifically for this event. Another email arrives from a greenhouse supplier confirming delivery of expensive plant shipments to the garden site Saturday at 8 AM, right before the storm hits.

    The proactive agent detects the storm warning and immediately correlates it with the calendar event, recognizing that the plant delivery will arrive just as dangerous weather approaches, putting both volunteers and valuable plants at risk. It identifies from messaging history that volunteers have invested planning effort and travel time into this event, so outright cancellation would waste social capital and momentum. By analyzing contacts, the agent discovers some volunteers possess the exact resources needed for storm protection: trucks to relocate delivered plants to shelter, tarps to cover garden beds, and access to the locked shed where emergency supplies are stored. The agent infers a time-critical coordination challenge where the workday must be shortened and restructured into a rapid storm-prep mission rather than the planned planting activity.

    The agent proactively offers to send a group message explaining the weather threat and proposing a revised 7:30 AM to 10 AM "storm protection blitz" before the weather arrives, individually message the volunteers with trucks asking them to arrive early to help move the plant delivery to the shed, contact the volunteer with tarps requesting they bring supplies for covering vulnerable garden areas, message the key holder to arrive first for shed access, draft an email to the greenhouse supplier requesting they expedite delivery to 7:30 AM if possible, and update the calendar event with the compressed timeline and revised "Storm Prep Day" title. The user accepts this emergency pivot coordination, recognizing the agent transformed a cancellation scenario into a productive protective mission by matching volunteer resources to weather threats, preserving group engagement while prioritizing safety, and coordinating multiple parties around a compressed timeline driven by external environmental factors beyond anyone's control..
    """

    start_time = datetime(2025, 11, 14, 14, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Draft
    is_benchmark_ready = False

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        # WARNING: this part is responsible to and can be modified only by Apps & Data Setup Agent
        """Initialize apps with baseline data for the volunteer storm coordination scenario."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize Contacts app with volunteer information
        self.contacts = StatefulContactsApp(name="Contacts")

        # Add user contact
        user_contact = Contact(
            first_name="Alex",
            last_name="Martinez",
            is_user=True,
            email="alex.martinez@email.com",
            phone="555-0100",
            description="Community garden coordinator",
        )
        self.contacts.add_contact(user_contact)

        # Add volunteers with resource information
        volunteers = [
            Contact(
                first_name="Jamie",
                last_name="Chen",
                email="jamie.chen@email.com",
                phone="555-0101",
                description="Has pickup truck, can transport plants",
            ),
            Contact(
                first_name="Marcus",
                last_name="Johnson",
                email="marcus.j@email.com",
                phone="555-0102",
                description="Has pickup truck and trailer",
            ),
            Contact(
                first_name="Sarah",
                last_name="Williams",
                email="sarah.w@email.com",
                phone="555-0103",
                description="Has tarps and protective equipment in garage",
            ),
            Contact(
                first_name="David",
                last_name="Lee",
                email="david.lee@email.com",
                phone="555-0104",
                description="Has garden shed key, arrives early",
            ),
            Contact(
                first_name="Emma",
                last_name="Rodriguez",
                email="emma.r@email.com",
                phone="555-0105",
                description="Driving from an hour away, very enthusiastic",
            ),
            Contact(
                first_name="Tom",
                last_name="Anderson",
                email="tom.anderson@email.com",
                phone="555-0106",
                description="Regular volunteer, available weekends",
            ),
            Contact(
                first_name="Lisa",
                last_name="Park",
                email="lisa.park@email.com",
                phone="555-0107",
                description="Regular volunteer, good with plants",
            ),
            Contact(
                first_name="Kevin",
                last_name="Brown",
                email="kevin.brown@email.com",
                phone="555-0108",
                description="Regular volunteer, experienced gardener",
            ),
        ]

        for volunteer in volunteers:
            self.contacts.add_contact(volunteer)

        # Initialize Calendar app with the scheduled garden workday
        self.calendar = StatefulCalendarApp(name="Calendar")

        garden_workday = CalendarEvent(
            title="Community Garden Workday - Planting Seedlings",
            start_datetime=datetime(2025, 11, 15, 9, 0, 0, tzinfo=UTC).timestamp(),
            end_datetime=datetime(2025, 11, 15, 15, 0, 0, tzinfo=UTC).timestamp(),
            location="Riverside Community Garden",
            description="Major planting day - new seedlings for winter crops. Eight volunteers signed up.",
            attendees=[
                "Alex Martinez",
                "Jamie Chen",
                "Marcus Johnson",
                "Sarah Williams",
                "David Lee",
                "Emma Rodriguez",
                "Tom Anderson",
                "Lisa Park",
                "Kevin Brown",
            ],
            tag="Volunteer",
        )
        self.calendar.set_calendar_event(garden_workday)

        # Initialize Email app with baseline state
        self.email = StatefulEmailApp(name="Emails")
        self.email.user_email = "alex.martinez@email.com"

        # Initialize Messaging app with volunteer group thread
        self.messaging = StatefulMessagingApp(name="Messages")
        self.messaging.current_user_id = "user_id"
        self.messaging.current_user_name = "Alex Martinez"

        # Register volunteer names and IDs
        volunteer_names = [
            "Jamie Chen",
            "Marcus Johnson",
            "Sarah Williams",
            "David Lee",
            "Emma Rodriguez",
            "Tom Anderson",
            "Lisa Park",
            "Kevin Brown",
        ]
        self.messaging.add_users(volunteer_names)

        # Create volunteer group conversation with planning messages
        group_participant_ids = [self.messaging.name_to_id[name] for name in volunteer_names]

        volunteer_group_conv = ConversationV2(
            participant_ids=group_participant_ids,
            title="Garden Volunteers",
            messages=[
                MessageV2(
                    sender_id=self.messaging.current_user_id,
                    content="Hi everyone! Just a reminder that our big planting day is Saturday 9 AM to 3 PM at Riverside Garden. We'll be putting in the winter seedlings!",
                    timestamp=datetime(2025, 11, 11, 10, 0, 0, tzinfo=UTC).timestamp(),
                ),
                MessageV2(
                    sender_id=self.messaging.name_to_id["Emma Rodriguez"],
                    content="So excited! I'm driving in from Oakdale (about an hour away) specifically for this. Can't wait to get those seedlings in the ground!",
                    timestamp=datetime(2025, 11, 11, 10, 15, 0, tzinfo=UTC).timestamp(),
                ),
                MessageV2(
                    sender_id=self.messaging.name_to_id["Sarah Williams"],
                    content="I'll bring some extra gloves and tools from my garage. Looking forward to it!",
                    timestamp=datetime(2025, 11, 11, 11, 30, 0, tzinfo=UTC).timestamp(),
                ),
                MessageV2(
                    sender_id=self.messaging.name_to_id["David Lee"],
                    content="I have the shed key so I can unlock everything when we arrive. See you all Saturday!",
                    timestamp=datetime(2025, 11, 11, 12, 0, 0, tzinfo=UTC).timestamp(),
                ),
            ],
        )
        self.messaging.add_conversation(volunteer_group_conv)

        # Register all apps
        self.apps = [
            self.agent_ui,
            self.system_app,
            self.contacts,
            self.calendar,
            self.email,
            self.messaging,
        ]

    def build_events_flow(self) -> None:
        # WARNING: this part is responsible to and can be modified only by events-flow agent
        """Build event flow - environment events with agent detection and agent actions."""
        # TODO: initialize all apps from self.apps like aui and system_app below
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        email_app = self.get_typed_app(StatefulEmailApp, "Emails")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        calendar_app = self.get_typed_app(StatefulCalendarApp, "Calendar")

        with EventRegisterer.capture_mode():
            # Environment event 1: Storm warning email from parks department (Friday 2 PM)
            storm_warning_email = email_app.send_email_to_user_with_id(
                email_id="storm_warning_001",
                sender="parks.dept@cityparks.gov",
                subject="URGENT: Severe Thunderstorm Warning - Saturday Morning",
                content="Dear Community Garden Coordinators,\n\nThe National Weather Service has issued a severe thunderstorm warning for Saturday, November 15th, 7:00 AM to 11:00 AM. Forecast includes:\n- Heavy rain and lightning\n- Hail up to 1 inch diameter\n- Wind gusts 40-50 mph\n\nPlease take precautions to secure any outdoor equipment and postpone outdoor activities during this window. The storm system is expected to move through quickly, with clearing by noon.\n\nStay safe,\nCity Parks Department",
            )

            # Environment event 2: Greenhouse delivery confirmation email (Friday 3 PM, 1 hour after storm warning)
            greenhouse_email = email_app.send_email_to_user_with_id(
                email_id="greenhouse_delivery_001",
                sender="orders@greenleafnursery.com",
                subject="Delivery Confirmation - Saturday Nov 15",
                content="Hello Alex,\n\nYour order of winter seedlings (tomatoes, peppers, kale - 120 plants, $450 value) is confirmed for delivery:\n\nDelivery Date: Saturday, November 15th\nTime Window: 8:00 AM - 8:30 AM\nLocation: Riverside Community Garden, main gate\n\nPlease ensure someone is present to receive the delivery. Plants are temperature-sensitive and should be sheltered promptly.\n\nThank you,\nGreenleaf Nursery",
            ).delayed(60 * 60)

            # Oracle event: Agent detects storm warning + delivery conflict and sends proposal
            agent_proposal = aui.send_message_to_user(
                content="I noticed the severe storm warning for Saturday 7-11 AM conflicts with your garden workday (9 AM-3 PM) and the $450 plant delivery arriving at 8 AM. The volunteers have invested significant planning (Emma is driving an hour), but the timing puts people and plants at risk.\n\nI can help reorganize this into a storm prep mission:\n- Contact the 2 volunteers with trucks (Jamie, Marcus) to arrive early and help move delivered plants to the shed\n- Message Sarah to bring her tarps for covering garden beds\n- Ask David (shed key holder) to arrive first at 7:30 AM\n- Draft email to nursery requesting 7:30 AM delivery if possible\n- Send group message explaining the weather pivot and new plan (7:30-10 AM storm prep instead of 9 AM-3 PM planting)\n- Update calendar event to reflect compressed timeline and new focus\n\nThis preserves the volunteer effort while prioritizing safety. Should I coordinate this emergency pivot?"
            ).delayed(5 * 60)

            # Oracle event: User accepts the proposal
            user_acceptance = aui.accept_proposal(
                content="Yes, please coordinate all of that. This makes much more sense than canceling - we can protect what we have and still engage the volunteers productively."
            ).delayed(2 * 60)

            # Oracle event: Agent sends group message to volunteer conversation
            # First, get the volunteer group conversation ID
            volunteer_conv_id = next(iter(messaging_app.conversations.keys()))

            agent_group_message = (
                messaging_app.create_and_add_message(
                    conversation_id=volunteer_conv_id,
                    sender_id=messaging_app.current_user_id,
                    content="IMPORTANT UPDATE: Severe storm warning for Saturday 7-11 AM with hail. Plant delivery still arriving at 8 AM. NEW PLAN: Storm Prep Mission, 7:30-10 AM. Focus shifts from planting to protecting the garden and securing the $450 delivery before weather hits. More details coming to those with specific roles. Thanks for your flexibility!",
                )
                .delayed(3 * 60)
                .depends_on(user_acceptance)
            )

            # Oracle event: Agent messages Jamie (truck owner #1) individually
            jamie_user_id = messaging_app.name_to_id["Jamie Chen"]
            agent_to_jamie = (
                messaging_app.send_message(
                    user_id=jamie_user_id,
                    content="Jamie - need your truck Saturday morning! Can you arrive at 7:45 AM to help move the plant delivery (120 seedlings) from the gate to the shed before the storm? Marcus will be there with his truck too. Should take 30 mins max.",
                )
                .delayed(1 * 60)
                .depends_on(agent_group_message)
            )

            # Oracle event: Agent messages Marcus (truck owner #2) individually
            marcus_user_id = messaging_app.name_to_id["Marcus Johnson"]
            agent_to_marcus = (
                messaging_app.send_message(
                    user_id=marcus_user_id,
                    content="Marcus - need your truck and trailer Saturday AM. Can you arrive at 7:45 AM to help Jamie move the nursery delivery to the shed before the storm hits? 120 plants to relocate quickly.",
                )
                .delayed(1 * 60)
                .depends_on(agent_group_message)
            )

            # Oracle event: Agent messages Sarah (tarps owner) individually
            sarah_user_id = messaging_app.name_to_id["Sarah Williams"]
            agent_to_sarah = (
                messaging_app.send_message(
                    user_id=sarah_user_id,
                    content="Sarah - can you bring your tarps Saturday at 8:30 AM? We need to cover the raised beds and any equipment before the storm. Your garage supplies will be perfect for this.",
                )
                .delayed(1 * 60)
                .depends_on(agent_group_message)
            )

            # Oracle event: Agent messages David (key holder) individually
            david_user_id = messaging_app.name_to_id["David Lee"]
            agent_to_david = (
                messaging_app.send_message(
                    user_id=david_user_id,
                    content="David - critical: can you arrive at 7:30 AM with the shed key? We need early access to store the plant delivery before the storm. You're the first person we need on site!",
                )
                .delayed(1 * 60)
                .depends_on(agent_group_message)
            )

            # Oracle event: Agent sends email to greenhouse requesting earlier delivery
            agent_email_to_nursery = (
                email_app.send_email(
                    recipients=["orders@greenleafnursery.com"],
                    subject="Re: Delivery Confirmation - Saturday Nov 15",
                    content="Hello,\n\nDue to severe weather forecast (thunderstorm 7-11 AM Saturday), could you expedite our delivery to 7:30 AM instead of 8:00 AM? We'll have crew ready to move plants to shelter immediately. The earlier timing would help us secure the seedlings before storm conditions intensify.\n\nIf 7:30 AM isn't possible, we'll make 8:00 AM work, but earlier would be greatly appreciated.\n\nThank you,\nAlex Martinez\nRiverside Community Garden",
                )
                .delayed(2 * 60)
                .depends_on(user_acceptance)
            )

            # Oracle event: Agent updates calendar event with new storm prep details
            garden_event_id = next(iter(calendar_app.events.keys()))
            agent_calendar_update = (
                calendar_app.edit_calendar_event(
                    event_id=garden_event_id,
                    title="Storm Prep Day - REVISED SCHEDULE",
                    start_datetime="2025-11-15 07:30:00",
                    end_datetime="2025-11-15 10:00:00",
                    description="WEATHER PIVOT: Severe storm 7-11 AM. Mission changed to storm preparation - secure plant delivery (arriving 7:30-8 AM), move to shed, cover beds with tarps, protect equipment. Original planting postponed. David opens shed 7:30 AM, Jamie/Marcus truck crew 7:45 AM for delivery, Sarah brings tarps 8:30 AM.",
                )
                .delayed(2 * 60)
                .depends_on(user_acceptance)
            )

            # Oracle event: Agent sends completion summary to user
            agent_completion_summary = (
                aui.send_message_to_user(
                    content="Storm prep coordination complete:\n✓ Group message sent explaining weather pivot\n✓ Jamie & Marcus (trucks) messaged for 7:45 AM plant relocation\n✓ Sarah (tarps) messaged for 8:30 AM bed covering\n✓ David (key) messaged for 7:30 AM shed access\n✓ Email sent to nursery requesting 7:30 AM delivery\n✓ Calendar updated to 7:30-10 AM 'Storm Prep Day'\n\nAll volunteers have specific roles matching their resources. The mission is now focused on protection rather than planting, keeping everyone engaged while prioritizing safety."
                )
                .delayed(3 * 60)
                .depends_on(agent_calendar_update)
            )

        # TODO: Register ALL events here in self.events
        self.events: list[Event] = [
            storm_warning_email,
            greenhouse_email,
            agent_proposal,
            user_acceptance,
            agent_group_message,
            agent_to_jamie,
            agent_to_marcus,
            agent_to_sarah,
            agent_to_david,
            agent_email_to_nursery,
            agent_calendar_update,
            agent_completion_summary,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:  # noqa: C901
        # WARNING: this part is responsible to and can be modified only by validation agent
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Check Step 1: Agent sent proposal to the user detecting storm conflict
            # Oracle events in capture_mode are tagged as EventType.ENV
            proposal_found = any(
                e.event_type == EventType.ENV
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "send_message_to_user"
                and any(
                    keyword in e.action.args.get("content", "").lower() for keyword in ["storm", "weather", "severe"]
                )
                and any(keyword in e.action.args.get("content", "").lower() for keyword in ["delivery", "plant"])
                and any(keyword in e.action.args.get("content", "").lower() for keyword in ["volunteer", "garden"])
                for e in log_entries
            )

            # Check Step 2: User accepted proposal (oracle event)
            user_acceptance_found = any(
                e.event_type == EventType.ENV
                and isinstance(e.action, Action)
                and e.action.class_name == "PASAgentUserInterface"
                and e.action.function_name == "accept_proposal"
                for e in log_entries
            )

            # Check Step 3a: Agent sent group message to volunteer conversation
            group_message_found = any(
                e.event_type == EventType.ENV
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "create_and_add_message"
                and any(keyword in e.action.args.get("content", "").lower() for keyword in ["storm", "weather"])
                for e in log_entries
            )

            # Check Step 3b: Agent messaged volunteers with trucks (Jamie and Marcus)
            truck_messages = [
                e
                for e in log_entries
                if e.event_type == EventType.ENV
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["truck", "plant", "delivery", "move"]
                )
            ]
            truck_messages_found = len(truck_messages) >= 2  # Should message at least 2 truck owners

            # Check Step 3c: Agent messaged volunteer about tarps (flexible on exact name)
            tarp_message_found = any(
                e.event_type == EventType.ENV
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and any(keyword in e.action.args.get("content", "").lower() for keyword in ["tarp", "cover"])
                for e in log_entries
            )

            # Check Step 3d: Agent messaged volunteer about shed key (flexible on exact name)
            key_message_found = any(
                e.event_type == EventType.ENV
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and any(keyword in e.action.args.get("content", "").lower() for keyword in ["key", "shed"])
                for e in log_entries
            )

            # Check Step 3e: Agent sent email to greenhouse/nursery requesting earlier delivery
            nursery_email_found = any(
                e.event_type == EventType.ENV
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulEmailApp"
                and e.action.function_name == "send_email"
                and "greenleafnursery.com" in str(e.action.args.get("recipients", []))
                and any(
                    keyword in e.action.args.get("content", "").lower()
                    for keyword in ["weather", "storm", "earlier", "expedite"]
                )
                for e in log_entries
            )

            # Check Step 3f: Agent updated calendar event with storm prep details
            calendar_update_found = any(
                e.event_type == EventType.ENV
                and isinstance(e.action, Action)
                and e.action.class_name == "StatefulCalendarApp"
                and e.action.function_name == "edit_calendar_event"
                and any(keyword in e.action.args.get("title", "").lower() for keyword in ["storm", "prep"])
                for e in log_entries
            )

            # Determine success: all critical checks must pass (completion summary is optional)
            success = (
                proposal_found
                and user_acceptance_found
                and group_message_found
                and truck_messages_found
                and tarp_message_found
                and key_message_found
                and nursery_email_found
                and calendar_update_found
            )

            if not success:
                rationale_parts = []
                if not proposal_found:
                    rationale_parts.append("no proposal about storm/weather conflict sent to user")
                if not user_acceptance_found:
                    rationale_parts.append("user acceptance not found")
                if not group_message_found:
                    rationale_parts.append("no group message sent to volunteers")
                if not truck_messages_found:
                    rationale_parts.append("insufficient truck owner messages (need 2)")
                if not tarp_message_found:
                    rationale_parts.append("no message about tarps sent")
                if not key_message_found:
                    rationale_parts.append("no message about shed key sent")
                if not nursery_email_found:
                    rationale_parts.append("no email to nursery requesting earlier delivery")
                if not calendar_update_found:
                    rationale_parts.append("calendar event not updated with storm prep details")

                rationale = "; ".join(rationale_parts)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)


"""end of the template to build scenario for Proactive Agent."""
