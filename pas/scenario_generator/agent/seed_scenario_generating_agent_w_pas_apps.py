from __future__ import annotations

# ruff: noqa: TC002, C901, S112, S110, SIM105, SIM102, D205, D415
import glob
import importlib.util
import json
import logging
import os
import re
import subprocess
import tempfile
import time

try:
    from datetime import UTC, datetime
except ImportError:
    from datetime import datetime

    UTC = UTC
import difflib
from collections import Counter, defaultdict
from inspect import getsource
from pathlib import Path
from typing import Any

from are.simulation.agents.agent_execution_result import AgentExecutionResult
from are.simulation.agents.default_agent.base_agent import BaseAgentLog
from are.simulation.agents.default_agent.default_tools import Tool
from are.simulation.agents.llm.llm_engine import LLMEngine
from are.simulation.scenarios import Scenario
from are.simulation.tool_box import DEFAULT_TOOL_DESCRIPTION_TEMPLATE, Toolbox
from are.simulation.tool_utils import AppTool, AppToolAdapter

from pas.scenario_generator.agent.app_combination_agent import AppCombinationAgent
from pas.scenario_generator.agent.summary_generating_agent import SummaryGeneratingAgent
from pas.scenario_generator.prompt.scenario_generator_prompts import (
    DEFAULT_SCENARIO_GENERATOR_REPAIR_SYSTEM_PROMPT,
    DEFAULT_SCENARIO_GENERATOR_REPAIR_SYSTEM_PROMPT_WITH_INSTRUCTIONS,
    DEFAULT_SCENARIO_GENERATOR_SEED_TASK,
    DEFAULT_SEED_SCENARIO_GENERATOR_SYSTEM_PROMPT,
    create_repair_note,
)

logger = logging.getLogger(__name__)


class AgentStoppedException(Exception):
    """Exception raised when the scenario generating agent is stopped."""

    pass


class SeedScenarioGeneratingAgent:
    """Agent for generating new scenarios based on example scenarios."""

    def __init__(
        self,
        llm_engine: LLMEngine,
        tools: list[Tool] | None = None,
        max_iterations: int = 3,
        import_instructions: str = "",
        app_def_scenario: Scenario | None = None,
    ) -> None:
        """Initialize the scenario generating agent.

        Args:
            llm_engine: The LLM engine to use for scenario generation
            tools: Optional list of tools to use
            max_iterations: Maximum number of generation iterations
            import_instructions: Instructions for valid imports
            app_def_scenario: Scenario that defines the available apps and tools (optional for backward compatibility)
        """
        self.llm_engine = llm_engine
        self.max_iterations = max_iterations
        self.tools = tools or []
        self._initialized = False
        self.import_instructions = import_instructions
        self.app_def_scenario = app_def_scenario

        # Initialize the app combination agent for intelligent app selection
        self.app_combination_agent = AppCombinationAgent(llm_engine)

        # Partitioned tool metadata for PAS tool-usage rules
        self._tool_names_by_category: dict[str, set[str]] = {
            "app": set(),
            "user": set(),
            "env": set(),
            "data": set(),
            "event_only": set(),
        }
        self._tools_for_prompt_by_category: dict[str, list[AppTool]] = {
            "init_allowed": [],
            "env_only": [],
            "all": [],
        }
        # Track app instances by class name for selected-app filtering
        self._app_instances_by_classname: dict[str, object] = {}
        # Track current selected apps for validation in a generation run
        self._current_selected_apps: set[str] = set()

    # ===== Minimal helpers to set up tools and prompts from an example scenario =====

    def remove_aui_irrelevant_tools(self, app_tools: list[AppTool]) -> list[AppTool]:
        """Remove AgentUserInterface tools that are not relevant for scenario generation."""
        try:
            # PAS generator only: consider PASAgentUserInterface tools
            aui_tool = next(tool for tool in app_tools if "PASAgentUserInterface" in tool.name)
        except StopIteration:
            return app_tools

        if aui_tool is not None:
            aui = aui_tool.class_instance
            # Ensure the agent does not block on user responses in this generation context
            logger.warning("Setting wait_for_user_response to False in AgentUserInterface")
            aui.wait_for_user_response = False

            tools_to_remove = {
                "PASAgentUserInterface__get_last_message_from_user",
                "PASAgentUserInterface__get_last_message_from_agent",
                "PASAgentUserInterface__get_last_unread_messages",
                "PASAgentUserInterface__get_all_messages",
            }
            logger.warning(f"Removing tools {tools_to_remove} from app_tools")
            app_tools = [tool for tool in app_tools if tool.name not in tools_to_remove]
        return app_tools

    def init_tools(self, app_def_scenario: Scenario) -> None:
        """Initialize tools from the app definition scenario, including PAS-extended tools.

        Some PAS applications (e.g., PASAgentUserInterface.accept_proposal/reject_proposal,
        HomeScreenSystemApp helpers, stateful Messaging/Calendar tools) may not be returned
        by the base scenario.get_tools() due to upstream collection differences. To ensure
        complete coverage, we supplement the tool list by scanning the actual app instances
        for any decorated tool methods and add any missing ones.
        """
        import inspect

        from are.simulation.tool_utils import ToolAttributeName, build_tool  # local import

        # 1) Collect tools reported by the scenario
        app_tools: list[AppTool] = app_def_scenario.get_tools()
        logger.info(
            "Found %d tools from app definition scenario: %s",
            len(app_tools),
            [tool.name for tool in app_tools],
        )

        # 2) Supplement with tools discovered directly on app instances (PAS extensions)
        discovered_tools: list[AppTool] = []

        # Build a set of existing (class_name, func_name) for deduplication
        existing_keys: set[tuple[str | None, str | None]] = {
            (getattr(t, "class_name", None), getattr(t, "func_name", None)) for t in app_tools
        }

        apps = getattr(app_def_scenario, "apps", []) or []

        def is_decorated_tool(func: object) -> bool:
            """Return True if function has any ARE tool decorator attribute."""
            if not callable(func):
                return False
            candidate = getattr(func, "__func__", func)  # unwrap bound method
            for attr in (
                ToolAttributeName.APP.value,
                ToolAttributeName.ENV.value,
                ToolAttributeName.DATA.value,
                ToolAttributeName.USER.value,
            ):
                if getattr(candidate, attr, False):
                    return True
            return False

        for app in apps:
            try:
                for _name, member in inspect.getmembers(app, predicate=callable):
                    if not is_decorated_tool(member):
                        continue
                    # Deduplicate against what scenario.get_tools() already returned
                    key = (app.__class__.__name__, getattr(getattr(member, "__func__", member), "__name__", None))
                    if key in existing_keys:
                        continue
                    try:
                        tool = build_tool(app, member)
                        discovered_tools.append(tool)
                        existing_keys.add(key)
                    except Exception:
                        # Skip non-registrable methods (e.g., missing docstring)
                        continue
            except Exception:
                continue

        if discovered_tools:
            logger.info(
                "Supplemented %d PAS tools not returned by scenario.get_tools(): %s",
                len(discovered_tools),
                [t.name for t in discovered_tools],
            )
            app_tools.extend(discovered_tools)

        # 3) Optionally trim irrelevant AUI tools (disabled by default)
        # app_tools = self.remove_aui_irrelevant_tools(app_tools)

        # 4) Adapt for the LLM engine
        are_simulation_tools = [AppToolAdapter(tool) for tool in app_tools]
        self.tools += are_simulation_tools
        logger.info(
            "Tools initialized from %s (including PAS supplements): %d tools",
            app_def_scenario.__class__.__name__,
            len(are_simulation_tools),
        )

        # 5) Build partitioned tool sets and prompt lists for PAS rules
        self._partition_tools_for_rules(app_tools)

    def _partition_tools_for_rules(self, app_tools: list[AppTool]) -> None:
        """Partition tools into categories for prompt rendering and validation."""
        # Reset containers
        for k in self._tool_names_by_category:
            self._tool_names_by_category[k] = set()
        self._tools_for_prompt_by_category["init_allowed"] = []
        self._tools_for_prompt_by_category["env_only"] = []
        self._tools_for_prompt_by_category["all"] = list(app_tools)

        # Collect unique app instances from tools
        app_instances: dict[int, object] = {}
        for t in app_tools:
            inst = getattr(t, "class_instance", None)
            if inst is not None:
                app_instances.setdefault(id(inst), inst)
                # Record by class name for selected-app queries later
                try:
                    cls_name = inst.__class__.__name__
                    self._app_instances_by_classname[cls_name] = inst
                except Exception:
                    pass

        from are.simulation.apps.app import ToolType
        from are.simulation.tool_utils import ToolAttributeName

        data_tools: list[AppTool] = []
        env_tools: list[AppTool] = []
        event_only: list[AppTool] = []

        for inst in app_instances.values():
            inst_any: Any = inst
            # Data tools
            try:
                data_tools_inst = inst_any.get_tools_with_attribute(ToolAttributeName.DATA, ToolType.DATA)
            except Exception:
                data_tools_inst = []
            for dt in data_tools_inst:
                if dt.func_name is not None:
                    self._tool_names_by_category["data"].add(dt.func_name)
                data_tools.append(dt)

            # Env tools
            try:
                env_tools_inst = inst_any.get_tools_with_attribute(ToolAttributeName.ENV, ToolType.ENV)
            except Exception:
                env_tools_inst = []
            for et in env_tools_inst:
                if et.func_name is not None:
                    self._tool_names_by_category["env"].add(et.func_name)
                env_tools.append(et)

            # User and App (for validation only)
            try:
                user_tools_inst = inst_any.get_tools_with_attribute(ToolAttributeName.USER, ToolType.USER)
            except Exception:
                user_tools_inst = []
            for ut in user_tools_inst:
                if ut.func_name is not None:
                    self._tool_names_by_category["user"].add(ut.func_name)

            try:
                app_tools_inst = inst_any.get_tools_with_attribute(ToolAttributeName.APP, ToolType.APP)
            except Exception:
                app_tools_inst = []
            for at in app_tools_inst:
                if at.func_name is not None:
                    self._tool_names_by_category["app"].add(at.func_name)

            # Event-only tools
            try:
                event_only_inst = inst_any.get_tools_with_attribute(None, None)
            except Exception:
                event_only_inst = []
            for eo in event_only_inst:
                if eo.func_name is not None:
                    self._tool_names_by_category["event_only"].add(eo.func_name)
                event_only.append(eo)

        # Prepare prompt groupings
        init_allowed_tools = []
        seen_names = set()
        for t in data_tools + event_only:
            if t.func_name and t.func_name not in seen_names:
                init_allowed_tools.append(t)
                seen_names.add(t.func_name)
        self._tools_for_prompt_by_category["init_allowed"] = init_allowed_tools
        self._tools_for_prompt_by_category["env_only"] = env_tools

    def init_system_prompt(self, example_scenario: Scenario) -> None:
        """Initialize the system prompt from an example scenario using the seed-specific prompt."""
        # Minimal prompt post-processing: set current time and clear agent reminder placeholder if present
        try:
            date_str = datetime.fromtimestamp(example_scenario.start_time or 0, tz=UTC).strftime("%Y-%m-%d %H")
        except Exception:
            date_str = datetime.fromtimestamp(0, tz=UTC).strftime("%Y-%m-%d %H")

        self.system_prompt = str(DEFAULT_SEED_SCENARIO_GENERATOR_SYSTEM_PROMPT)
        self.system_prompt = self.system_prompt.replace(
            "<<curent_time_description>>", f"Today's date in 'YYYY-MM-DD HH' format is {date_str}"
        ).replace("<<agent_reminder_description>>", "")

    def _validate_and_prepare_scenario_generation(
        self, app_def_scenario: Scenario, example_scenarios: list[Scenario]
    ) -> None:
        """Validate input and setup tools from app definition scenario."""
        if app_def_scenario is None:
            raise ValueError("App definition scenario is required")

        if example_scenarios is None or len(example_scenarios) == 0:
            raise ValueError("At least one example scenario is required")

        # Initialize tools from the app definition scenario (not from example scenarios)
        self.init_tools(app_def_scenario)

        # Initialize system prompt from the first example scenario
        first_example = example_scenarios[0]
        self.init_system_prompt(first_example)

    def _setup_system_prompt(self, selected_import_instructions: str | None = None) -> str:
        """Build and return the seed-specific system prompt with tool descriptions and import instructions."""
        system_prompt = str(DEFAULT_SEED_SCENARIO_GENERATOR_SYSTEM_PROMPT)
        toolbox = Toolbox(tools=self.tools)

        tool_descriptions = toolbox.show_tool_descriptions(DEFAULT_TOOL_DESCRIPTION_TEMPLATE)
        if isinstance(system_prompt, str):
            system_prompt = system_prompt.replace("<<tool_descriptions>>", tool_descriptions)

        # Use selected import instructions if provided, otherwise use the default
        import_instructions = selected_import_instructions if selected_import_instructions else self.import_instructions
        if isinstance(system_prompt, str):
            system_prompt = system_prompt.replace("<<import_instructions>>", import_instructions)

        # Basic current-time replacement
        try:
            # Use current UTC time to reflect "Today's date"
            date_str = datetime.now(tz=UTC).strftime("%Y-%m-%d %H")
        except Exception:
            date_str = datetime.fromtimestamp(0, tz=UTC).strftime("%Y-%m-%d %H")
        system_prompt = system_prompt.replace(
            "<<curent_time_description>>", f"Today's date in 'YYYY-MM-DD HH' format is {date_str}"
        ).replace("<<agent_reminder_description>>", "")

        # Append PAS tool usage rules and grouped tool descriptions
        try:
            # Build init_allowed descriptions but SCOPE to selected apps only
            init_allowed_all = self._tools_for_prompt_by_category.get("init_allowed", [])
            init_allowed_selected: list[AppTool] = []
            for t in init_allowed_all:
                try:
                    inst = getattr(t, "class_instance", None)
                    cls_name = inst.__class__.__name__ if inst is not None else None
                    if cls_name in self._current_selected_apps:
                        init_allowed_selected.append(t)
                except Exception:
                    continue
            # Use adapters so the rendered descriptions include inputs/outputs exactly like tool_descriptions
            init_toolbox = Toolbox(tools=[AppToolAdapter(t) for t in init_allowed_selected])
            init_desc = init_toolbox.show_tool_descriptions(DEFAULT_TOOL_DESCRIPTION_TEMPLATE)
            # Selected-app scoped allowed non-oracle methods (from notification templates)
            allowed_non_oracle = sorted(self._get_allowed_non_oracle_methods_for_selected_apps())
            # Selected-app scoped init methods (data + event-only)
            selected_sets = self._collect_tool_names_for_selected_apps()
            allowed_init_selected = sorted(selected_sets.get("data", set()) | selected_sets.get("event_only", set()))
            # Selected-app scoped oracle methods (any category)
            allowed_oracle_all = sorted(self._get_allowed_oracle_methods_for_selected_apps())

            # Debug logs for allowed methods per stage
            try:
                logger.info(
                    "[PAS Rules] Selected apps: %s",
                    ", ".join(sorted(self._current_selected_apps)) if self._current_selected_apps else "(none)",
                )
                logger.info(
                    "[PAS Rules] Allowed init (data + event-only) methods: %s", ", ".join(allowed_init_selected)
                )
                logger.info(
                    "[PAS Rules] Allowed non-oracle (capture_mode) methods (from notification templates): %s",
                    ", ".join(allowed_non_oracle),
                )
                logger.info(
                    "[PAS Rules] Allowed oracle (capture_mode .oracle()) methods: %s",
                    ", ".join(allowed_oracle_all),
                )
            except Exception:
                pass
            from pas.scenario_generator.prompt.scenario_generator_prompts import (
                PAS_GROUPED_BLOCK_TEMPLATE,
                PAS_RULES_BLOCK_TEMPLATE,
            )

            rules = PAS_RULES_BLOCK_TEMPLATE.replace("<<non_oracle_methods_flat>>", ", ".join(allowed_non_oracle))
            grouped = (
                PAS_GROUPED_BLOCK_TEMPLATE.replace("<<init_allowed_block>>", init_desc)
                # Use detailed tool descriptions (with inputs/outputs) for allowed non-oracle methods, grouped by app
                .replace(
                    "<<allowed_non_oracle_by_app_block>>",
                    self._format_allowed_non_oracle_methods_by_app_descriptions(),
                )
            )
            # Inject PAS rules and grouped sections into the system prompt template
            system_prompt = system_prompt.replace("<<pas_rules_block>>", rules)
            system_prompt = system_prompt.replace("<<pas_grouped_block>>", grouped)
        except Exception:
            # If anything goes wrong, keep default prompt without grouped sections
            system_prompt = system_prompt.replace("<<pas_rules_block>>", "")
            system_prompt = system_prompt.replace("<<pas_grouped_block>>", "")

        # Append existing scenario summaries to help avoid duplicates
        try:
            summaries = self._load_scenario_summaries()
            if summaries:
                lines = []
                for sid, summary in summaries.items():
                    # Keep it compact; single line per summary
                    compact = " ".join(str(summary).split())
                    lines.append(f"- {sid}: {compact}")
                summaries_text = "\n".join(lines)
                system_prompt += (
                    f"\n\nEXISTING SCENARIO SUMMARIES (avoid creating duplicates or close variants):\n{summaries_text}"
                )
        except Exception:
            # If loading fails, continue without summaries
            pass

        return system_prompt

    def _format_allowed_non_oracle_methods_by_app_descriptions(self) -> str:
        """Return detailed descriptions (with inputs/outputs) for allowed non-oracle env methods, grouped by selected app.

        This mirrors the formatting of tool_descriptions by leveraging Toolbox.show_tool_descriptions,
        but restricts to only the methods allowed by notification templates for the current selected apps.
        """
        allowed_map = self._get_allowed_non_oracle_methods_map_for_selected_apps()
        if not allowed_map:
            return "(none)"

        # Build quick lookup of ENV AppTool objects for selected apps
        # Important: use ENV tools, since allowed_non_oracle refers to environment-triggered methods
        app_tools_all: list[AppTool] = self._tools_for_prompt_by_category.get("env_only", [])

        def tools_for_app_and_methods(app_name: str, method_names: list[str]) -> list[AppTool]:
            selected: list[AppTool] = []
            names_set = set(method_names)
            for t in app_tools_all:
                try:
                    inst = getattr(t, "class_instance", None)
                    cls_name = inst.__class__.__name__ if inst is not None else None
                    if cls_name == app_name and getattr(t, "func_name", None) in names_set:
                        selected.append(t)
                except Exception:
                    continue
            return selected

        blocks: list[str] = []
        for app_name in sorted(self._current_selected_apps):
            methods = allowed_map.get(app_name, [])
            if not methods:
                # Skip apps without allowed non-oracle methods
                continue
            subset_raw = tools_for_app_and_methods(app_name, methods)
            if not subset_raw:
                continue
            # Use adapters to preserve inputs/outputs formatting
            tb = Toolbox(tools=[AppToolAdapter(t) for t in subset_raw])
            desc = tb.show_tool_descriptions(DEFAULT_TOOL_DESCRIPTION_TEMPLATE)
            blocks.append(f"{app_name}\n{desc}")

        return "\n\n".join(blocks) if blocks else "(none)"

    def _get_allowed_non_oracle_methods_map_for_selected_apps(self) -> dict[str, list[str]]:
        """Return mapping of selected app -> allowed non-oracle method names from notification templates."""
        result: dict[str, list[str]] = {}
        if not self._current_selected_apps:
            return result
        try:
            from pas.apps.notification_templates import NOTIFICATION_TEMPLATES
        except Exception:
            return result

        combined: dict[str, set[str]] = defaultdict(set)
        for scope in ("user", "agent"):
            app_map = NOTIFICATION_TEMPLATES.get(scope, {})
            for app_name in self._current_selected_apps:
                app_methods = app_map.get(app_name, {})
                if app_methods:
                    combined[app_name].update(app_methods.keys())

        for app_name, name_set in combined.items():
            result[app_name] = sorted(name_set)
        return result

    def _format_allowed_non_oracle_methods_by_app(self) -> str:
        """Format per-app allowed non-oracle methods for inclusion in the prompt."""
        allowed_map = self._get_allowed_non_oracle_methods_map_for_selected_apps()
        if not allowed_map:
            return "(none)"
        lines = []
        for app_name in sorted(allowed_map.keys()):
            methods = allowed_map[app_name]
            lines.append(f"{app_name}: {', '.join(methods)}")
        return "\n".join(lines)

    def _get_allowed_non_oracle_methods_for_selected_apps(self) -> set[str]:
        """Return method names allowed for non-oracle events based on notification templates and selected apps."""
        allowed: set[str] = set()
        if not self._current_selected_apps:
            return allowed
        try:
            from pas.apps.notification_templates import NOTIFICATION_TEMPLATES
        except Exception:
            return allowed

        for scope in ("user", "agent"):
            app_map = NOTIFICATION_TEMPLATES.get(scope, {})
            for app_name in self._current_selected_apps:
                methods = app_map.get(app_name, {})
                allowed.update(methods.keys())
        return allowed

    def _get_allowed_oracle_methods_for_selected_apps(self) -> set[str]:
        """Return all tool method names from selected apps (any category) for oracle usage."""
        if not self._current_selected_apps:
            return set()
        selected_sets = self._collect_tool_names_for_selected_apps()
        return set().union(
            selected_sets.get("app", set()),
            selected_sets.get("user", set()),
            selected_sets.get("env", set()),
            selected_sets.get("data", set()),
            selected_sets.get("event_only", set()),
        )

    def _collect_tool_names_for_selected_apps(self) -> dict[str, set[str]]:
        """Collect tool method names by category for selected apps only."""
        categories: dict[str, set[str]] = {
            "app": set(),
            "user": set(),
            "env": set(),
            "data": set(),
            "event_only": set(),
        }
        if not self._current_selected_apps:
            return categories
        from are.simulation.apps.app import ToolType
        from are.simulation.tool_utils import ToolAttributeName

        for app_name in self._current_selected_apps:
            inst = self._app_instances_by_classname.get(app_name)
            if inst is None:
                continue
            inst_any: Any = inst
            try:
                for name, attr, ttype in (
                    ("data", ToolAttributeName.DATA, ToolType.DATA),
                    ("env", ToolAttributeName.ENV, ToolType.ENV),
                    ("user", ToolAttributeName.USER, ToolType.USER),
                    ("app", ToolAttributeName.APP, ToolType.APP),
                ):
                    tools = inst_any.get_tools_with_attribute(attr, ttype)
                    for tool in tools:
                        if tool.func_name is not None:
                            categories[name].add(tool.func_name)
            except Exception:
                pass
            try:
                eo_tools = inst_any.get_tools_with_attribute(None, None)
                for tool in eo_tools:
                    if tool.func_name is not None:
                        categories["event_only"].add(tool.func_name)
            except Exception:
                pass
        return categories

    def _create_seed_task_from_scenarios(
        self, example_scenarios: list[Scenario], scenario_summary: str | None = None
    ) -> str:
        """Create the seed task message from example scenarios using the seed-specific template."""
        code_blocks = []
        for i, sc in enumerate(example_scenarios, start=1):
            try:
                src = getsource(sc.__class__)
            except Exception:
                src = ""
            code_blocks.append(f"Example {i}:\n```python\n{src}\n```")

        # Use the seed-specific task template instead of the general one
        seed_task_with_examples = DEFAULT_SCENARIO_GENERATOR_SEED_TASK + "\n\n{example_code_blocks}"
        base_task = seed_task_with_examples.format(example_code_blocks="\n\n".join(code_blocks))

        # Add scenario summary guidance if provided
        if scenario_summary:
            summary_guidance = f"\n\nSCENARIO GUIDANCE:\nBased on the app combination analysis, this scenario should:\n{scenario_summary}\n\nUse this guidance to create a scenario that demonstrates the described workflow and achieves the specified outcomes."
            return base_task + summary_guidance

        return base_task

    def _create_initial_messages(self, system_prompt: str, seed_task: str) -> list[dict[str, str]]:
        """Create the initial messages for the LLM."""
        return [{"role": "system", "content": system_prompt}, {"role": "user", "content": seed_task}]

    def _run_generation_iterations(self) -> tuple[str | None, Path | None]:
        """Run the iterative generation process and return (code_text, written_path)."""
        previous_code: str | None = None
        issues: list[str] = []
        written_path: Path | None = None
        for it in range(max(1, self.max_iterations)):
            logger.info(f"==== Iteration {it} began ====")

            # Build messages depending on whether we're in a repair cycle
            if previous_code is None:
                adjusted_messages = list(self.messages)
            else:
                # Use a concise repair system prompt to avoid creation-time distractions
                if self.import_instructions:
                    repair_system_prompt = DEFAULT_SCENARIO_GENERATOR_REPAIR_SYSTEM_PROMPT_WITH_INSTRUCTIONS.format(
                        import_instructions=self.import_instructions
                    )
                else:
                    repair_system_prompt = DEFAULT_SCENARIO_GENERATOR_REPAIR_SYSTEM_PROMPT

                repair_messages = [{"role": "system", "content": repair_system_prompt}]
                repair_note = create_repair_note(issues, previous_code)
                repair_messages.append({"role": "user", "content": repair_note})
                adjusted_messages = repair_messages
            # logger.info(f"==== Adjusted messages: {adjusted_messages} ====")

            llm_output_tuple = self.llm_engine(
                adjusted_messages, stop_sequences=[], additional_trace_tags=["scenario_generation"], schema=None
            )
            if isinstance(llm_output_tuple, tuple) and len(llm_output_tuple) == 2:
                llm_output, _ = llm_output_tuple
            else:
                llm_output = llm_output_tuple

            code_text: str | None = None
            if isinstance(llm_output, str):
                m = re.search(r"```(?:python)?\s*([\s\S]*?)```", llm_output)
                if m:
                    code_text = m.group(1).strip()
            if not code_text:
                previous_code = llm_output if isinstance(llm_output, str) else None
                issues = ["Model did not return a fenced python block. Return a single fenced python code block only."]
                continue

            # Fix scenario naming issues first
            logger.info("==== Fixing scenario naming issues ====")
            code_text = self._fix_scenario_naming_issues(code_text)

            # Fix common linting issues
            logger.info("==== Fixing linting issues ====")
            code_text = self._fix_generated_file_linting_issues(code_text)

            # Autofix common API mistakes (e.g., approvals)
            logger.info("==== Auto-fixing common API mistakes ====")
            code_text = self._autofix_common_api_mistakes(code_text)

            # Validate imports against provided instructions
            issues = self._validate_imports(code_text)

            # Validate generated file for syntax and other issues
            logger.info("==== Validating generated file ====")
            validation_issues = self._validate_generated_file(code_text)
            issues.extend(validation_issues)

            # Validate comprehensive tool usage (critical for seed mode)
            logger.info("==== Validating comprehensive tool usage ====")
            tool_usage_issues = self._validate_comprehensive_tool_usage(code_text)
            issues.extend(tool_usage_issues)

            # Validate PAS tool-usage rules across init/build methods
            logger.info("==== Validating PAS tool-usage rules ====")
            rule_issues = self._validate_tool_usage_rules(code_text)
            issues.extend(rule_issues)

            # Validate strict API correctness to prevent recurring mistakes
            # logger.info("==== Validating API correctness rules ====")
            # api_issues = self._validate_api_correctness(code_text)
            # issues.extend(api_issues)

            # Validate proactive interaction pattern (critical for seed mode)
            logger.info("==== Validating proactive interaction pattern ====")
            proactive_issues = self._validate_proactive_interaction_pattern(code_text)
            issues.extend(proactive_issues)

            # Validate similarity against existing scenarios if no other issues
            if not issues:
                logger.info("==== Validating similarity against existing scenario summaries ====")
                similarity_issues = self._validate_similarity_against_existing_scenario_summary(code_text)
                issues.extend(similarity_issues)

            # # Validate mock run if no other issues
            # if not issues:
            #     logger.info("==== Validating mock run ====")
            #     mock_validation_issues = self._validate_mock_run(code_text)
            #     issues.extend(mock_validation_issues)
            #     if issues:
            #         logger.info(f"==== Mock run validation issues: {issues} ====")

            if not issues:
                logger.info("==== Writing file ====")
                try:
                    written_path = self._write_generated_scenario(code_text)
                    logger.info("==== File written and validation passed ====")
                    break

                except Exception as e:
                    issues = [f"Failed to write file: {e}"]
                    previous_code = code_text
                    continue
            else:
                logger.info(f"==== Iteration {it} has issues {issues}, continue and try again ====")
                previous_code = code_text
                continue

        return previous_code, written_path

    def _autofix_common_api_mistakes(self, code_text: str) -> str:
        """Apply simple, safe textual fixes for recurring mistakes to help the loop converge."""
        try:
            # Replace approvals using send_message_to_agent(...) with accept_proposal(...)
            # Heuristic: global replace is acceptable since accept_proposal mirrors signature.
            code_text = code_text.replace(".send_message_to_agent(", ".accept_proposal(")
        except Exception:
            pass
        return code_text

    def _validate_api_correctness(self, code_text: str) -> list[str]:
        """Validate common API correctness issues seen in generated scenarios."""
        problems: list[str] = []
        try:
            import ast

            tree = ast.parse(code_text)

            def find_calls_with_attr(attr_name: str) -> list[ast.Call]:
                return [
                    n
                    for n in ast.walk(tree)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == attr_name
                ]

            def function_def_by_name(name: str) -> ast.FunctionDef | None:
                for n in ast.walk(tree):
                    if isinstance(n, ast.FunctionDef) and n.name == name:
                        return n
                return None

            # 1) Forbid env_action and EventRegisterer.env_event usage
            if find_calls_with_attr("env_action"):
                problems.append("Do not use env_action(). Call allowed non-oracle ENV methods directly by name.")
            for n in ast.walk(tree):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                    if (
                        n.func.attr == "env_event"
                        and isinstance(n.func.value, ast.Name)
                        and n.func.value.id == "EventRegisterer"
                    ):
                        problems.append(
                            "Do not use EventRegisterer.env_event(). Use allowed non-oracle ENV methods directly."
                        )
                    if (
                        n.func.attr == "create_env_event"
                        and isinstance(n.func.value, ast.Name)
                        and n.func.value.id == "EventRegisterer"
                    ):
                        problems.append(
                            "Do not use EventRegisterer.create_env_event(). Use allowed non-oracle ENV methods directly; avoid placeholder events."
                        )
                    if (
                        n.func.attr == "register_env_event"
                        and isinstance(n.func.value, ast.Name)
                        and n.func.value.id == "EventRegisterer"
                    ):
                        problems.append(
                            "Do not use EventRegisterer.register_env_event(). Use allowed non-oracle ENV methods directly on the app (e.g., messaging.create_and_add_message(...), calendar.add_calendar_event(...))."
                        )

            # 2) Disallow user_name argument in create_and_add_message and check literal conversation_id
            for call in find_calls_with_attr("create_and_add_message"):
                for kw in call.keywords:
                    if kw.arg == "user_name":
                        problems.append(
                            "create_and_add_message() does not accept 'user_name'. Use 'sender_id' and 'conversation_id'."
                        )
                    if (
                        kw.arg == "conversation_id"
                        and isinstance(kw.value, ast.Constant)
                        and isinstance(kw.value.value, str)
                    ):
                        problems.append(
                            "Avoid hardcoded conversation_id strings. Use the ID returned from create_group_conversation()."
                        )

            # Also check other messaging APIs for literal conversation_id
            for attr in ("send_message_to_group_conversation", "read_conversation", "download_attachment"):
                for call in find_calls_with_attr(attr):
                    for kw in call.keywords:
                        if (
                            kw.arg == "conversation_id"
                            and isinstance(kw.value, ast.Constant)
                            and isinstance(kw.value.value, str)
                        ):
                            problems.append(
                                f"'{attr}' uses a literal conversation_id. Capture and reuse the returned ID from create_group_conversation()."
                            )

            # 3) Ensure messaging preconditions (current_user_id/name and conversation creation)
            init_fn = function_def_by_name("init_and_populate_apps")
            if init_fn is not None:
                found_user_id_set = False
                found_user_name_set = False
                found_conversation_created = False
                for n in ast.walk(init_fn):
                    # Detect attribute sets for current_user_id and current_user_name
                    if isinstance(n, ast.Assign):
                        for t in n.targets:
                            if isinstance(t, ast.Attribute) and t.attr == "current_user_id":
                                found_user_id_set = True
                            if isinstance(t, ast.Attribute) and t.attr == "current_user_name":
                                found_user_name_set = True
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                        if n.func.attr in ("create_group_conversation", "add_conversation"):
                            found_conversation_created = True
                # Only warn if the build_events_flow uses messaging env methods
                build_fn = function_def_by_name("build_events_flow")
                uses_messaging_env = False
                found_conversation_created_in_build = False
                if build_fn is not None:
                    for n in ast.walk(build_fn):
                        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                            if n.func.attr in (
                                "create_and_add_message",
                                "add_message",
                                "send_message_to_group_conversation",
                            ):
                                uses_messaging_env = True
                                break
                    # Also accept conversation creation inside build_events_flow (inside capture_mode)
                    for n in ast.walk(build_fn):
                        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                            if n.func.attr in ("create_group_conversation", "add_conversation"):
                                found_conversation_created_in_build = True
                                break
                if uses_messaging_env:
                    if not found_user_id_set or not found_user_name_set:
                        problems.append(
                            "Messaging preconditions missing: set messaging.current_user_id and messaging.current_user_name in init_and_populate_apps(), and add users as needed."
                        )
                    # Relaxation: allow conversation creation either in init_and_populate_apps or in build_events_flow
                    if not (found_conversation_created or found_conversation_created_in_build):
                        problems.append(
                            "Conversation precondition missing: create a conversation in init_and_populate_apps() OR early inside build_events_flow (within capture_mode) and reuse its returned conversation_id."
                        )

            # 4) Approval should use accept_proposal/reject_proposal, not send_message_to_agent
            if find_calls_with_attr("send_message_to_agent"):
                problems.append(
                    "Use PASAgentUserInterface.accept_proposal(...) or reject_proposal(...) for approvals instead of send_message_to_agent."
                )

            # 5) get_current_time().oracle() misuse
            for n in ast.walk(tree):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "oracle":
                    # Check if the receiver is a call to get_current_time
                    recv = n.func.value
                    if (
                        isinstance(recv, ast.Call)
                        and isinstance(recv.func, ast.Attribute)
                        and recv.func.attr == "get_current_time"
                    ):
                        problems.append(
                            "Do not chain .oracle() after get_current_time(). Use it as a regular call when needed."
                        )

        except Exception as e:
            problems.append(f"API correctness validation failed: {e}")
        return problems

    def _validate_tool_usage_rules(self, code_text: str) -> list[str]:
        """Validate tool usage rules for init_and_populate_apps and build_event_flow."""
        problems: list[str] = []
        try:
            import ast

            tree = ast.parse(code_text)

            # Build quick lookup sets of function names by category
            data_names = self._tool_names_by_category.get("data", set())
            env_names = self._tool_names_by_category.get("env", set())
            # Ensure common HomeScreenSystemApp ENV helpers are treated as env tools even if meta detection missed them
            env_names = env_names | {
                "get_current_time",
                "wait_for_notification",
            }
            user_names = self._tool_names_by_category.get("user", set())
            app_names = self._tool_names_by_category.get("app", set())
            event_only_names = self._tool_names_by_category.get("event_only", set())
            all_names = set().union(data_names, env_names, user_names, app_names, event_only_names)

            def collect_called_method_names(node: ast.AST) -> set[str]:
                names: set[str] = set()
                for call in [n for n in ast.walk(node) if isinstance(n, ast.Call)]:
                    if isinstance(call.func, ast.Attribute):
                        names.add(call.func.attr)
                return names

            # 1) init_and_populate_apps: only data or event-only tool method names
            for n in ast.walk(tree):
                if isinstance(n, ast.FunctionDef) and n.name == "init_and_populate_apps":
                    called = collect_called_method_names(n)
                    # Restrict to names that correspond to available tools
                    called_tools = called & all_names
                    # Allow a small whitelist of ENV methods needed to create initial data (e.g. conversations)
                    init_env_allowed = {"create_group_conversation"}
                    disallowed = called_tools - (data_names | event_only_names | init_env_allowed)
                    if disallowed:
                        problems.append(
                            "init_and_populate_apps uses disallowed tools. Only data tools or event-only tools "
                            f"(@event_registered only) are permitted. Offenders: {sorted(disallowed)}"
                        )

            # 2) build_event_flow: inside capture_mode with non-oracle => only env tools;
            #    oracle chains can use any tools.
            def find_capture_mode_with_blocks(module: ast.Module) -> list[ast.With]:
                blocks: list[ast.With] = []
                for with_node in [w for w in ast.walk(module) if isinstance(w, ast.With)]:
                    # Match 'with EventRegisterer.capture_mode():' or similar
                    for item in with_node.items:
                        ctx = item.context_expr
                        ctx_name = ""
                        if isinstance(ctx, ast.Call):
                            func = ctx.func
                            if isinstance(func, ast.Attribute):
                                ctx_name = func.attr
                            elif isinstance(func, ast.Name):
                                ctx_name = func.id
                        elif isinstance(ctx, ast.Attribute):
                            ctx_name = ctx.attr
                        elif isinstance(ctx, ast.Name):
                            ctx_name = ctx.id
                        if "capture_mode" in ctx_name:
                            blocks.append(with_node)
                return blocks

            def analyze_expr_for_oracle_and_initial_calls(expr: ast.AST) -> tuple[set[str], bool]:
                """Return (initial_called_tool_names, has_oracle_in_chain) for an expression.
                We approximate by:
                  - Any 'oracle' call anywhere under this expr marks has_oracle_in_chain=True
                  - Initial method names = method names of the first attribute call in chains
                """
                has_oracle = False
                initial_names: set[str] = set()

                # Detect any oracle calls in the subtree
                for call in [n for n in ast.walk(expr) if isinstance(n, ast.Call)]:
                    if isinstance(call.func, ast.Attribute) and call.func.attr == "oracle":
                        has_oracle = True
                        break

                # Collect attribute call names that look like tool entry points
                # Heuristic: calls whose function name is in known tool names
                for call in [n for n in ast.walk(expr) if isinstance(n, ast.Call)]:
                    if isinstance(call.func, ast.Attribute):
                        method_name = call.func.attr
                        if method_name in all_names:
                            initial_names.add(method_name)
                return initial_names, has_oracle

            for n in ast.walk(tree):
                if isinstance(n, ast.FunctionDef) and n.name == "build_events_flow":
                    # Evaluate only WITH blocks that are capture_mode
                    for with_block in find_capture_mode_with_blocks(tree):
                        for stmt in with_block.body:
                            if isinstance(stmt, (ast.Expr, ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Return)):
                                names, has_oracle = analyze_expr_for_oracle_and_initial_calls(stmt)
                                if not names:
                                    continue
                                if has_oracle:
                                    # Any tools allowed in oracle chain
                                    continue
                                # Non-oracle inside capture_mode: only env tools, and must not be user/app
                                non_env = names - env_names
                                offending_user = names & user_names
                                offending_app = names & app_names
                                # Explicitly forbid 'open_app' in non-oracle capture blocks
                                if "open_app" in names:
                                    non_env = non_env | {"open_app"}
                                offenders = non_env | offending_user | offending_app
                                if offenders:
                                    problems.append(
                                        "Inside build_events_flow capture_mode, non-oracle tool usage must be ENV tools only. "
                                        f"Offenders: {sorted(offenders)}"
                                    )
        except Exception as e:
            problems.append(f"Tool usage rule validation failed: {e}")
        return problems

    def _write_generated_scenario(self, code_text: str) -> Path:
        """Write the generated scenario to a file and return the path."""
        sid_match = re.search(r"@register_scenario\(\s*['\"]([^'\"]+)['\"]\s*\)", code_text)
        if sid_match:
            scenario_id = sid_match.group(1).strip()
            file_name = f"{scenario_id}.py"
        else:
            class_match = re.search(r"class\s+(\w+)\s*\(", code_text)
            base = class_match.group(1) if class_match else f"generated_{int(time.time())}"
            file_name = f"{base.lower()}.py"

        target_dir = Path(__file__).resolve().parents[2] / "scenarios" / "generated_scenarios_w_pas_apps"
        target_dir.mkdir(parents=True, exist_ok=True)
        written_path = target_dir / file_name
        written_path.write_text(code_text, encoding="utf-8")
        return written_path

    # ===== Core minimal run for scenario generation =====

    def scenario_generation_run(
        self,
        example_scenarios: list[Scenario],
        app_def_scenario: Scenario | None = None,
        initial_agent_logs: list[BaseAgentLog] | None = None,
        total_scenarios: int = 1,
        apps_per_scenario: int = 4,
        selected_apps: list[str] | None = None,
    ) -> AgentExecutionResult:
        """Generate multiple scenarios with different app combinations.

        - Set tools from the app definition scenario (defines available apps)
        - Set prompt from the first example scenario
        - Generate multiple scenarios with different app combinations
        - Each scenario uses AgentUserInterface + apps_per_scenario other apps
        - Track used app combinations to avoid duplicates
        - Build system prompts with selected tools for each scenario
        - Write each scenario to are/simulation/scenarios/generated_scenarios

        Args:
            example_scenarios: List of example scenarios for reference
            app_def_scenario: Scenario that defines available apps and tools
            initial_agent_logs: Optional initial agent logs
            total_scenarios: Total number of scenarios to generate
            apps_per_scenario: Number of apps (excluding AgentUserInterface) to use per scenario
            selected_apps: Optional explicit app class names to use for all scenarios. When provided,
                bypasses app combination generation and reuses this set for each scenario.
        """
        # Use provided app_def_scenario or fall back to stored one
        if app_def_scenario is None and self.app_def_scenario is not None:
            app_def_scenario = self.app_def_scenario
        elif app_def_scenario is None:
            raise ValueError("App definition scenario is required")

        # Validate input and prepare scenario generation
        self._validate_and_prepare_scenario_generation(app_def_scenario, example_scenarios)

        # Get available apps and initialize history tracking
        available_apps = self._get_available_apps()

        logger.info(f"Available apps: {available_apps}")
        logger.info(
            f"Generating {total_scenarios} scenarios with {apps_per_scenario} apps each (plus PASAgentUserInterface and HomeScreenSystemApp)"
        )

        # If explicit selection is provided (via --scale), bypass combination agent and reuse the same set every time
        if selected_apps:
            # Sanitize/validate provided apps against available apps
            selected_set = {app for app in selected_apps if app in available_apps}
            missing = [app for app in selected_apps if app not in available_apps]
            if missing:
                logger.warning(
                    f"Some requested apps are not available and will be ignored: {sorted(missing)}; available={sorted(available_apps)}"
                )

            # Ensure we always have exactly the provided set (AgentUserInterface and SystemApp are auto-included later)
            if not selected_set:
                logger.error("No valid apps provided via --scale; falling back to combination agent selection")
                use_scale_mode = False
            else:
                use_scale_mode = True
                all_app_combinations = [frozenset(selected_set)] * max(1, total_scenarios)
                # Summaries not driven by app_combination_agent in scale mode; create simple placeholders
                all_summaries = [f"Scenario focusing on apps: {', '.join(sorted(selected_set))}"] * len(
                    all_app_combinations
                )
        else:
            use_scale_mode = False

        # Otherwise, use intelligent reasoning to generate combinations
        if not use_scale_mode:
            # Build app tools info for the combination agent
            app_tools_info = defaultdict(list)
            for tool in self.tools:
                app_name = tool.name.split("__")[0]
                if app_name not in {"PASAgentUserInterface", "HomeScreenSystemApp"}:  # Exclude PAS AUI and System
                    app_tools_info[app_name].append(tool)

            logger.info("==== Generating all app combinations at once ====")
            all_app_combinations, all_summaries = self.app_combination_agent.generate_all_app_combinations(
                available_apps=available_apps,
                total_scenarios=total_scenarios,
                apps_per_scenario=apps_per_scenario,
                app_tools_info=dict(app_tools_info),
                example_scenarios=example_scenarios,
            )

        # Log the summaries for debugging
        logger.info("Generated scenario summaries:")
        for i, summary in enumerate(all_summaries, 1):
            logger.info(f"  Summary {i}: {summary}")

        if len(all_app_combinations) < total_scenarios:
            logger.warning(
                f"Only generated {len(all_app_combinations)} combinations, but {total_scenarios} were requested"
            )

        logger.info(f"Generated {len(all_app_combinations)} distinct app combinations:")
        for i, combo in enumerate(all_app_combinations, 1):
            logger.info(f"  Combination {i}: {sorted(combo)}")

        generated_scenarios = []

        # Generate scenarios using the pre-generated combinations
        for scenario_num, selected_combo in enumerate(all_app_combinations[:total_scenarios]):
            logger.info(f"==== Generating scenario {scenario_num + 1}/{total_scenarios} ====")
            logger.info(f"Using app combination: {sorted(selected_combo)}")

            # Get the corresponding scenario summary
            scenario_summary = all_summaries[scenario_num] if scenario_num < len(all_summaries) else None
            if scenario_summary:
                logger.info(f"Scenario guidance: {scenario_summary}")

            # Get tools for selected apps
            selected_tools = self._get_tools_for_apps(selected_combo)

            # Generate import instructions for selected apps only
            selected_import_instructions = self._generate_import_instructions_for_selected_apps(selected_combo)
            logger.info(f"Selected import instructions: {selected_import_instructions}")

            # Temporarily replace self.tools with selected tools
            original_tools = self.tools.copy()
            self.tools = selected_tools

            try:
                # Setup system prompt with selected tools and selected import instructions
                # Track selected apps for validation/prompt scoping
                self._current_selected_apps = set(selected_combo)
                system_prompt = self._setup_system_prompt(selected_import_instructions)
                # IMPORTANT: Use the same selected-only import instructions for validation
                original_import_instructions = self.import_instructions
                self.import_instructions = selected_import_instructions
                seed_task = self._create_seed_task_from_scenarios(example_scenarios, scenario_summary)
                self.messages = self._create_initial_messages(system_prompt, seed_task)

                # Run generation iterations
                _, written_path = self._run_generation_iterations()

                if written_path:
                    generated_scenarios.append(str(written_path))
                    logger.info(f"Successfully generated scenario {scenario_num + 1}: {written_path}")
                else:
                    logger.warning(f"Failed to generate scenario {scenario_num + 1}")

            finally:
                # Restore original tools
                self.tools = original_tools
                self._current_selected_apps = set()
                # Restore original import instructions
                try:
                    self.import_instructions = original_import_instructions
                except Exception:
                    pass

        # Prepare output message
        if generated_scenarios:
            out = f"Generated {len(generated_scenarios)} scenarios:\n" + "\n".join(
                f"- {path}" for path in generated_scenarios
            )
        else:
            out = "No scenarios were successfully generated"

        return AgentExecutionResult(output=out)

    def _parse_from_import(self, s: str) -> tuple[str, list[str]]:
        """Parse 'from mod import A, B as C' statement and return (module, [symbols])."""
        try:
            parts = s.split()
            mod = parts[1]
            after_import = s.split(" import ", 1)[1]
            symbols = [tok.strip() for tok in after_import.split(",")]
            # remove aliases
            symbols = [sym.split(" as ")[0].strip() for sym in symbols]
        except Exception as e:
            logger.warning(f"Failed to parse import statement '{s}': {e}")
            return "", []
        else:
            return mod, symbols

    def _parse_import_statement(self, s: str) -> list[str]:
        """Parse 'import mod, mod2' statement and return [modules]."""
        try:
            after = s[len("import ") :]
            modules = [tok.strip() for tok in after.split(",")]
        except Exception as e:
            logger.warning(f"Failed to parse import statement '{s}': {e}")
            return []
        else:
            return modules

    def _validate_from_import(self, s: str, instructions: str) -> list[str]:
        """Validate a 'from ... import ...' statement against instructions."""
        problems: list[str] = []
        mod, symbols = self._parse_from_import(s)
        if not mod or not symbols:
            return problems

        for sym in symbols:
            token = f"from {mod} import {sym}"
            if token not in instructions:
                problems.append(f"Missing allowed import in instructions: '{token}'")
        return problems

    def _validate_import_statement(self, s: str, instructions: str) -> list[str]:
        """Validate an 'import ...' statement against instructions."""
        problems: list[str] = []
        modules = self._parse_import_statement(s)
        for mod in modules:
            token = f"import {mod}"
            if token not in instructions:
                problems.append(f"Missing allowed import in instructions: '{token}'")
        return problems

    def _fix_scenario_naming_issues(self, code_text: str) -> str:
        """Fix scenario naming issues by removing 'scenario_' prefix from decorators, class names, and content."""
        lines = code_text.split("\n")
        fixed_lines = []

        for line in lines:
            # Fix @register_scenario decorator
            if "@register_scenario(" in line:
                # Extract the scenario ID and remove 'scenario_' prefix if present
                import re

                match = re.search(r'@register_scenario\(["\'"]([^"\'"]+)["\'"]\)', line)
                if match:
                    scenario_id = match.group(1)
                    if scenario_id.startswith("scenario_"):
                        scenario_id = scenario_id[9:]  # Remove "scenario_" prefix (9 characters)
                        fixed_line = line.replace(match.group(1), scenario_id)
                        fixed_lines.append(fixed_line)
                        logger.info(f"Fixed scenario ID: {match.group(1)} -> {scenario_id}")
                        continue

            # Fix class names that start with "Scenario" - remove the "Scenario" prefix entirely
            if line.strip().startswith("class Scenario"):
                import re

                class_match = re.search(r"class\s+(Scenario\w+)", line)
                if class_match:
                    class_name = class_match.group(1)
                    # Remove "Scenario" prefix (8 characters) from class name
                    scenario_part = class_name[8:]  # Remove "Scenario" prefix (8 characters)
                    fixed_class_name = scenario_part
                    fixed_line = line.replace(class_name, fixed_class_name)
                    fixed_lines.append(fixed_line)
                    logger.info(f"Fixed class name: {class_name} -> {fixed_class_name}")
                    continue

            fixed_lines.append(line)

        return "\n".join(fixed_lines)

    def _fix_generated_file_linting_issues(self, code_text: str) -> str:
        """Fix common linting issues in generated code, specifically 'true'/'false' vs 'True'/'False'."""
        lines = code_text.split("\n")
        fixed_lines = []

        for line in lines:
            # Skip import lines entirely
            if line.strip().startswith("import ") or line.strip().startswith("from "):
                fixed_lines.append(line)
                continue

            # For non-import lines, replace 'true' and 'false' with 'True' and 'False'
            # But be careful not to replace them in comments or strings
            if "true" in line.lower() or "false" in line.lower():
                # Simple approach: replace 'false' with 'False' and 'true' with 'True'
                # This is safe for most cases since these are boolean literals
                fixed_line = line.replace("false", "False").replace("true", "True")
                fixed_lines.append(fixed_line)
            else:
                fixed_lines.append(line)

        return "\n".join(fixed_lines)

    def _validate_syntax(self, code_text: str) -> list[str]:
        """Validate Python syntax by attempting to compile the code."""
        problems: list[str] = []

        try:
            # Try to compile the code to catch syntax errors
            compile(code_text, "<generated_scenario>", "exec")
        except SyntaxError as e:
            problems.append(f"Syntax error at line {e.lineno}: {e.msg}")
        except Exception as e:
            # Catch other compilation errors
            problems.append(f"Compilation error: {e}")

        return problems

    def _validate_generated_file(self, code_text: str) -> list[str]:
        """Validate the generated file content for various issues."""
        problems: list[str] = []

        # Validate syntax
        problems.extend(self._validate_syntax(code_text))

        return problems

    def _validate_comprehensive_tool_usage(self, code_text: str) -> list[str]:
        """Validate app usage across the generated scenario (non-blocking).

        Loosened requirement: It is acceptable if some initialized/available apps are not used.
        This validator now only logs which apps appear to be used versus unused and does not
        enforce usage by returning blocking problems.
        """
        problems: list[str] = []

        # Get all available apps and their tools from the current tools
        available_apps: dict[str, list[str]] = {}
        for tool in self.tools:
            app_name = tool.name.split("__")[0]
            if app_name not in available_apps:
                available_apps[app_name] = []
            available_apps[app_name].append(tool.name)

        logger.info(f"Available apps: {len(available_apps)} - {sorted(available_apps.keys())}")

        # Find all tool calls in the generated code
        used_apps = set()
        lines = code_text.split("\n")

        # More specific tool usage detection - look for actual method calls
        for line in lines:
            line = line.strip()
            # Skip comments, imports, and variable declarations
            if (
                line.startswith("#")
                or line.startswith("import")
                or line.startswith("from")
                or ("=" in line and "(" not in line)
            ):  # Skip variable assignments without method calls
                continue

            # Look for actual method calls using the specific tool format
            for app_name, app_tools in available_apps.items():
                for tool_name in app_tools:
                    # Extract the method part (e.g., "send_email" from "EmailClientApp__send_email")
                    if "__" in tool_name:
                        method_name = tool_name.split("__")[1]
                        # Look for specific method calls like "app.method(" or "var.method("
                        if f".{method_name}(" in line or (method_name in line and "(" in line):
                            used_apps.add(app_name)
                            logger.info(f"Found usage of app {app_name} via tool: {tool_name} in line: {line[:100]}...")

                    # Also check for direct usage of the tool name in method calls
                    elif tool_name in line and "(" in line:
                        used_apps.add(app_name)
                        logger.info(f"Found usage of app {app_name} via tool: {tool_name} in line: {line[:100]}...")

                    # Check for variable usage that matches app patterns
                    # This handles cases where variables are used instead of direct class references
                    elif any(
                        var_pattern in line
                        for var_pattern in [
                            "aui",
                            "email",
                            "messaging",
                            "calendar",
                            "contacts",
                            "fs",
                            "app",
                            "client",
                            "system",
                        ]
                    ):
                        # Check if this line contains method calls that match available tools
                        if (
                            "(" in line
                            and (
                                ".send_" in line
                                or ".get_" in line
                                or ".add_" in line
                                or ".create_" in line
                                or ".list_" in line
                                or ".search_" in line
                                or ".delete_" in line
                                or ".move_" in line
                                or ".read_" in line
                                or "send_message" in line
                                or "add_calendar_event" in line
                                or "add_contact" in line
                                or "send_email" in line
                            )
                            and "__" in tool_name
                        ):
                            available_method = tool_name.split("__")[1]
                            if available_method in line or f".{available_method}(" in line:
                                used_apps.add(app_name)
                                logger.info(
                                    f"Found usage of app {app_name} via tool: {tool_name} in line: {line[:100]}..."
                                )

        logger.info(f"Used apps: {len(used_apps)} - {sorted(used_apps)}")

        # Report usage summary without enforcing problems
        unused_apps = set(available_apps.keys()) - used_apps
        try:
            logger.info(
                "App usage summary (non-blocking): %d/%d apps used. Unused: %s",
                len(used_apps),
                len(available_apps),
                ", ".join(sorted(unused_apps)) if unused_apps else "(none)",
            )
        except Exception:
            pass

        # Do not block generation based on usage; return no problems
        return []

    def _validate_proactive_interaction_pattern(self, code_text: str) -> list[str]:
        """Validate that the generated scenario includes the mandatory proactive interaction pattern."""
        problems: list[str] = []

        # Look for the required components of the proactive interaction pattern:
        # 1. Agent proposes action: aui.send_message_to_user(content="[proposal with question]")
        # 2. User responds: aui.accept_proposal(...) or aui.reject_proposal(...) (or legacy aui.send_message_to_agent(...))
        # 3. Agent executes the proposed action based on user approval

        lines = code_text.split("\n")

        # Find agent proposal (send_message_to_user with question)
        agent_proposal_found = False
        user_response_found = False

        for i, line in enumerate(lines):
            line = line.strip()

            # Check for agent proposal pattern
            if "send_message_to_user" in line:
                agent_proposal_found = True
                logger.info(f"Found agent proposal in line {i + 1}: {line[:100]}...")

            # Check for user response pattern (accept/reject or legacy send_message_to_agent)
            if ("accept_proposal" in line or "reject_proposal" in line or "send_message_to_agent" in line) and (
                "yes" in line.lower()
                or "approve" in line.lower()
                or "confirm" in line.lower()
                or "please" in line.lower()
                or "go ahead" in line.lower()
                or "sure" in line.lower()
            ):
                user_response_found = True
                logger.info(f"Found user response in line {i + 1}: {line[:100]}...")

            # Also check for the pattern in multi-line format
            elif (
                "accept_proposal" in line or "reject_proposal" in line or "send_message_to_agent" in line
            ) and i < len(lines) - 1:
                # Check the next few lines for response content
                for j in range(i + 1, min(i + 3, len(lines))):
                    next_line = lines[j].strip()
                    if (
                        "yes" in next_line.lower()
                        or "approve" in next_line.lower()
                        or "confirm" in next_line.lower()
                        or "please" in next_line.lower()
                        or "go ahead" in next_line.lower()
                        or "sure" in next_line.lower()
                    ):
                        user_response_found = True
                        logger.info(f"Found user response in lines {i + 1}-{j + 1}: {line[:50]}... {next_line[:50]}...")
                        break

        # Report missing components
        if not agent_proposal_found:
            problems.append(
                "MISSING: Agent proposal pattern - The scenario must include aui.send_message_to_user() with a question/proposal"
            )

        if not user_response_found:
            problems.append(
                "MISSING: User response pattern - The scenario must include aui.accept_proposal()/reject_proposal() "
                "with meaningful, contextual approval response (legacy aui.send_message_to_agent also accepted)"
            )

        if not (agent_proposal_found and user_response_found):
            problems.append("CRITICAL: The scenario MUST include the complete proactive interaction pattern:")
            problems.append(
                "  1. Agent proposes action: aui.send_message_to_user(content='[specific proposal with question]')"
            )
            problems.append(
                "  2. User responds: aui.accept_proposal(content='[meaningful approval like \"Yes, please share it with Jordan\"]')"
            )
            problems.append("  3. Agent executes the proposed action based on user approval")
            problems.append("This pattern should be central to the scenario's workflow, not just a minor interaction.")

        return problems

    def _get_available_apps(self) -> list[str]:
        """Get list of available app names from tool_dict, excluding AgentUserInterface and SystemApp."""
        available_apps = []
        for tool in self.tools:
            app_name = tool.name.split("__")[0]
            if app_name not in {"PASAgentUserInterface", "HomeScreenSystemApp"} and app_name not in available_apps:
                available_apps.append(app_name)
        return available_apps

    def _select_app_combination(
        self,
        available_apps: list[str],
        apps_per_scenario: int,
        history_combinations: set[frozenset[str]],
        example_scenarios: list[Scenario] | None = None,
    ) -> frozenset[str]:
        """Select a unique combination of apps for scenario generation using intelligent reasoning."""
        # Build app tools info for the combination agent
        app_tools_info = defaultdict(list)
        for tool in self.tools:
            app_name = tool.name.split("__")[0]
            if app_name not in {
                "PASAgentUserInterface",
                "HomeScreenSystemApp",
            }:  # Exclude PAS AUI and PAS SystemApp from the tools info
                app_tools_info[app_name].append(tool)

        # Use the intelligent app combination agent
        return self.app_combination_agent.select_app_combination(
            available_apps=available_apps,
            apps_per_scenario=apps_per_scenario,
            history_combinations=history_combinations,
            app_tools_info=dict(app_tools_info),
            example_scenarios=example_scenarios,
        )

    def _get_tools_for_apps(self, selected_apps: frozenset[str]) -> list[Tool]:
        """Get tools for the selected app combination (including AgentUserInterface and SystemApp)."""
        selected_tools = []

        # Always include PASAgentUserInterface and HomeScreenSystemApp tools
        for tool in self.tools:
            if tool.name.startswith("PASAgentUserInterface__") or tool.name.startswith("HomeScreenSystemApp__"):
                selected_tools.append(tool)

        # Add tools for selected apps
        for tool in self.tools:
            app_name = tool.name.split("__")[0]
            if app_name in selected_apps:
                selected_tools.append(tool)

        logger.info(
            f"Selected {len(selected_tools)} tools for apps: PASAgentUserInterface + HomeScreenSystemApp + {sorted(selected_apps)}"
        )
        return selected_tools

    def _generate_import_instructions_for_selected_apps(self, selected_apps: frozenset[str]) -> str:
        """Generate import instructions that only include the selected apps and their dependencies."""
        # Always include PASAgentUserInterface and HomeScreenSystemApp
        apps_to_import = {"PASAgentUserInterface", "HomeScreenSystemApp"} | selected_apps

        # Generate import instructions for only the selected apps
        from pas.scenario_generator.utils.list_all_app_imports import make_import_instructions, scan_package

        # Get the catalog for all apps but filter to only selected ones
        catalog = scan_package("pas.apps", include_sigs=True, doclen=140)

        # Filter catalog to only include selected apps - maintain the list structure
        filtered_modules = []
        for module_info in catalog.get("modules", []):
            # Check if this module contains any of our selected apps
            module_classes = [cls["name"] for cls in module_info.get("exports", {}).get("classes", [])]
            if any(app in module_classes for app in apps_to_import):
                filtered_modules.append(module_info)

        # Create filtered catalog with the same structure as the original
        filtered_catalog = {
            "package": catalog.get("package", ""),
            "scanned_at": catalog.get("scanned_at", ""),
            "root_paths": catalog.get("root_paths", []),
            "modules": filtered_modules,
            "import_suggestions": catalog.get("import_suggestions", []),
        }

        # Generate import instructions for filtered catalog
        import_instructions = make_import_instructions(
            filtered_catalog,
            max_mods=len(apps_to_import) + 2,  # Limit to selected apps + some buffer
            max_per_mod=10,
            include_sigs=True,
        )

        # Add basic scenario imports that are always needed
        basic_imports = [
            "from are.simulation.scenarios.scenario import Scenario, ScenarioValidationResult",
            "from are.simulation.scenarios.utils.registry import register_scenario",
            "from are.simulation.types import AbstractEnvironment, EventRegisterer, EventType",
            "from typing import Any",
        ]

        # Combine basic imports with app-specific imports, avoiding duplicates
        missing_basics = [line for line in basic_imports if line not in import_instructions]
        prefix = "\n".join(missing_basics)
        full_import_instructions = (prefix + ("\n\n" if prefix else "")) + import_instructions

        # Ensure per-symbol tokens exist for validator (it checks 'from X import Y' individually)
        # Even if a combined import exists, add single-symbol forms so validation passes.
        per_symbol_required = [
            "from are.simulation.scenarios.scenario import Scenario",
            "from are.simulation.scenarios.scenario import ScenarioValidationResult",
            "from are.simulation.scenarios.utils.registry import register_scenario",
            "from are.simulation.types import AbstractEnvironment",
            "from are.simulation.types import EventRegisterer",
            "from are.simulation.types import EventType",
        ]
        for token in per_symbol_required:
            if token not in full_import_instructions:
                full_import_instructions = token + "\n" + full_import_instructions

        logger.info(f"Generated import instructions for selected apps: {sorted(apps_to_import)}")
        return full_import_instructions

    def _validate_mock_run(self, code_text: str) -> list[str]:
        """Validate that the generated scenario passes mock run validation."""
        problems: list[str] = []

        # First, validate comprehensive tool usage
        tool_usage_problems = self._validate_comprehensive_tool_usage(code_text)
        problems.extend(tool_usage_problems)

        # Extract scenario ID from the generated code
        sid_match = re.search(r"@register_scenario\(\s*['\"]([^'\"]+)['\"]\s*\)", code_text)
        if not sid_match:
            problems.append("Could not find scenario ID in generated code")
            return problems

        scenario_id = sid_match.group(1).strip()
        logger.info(f"Starting mock run validation for scenario: {scenario_id}")
        logger.info(f"Full regex match: {sid_match.group(0)}")
        logger.info(f"Extracted scenario_id: '{scenario_id}'")

        # Log the scenario ID that was generated
        logger.info(f"Generated scenario_id: '{scenario_id}'")

        try:
            # Write the code to a temporary file for testing
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code_text)
                temp_file_path = f.name
            logger.info(f"Created temporary file for validation: {temp_file_path}")

            try:
                # Import the temporary file to register the scenario class
                logger.info("Creating module spec for temporary scenario file")
                spec = importlib.util.spec_from_file_location("temp_scenario", temp_file_path)

                if spec is None:
                    problems.append(f"spec_from_file_location returned None for file: {temp_file_path}")
                    logger.error(f"spec_from_file_location returned None for file: {temp_file_path}")
                    return problems

                if spec.loader is None:
                    problems.append(f"spec.loader is None for file: {temp_file_path}")
                    logger.error(f"spec.loader is None for file: {temp_file_path}")
                    return problems

                logger.info(f"Module spec created successfully: {spec.name}")

                # Create and execute the module to trigger @register_scenario decorators
                logger.info("Creating module from spec")
                temp_module = importlib.util.module_from_spec(spec)

                # Ensure the module has a proper __name__ attribute
                temp_module.__name__ = spec.name
                logger.info(f"Module name set to: {temp_module.__name__}")

                # Ensure the module is registered in sys.modules before execution
                import sys

                sys.modules[spec.name] = temp_module
                logger.info(f"Module registered in sys.modules: {spec.name}")

                logger.info("Executing module to register scenario")
                try:
                    spec.loader.exec_module(temp_module)
                    logger.info(f"Successfully imported and registered temporary scenario: {scenario_id}")

                    # Log module info after execution
                    logger.info(f"Module __name__ after execution: {getattr(temp_module, '__name__', 'MISSING')}")
                    logger.info(f"Module __file__ after execution: {getattr(temp_module, '__file__', 'MISSING')}")

                    # Check if scenario class was created and has proper module
                    scenario_class_name = f"Scenario{scenario_id.replace('_', '').title()}"
                    if hasattr(temp_module, scenario_class_name):
                        scenario_class = getattr(temp_module, scenario_class_name)
                        logger.info(f"Scenario class found: {scenario_class}")
                        logger.info(f"Scenario class __module__: {getattr(scenario_class, '__module__', 'MISSING')}")
                        logger.info(f"Scenario class MRO: {[cls.__name__ for cls in scenario_class.__mro__]}")

                except AttributeError as e:
                    if "'NoneType' object has no attribute '__dict__'" in str(e):
                        logger.exception("Module execution failed with NoneType __dict__ error")
                        logger.exception(f"Module __name__: {getattr(temp_module, '__name__', 'MISSING')}")
                        logger.exception(
                            f"sys.modules keys around temp_scenario: {[k for k in sys.modules if 'temp' in k.lower()]}"
                        )

                        # Try to identify which class is causing the issue
                        import inspect

                        source_lines = inspect.getsourcelines(temp_module)
                        logger.exception(f"Module source (first 50 lines):\n{''.join(source_lines[0][:50])}")

                        raise  # Re-raise to maintain original error
                    else:
                        raise  # Re-raise other AttributeErrors

                # Run the mock scenario command with temporary file
                cmd = [
                    "python",
                    "pas/scenario_generator/utils/run_scenario.py",
                    "-s",
                    scenario_id,
                    "-a",
                    "default",
                    "--provider",
                    "mock",
                    "--temp-file",
                    temp_file_path,
                ]
                logger.info(f"Running mock scenario command: {' '.join(cmd)}")
                logger.info(
                    f"Command breakdown: script={cmd[0]}, scenario_id={cmd[2]}, agent={cmd[4]}, provider={cmd[6]}, temp_file={cmd[8]}"
                )

                try:
                    logger.info("Starting subprocess for mock run")
                    result = subprocess.run(  # noqa: S603
                        cmd,
                        cwd=os.getcwd(),
                        capture_output=True,
                        text=True,
                        timeout=30,  # 60 second timeout
                    )

                    logger.info(f"Subprocess completed with return code: {result.returncode}")

                    # Log detailed subprocess output for debugging
                    if result.returncode != 0:
                        logger.error("Mock run subprocess failed - detailed output:")
                        logger.error(f"STDOUT: {result.stdout}")
                        logger.error(f"STDERR: {result.stderr}")

                        # Parse error type from output
                        error_type = self._parse_error_type(result.stdout)
                        if error_type:
                            logger.error(f"Detected error type: {error_type}")

                        # Add detailed error information to problems
                        if result.stderr:
                            problems.append(f"Subprocess error: {result.stderr}")
                        if "ERROR_TYPE:" in result.stdout:
                            problems.append(f"Error type detected in output: {result.stdout}")
                    else:
                        logger.info("Mock run subprocess succeeded")

                    # Safely access stdout and stderr
                    stdout = result.stdout if result.stdout is not None else ""
                    stderr = result.stderr if result.stderr is not None else ""
                    output = stdout + stderr

                    logger.info(f"Mock run output length: {len(output)} characters")
                    if result.returncode != 0:
                        logger.warning(f"Mock run failed with return code {result.returncode}")
                    if stderr:
                        logger.warning(f"Mock run stderr: {stderr[:]}...")  # First 200 chars

                except Exception as e:
                    logger.error(f"Mock run subprocess failed: {e}", exc_info=True)

                    # Try to read error details from runtime_error files
                    error_dir = "/Users/jasonz/Projects/ucsb/proactiveGoalInference/runtime_error"
                    if os.path.exists(error_dir):
                        # Find the most recent error file
                        error_files = glob.glob(os.path.join(error_dir, "scenario_error_*.txt"))
                        if error_files:
                            # Sort by modification time (newest first)
                            error_files.sort(key=os.path.getmtime, reverse=True)
                            latest_error_file = error_files[0]

                            try:
                                with open(latest_error_file) as f:
                                    error_content = f.read()

                                logger.info(f"Found error file: {latest_error_file}")
                                logger.info(f"Error content:\n{error_content}")

                                # Parse the error content to extract useful information
                                parsed_issues = self._parse_error_log_file(error_content)

                                # Add all parsed issues to problems for the agent to use
                                problems.extend(parsed_issues)

                                # Clean up the error file after reading
                                try:
                                    os.remove(latest_error_file)
                                    logger.info(f"Cleaned up error file: {latest_error_file}")
                                except OSError:
                                    pass  # File might already be deleted

                            except Exception as file_error:
                                logger.warning(f"Could not read error file {latest_error_file}: {file_error}")

                    return problems

                # Check for required validation strings
                has_validation_result = "Result: ScenarioValidationResult" in output
                has_mock_response = (
                    "Good choice, this is a mock, so I can't do anything. Let's return the result." in output
                )

                logger.info(
                    f"Validation check - has_validation_result: {has_validation_result}, has_mock_response: {has_mock_response}"
                )

                # If both validation strings are present, mock run was successful
                if has_validation_result and has_mock_response:
                    logger.info(f"Mock run validation passed for scenario: {scenario_id}")
                    return []  # Return empty problems list - validation passed

                # If either validation string is missing, validation failed
                if not has_validation_result:
                    problems.append("Mock run did not produce 'Result: ScenarioValidationResult' in output")
                    logger.error("Mock run did not produce 'Result: ScenarioValidationResult' in output")
                    # Include first 500 chars of output for debugging
                    problems.append(f"Mock run output (first 500 chars): {output[:500]}...")

                if not has_mock_response:
                    problems.append("Mock run did not produce expected mock response")
                    logger.error("Mock run did not produce expected mock response")
                    # Include first 500 chars of output for debugging
                    problems.append(f"Mock run output (first 500 chars): {output[:500]}...")

                if result.returncode != 0:
                    problems.append(f"Mock run failed with return code {result.returncode}")
                    logger.error(f"Mock run failed with return code {result.returncode}")
                    if stderr:  # Use stderr variable instead of result.stderr
                        problems.append(f"Mock run stderr: {stderr}")

            finally:
                # Clean up temporary file
                logger.info(f"Cleaning up temporary file: {temp_file_path}")
                try:
                    os.unlink(temp_file_path)
                    logger.info("Temporary file cleaned up successfully")
                except OSError as e:
                    logger.warning(f"Failed to clean up temporary file {temp_file_path}: {e}")

        except Exception as e:
            import traceback

            error_details = f"Failed to validate mock run: {e}"
            error_traceback = traceback.format_exc()
            problems.append(error_details)
            logger.exception(f"{error_details}\nFull traceback:\n{error_traceback}")

        return problems

    def _parse_error_log_file(self, error_content: str) -> list[str]:
        """Parse error log file content and extract useful information for the agent.

        Args:
            error_content: The full content of the error log file

        Returns:
            List of formatted issue strings that can be used in repair prompts
        """
        issues = []

        # Extract the main error details
        error_details_match = re.search(r"Error Details:\s*(.+?)(?=\n\n|$)", error_content, re.DOTALL)
        if error_details_match:
            error_details = error_details_match.group(1).strip()
            issues.append(f"Runtime Error: {error_details}")

        # Extract error type
        error_type_match = re.search(r"Error Type:\s*(.+)", error_content)
        if error_type_match:
            error_type = error_type_match.group(1).strip()
            issues.append(f"Error Type: {error_type}")

        # Extract scenario name
        scenario_match = re.search(r"Scenario:\s*(.+)", error_content)
        if scenario_match:
            scenario_name = scenario_match.group(1).strip()
            issues.append(f"Scenario: {scenario_name}")

        # Extract the specific AttributeError details
        attribute_error_match = re.search(r"'(.+?)' object has no attribute '(.+?)'", error_content)
        if attribute_error_match:
            object_type = attribute_error_match.group(1)
            missing_method = attribute_error_match.group(2)
            issues.append(
                f"Missing Method: {object_type}.{missing_method}() - this method doesn't exist on the {object_type} object"
            )

            # Provide helpful suggestions based on common calendar methods
            if object_type == "CalendarApp" and missing_method == "create_event":
                issues.append(
                    "Suggestion: Check available CalendarApp methods. Common alternatives: schedule_event, add_event, create_appointment, or use a different calendar import"
                )

        # Extract traceback information for context
        traceback_match = re.search(r'File "[^"]+", line (\d+), in (\w+)', error_content)
        if traceback_match:
            line_number = traceback_match.group(1)
            method_name = traceback_match.group(2)
            issues.append(f"Error occurred at line {line_number} in method '{method_name}'")

        # Extract the main exception type from traceback
        main_exception_match = re.search(r"(\w+Error): (.+)", error_content)
        if main_exception_match:
            exception_type = main_exception_match.group(1)
            exception_message = main_exception_match.group(2)
            issues.append(f"Exception: {exception_type} - {exception_message}")

        # If no specific issues were extracted, add the raw error as fallback
        if not issues:
            issues.append(f"Runtime Error Details: {error_content[:200]}...")

        return issues

    def _parse_error_type(self, output: str) -> str | None:
        """Parse error type from subprocess output."""
        if not output:
            return None

        # Look for ERROR_TYPE markers in the output
        lines = output.split("\n")
        for line in lines:
            if line.startswith("ERROR_TYPE:"):
                return line.strip()
        return None

    def _validate_imports(self, code_text: str) -> list[str]:
        problems: list[str] = []
        instructions = self.import_instructions or ""
        if not instructions:
            return problems  # nothing to validate against

        has_import = False

        for raw in code_text.splitlines():
            s = raw.strip()
            if not s or s.startswith("#"):
                continue
            if s.startswith("from ") and " import " in s:
                has_import = True
                problems.extend(self._validate_from_import(s, instructions))
            elif s.startswith("import "):
                has_import = True
                problems.extend(self._validate_import_statement(s, instructions))

        if not has_import:
            problems.append(
                "No import found in the code, need to import the tools at the beginning of the file. from the INSTRUSTIONS TO IMPORT AVAILABLE TOOLS."
            )
        return problems

    def _tokens_from_text(self, text: str) -> list[str]:
        """Extract identifiers and keywords from text."""
        return re.findall(r"[A-Za-z_][A-Za-z_0-9]*", text)

    def _shingles(self, tokens: list[str], k: int = 3) -> set[str]:
        """Generate k-gram token shingles from a list of tokens."""
        if len(tokens) < k:
            return {" ".join(tokens)} if tokens else set()
        return {" ".join(tokens[i : i + k]) for i in range(len(tokens) - k + 1)}

    def _jaccard(self, a: set[str], b: set[str]) -> float:
        """Calculate Jaccard similarity between two sets."""
        if not a and not b:
            return 1.0
        inter = len(a & b)
        union = len(a | b) or 1
        return inter / union

    def _cosine_counter(self, ca: Counter[str], cb: Counter[str]) -> float:
        """Calculate cosine similarity between two Counter objects."""
        if not ca and not cb:
            return 1.0
        keys = set(ca) | set(cb)
        dot = sum(ca[k] * cb[k] for k in keys)
        na = sum(v * v for v in ca.values()) ** 0.5
        nb = sum(v * v for v in cb.values()) ** 0.5
        return 0.0 if na == 0 or nb == 0 else dot / (na * nb)

    def _normalize_text(self, text: str) -> str:
        """Normalize text by collapsing whitespace."""
        return re.sub(r"\s+", " ", text).strip()

    def _compare_summaries(self, summary1: str, summary2: str, k: int = 3) -> dict[str, float | int]:
        """Compare two summaries using multiple similarity metrics."""
        s1 = self._normalize_text(summary1)
        s2 = self._normalize_text(summary2)

        # Metric 1: difflib
        sm_ratio = difflib.SequenceMatcher(a=s1, b=s2, autojunk=False).ratio()

        # Metric 2: Jaccard over token shingles
        toks1, toks2 = self._tokens_from_text(s1), self._tokens_from_text(s2)
        sh1, sh2 = self._shingles(toks1, k=k), self._shingles(toks2, k=k)
        jac = self._jaccard(sh1, sh2)

        # Metric 3: Cosine over token frequency
        c1, c2 = Counter(toks1), Counter(toks2)
        cos = self._cosine_counter(c1, c2)

        return {
            "difflib_ratio": sm_ratio,
            "jaccard_shingles": jac,
            "cosine_tokens": cos,
            "len_tokens_1": len(toks1),
            "len_tokens_2": len(toks2),
        }

    def _load_scenario_summaries(self) -> dict[str, str]:
        """Load scenario summaries from JSON file if it exists.

        Returns:
            Dictionary mapping scenario IDs to summaries
        """
        target_dir = Path(__file__).resolve().parents[2] / "scenarios" / "generated_scenarios_w_pas_apps"
        summaries_path = target_dir / "scenario_summaries.json"

        if summaries_path.exists():
            try:
                with open(summaries_path, encoding="utf-8") as f:
                    summaries = json.load(f)
                    logger.info(f"Loaded {len(summaries)} scenario summaries from {summaries_path}")
                    return summaries
            except Exception as e:
                logger.warning(f"Failed to load scenario summaries from {summaries_path}: {e}")
                return {}
        else:
            logger.info(f"Scenario summaries file not found at {summaries_path}")
            return {}

    def _validate_similarity_against_existing_scenario_summary(self, code_text: str) -> list[str]:
        """Validate that the generated scenario summary is not too similar to existing scenario summaries.

        Args:
            code_text: The generated scenario code as a string

        Returns:
            List of issues if similarity is too high with any existing scenario summary
        """
        problems: list[str] = []

        # Extract the scenario ID from the generated code
        new_scenario_id_match = re.search(r"@register_scenario\(\s*['\"]([^'\"]+)['\"]\s*\)", code_text)
        new_scenario_id = new_scenario_id_match.group(1).strip() if new_scenario_id_match else None

        if not new_scenario_id:
            logger.warning("Could not extract scenario ID from generated code, skipping summary-based validation")
            return problems

        # Load existing summaries
        existing_summaries = self._load_scenario_summaries()

        if not existing_summaries:
            logger.info("No existing scenario summaries found for comparison")
            return problems

        # Remove the current scenario from existing summaries if it exists
        if new_scenario_id in existing_summaries:
            existing_summaries = {k: v for k, v in existing_summaries.items() if k != new_scenario_id}

        if not existing_summaries:
            logger.info("No other existing scenario summaries found for comparison")
            return problems

        logger.info(f"Found {len(existing_summaries)} existing scenario summaries to compare against")

        # Generate summary for the new scenario code
        try:
            summary_agent = SummaryGeneratingAgent(self.llm_engine)
            new_summary = summary_agent.generate_summary(code_text)

            if not new_summary:
                logger.warning("Failed to generate summary for new scenario, skipping summary-based validation")
                return problems

            logger.info(f"Generated summary for new scenario '{new_scenario_id}': {new_summary[:100]}...")

        except Exception:
            logger.exception("Error generating summary for new scenario")
            return problems

        # Thresholds (matching the code-based validation)
        # Tighten thresholds slightly to reduce near-duplicate summaries
        difflib_threshold = 0.7
        jaccard_threshold = 0.7
        cosine_threshold = 0.8
        k = 3

        # Compare against each existing summary
        for existing_scenario_id, existing_summary in existing_summaries.items():
            logger.info(f"Comparing summary with existing scenario '{existing_scenario_id}'")

            try:
                scores = self._compare_summaries(new_summary, existing_summary, k=k)

                logger.info(
                    f"Comparison with '{existing_scenario_id}': "
                    f"difflib_ratio={scores['difflib_ratio']:.4f}, "
                    f"jaccard_shingles={scores['jaccard_shingles']:.4f}, "
                    f"cosine_tokens={scores['cosine_tokens']:.4f}"
                )

                # Check if any metric exceeds its threshold
                is_duplicate = (
                    scores["difflib_ratio"] >= difflib_threshold
                    or scores["jaccard_shingles"] >= jaccard_threshold
                    or scores["cosine_tokens"] >= cosine_threshold
                )

                if is_duplicate:
                    logger.warning(
                        f"Found duplicate scenario summary! Similarity scores with '{existing_scenario_id}':"
                    )
                    logger.warning(f"  difflib_ratio: {scores['difflib_ratio']:.4f} (threshold: {difflib_threshold})")
                    logger.warning(
                        f"  jaccard_shingles: {scores['jaccard_shingles']:.4f} (threshold: {jaccard_threshold})"
                    )
                    logger.warning(f"  cosine_tokens: {scores['cosine_tokens']:.4f} (threshold: {cosine_threshold})")

                    # Build error message similar to code-based validation
                    error_msg = (
                        f"Generated scenario is too similar to existing scenario '{existing_scenario_id}'. "
                        f"Similarity scores with different thresholds (higher = more similar):\n"
                        f"• difflib_ratio={scores['difflib_ratio']:.4f} (threshold: {difflib_threshold} - structural/sequential similarity)\n"
                        f"• jaccard_shingles={scores['jaccard_shingles']:.4f} (threshold: {jaccard_threshold} - pattern similarity)\n"
                        f"• cosine_tokens={scores['cosine_tokens']:.4f} (threshold: {cosine_threshold} - vocabulary similarity)\n\n"
                    )

                    # Add existing scenario summary for context
                    error_msg += f"Existing similar scenario summary:\n{existing_summary}\n\n"

                    error_msg += (
                        "Please generate a scenario with different content, structure, identifiers, event flow, and app usage patterns. "
                        "Focus on changing: variable names, email subjects, event titles, registry IDs, sequence of events, "
                        "and avoid copying similar code patterns, token combinations, or structural elements."
                    )

                    problems.append(error_msg)
                    break  # No need to check other scenarios once we find a duplicate

                else:
                    logger.info(f"Comparison with '{existing_scenario_id}' completed successfully (not a duplicate)")

            except Exception as e:
                logger.exception(f"Error comparing with existing scenario '{existing_scenario_id}'")
                problems.append(f"Error during similarity comparison with '{existing_scenario_id}': {e}")

        # If no problems found, persist the new scenario summary
        if not problems and new_scenario_id and new_summary:
            try:
                self._save_scenario_summary(new_scenario_id, new_summary)
            except Exception:
                logger.exception("Failed to save scenario summary")

        return problems

    def _save_scenario_summary(self, scenario_id: str, summary: str) -> None:
        """Save or update the summary for a scenario in the PAS summaries JSON."""
        try:
            import json
            from pathlib import Path

            summaries_dir = Path(__file__).resolve().parents[2] / "scenarios" / "generated_scenarios_w_pas_apps"
            summaries_dir.mkdir(parents=True, exist_ok=True)
            summaries_path = summaries_dir / "scenario_summaries.json"

            existing: dict[str, str] = {}
            if summaries_path.exists():
                try:
                    existing = json.loads(summaries_path.read_text(encoding="utf-8"))
                except Exception:
                    existing = {}

            existing[scenario_id] = summary
            with open(summaries_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved summary for scenario '{scenario_id}' to {summaries_path}")
        except Exception as e:
            logger.warning(f"Could not save summary for scenario '{scenario_id}': {e}")

    def _validate_similarity_against_existing(self, code_text: str) -> list[str]:
        """Validate that the generated scenario is not too similar to existing scenarios.

        Args:
            code_text: The generated scenario code as a string

        Returns:
            List of issues if similarity is too high with any existing scenario
        """
        problems: list[str] = []

        # Get the target directory for generated scenarios
        target_dir = Path(__file__).resolve().parents[2] / "scenarios" / "generated_scenarios_w_pas_apps"

        if not target_dir.exists():
            logger.info(f"Generated scenarios directory does not exist: {target_dir}")
            return problems

        # Get all existing scenario files (excluding __pycache__ and non-python files)
        existing_scenarios = [
            f for f in target_dir.glob("*.py") if f.is_file() and not f.name.startswith("__") and f.name.endswith(".py")
        ]

        # Extract the scenario ID from the generated code to avoid comparing with itself
        # if it was written in a previous iteration
        new_scenario_id_match = re.search(r"@register_scenario\(\s*['\"]([^'\"]+)['\"]\s*\)", code_text)
        new_scenario_id = new_scenario_id_match.group(1).strip() if new_scenario_id_match else None

        if new_scenario_id:
            # Filter out the file that would be generated for this scenario ID
            existing_scenarios = [f for f in existing_scenarios if not f.name.startswith(f"{new_scenario_id}.py")]

        if not existing_scenarios:
            logger.info("No existing scenarios found for similarity comparison")
            return problems

        logger.info(f"Found {len(existing_scenarios)} existing scenarios to compare against")
        if new_scenario_id:
            excluded_files = [
                f
                for f in target_dir.glob("*.py")
                if f.is_file()
                and not f.name.startswith("__")
                and f.name.endswith(".py")
                and f.name.startswith(f"{new_scenario_id}.py")
            ]
            if excluded_files:
                logger.info(f"Excluding self-generated file: {excluded_files[0].name}")

        # Create a temporary file for the new scenario
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code_text)
            temp_file_path = f.name

        try:
            # Compare against each existing scenario
            for existing_scenario in existing_scenarios:
                logger.info(f"Comparing with existing scenario: {existing_scenario.name}")

                try:
                    # Run the deduplicate script to get all similarity scores
                    cmd = [
                        "python",
                        "pas/scenario_generator/utils/deduplicate_scenarios.py",
                        str(existing_scenario),
                        temp_file_path,
                        "--threshold",
                        "1.0",  # Set high to get all scores without early exit
                        "--metric",
                        "max",
                        "--k",
                        "3",
                    ]

                    result = subprocess.run(cmd, cwd=os.getcwd(), capture_output=True, text=True, timeout=30)  # noqa: S603

                    # Always get scores (since we set threshold to 1.0, it won't exit early)
                    similarity_output = result.stdout + result.stderr

                    # Extract similarity scores
                    difflib_match = re.search(r"difflib_ratio\s*:\s*([0-9.]+)", similarity_output)
                    jaccard_match = re.search(r"jaccard_shingles:\s*([0-9.]+)", similarity_output)
                    cosine_match = re.search(r"cosine_tokens\s*:\s*([0-9.]+)", similarity_output)

                    difflib_score = float(difflib_match.group(1)) if difflib_match else 0.0
                    jaccard_score = float(jaccard_match.group(1)) if jaccard_match else 0.0
                    cosine_score = float(cosine_match.group(1)) if cosine_match else 0.0

                    # Apply different thresholds for different metrics
                    difflib_threshold = 0.8
                    jaccard_threshold = 0.8
                    cosine_threshold = 0.94

                    # Check if any score exceeds its respective threshold
                    is_duplicate = (
                        difflib_score >= difflib_threshold
                        or jaccard_score >= jaccard_threshold
                        or cosine_score >= cosine_threshold
                    )

                    if is_duplicate:
                        logger.warning(f"Found duplicate scenario! Similarity scores with {existing_scenario.name}:")
                        logger.warning(f"  difflib_ratio: {difflib_score:.4f} (threshold: {difflib_threshold})")
                        logger.warning(f"  jaccard_shingles: {jaccard_score:.4f} (threshold: {jaccard_threshold})")
                        logger.warning(f"  cosine_tokens: {cosine_score:.4f} (threshold: {cosine_threshold})")

                        # Read the existing scenario code for context
                        try:
                            existing_code = existing_scenario.read_text(encoding="utf-8")

                            problems.append(
                                f"Generated scenario is too similar to existing scenario '{existing_scenario.name}'. "
                                f"Similarity scores with different thresholds (higher = more similar):\n"
                                f"• difflib_ratio={difflib_score:.4f} (threshold: {difflib_threshold} - structural/sequential similarity)\n"
                                f"• jaccard_shingles={jaccard_score:.4f} (threshold: {jaccard_threshold} - pattern similarity)\n"
                                f"• cosine_tokens={cosine_score:.4f} (threshold: {cosine_threshold} - vocabulary similarity)\n\n"
                                f"Existing similar scenario code:\n```python\n{existing_code}\n```\n\n"
                                "Please generate a scenario with different content, structure, identifiers, event flow, and app usage patterns. "
                                "Focus on changing: variable names, email subjects, event titles, registry IDs, sequence of events, "
                                "and avoid copying similar code patterns, token combinations, or structural elements."
                            )
                        except Exception as e:
                            logger.warning(f"Could not read existing scenario code: {e}")
                            problems.append(
                                f"Generated scenario is too similar to existing scenario '{existing_scenario.name}'. "
                                f"Similarity scores with different thresholds (higher = more similar):\n"
                                f"• difflib_ratio={difflib_score:.4f} (threshold: {difflib_threshold} - structural/sequential similarity)\n"
                                f"• jaccard_shingles={jaccard_score:.4f} (threshold: {jaccard_threshold} - pattern similarity)\n"
                                f"• cosine_tokens={cosine_score:.4f} (threshold: {cosine_threshold} - vocabulary similarity)\n\n"
                                "Please generate a scenario with different content, structure, identifiers, event flow, and app usage patterns. "
                                "Focus on changing: variable names, email subjects, event titles, registry IDs, sequence of events, "
                                "and avoid copying similar code patterns, token combinations, or structural elements."
                            )
                        break  # No need to check other scenarios once we find a duplicate

                    else:
                        logger.info(
                            f"Comparison with {existing_scenario.name} completed successfully (not a duplicate)"
                        )

                except subprocess.TimeoutExpired:
                    logger.warning(f"Similarity comparison with {existing_scenario.name} timed out")
                    problems.append(f"Similarity comparison with {existing_scenario.name} timed out")
                except Exception as e:
                    logger.exception(f"Error comparing with {existing_scenario.name}")
                    problems.append(f"Error during similarity comparison with {existing_scenario.name}: {e}")

        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_file_path)
                logger.info("Cleaned up temporary file for similarity comparison")
            except OSError as e:
                logger.warning(f"Failed to clean up temporary file {temp_file_path}: {e}")

        return problems
