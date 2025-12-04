from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pas.scenario_generator.prompt.multi_step_scenario_generating_agent_prompts import (
    configure_dynamic_context,
)

from .claude_backend import ClaudeAgentRuntimeConfig, ClaudeFilesystemConfig
from .scenario_uniqueness_agent import ScenarioUniquenessCheckAgent
from .step_agents import AppsAndDataSetupAgent, EventsFlowAgent, ScenarioDescriptionAgent, StepResult, ValidationAgent

logger = logging.getLogger(__name__)


@dataclass
class RunCheckResult:
    """Summary of a single scenario run used to gate multi-step progress."""

    passed: bool
    feedback: str
    runtime_error: bool
    validation_reached: bool
    validation_success: bool


class MultiStepScenarioGeneratingAgentsOrchestrator:
    """Coordinates the dedicated step agents to build a proactive scenario."""

    def __init__(
        self,
        *,
        output_dir: str | Path | None = None,
        max_iterations: int = 3,
        prompt_context: dict[str, str] | None = None,
        debug_prompts: bool = False,
        resume_from_step2: bool = False,
        resume_from_step: str | None = None,
        claude_filesystem_config: ClaudeFilesystemConfig | None = None,
    ) -> None:
        """Initialize the orchestrator and supporting step agents."""
        self.max_iterations = max_iterations
        self.debug_prompts = debug_prompts
        # Backwards compatibility: boolean resume_from_step2 maps to "step2" unless
        # an explicit resume_from_step value is provided.
        self.resume_from_step = resume_from_step or ("step2" if resume_from_step2 else None)
        base_dir = Path(__file__).resolve().parents[2]
        self.repo_root = base_dir.parent
        self.output_dir = Path(output_dir or base_dir / "generated_scenarios")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # Use the editable_seed_scenario-based working file so Claude Agent can
        # repeatedly edit a single, stable filename. The original seed template
        # remains read-only for reference.
        self.scenario_file = self.output_dir / "editable_seed_scenario.py"
        self.generated_dir = base_dir / "generated_scenarios"
        self.valid_descriptions_path = self.generated_dir / "valid_descriptions.json"
        self.success_dir = self.generated_dir / "successful_scenarios"
        self.failed_dir = self.generated_dir / "failed_scenarios"
        self.failed_no_runtime_dir = self.generated_dir / "failed_scenarios_no_runtime_errors"
        self.success_dir.mkdir(parents=True, exist_ok=True)
        self.failed_dir.mkdir(parents=True, exist_ok=True)
        self.failed_no_runtime_dir.mkdir(parents=True, exist_ok=True)
        self._last_check_result: RunCheckResult | None = None
        # Declarative filesystem policy for Claude Agent SDK usage. Enforcement
        # will be wired via hooks and tool options in a follow-up change.
        if claude_filesystem_config is None:
            self.claude_filesystem_config = ClaudeFilesystemConfig(
                read_only_roots=[self.repo_root],
                editable_files=[self.scenario_file],
            )
        else:
            self.claude_filesystem_config = claude_filesystem_config
        self._historical_descriptions = self._read_valid_descriptions()

        # Per-step Claude runtime configurations. Narrative and uniqueness
        # checks do not need code-editing tools, while Steps 2-4 use Read/Write
        # to modify the seed_scenario file.
        self._claude_config_uniqueness = ClaudeAgentRuntimeConfig(
            cwd=self.repo_root,
            allowed_tools=["Read"],
            permission_mode="acceptEdits",
            filesystem=self.claude_filesystem_config,
        )
        self._claude_config_step1 = ClaudeAgentRuntimeConfig(
            cwd=self.repo_root,
            allowed_tools=["Read"],
            permission_mode="acceptEdits",
            filesystem=self.claude_filesystem_config,
        )
        self._claude_config_code_steps = ClaudeAgentRuntimeConfig(
            cwd=self.repo_root,
            allowed_tools=["Read", "Write"],
            permission_mode="acceptEdits",
            filesystem=self.claude_filesystem_config,
        )

        if prompt_context is not None:
            configure_dynamic_context(**prompt_context)

        if self.debug_prompts:
            logger.info(
                "Debug prompts mode enabled for multi-step scenario generator; "
                "all Claude calls will be skipped. Prompts and planned "
                "file operations will be logged instead.",
            )

        # Use the canonical original seed template with explicit start/end markers
        # so we can safely strip any natural-language preamble/epilogue that Claude
        # might emit around the template body.
        self.seed_template_path = base_dir / "example_proactive_scenarios" / "original_seed_scenario.py"
        self.seed_template_text = self._safe_read_text(self.seed_template_path)

        if self.debug_prompts:
            logger.info("Scenario working file: %s", self.scenario_file)
            logger.info("Seed template path: %s", self.seed_template_path)
            logger.info("Valid descriptions path: %s", self.valid_descriptions_path)
            logger.info(
                "Claude filesystem config: read_only_roots=%s, editable_files=%s",
                self.claude_filesystem_config.read_only_roots,
                self.claude_filesystem_config.editable_files,
            )
            if prompt_context is not None:
                logger.info("Selected apps for this run: %s", prompt_context.get("selected_apps", "(unknown)"))

        self.uniqueness_agent = ScenarioUniquenessCheckAgent(
            historical_descriptions=self._historical_descriptions,
            debug_prompts=debug_prompts,
            debug_printer=self._debug_print if debug_prompts else None,
            claude_runtime_config=self._claude_config_uniqueness,
        )
        self.step1_agent = ScenarioDescriptionAgent(
            max_iterations=max_iterations,
            uniqueness_agent=self.uniqueness_agent,
            debug_prompts=debug_prompts,
            debug_printer=self._debug_print if debug_prompts else None,
            claude_runtime_config=self._claude_config_step1,
        )
        self.step2_agent = AppsAndDataSetupAgent(
            max_iterations=max_iterations,
            debug_prompts=debug_prompts,
            debug_printer=self._debug_print if debug_prompts else None,
            claude_runtime_config=self._claude_config_code_steps,
        )
        self.step3_agent = EventsFlowAgent(
            max_iterations=max_iterations,
            debug_prompts=debug_prompts,
            debug_printer=self._debug_print if debug_prompts else None,
            claude_runtime_config=self._claude_config_code_steps,
        )
        self.step4_agent = ValidationAgent(
            max_iterations=max_iterations,
            debug_prompts=debug_prompts,
            debug_printer=self._debug_print if debug_prompts else None,
            claude_runtime_config=self._claude_config_code_steps,
        )

    def run(self) -> dict[str, Any]:  # noqa: C901
        """Execute the four-step pipeline and return artifact metadata."""
        logger.info("Starting multi-step scenario generation.")

        try:
            step1_path = self.output_dir / "step1_scenario_description.md"

            resume_mode = self.resume_from_step

            if resume_mode in {"step2", "step3", "step4"} and not self.debug_prompts:
                step1 = self._load_existing_step1_result(step1_path)
            else:

                def step1_check(description: str, iteration: int) -> tuple[bool, str]:
                    # Intentionally do NOT write any new files for Step 1.
                    # Step 1 is allowed to affect only `valid_descriptions.json`.
                    return True, ""

                check1 = None if self.debug_prompts else step1_check

                history_block = self.uniqueness_agent.get_recent_history()
                step1 = self.step1_agent.run(
                    historical_descriptions=history_block,
                    check_callback=check1,
                )
                logger.info("Step 1 completed with %s iterations.", step1.iterations)
                if not self.debug_prompts:
                    self._append_valid_description(step1.content)

            # Step 2: Apps & Data Setup
            if resume_mode in {"step3", "step4"} and not self.debug_prompts:
                logger.info("Resuming from %s: skipping Step 2 generation.", resume_mode)
                scenario_seed_content = self._safe_read_text(self.scenario_file)
                scenario_after_step2 = scenario_seed_content
                step2 = StepResult(
                    name="Step 2: Apps & Data Setup (resumed)",
                    content=scenario_seed_content,
                    iterations=0,
                    notes={"resumed_from_disk": True},
                    conversation=[],
                )
            else:
                # Always start each multi-step run from the pristine seed template, so that
                # Step 2 is constrained to edit only its designated regions.
                if not self.debug_prompts and self.seed_template_text:
                    self.scenario_file.write_text(self.seed_template_text, encoding="utf-8")
                    scenario_seed_content = self.seed_template_text
                else:
                    scenario_seed_content = self._get_or_initialize_scenario_file()

                def step2_check(code: str, iteration: int) -> tuple[bool, str]:
                    # Guardrail: ensure Validation agent returns the full scenario file,
                    # not just a natural-language explanation of checks.
                    if not self._looks_like_complete_scenario(code):
                        feedback = (
                            "[validation-check] Your previous reply did not look like a "
                            "complete Python scenario file. Reply with ONLY the full "
                            "updated file contents between the existing "
                            '"""start of the template to build scenario for Proactive Agent.""" '
                            'and """end of the template to build scenario for Proactive Agent.""" '
                            "markers, with no natural-language explanation or markdown."
                        )
                        return False, feedback

                    self._write_output(
                        content=code,
                        path=self.scenario_file,
                        header="Step 2 - init_and_populate_apps plan",
                        append=False,
                        include_header=False,
                    )
                    result = self._run_step_check("apps-data-check", self.scenario_file)
                    return result.passed, result.feedback

                check2 = None if self.debug_prompts else step2_check

                step2 = self.step2_agent.run(
                    scenario_description=step1.content,
                    scenario_file_path=str(self.scenario_file),
                    scenario_file_contents=scenario_seed_content,
                    check_callback=check2,
                )
                logger.info("Step 2 completed with %s iterations.", step2.iterations)

                scenario_after_step2 = (
                    self._debug_placeholder_content("scenario_after_step2", step2.content)
                    if self.debug_prompts
                    else self._safe_read_text(self.scenario_file)
                )

                # Snapshot the scenario after Step 2 completes successfully.
                if not self.debug_prompts:
                    self._snapshot_scenario("step2")

            # Step 3: Events Flow
            if resume_mode == "step4" and not self.debug_prompts:
                logger.info("Resuming from step4: skipping Step 3 generation.")
                scenario_after_step3 = self._safe_read_text(self.scenario_file)
                step3 = StepResult(
                    name="Step 3: Events Flow (resumed)",
                    content=scenario_after_step3,
                    iterations=0,
                    notes={"resumed_from_disk": True},
                    conversation=[],
                )
            else:

                def step3_check(code: str, iteration: int) -> tuple[bool, str]:
                    # Guardrail: don't let natural-language thoughts clobber the
                    # scenario file. Ensure the response looks like a full scenario.
                    if not self._looks_like_complete_scenario(code):
                        feedback = (
                            "[events-flow-check] Your previous reply did not look like a "
                            "complete Python scenario file. Reply with ONLY the full "
                            "updated file contents between the existing "
                            '"""start of the template to build scenario for Proactive Agent.""" '
                            'and """end of the template to build scenario for Proactive Agent.""" '
                            "markers, with no natural-language explanation or markdown."
                        )
                        return False, feedback

                    self._write_output(
                        content=code,
                        path=self.scenario_file,
                        header="Step 3 - build_events_flow outline",
                        append=False,
                        include_header=False,
                    )
                    result = self._run_step_check("events-flow-check", self.scenario_file)
                    return result.passed, result.feedback

                check3 = None if self.debug_prompts else step3_check

                step3 = self.step3_agent.run(
                    scenario_description=step1.content,
                    apps_and_data=step2.content,
                    scenario_file_contents=scenario_after_step2,
                    check_callback=check3,
                )
                logger.info("Step 3 completed with %s iterations.", step3.iterations)

                scenario_after_step3 = (
                    self._debug_placeholder_content("scenario_after_step3", step3.content)
                    if self.debug_prompts
                    else self._safe_read_text(self.scenario_file)
                )

                # Snapshot the scenario after Step 3 completes successfully.
                if not self.debug_prompts:
                    self._snapshot_scenario("step3")

            def step4_check(code: str, iteration: int) -> tuple[bool, str]:
                # Guardrail: ensure Validation agent returns the full scenario file,
                # not just a natural-language explanation of checks.
                if not self._looks_like_complete_scenario(code):
                    feedback = (
                        "[validation-check] Your previous reply did not look like a "
                        "complete Python scenario file. Reply with ONLY the full "
                        "updated file contents between the existing "
                        '"""start of the template to build scenario for Proactive Agent.""" '
                        'and """end of the template to build scenario for Proactive Agent.""" '
                        "markers, with no natural-language explanation or markdown."
                    )
                    return False, feedback

                self._write_output(
                    content=code,
                    path=self.scenario_file,
                    header="Step 4 - validate() expectations",
                    append=False,
                    include_header=False,
                )
                result = self._run_step_check(
                    "validation-check",
                    self.scenario_file,
                    require_validation_success=True,
                )
                return result.passed, result.feedback

            check4 = None if self.debug_prompts else step4_check

            step4 = self.step4_agent.run(
                scenario_description=step1.content,
                events_flow=step3.content,
                scenario_file_contents=scenario_after_step3,
                check_callback=check4,
            )
            logger.info("Step 4 completed with %s iterations.", step4.iterations)

            if not self.debug_prompts:
                self._persist_scenario(self.success_dir)

            logger.info("Multi-step scenario generation pipeline complete.")
            return {
                "description_path": str(self.valid_descriptions_path),
                "scenario_file_path": str(self.scenario_file),
                "steps": [
                    step1,
                    step2,
                    step3,
                    step4,
                ],
            }
        except Exception as exc:
            logger.exception("Multi-step generation failed")
            runtime_error = True
            validation_reached = False
            if self._last_check_result is not None:
                runtime_error = self._last_check_result.runtime_error or not self._last_check_result.validation_reached
                validation_reached = self._last_check_result.validation_reached
            self._persist_failed_scenario(str(exc), runtime_error=runtime_error, validation_reached=validation_reached)
            raise

    def _write_output(
        self,
        *,
        content: str,
        path: Path,
        header: str,
        append: bool,
        include_header: bool = True,
    ) -> None:
        """Persist model output to disk, inserting lightweight headers for traceability."""
        path.parent.mkdir(parents=True, exist_ok=True)
        normalized = content.strip()

        # For the working scenario file, defensively strip any natural-language
        # preamble or epilogue that might have been emitted around the template.
        if path == self.scenario_file:
            normalized = self._strip_outside_template_markers(normalized)

        if include_header:
            block = f"# {header}\n{normalized}\n"
            text_to_write = block
            if append and path.exists():
                text_to_write = "\n\n" + block
        else:
            text_to_write = f"{normalized}\n"
            append = False

        if append:
            with path.open("a", encoding="utf-8") as file:
                file.write(text_to_write)
        else:
            path.write_text(text_to_write, encoding="utf-8")

    @staticmethod
    def _strip_outside_template_markers(text: str) -> str:
        """Keep only the portion of the file between the template start/end markers.

        This allows Claude to think "out loud" in its response while ensuring that
        the persisted Python file remains importable by trimming any prose that
        appears before or after the canonical template body.
        """
        start_marker = '"""start of the template to build scenario for Proactive Agent."""'
        end_marker = '"""end of the template to build scenario for Proactive Agent."""'

        lines = text.splitlines()
        start_idx: int | None = None
        end_idx: int | None = None

        for idx, line in enumerate(lines):
            if start_marker in line and start_idx is None:
                start_idx = idx
            if end_marker in line:
                end_idx = idx

        if start_idx is not None and end_idx is not None and start_idx <= end_idx:
            kept = lines[start_idx : end_idx + 1]
            return "\n".join(kept).strip()

        # Fallback: if markers are missing (e.g., older templates), leave text as-is.
        return text

    @staticmethod
    def _looks_like_complete_scenario(text: str) -> bool:
        """Heuristic check that a Claude reply is a full scenario file, not just prose."""
        stripped = text.strip()
        if not stripped:
            return False

        # Require our template markers and a register_scenario decorator as signs
        # that the model is returning an edited scenario, not only analysis.
        has_start = '"""start of the template to build scenario for Proactive Agent."""' in stripped
        has_end = '"""end of the template to build scenario for Proactive Agent."""' in stripped
        has_register = "@register_scenario(" in stripped
        return has_start and has_end and has_register

    def _snapshot_scenario(self, step_label: str) -> None:
        """Save a point-in-time copy of the editable seed scenario after a step.

        For example, after Step 2 and Step 3 complete successfully we capture
        `editable_seed_scenario_step2.py` and `editable_seed_scenario_step3.py`
        so users can inspect or resume from those artifacts if needed.
        """
        try:
            import shutil

            snapshot_name = f"editable_seed_scenario_{step_label}.py"
            snapshot_path = self.output_dir / snapshot_name
            shutil.copy2(self.scenario_file, snapshot_path)
            logger.info("Snapshot for %s written to %s", step_label, snapshot_path)
        except Exception:  # pragma: no cover - snapshot failures are non-fatal
            logger.exception("Failed to snapshot scenario after %s", step_label)

    def _load_existing_step1_result(self, step1_path: Path) -> StepResult:
        """Load a previously generated Step 1 description from disk.

        This is used when resuming the pipeline from Step 2 after fixing issues
        downstream, so we can reuse the narrative without re-running the LLM.
        """
        # Prefer the legacy markdown path if present and non-empty (backward compatible),
        # otherwise fall back to the most recent entry in `valid_descriptions.json`.
        raw = self._safe_read_text(step1_path)
        description: str | None = None
        if raw.strip():
            lines = raw.splitlines()
            # Drop header/comment lines (e.g., "# Step 1 - Scenario Description")
            content_lines = [line for line in lines if not line.lstrip().startswith("#")]
            candidate = "\n".join(content_lines).strip()
            if candidate:
                description = candidate
        if description is None:
            history = self._read_valid_descriptions()
            if history:
                last = history[-1]
                candidate = (last.get("description") or "").strip()
                if candidate:
                    description = candidate
        if not description:
            raise RuntimeError(
                "Cannot resume from Step 2: missing markdown and no valid description found in valid_descriptions.json"
            )

        return StepResult(
            name="Step 1: Scenario Description (resumed)",
            content=description,
            iterations=0,
            notes={
                "resumed_from_disk": True,
                "source_path": str(step1_path),
            },
            conversation=[],
        )

    def _run_step_check(
        self,
        label: str,
        artifact_path: Path,
        require_validation_success: bool = False,
    ) -> RunCheckResult:
        """Run the generated scenario via `run_scenario.py` and summarize the result.

        This helper is the canonical integration point between the Claude-backed
        step agents (which edit the scenario file) and the meta-ARE runner,
        which validates that the scenario can be imported, executed, and passes
        its `validate()` checks.
        """
        code = self._safe_read_text(artifact_path)
        scenario_id = self._extract_scenario_id(code)
        if scenario_id is None:
            result = RunCheckResult(
                passed=False,
                feedback=f"[{label}] Failed to parse scenario_id from file {artifact_path}",
                runtime_error=True,
                validation_reached=False,
                validation_success=False,
            )
            self._last_check_result = result
            return result

        logger.info(
            "Running scenario check '%s' for scenario_id='%s' using artifact '%s'",
            label,
            scenario_id,
            artifact_path,
        )
        cmd = [
            sys.executable,
            "/Users/jasonz/Projects/ucsb/proactiveGoalInference/pas/scenario_generator/utils/run_scenario.py",
            "-s",
            scenario_id,
            "-a",
            "default",
            "--provider",
            "mock",
            "--temp-file",
            str(artifact_path),
        ]
        env = os.environ.copy()
        env.setdefault("PYTHONPATH", str(self.repo_root))
        proc = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            cwd=self.repo_root,
            env=env,
        )
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        registration_ok = "All scenarios properly registered, proceeding with execution" in output
        runtime_error = (
            proc.returncode != 0 or "ERROR_TYPE" in output or "Failed to load scenario" in output or not registration_ok
        )
        validation_reached = "ScenarioValidationResult(" in output
        validation_success = "ScenarioValidationResult(success=True" in output

        passed = True
        if runtime_error or not validation_reached or (require_validation_success and not validation_success):
            passed = False

        summary = self._summarize_run_output(
            output=output,
            registration_ok=registration_ok,
            runtime_error=runtime_error,
            validation_reached=validation_reached,
            validation_success=validation_success,
        )
        feedback = f"[{label}] {'PASSED' if passed else 'FAILED'} run for scenario '{scenario_id}'.\n{summary}"
        result = RunCheckResult(
            passed=passed,
            feedback=feedback,
            runtime_error=runtime_error,
            validation_reached=validation_reached,
            validation_success=validation_success,
        )
        self._last_check_result = result
        return result

    def _get_or_initialize_scenario_file(self) -> str:
        """Return current scenario file contents, seeding from template if missing."""
        if self.scenario_file.exists():
            return self._safe_read_text(self.scenario_file)
        if self.seed_template_text:
            self.scenario_file.write_text(self.seed_template_text, encoding="utf-8")
            return self.seed_template_text
        self.scenario_file.touch()
        return ""

    @staticmethod
    def _safe_read_text(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def _read_valid_descriptions(self) -> list[dict[str, Any]]:
        try:
            existing_text = self.valid_descriptions_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        existing_text = existing_text.strip()
        if not existing_text:
            return []
        try:
            parsed = json.loads(existing_text)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return parsed
        return []

    @staticmethod
    def _extract_scenario_id(code_text: str) -> str | None:
        match = re.search(r'@register_scenario\(\s*["\']([^"\']+)["\']\s*\)', code_text)
        if match:
            return match.group(1).strip()
        return None

    @staticmethod
    def _summarize_run_output(
        output: str,
        *,
        registration_ok: bool,
        runtime_error: bool,
        validation_reached: bool,
        validation_success: bool,
    ) -> str:
        lines = [line.strip() for line in output.strip().splitlines() if line.strip()]

        def find_line(pattern: str) -> str | None:
            for line in lines:
                if pattern in line:
                    return line
            return None

        registration_summary = (
            "PASS - Scenario registered successfully."
            if registration_ok
            else "FAILED - Scenario did not reach execution phase."
        )

        runtime_summary = "PASS - No runtime errors detected."
        if runtime_error:
            error_lines = [line for line in lines if "ERROR" in line or "Exception" in line]
            snippet = "\n".join(error_lines[:3]) or "\n".join(lines[-5:])
            runtime_summary = f"FAILED - Runtime issues observed:\n{snippet}"

        validation_summary = "NOT RUN - Validation step not reached."
        if validation_reached and validation_success:
            validation_summary = "PASS - ScenarioValidationResult(success=True)."
        elif validation_reached:
            val_line = find_line("ScenarioValidationResult(") or ""
            validation_summary = f"FAILED - {val_line}"

        return "\n".join([
            f"Registration: {registration_summary}",
            f"Runtime: {runtime_summary}",
            f"Validation: {validation_summary}",
        ])

    def _append_valid_description(self, description: str) -> None:
        entry = {
            "description": description,
            "timestamp": datetime.utcnow().isoformat(),
        }
        existing = self._read_valid_descriptions()
        existing.append(entry)
        self.valid_descriptions_path.parent.mkdir(parents=True, exist_ok=True)
        self.valid_descriptions_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        self._historical_descriptions = existing

    def _persist_scenario(self, target_dir: Path) -> None:
        if not self.scenario_file.exists():
            return
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        target_path = target_dir / f"scenario_{timestamp}.py"
        shutil.copy2(self.scenario_file, target_path)

    def _persist_failed_scenario(
        self, reason: str, runtime_error: bool = True, validation_reached: bool = False
    ) -> None:
        if not self.scenario_file.exists():
            return
        with self.scenario_file.open("a", encoding="utf-8") as handle:
            handle.write(f"\n# FAILED SCENARIO REASON: {reason}\n")
        target = self.failed_dir if runtime_error or not validation_reached else self.failed_no_runtime_dir
        self._persist_scenario(target)

    def _debug_print(self, message: str) -> None:
        print(message)

    @staticmethod
    def _debug_placeholder_content(label: str, detail: str | None = None) -> str:
        detail_block = f"\n{detail}" if detail else ""
        return f"# [DEBUG PLACEHOLDER] {label}{detail_block}"
