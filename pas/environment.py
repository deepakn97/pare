from are.simulation.environment import Environment
from are.simulation.types import CompletedEvent

from pas.apps.core import StatefulApp


class StateAwareEnvironmentWrapper(Environment):
    """Environment wrapper that triggers state transitions in StatefulApps.

    // RL NOTE: This is the environment in the RL sense - manages state transitions and
    // provides observations (available actions) to agents based on current navigation state.
    """

    def handle_completed_event(self, event: CompletedEvent) -> None:
        """Intercept events to trigger navigation state transitions in StatefulApps.

        // RL NOTE: This is where the environment processes actions and transitions to next state.
        // Log (s, a, r, s') tuples here for RL dataset generation.

        Args:
            event: Completed event from tool execution
        """
        super().handle_completed_event(event)  # Normal processing first

        # Handle state transitions for StatefulApps
        app_name = event.app_name()
        app = self.get_app_by_name(app_name)

        if isinstance(app, StatefulApp):
            app.handle_state_transition(event)
