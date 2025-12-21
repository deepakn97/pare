from __future__ import annotations

import json
import os
from typing import Any

from are.simulation.scenarios.scenario import Scenario
from are.simulation.utils.serialization import EnumEncoder

from pas import PROJECT_ROOT
from pas.scenarios.utils.scenario_expander import PASEnvEventsExpander


class PASScenario(Scenario):
    """Base class for all PAS scenarios."""

    def __post_init__(self) -> None:
        super().__post_init__()
        for attr in ["start_time", "status", "is_benchmark_ready", "duration", "time_increment_in_seconds"]:
            class_value = getattr(self.__class__, attr, None)
            if class_value is not None:
                setattr(self, attr, class_value)

    def initialize(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the scenario with all events and noise configurations."""
        if self._initialized:  # type: ignore[has-type]
            return

        # Initialize apps with the context
        self.init_and_populate_apps(*args, **kwargs)

        # Set the seed for each app
        if self.apps is not None:
            for app in self.apps:
                app.set_seed(self.seed)

        self.apply_augmentation_configs()

        # Preserve the initial state of the apps.
        self._initial_apps = {
            app.name: {
                "class_name": app.__class__.__name__,
                "serialized_state": json.dumps(app.get_state(), cls=EnumEncoder),
            }
            for app in self.apps or []
        }

        self.build_events_flow()

        if self.env_events_config is not None:
            augmentation_data_path_relative = os.getenv(
                "ENV_AUGMENTATION_DATA_PATH", "data/metaare_augmentation_data.json"
            )
            augmentation_data_path = PROJECT_ROOT / augmentation_data_path_relative
            if not augmentation_data_path.exists():
                raise ValueError(
                    f"ENV_AUGMENTATION_DATA_PATH is not set, but Environmental Noise is enabled. Expected path: {augmentation_data_path}"
                )
            with open(augmentation_data_path) as f:
                augmentation_data = json.load(f)
            self.augmentation_data = augmentation_data
            expander = PASEnvEventsExpander(env_events_config=self.env_events_config)
            expander.add_env_events_to_scenario(scenario=self, apps_augmentation_data=self.augmentation_data["apps"])

        self._initialized = True

    def apply_augmentation_configs(self) -> None:
        """Apply the augmentation configurations to the scenario."""
        if self.tool_augmentation_config is not None and self.apps is not None:
            for app in self.apps:
                app.set_failure_probability(self.tool_augmentation_config.tool_failure_probability)

            if self.augmentation_data is not None:
                name_map = self.augmentation_data.get("tool_names_mapping", {})
                desc_map = self.augmentation_data.get("tool_descriptions_mapping", {})
                apps_to_filter = ["PASAgentUserInterface", "HomeScreenSystemApp"]
                filtered_apps = [app for app in self.apps if app.name not in apps_to_filter]

                for app in filtered_apps:
                    for tool in app.get_tools():
                        if self.tool_augmentation_config.apply_tool_name_augmentation:
                            tool._public_name = name_map.get(tool.name, tool.name)

                        if self.tool_augmentation_config.apply_tool_description_augmentation:
                            tool._public_description = desc_map.get(tool.name, tool.function_description)
