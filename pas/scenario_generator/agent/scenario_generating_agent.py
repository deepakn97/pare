import glob
import importlib.util
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

from pas.scenario_generator.prompt import DEFAULT_SCENARIO_GENERATOR_SYSTEM_PROMPT
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
        max_iterations: int = 3,
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

        self.system_prompt = str(DEFAULT_SCENARIO_GENERATOR_SYSTEM_PROMPT)
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
        system_prompt = str(DEFAULT_SCENARIO_GENERATOR_SYSTEM_PROMPT)
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

    def _run_generation_iterations(self) -> tuple[str | None, Path | None]:  # noqa: C901
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

            # Fix common linting issues first
            logger.info("==== Fixing linting issues ====")
            code_text = self._fix_generated_file_linting_issues(code_text)

            # Validate imports against provided instructions
            issues = self._validate_imports(code_text)

            # Validate generated file for syntax and other issues
            logger.info("==== Validating generated file ====")
            validation_issues = self._validate_generated_file(code_text)
            issues.extend(validation_issues)

            # Validate similarity against existing scenarios if no other issues
            if not issues:
                logger.info("==== Validating similarity against existing scenarios ====")
                similarity_issues = self._validate_similarity_against_existing(code_text)
                issues.extend(similarity_issues)

            # # Validate mock run if no other issues
            # if not issues:
            #     logger.info("==== Validating mock run ====")
            #     mock_validation_issues = self._validate_mock_run(code_text)
            #     issues.extend(mock_validation_issues)
            #     if issues:
            #         logger.info(f"==== Mock run validation issues: {issues} ====")

            if not issues:
                if issues:
                    logger.info(f"==== Issues: {issues} ====")
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

    def _validate_mock_run(self, code_text: str) -> list[str]:  # noqa: C901
        """Validate that the generated scenario passes mock run validation."""
        problems: list[str] = []

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

    def _validate_similarity_against_existing(self, code_text: str) -> list[str]:  # noqa: C901
        """Validate that the generated scenario is not too similar to existing scenarios.

        Args:
            code_text: The generated scenario code as a string

        Returns:
            List of issues if similarity is too high with any existing scenario
        """
        problems: list[str] = []

        # Get the target directory for generated scenarios
        target_dir = Path(__file__).resolve().parents[2] / "scenarios" / "generated_scenarios"

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
                    difflib_threshold = 0.85
                    jaccard_threshold = 0.8
                    cosine_threshold = 0.93

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
