from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from are.simulation.apps.messaging_v2 import ConversationV2, MessageV2
from are.simulation.scenarios.scenario import ScenarioStatus, ScenarioValidationResult
from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType

from pas.apps import (
    HomeScreenSystemApp,
    PASAgentUserInterface,
    StatefulCabApp,
    StatefulMessagingApp,
)
from pas.scenarios import PASScenario
from pas.scenarios.utils.registry import register_scenario


@register_scenario("mid_ride_urgent_diversion")
class MidRideUrgentDiversion(PASScenario):
    """Agent handles urgent mid-ride route change when user discovers forgotten essential item. The user has an active cab ride to the airport departing in 90 minutes. Mid-journey, the user receives a message from their roommate Sam: "Hey! I accidentally grabbed your laptop charger this morning and I'm at work until 8 PM. Just realized when I opened my bag. So sorry!" The user realizes they need the charger for a multi-day trip. The agent must: 1. Use get_current_ride_status to check the active ride's progress and current location. 2. Identify that the charger is at Sam's workplace and retrieve Sam's work address from prior message context. 3. Use get_quotation to calculate cost and time for a modified route: current location → Sam's workplace → airport. 4. Determine if the diversion still allows the user to reach the airport on time for their flight. 5. Propose canceling the current ride and booking a new ride with the workplace diversion (first leg: home → Sam's workplace). 6. After user acceptance, execute user_cancel_ride and order_ride for the first leg to Sam's workplace. 7. Send a message to Sam with the estimated pickup time at their workplace.

    This scenario exercises mid-ride monitoring and status tracking, reactive problem-solving when messaging reveals a new constraint, comparative feasibility analysis (original vs diverted route timing), ride cancellation and re-booking workflows, and cross-app coordination where messaging context drives ride modification rather than initial booking decisions.
    """

    start_time = datetime(2025, 11, 18, 9, 0, 0, tzinfo=UTC).timestamp()
    status = ScenarioStatus.Valid
    is_benchmark_ready = True

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize apps with test data."""
        self.agent_ui = PASAgentUserInterface()
        self.system_app = HomeScreenSystemApp(name="System")

        # Initialize messaging app
        self.messaging = StatefulMessagingApp(name="Messages")

        # Add contact: Sam (roommate) - this will automatically set up id_to_name and name_to_id
        self.messaging.add_users(["Sam"])
        self.sam_contact_id = self.messaging.name_to_id["Sam"]

        # Create a conversation with Sam that contains prior context about work address
        sam_conversation = ConversationV2(
            participant_ids=[self.messaging.current_user_id, self.sam_contact_id], title="Sam"
        )

        # Add older message context mentioning Sam's workplace
        prior_message_timestamp = self.start_time - 86400  # 1 day ago
        sam_conversation.messages.append(
            MessageV2(
                sender_id=self.sam_contact_id,
                content="Just started my new job at TechCorp! The office is at 456 Innovation Drive.",
                timestamp=prior_message_timestamp,
            )
        )
        sam_conversation.messages.append(
            MessageV2(
                sender_id=self.messaging.current_user_id,
                content="That's great! Congrats on the new role!",
                timestamp=prior_message_timestamp + 300,
            )
        )
        sam_conversation.last_updated = prior_message_timestamp + 300

        self.messaging.add_conversation(sam_conversation)
        # Store conversation_id for use in build_events_flow
        self.sam_conversation_id = sam_conversation.conversation_id

        # Initialize cab app
        self.cab = StatefulCabApp(name="Cab")

        # Add an ongoing ride to the airport (booked and in progress)
        # Flight is at 11:30 AM (start_time is 9:00 AM, so 2.5 hours window)
        # The ride was ordered to depart from home at 9:00 AM
        self.cab.add_new_ride(
            service_type="Default",
            start_location="123 Home Street",
            end_location="San Francisco International Airport",
            price=45.0,
            duration=60.0,  # 60 minutes
            time_stamp=self.start_time,
            distance_km=30.0,
        )
        # Get the ride that was just added and modify it to be in progress
        ongoing_ride = self.cab.ride_history[-1]
        ongoing_ride.status = "IN_PROGRESS"
        ongoing_ride.delay = 0.0
        # Note: Setting on_going_ride is required for scenario setup to simulate an ongoing ride
        self.cab.on_going_ride = ongoing_ride

        # Register all apps
        self.apps = [self.agent_ui, self.system_app, self.messaging, self.cab]

    def build_events_flow(self) -> None:
        """Build event flow - environment events with agent detection and agent actions."""
        aui = self.get_typed_app(PASAgentUserInterface)
        system_app = self.get_typed_app(HomeScreenSystemApp, "System")
        messaging_app = self.get_typed_app(StatefulMessagingApp, "Messages")
        cab_app = self.get_typed_app(StatefulCabApp, "Cab")

        with EventRegisterer.capture_mode():
            # Event 1: Sam sends urgent message about accidentally taking the laptop charger (environment event)
            # This is the initial trigger that creates the problem
            sam_message_event = messaging_app.create_and_add_message(
                conversation_id=self.sam_conversation_id,
                sender_id=self.sam_contact_id,
                content="Hey! I accidentally grabbed your laptop charger this morning and I'm at work until 8 PM. Just realized when I opened my bag. So sorry! Not sure if you are already on your ride to the airport.",
            ).delayed(10)

            # Agent observes the problem notification and needs to check current ride status to assess feasibility
            # Motivated by: Sam's message reveals a forgotten essential item, agent needs current location to plan diversion
            check_ride_status_event = (
                cab_app.get_current_ride_status().oracle().depends_on(sam_message_event, delay_seconds=3)
            )

            # Agent needs to read the conversation history to find Sam's workplace address mentioned in prior messages
            # Motivated by: To plan the diversion route, agent must know where Sam's workplace is located
            read_conversation_event = (
                messaging_app.read_conversation(conversation_id=self.sam_conversation_id, offset=0, limit=10)
                .oracle()
                .depends_on(check_ride_status_event, delay_seconds=2)
            )

            # Agent gets a quotation for the first leg of diverted route: home → Sam's workplace
            # Note: Using "123 Home Street" as the start location since the user's ride originated from home
            # and the diversion plan is to cancel the current ride and book a new one from home to Sam's workplace
            # Motivated by: Need to calculate if the diversion is feasible (cost + timing) before proposing to user
            get_diversion_quote_event = (
                cab_app.get_quotation(
                    start_location="123 Home Street", end_location="456 Innovation Drive", service_type="Default"
                )
                .oracle()
                .depends_on(read_conversation_event, delay_seconds=2)
            )

            # Get quotation for second leg: Sam's workplace → airport
            # Motivated by: Need complete route cost/time to assess feasibility and inform user
            get_second_leg_quote_event = (
                cab_app.get_quotation(
                    start_location="456 Innovation Drive",
                    end_location="San Francisco International Airport",
                    service_type="Default",
                )
                .oracle()
                .depends_on(get_diversion_quote_event, delay_seconds=2)
            )

            # Agent proposes the diversion plan to the user
            # Motivated by: Sam's message revealed forgotten charger, agent determined diversion is feasible based on quotations
            proposal_event = (
                aui.send_message_to_user(
                    content="I saw Sam's message about your laptop charger. I can cancel your current airport ride and book a new ride from home to Sam's workplace (456 Innovation Drive) so you can pick it up. After you get the charger, you can continue to the airport. This will require canceling the current ride and booking the first leg to Sam's workplace. The total journey will take longer but you'll still make your flight. Would you like me to proceed?"
                )
                .oracle()
                .depends_on(get_second_leg_quote_event, delay_seconds=3)
            )

            # User accepts the proposal
            # Motivated by: User needs the charger for their trip and accepts the feasible diversion plan
            acceptance_event = (
                aui.accept_proposal(
                    content="Yes, please do that and book the first leg to Sam's workplace, and inform Sam about it. I really need that charger."
                )
                .oracle()
                .depends_on(proposal_event, delay_seconds=5)
            )

            # Agent cancels the current ride
            # Motivated by: Must cancel current direct ride before booking new diverted route (first leg to Sam's workplace)
            cancel_event = cab_app.user_cancel_ride().oracle().depends_on(acceptance_event, delay_seconds=2)

            # Agent books new ride: home → Sam's workplace (first leg of the diverted route)
            # Note: The agent books a ride from home to Sam's workplace. After the user picks up the charger,
            # they will need to book a second ride from Sam's workplace to the airport, but that is outside
            # the scope of this scenario which focuses on the mid-ride diversion and first leg booking.
            # Motivated by: User accepted; executing the diversion by booking first leg to Sam's workplace
            book_first_leg_event = (
                cab_app.order_ride(
                    start_location="123 Home Street", end_location="456 Innovation Drive", service_type="Default"
                )
                .oracle()
                .depends_on(cancel_event, delay_seconds=2)
            )

            # Agent sends message to Sam with pickup ETA
            # Motivated by: Sam needs to know when to meet user at workplace entrance with the charger
            notify_sam_event = (
                messaging_app.send_message(
                    user_id=self.sam_contact_id,
                    content="No problem! I'm diverting my ride to pick up the charger from you. I'll be at your office (456 Innovation Drive) in about 15 minutes. Can you meet me outside with the charger?",
                )
                .oracle()
                .depends_on(book_first_leg_event, delay_seconds=2)
            )

        # Register ALL events here in self.events
        self.events = [
            sam_message_event,
            check_ride_status_event,
            read_conversation_event,
            get_diversion_quote_event,
            get_second_leg_quote_event,
            proposal_event,
            acceptance_event,
            cancel_event,
            book_first_leg_event,
            notify_sam_event,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Validate that agent detects the environment events and made actions accordingly."""
        try:
            log_entries = env.event_log.list_view()

            # Filter to only agent/oracle events (EventType.AGENT)
            agent_events = [e for e in log_entries if e.event_type == EventType.AGENT]

            # STRICT Check 1: Agent obtained quotation for first leg (home → Sam's workplace)
            # This is the critical quotation needed to book the diverted ride
            first_leg_quotation_obtained = any(
                e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "get_quotation"
                and e.action.args.get("start_location") is not None
                and e.action.args.get("end_location") is not None
                and "123 home street" in e.action.args.get("start_location", "").lower()
                and "456 innovation drive" in e.action.args.get("end_location", "").lower()
                for e in agent_events
            )

            # STRICT Check 2: Agent canceled the current ride
            # This is required before booking a new ride
            ride_canceled = any(
                e.action.class_name == "StatefulCabApp" and e.action.function_name == "user_cancel_ride"
                for e in agent_events
            )

            # STRICT Check 3: Agent booked new ride to Sam's workplace
            # The ride must be ordered from home to Sam's workplace to execute the diversion
            new_ride_booked = any(
                e.action.class_name == "StatefulCabApp"
                and e.action.function_name == "order_ride"
                and e.action.args.get("start_location") is not None
                and e.action.args.get("end_location") is not None
                and "123 home street" in e.action.args.get("start_location", "").lower()
                and "456 innovation drive" in e.action.args.get("end_location", "").lower()
                for e in agent_events
            )

            # STRICT Check 4: Agent notified Sam about the pickup
            # Sam must be informed so they can meet the user with the charger
            sam_notified = any(
                e.action.class_name == "StatefulMessagingApp"
                and e.action.function_name == "send_message"
                and e.action.args.get("user_id") == self.sam_contact_id
                for e in agent_events
            )

            # Combine all checks
            all_checks_passed = first_leg_quotation_obtained and ride_canceled and new_ride_booked and sam_notified

            # Build rationale for failures
            if not all_checks_passed:
                failed_checks = []
                if not first_leg_quotation_obtained:
                    failed_checks.append("agent did not obtain quotation for home to Sam's workplace route")
                if not ride_canceled:
                    failed_checks.append("agent did not cancel current ride")
                if not new_ride_booked:
                    failed_checks.append("agent did not book new ride from home to Sam's workplace")
                if not sam_notified:
                    failed_checks.append("agent did not notify Sam about pickup")

                rationale = "; ".join(failed_checks)
                return ScenarioValidationResult(success=False, rationale=rationale)

            return ScenarioValidationResult(success=True)

        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
