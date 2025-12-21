from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING, Any, cast

import numpy as np
from are.simulation.scenarios.utils.scenario_expander import (
    ENV_EVENT_DEFAULT_HORIZON,
    ENV_EVENT_EXPANSION_TAG,
    EnvEventsExpander,
)
from are.simulation.types import EventRegisterer

if TYPE_CHECKING:
    from are.simulation.scenarios import Scenario

    from pas.apps import StatefulEmailApp, StatefulMessagingApp

logger = logging.getLogger(__name__)


def default_weight_per_app_class() -> dict[str, float]:
    """Default weight per app class for PAS Env Events Expander."""
    return {
        "StatefulEmailApp": 1.0,
        "StatefulMessagingApp": 1.0,
        "StatefulShoppingApp": 1.0,
    }


class PASEnvEventsExpander(EnvEventsExpander):
    """Environmental events expander compatible with PAS Apps and Scenarios.

    Overrides the `add_env_events_to_scenario` method to work with PAS Stateful App types instead of Meta-ARE base app types.
    """

    def get_num_env_events_per_app(self, num_env_events: int) -> dict[str, int]:
        """Get the number of environmental events per app for PAS Env Events Expander."""
        # Calculate the number of events per app
        num_env_events_per_app = {}
        total_weight = sum(
            self.config.weight_per_app_class.get(self.resolved_app_names[app], 0) for app in self.resolved_app_names
        )

        for app in self.resolved_app_names:
            weight = self.config.weight_per_app_class.get(self.resolved_app_names[app], 0)
            num_env_events_per_app[app] = int((weight / total_weight) * num_env_events)
        return num_env_events_per_app

    def _resolve_app_names(self, app_names: list[str]) -> dict[str, str]:
        """Resolve app names to their canonical form for PAS Env Events Expander."""
        # Import here to avoid circular import
        from pas.constants import APP_ALIAS

        resolved_names = {}
        for app in app_names:
            for canonical_name, aliases in APP_ALIAS.items():
                if app == canonical_name or app in (aliases if isinstance(aliases, list) else [aliases]):
                    resolved_names[app] = canonical_name
                    break
        return resolved_names

    def add_env_events_to_scenario(self, scenario: Scenario, apps_augmentation_data: list[dict[str, Any]]) -> None:
        """Add environmental noise to a PAS Scenario.

        This override replaces Meta-ARE app type casts with PAS Stateful App types. Additionally, the noisy events do not depend on a start event from the scenario. They are scheduled to start at the beginning of the scenario.

        Args:
            scenario: The PAS Scenario to add environmental noise to.
            apps_augmentation_data: The augmentation data for the apps in the scenario.
        """
        scenario_app_class_names = [app.__class__.__name__ for app in scenario.apps]
        augmentation_app_names = [d["name"] for d in apps_augmentation_data]

        resolved_aug_names = self._resolve_app_names(augmentation_app_names)
        # Only keep the augmentation app names that are in the scenario
        self.resolved_app_names = {
            aug_name: resolved_aug_names.get(aug_name)
            for aug_name in augmentation_app_names
            if resolved_aug_names.get(aug_name) in scenario_app_class_names
        }

        duration = scenario.duration if scenario.duration else ENV_EVENT_DEFAULT_HORIZON

        np_rng = np.random.default_rng(self.config.env_events_seed)
        rng = random.Random(self.config.env_events_seed)  # noqa: S311

        num_env_events = int(self.config.num_env_events_per_minute * duration / 60)
        num_env_events_per_app = self.get_num_env_events_per_app(num_env_events)

        # Define app type mappings
        messaging_apps = ["StatefulMessagingApp", "Messages", "Chats"]
        email_apps = ["StatefulEmailApp", "Email", "Emails"]
        shopping_apps = ["StatefulShoppingApp", "Shopping"]

        d_events: dict[str, Any] = {}

        with EventRegisterer.capture_mode():
            for d in apps_augmentation_data:
                app_name = self.resolved_app_names.get(d["name"], "")
                if not app_name:
                    continue

                # Handle messaging events - use StatefulMessagingApp
                if d["name"] in messaging_apps:
                    self._add_messaging_events(
                        scenario=scenario,
                        app_name=d["name"],
                        app_data=d["app_state"],
                        d_events=d_events,
                        duration=duration,
                        num_events=num_env_events_per_app[d["name"]],
                        np_rng=np_rng,
                        rng=rng,
                    )

                # Handle email events - use StatefulEmailApp
                if d["name"] in email_apps:
                    self._add_email_events(
                        scenario=scenario,
                        app_name=d["name"],
                        app_data=d["app_state"],
                        d_events=d_events,
                        duration=duration,
                        num_events=num_env_events_per_app[d["name"]],
                        np_rng=np_rng,
                        rng=rng,
                    )

                # Handle shopping events - use StatefulShoppingApp
                if d["name"] in shopping_apps:
                    self._add_shopping_events(
                        scenario=scenario,
                        app_name=d["name"],
                        app_data=d["app_state"],
                        d_events=d_events,
                        duration=duration,
                        num_events=num_env_events_per_app[d["name"]],
                        np_rng=np_rng,
                        rng=rng,
                    )

            scenario.events += [e.with_id(f"{ENV_EVENT_EXPANSION_TAG}_{key}") for key, e in d_events.items()]

            logger.warning(f"Added {len(d_events)} env events to the scenario, total {len(scenario.events)} events")

    def _add_messaging_events(
        self,
        scenario: Scenario,
        app_name: str,
        app_data: dict[str, Any],
        d_events: dict[str, Any],
        duration: float,
        num_events: int,
        np_rng: np.random.Generator,
        rng: random.Random,
    ) -> None:
        # try getting the app from scenario, if it fails, don't add events for this app since it is not in the scenario
        try:
            app = cast("StatefulMessagingApp", scenario.get_app(app_name))
        except ValueError:
            logger.warning(f"App {app_name} not found in scenario, skipping environmental noise events")
            return

        conversations = list(app_data["conversations"].values())
        n_conversation_events = max(
            num_events // self.config.n_message_events_per_conversation,
            len(conversations),
        )
        n_conversation_events = min(n_conversation_events, len(conversations))
        conversations = rng.sample(conversations, k=n_conversation_events)
        average_rate = n_conversation_events / duration
        inter_arrival_times = np_rng.exponential(scale=1 / average_rate, size=n_conversation_events)
        ticks = np.cumsum(inter_arrival_times)
        for i, (tick, conversation) in enumerate(zip(ticks, conversations, strict=False)):
            if tick > duration:
                break
            n_messages = len(conversation["messages"])
            if n_messages == 0:
                continue
            n_message_events = min(n_messages, self.config.n_message_events_per_conversation)
            message_average_rate = n_message_events / (duration - tick)
            message_inter_arrival_times = np_rng.exponential(scale=1 / message_average_rate, size=n_message_events)
            for i, message in enumerate(conversation["messages"]):
                if i >= n_message_events:
                    break
                else:
                    d_events[f"{app_name}_{conversation['conversation_id']}_{i}"] = app.create_and_add_message(
                        conversation_id=conversation["conversation_id"],
                        sender_id=message["sender"],
                        content=message["content"],
                    )
                if i == 0:
                    d_events[f"{app_name}_{conversation['conversation_id']}_{i}"].depends_on(None, delay_seconds=tick)
                else:
                    d_events[f"{app_name}_{conversation['conversation_id']}_{i}"].depends_on(
                        d_events[f"{app_name}_{conversation['conversation_id']}_{i - 1}"],
                        delay_seconds=message_inter_arrival_times[i - 1],
                    )

    def _add_email_events(
        self,
        scenario: Scenario,
        app_name: str,
        app_data: dict[str, Any],
        d_events: dict[str, Any],
        duration: float,
        num_events: int,
        np_rng: np.random.Generator,
        rng: random.Random,
    ) -> None:
        try:
            app = cast("StatefulEmailApp", scenario.get_app(app_name))
        except ValueError:
            logger.warning(f"App {app_name} not found in scenario, skipping environmental noise events")
            return
        emails = list(app_data["folders"]["INBOX"]["emails"])
        rng.shuffle(emails)
        n_emails = len(emails)
        if n_emails == 0:
            return

        n_events = min(n_emails, num_events)
        average_rate = n_events / duration
        inter_arrival_times = np_rng.exponential(scale=1 / average_rate, size=n_events)
        ticks = np.cumsum(inter_arrival_times)
        for _, (tick, email) in enumerate(zip(ticks, emails, strict=False)):
            d_events[f"email_{email['email_id']}"] = app.create_and_add_email(
                sender=email["sender"],
                recipients=email["recipients"],
                subject=email["subject"],
                content=email["content"],
                folder_name="INBOX",
            ).depends_on(None, delay_seconds=tick)

    def _add_shopping_events(
        self,
        scenario: Scenario,
        app_name: str,
        app_data: dict[str, Any],
        d_events: dict[str, Any],
        duration: float,
        num_events: int,
        np_rng: np.random.Generator,
        rng: random.Random,
    ) -> None:
        # ! TODO: Uncomment following lines when we have a ShoppingApp in PAS
        # try:
        #     app = cast("StatefulShoppingApp", scenario.get_app(app_name))
        # except ValueError:
        #     logger.warning(f"App {app_name} not found in scenario, skipping environmental noise events")
        #     return
        # n_products = len(app_data["products"])
        # products_list = list(app_data["products"].values())
        # rng.shuffle(products_list)
        # if n_products == 0:
        #     return

        # n_events = min(n_products, num_events // self.config.n_item_events_per_product)
        # average_rate = n_events / duration
        # inter_arrival_times = np_rng.exponential(scale=1 / average_rate, size=n_events)
        # ticks = np.cumsum(inter_arrival_times)
        # for i, (tick, product) in enumerate(zip(ticks, products_list, strict=False)):
        #     if tick > duration:
        #         break
        #     d_events[f"shopping_product_{product['product_id']}"] = app.add_product(
        #         name=product["name"],
        #     ).depends_on(None, delay_seconds=tick)

        #     n_items = len(product["variants"])
        #     if n_items == 0:
        #         continue
        #     n_item_events = min(n_items, self.config.n_item_events_per_product)
        #     item_average_rate = n_item_events / (duration - tick)
        #     item_inter_arrival_times = np_rng.exponential(scale=1 / item_average_rate, size=n_item_events)
        #     item_ticks = np.cumsum(item_inter_arrival_times)
        #     for i, (item_tick, item) in enumerate(zip(item_ticks, product["variants"].values(), strict=False)):
        #         d_events[f"shopping_item_{item['item_id']}"] = app.add_item_to_product(
        #             product_id=f"{{{{{ENV_EVENT_EXPANSION_TAG}_shopping_product_{product['product_id']}}}}}",
        #             price=item["price"],
        #             available=item["available"],
        #             options=item["options"],
        #         ).depends_on(d_events[f"shopping_product_{product['product_id']}"], delay_seconds=item_tick)

        # for i, (item_id, discount_codes) in enumerate(d["app_state"]["discount_codes"].items()):
        #     discount_codes = cast("dict[str, float]", discount_codes)
        #     discount_codes = {str(k): float(v) for k, v in discount_codes.items()}
        #     delay_tick = np_rng.exponential(scale=duration // 2, size=1)[0]
        #     if f"shopping_item_{item_id}" in d_events:
        #         for code, value in discount_codes.items():
        #             discount_code = {code: value}
        #             d_events[f"shopping_discount_code_{item_id}_{code}"] = app.add_discount_code(
        #                 item_id=f"{{{{{ENV_EVENT_EXPANSION_TAG}_shopping_item_{item_id}}}}}",
        #                 discount_code=discount_code,
        #             ).depends_on(d_events[f"shopping_item_{item_id}"], delay_seconds=delay_tick)
        pass
