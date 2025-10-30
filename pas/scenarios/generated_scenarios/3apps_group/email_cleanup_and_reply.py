from typing import Any

from are.simulation.apps.agent_user_interface import AgentUserInterface
from are.simulation.apps.email_client import Email, EmailClientApp
from are.simulation.apps.system import SystemApp
from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult
from are.simulation.scenarios.utils.registry import register_scenario
from are.simulation.types import AbstractEnvironment, Action, EventRegisterer, EventType


@register_scenario("email_cleanup_and_reply")
class EmailCleanupAndReply(Scenario):
    """Scenario demonstrating email organization and proactive interaction.

    The assistant helps the user clean up their inbox by finding a specific message,
    proposing an action to reply, and organizing older emails. This uses all available
    applications (system, email client, agent UI) and includes proactive user approval.
    """

    start_time: float | None = 0
    duration: float | None = 60

    def init_and_populate_apps(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and seed the email system with mock data for demonstration."""
        aui = AgentUserInterface()
        system = SystemApp(name="sys_core")
        email_app = EmailClientApp()

        # Populate inbox with several test emails
        email_app._populate_folder(
            "INBOX",
            [
                Email(
                    email_id="em01",
                    sender="newsletter@techinsights.com",
                    recipients=["user@sample.com"],
                    subject="Weekly Tech Update",
                    content="Here are your weekly updates. Lots of reading material!",
                ),
                Email(
                    email_id="em02",
                    sender="colleague@workmail.com",
                    recipients=["user@sample.com"],
                    subject="Project Alpha Report",
                    content=(
                        "Hey, please review the attached draft of the Project Alpha summary. "
                        "Let me know your thoughts before Friday."
                    ),
                    attachments={"alpha_draft.docx": b"Binary data of draft"},
                ),
                Email(
                    email_id="em03",
                    sender="mark@brandpartner.io",
                    recipients=["user@sample.com"],
                    subject="Q2 Collaboration Notes",
                    content="Quick reminder: will you be at the strategy call tomorrow?",
                ),
            ],
        )

        self.apps = [aui, email_app, system]

    def build_events_flow(self) -> None:
        """Define the oracle flow for the cleanup and reply scenario."""
        aui = self.get_typed_app(AgentUserInterface)
        email_app = self.get_typed_app(EmailClientApp)
        system = self.get_typed_app(SystemApp)

        with EventRegisterer.capture_mode():
            # User starts by asking for inbox cleanup suggestions
            user_request = aui.send_message_to_agent(
                content="Can you help me clean up my inbox and handle the important emails?"
            ).depends_on(None, delay_seconds=1)

            # Agent lists all emails
            list_emails = (
                email_app.list_emails(folder_name="INBOX", offset=0, limit=10)
                .oracle()
                .depends_on(user_request, delay_seconds=1)
            )

            # Agent retrieves a specific email to review contents
            get_email = (
                email_app.get_email_by_id(email_id="em02", folder_name="INBOX")
                .oracle()
                .depends_on(list_emails, delay_seconds=1)
            )

            # Agent gets current time to decide time-sensitive actions
            check_time = system.get_current_time().oracle().depends_on(get_email, delay_seconds=1)

            # Agent proactively proposes replying to the colleague
            propose_reply = aui.send_message_to_user(
                content="I found an unread project email from your colleague titled 'Project Alpha Report'. Would you like me to reply with a quick acknowledgment?"
            ).depends_on(check_time, delay_seconds=1)

            # User confirms with a contextual approval (proactive interaction requirement)
            user_confirmation = aui.send_message_to_agent(
                content="Yes, please reply and thank them for the draft. I'll review it later."
            ).depends_on(propose_reply, delay_seconds=1)

            # Agent replies to the email after confirmation
            reply_action = (
                email_app.reply_to_email(
                    email_id="em02",
                    folder_name="INBOX",
                    content="Thanks for sharing the report! I'll go through it and respond with feedback before Friday.",
                    attachment_paths=None,
                )
                .oracle()
                .depends_on(user_confirmation, delay_seconds=1)
            )

            # Agent moves the replied email to another folder for organization
            move_email = (
                email_app.move_email(email_id="em02", source_folder_name="INBOX", dest_folder_name="ARCHIVE")
                .oracle()
                .depends_on(reply_action, delay_seconds=1)
            )

            # Agent also searches for promotional emails to delete
            search_promos = (
                email_app.search_emails(query="newsletter", folder_name="INBOX")
                .oracle()
                .depends_on(move_email, delay_seconds=1)
            )

            # Agent deletes the unwanted promotional email
            delete_old = (
                email_app.delete_email(email_id="em01", folder_name="INBOX")
                .oracle()
                .depends_on(search_promos, delay_seconds=1)
            )

            # To simulate time passing before final cleanup confirmation
            system_wait = system.wait_for_notification(timeout=5).oracle().depends_on(delete_old, delay_seconds=1)

        self.events = [
            user_request,
            list_emails,
            get_email,
            check_time,
            propose_reply,
            user_confirmation,
            reply_action,
            move_email,
            search_promos,
            delete_old,
            system_wait,
        ]

    def validate(self, env: AbstractEnvironment) -> ScenarioValidationResult:
        """Ensure emails were processed correctly: replied, moved, and deleted."""
        try:
            logs = env.event_log.list_view()
            reply_sent = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.class_name == "EmailClientApp"
                and ev.action.function_name == "reply_to_email"
                and "Thanks for sharing" in ev.action.args["content"]
                for ev in logs
            )
            moved_to_archive = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.function_name == "move_email"
                and ev.action.args["dest_folder_name"] == "ARCHIVE"
                for ev in logs
            )
            deleted_promos = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.function_name == "delete_email"
                and ev.action.args["email_id"] == "em01"
                for ev in logs
            )
            proactive_message = any(
                ev.event_type == EventType.AGENT
                and isinstance(ev.action, Action)
                and ev.action.function_name == "send_message_to_user"
                and "project email" in ev.action.args["content"].lower()
                for ev in logs
            )

            return ScenarioValidationResult(
                success=(reply_sent and moved_to_archive and deleted_promos and proactive_message)
            )
        except Exception as e:
            return ScenarioValidationResult(success=False, exception=e)
