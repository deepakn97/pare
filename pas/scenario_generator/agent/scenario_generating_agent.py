import logging
import re
import time
from datetime import UTC, datetime
from inspect import getsource
from pathlib import Path
from typing import TYPE_CHECKING

from are.simulation.agents.agent_execution_result import AgentExecutionResult
from are.simulation.agents.default_agent.base_agent import BaseAgentLog
from are.simulation.agents.default_agent.default_tools import Tool
from are.simulation.agents.llm.llm_engine import LLMEngine
from are.simulation.scenarios import Scenario

if TYPE_CHECKING:
    from are.simulation.apps import AgentUserInterface
from are.simulation.tool_box import DEFAULT_TOOL_DESCRIPTION_TEMPLATE, Toolbox
from are.simulation.tool_utils import AppTool, AppToolAdapter

from pas.scenario_generator.prompt import DEFAULT_ARE_SIMULATION_SCENARIO_GENERATOR_AGENT_REACT_JSON_SYSTEM_PROMPT
from pas.scenario_generator.prompt.scenario_generator_prompts import (
    DEFAULT_SCENARIO_GENERATOR_REPAIR_SYSTEM_PROMPT,
    DEFAULT_SCENARIO_GENERATOR_REPAIR_SYSTEM_PROMPT_WITH_INSTRUCTIONS,
    SEED_TASK_WITH_EXAMPLES_BASE,
    create_repair_note,
)

logger = logging.getLogger(__name__)


class AgentStoppedException(Exception):
    """Exception raised when the scenario generating agent is stopped."""

    pass


class ScenarioGeneratingAgent:
    """Agent for generating new scenarios based on example scenarios."""

    def __init__(
        self,
        llm_engine: LLMEngine,
        tools: list[Tool] | None = None,
        max_iterations: int = 1,
        import_instructions: str = "",
    ) -> None:
        """Initialize the scenario generating agent.

        Args:
            llm_engine: The LLM engine to use for scenario generation
            tools: Optional list of tools to use
            max_iterations: Maximum number of generation iterations
            import_instructions: Instructions for valid imports
        """
        self.llm_engine = llm_engine
        self.max_iterations = max_iterations
        self.tools = tools or []
        self._initialized = False
        self.import_instructions = import_instructions

    # ===== Minimal helpers to set up tools and prompts from an example scenario =====

    def remove_aui_irrelevant_tools(self, app_tools: list[AppTool]) -> list[AppTool]:
        """Remove AgentUserInterface tools that are not relevant for scenario generation."""
        try:
            aui_tool = next(tool for tool in app_tools if "AgentUserInterface" in tool.name)
        except StopIteration:
            return app_tools

        if aui_tool is not None:
            aui: AgentUserInterface = aui_tool.class_instance
            # Ensure the agent does not block on user responses in this generation context
            logger.warning("Setting wait_for_user_response to False in AgentUserInterface")
            aui.wait_for_user_response = False

            tools_to_remove = {
                "AgentUserInterface__get_last_message_from_user",
                "AgentUserInterface__get_last_message_from_agent",
                "AgentUserInterface__get_last_unread_messages",
                "AgentUserInterface__get_all_messages",
            }
            logger.warning(f"Removing tools {tools_to_remove} from app_tools")
            app_tools = [tool for tool in app_tools if tool.name not in tools_to_remove]
        return app_tools

    def init_tools(self, example_scenario: Scenario) -> None:
        """Initialize tools from an example scenario."""
        app_tools = example_scenario.get_tools()
        logger.info(f"Found {len(app_tools)} tools: {[tool.name for tool in app_tools]}")
        app_tools = self.remove_aui_irrelevant_tools(app_tools)
        are_simulation_tools = [AppToolAdapter(tool) for tool in app_tools]
        self.tools += are_simulation_tools
        logger.info(f"Tools: {self.tools}")

    def init_system_prompt(self, example_scenario: Scenario) -> None:
        """Initialize the system prompt from an example scenario."""
        # Minimal prompt post-processing: set current time and clear agent reminder placeholder if present
        try:
            date_str = datetime.fromtimestamp(example_scenario.start_time or 0, tz=UTC).strftime("%Y-%m-%d %H")
        except Exception:
            date_str = datetime.fromtimestamp(0, tz=UTC).strftime("%Y-%m-%d %H")

        self.system_prompt = str(DEFAULT_ARE_SIMULATION_SCENARIO_GENERATOR_AGENT_REACT_JSON_SYSTEM_PROMPT)
        self.system_prompt = self.system_prompt.replace(
            "<<curent_time_description>>", f"Today's date in 'YYYY-MM-DD HH' format is {date_str}"
        ).replace("<<agent_reminder_description>>", "")

    def _validate_and_prepare_scenario_generation(self, example_scenarios: list[Scenario]) -> Scenario:
        """Validate input and return the first scenario for setup."""
        if example_scenarios is None or len(example_scenarios) == 0:
            raise ValueError("At least one example scenario is required")

        first = example_scenarios[0]
        self.init_tools(first)
        return first

    def _setup_system_prompt(self, first_scenario: Scenario) -> str:
        """Build and return the system prompt with tool descriptions and import instructions."""
        system_prompt = getattr(self, "system_prompt", "")
        toolbox = Toolbox(tools=self.tools)
        tool_descriptions = toolbox.show_tool_descriptions(DEFAULT_TOOL_DESCRIPTION_TEMPLATE)
        if isinstance(system_prompt, str):
            system_prompt = system_prompt.replace("<<tool_descriptions>>", tool_descriptions)

        # build system prompt with import instructions
        if isinstance(system_prompt, str):
            system_prompt = system_prompt.replace("<<import_instructions>>", self.import_instructions)

        # Basic current-time replacement
        try:
            date_str = datetime.fromtimestamp(first_scenario.start_time or 0, tz=UTC).strftime("%Y-%m-%d %H")
        except Exception:
            date_str = datetime.fromtimestamp(0, tz=UTC).strftime("%Y-%m-%d %H")
        system_prompt = system_prompt.replace(
            "<<curent_time_description>>", f"Today's date in 'YYYY-MM-DD HH' format is {date_str}"
        ).replace("<<agent_reminder_description>>", "")

        return system_prompt

    def _create_seed_task_from_scenarios(self, example_scenarios: list[Scenario]) -> str:
        """Create the seed task message from example scenarios."""
        code_blocks = []
        for i, sc in enumerate(example_scenarios, start=1):
            try:
                src = getsource(sc.__class__)
            except Exception:
                src = ""
            code_blocks.append(f"Example {i}:\n```python\n{src}\n```")

        return SEED_TASK_WITH_EXAMPLES_BASE.format(example_code_blocks="\n\n".join(code_blocks))

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

            # Validate imports against provided instructions
            issues = self._validate_imports(code_text)
            if not issues or it == self.max_iterations - 1:
                logger.info("==== Writing file ====")
                logger.info("==== max iterations reached ====")
                try:
                    written_path = self._write_generated_scenario(code_text)
                    break
                except Exception as e:
                    issues = [f"Failed to write file: {e}"]
                    previous_code = code_text
                    continue
            else:
                logger.info(f"==== Iteration {it} has issues, continue and try again ====")
                previous_code = code_text
                continue

        return previous_code, written_path

    def _write_generated_scenario(self, code_text: str) -> Path:
        """Write the generated scenario to a file and return the path."""
        sid_match = re.search(r"@register_scenario\(\s*['\"]([^'\"]+)['\"]\s*\)", code_text)
        if sid_match:
            scenario_id = sid_match.group(1).strip()
            file_name = f"{scenario_id}_scenario.py"
        else:
            class_match = re.search(r"class\s+(\w+)\s*\(", code_text)
            base = class_match.group(1) if class_match else f"generated_{int(time.time())}"
            file_name = f"{base.lower()}_scenario.py"

        target_dir = Path(__file__).resolve().parents[2] / "scenarios" / "generated_scenarios"
        target_dir.mkdir(parents=True, exist_ok=True)
        written_path = target_dir / file_name
        written_path.write_text(code_text, encoding="utf-8")
        return written_path

    # ===== Core minimal run for scenario generation =====

    def scenario_generation_run(
        self, example_scenarios: list[Scenario], initial_agent_logs: list[BaseAgentLog] | None = None
    ) -> AgentExecutionResult:
        """Minimal scenario generation without depending on BaseAgent internals.

        - Set tools and prompt from the first example scenario
        - Build a system prompt including AVAILABLE TOOLS
        - Seed with one or more example scenario source codes
        - Single LLM call that outputs a fenced python code block
        - Write the block to are/simulation/scenarios/generated_scenarios
        """
        # Validate input and prepare first scenario
        first_scenario = self._validate_and_prepare_scenario_generation(example_scenarios)

        # Setup system prompt and create initial messages
        system_prompt = self._setup_system_prompt(first_scenario)
        seed_task = self._create_seed_task_from_scenarios(example_scenarios)
        self.messages = self._create_initial_messages(system_prompt, seed_task)

        # Run generation iterations
        _, written_path = self._run_generation_iterations()

        out = f"Scenario generated: {written_path}" if written_path else "Scenario generation attempted"
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
