from __future__ import annotations

import ast
import functools
import importlib
import json
import logging
import os
import re
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pare.scenarios.generator.prompt import scenario_generating_agent_prompts as prompt_module
from pare.scenarios.generator.prompt.scenario_generating_agent_prompts import (
    configure_dynamic_context,
)
from scripts.run_scenarios import run_scenarios

from .claude_backend import ClaudeAgentRuntimeConfig, ClaudeFilesystemConfig
from .scenario_uniqueness_agent import ScenarioUniquenessCheckAgent
from .step_agents import StepEditAgent, StepResult

logger = logging.getLogger(__name__)


@dataclass
class RunCheckResult:
    """Summary of a single scenario run used to gate multi-step progress."""

    passed: bool
    feedback: str
    runtime_error: bool
    validation_reached: bool
    validation_success: bool


class ScenarioGeneratingAgentOrchestrator:
    """Coordinates the dedicated step agents to build a proactive scenario."""

    _ALWAYS_INCLUDED_APPS = {"PAREAgentUserInterface", "HomeScreenSystemApp"}  # noqa: RUF012

    def __init__(
        self,
        *,
        output_dir: str | Path | None = None,
        max_iterations: int = 3,
        trajectory_dir: str | Path | None = None,
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
        # This file lives under `pare/scenarios/generator/agent/...`.
        # - generator_dir: pare/scenarios/generator
        # - scenarios_dir: pare/scenarios
        # - pare_dir:       pare
        generator_dir = Path(__file__).resolve().parents[1]
        scenarios_dir = generator_dir.parent
        pas_dir = scenarios_dir.parent

        # Keep repo_root aligned to the `pare/` package directory (so relative paths
        # like repo_root/"scenarios"/... resolve under `pare/scenarios/`).
        self.repo_root = pas_dir

        # Directory that tracks the per-step trajectory for this run, e.g.,
        # pare/scenario_generator/step_trajectory/trajectory_YYYYMMDDTHHMMSS.
        trajectory_root = generator_dir / "step_trajectory"
        if trajectory_dir is not None:
            self.trajectory_dir = Path(trajectory_dir)
        else:
            timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
            self.trajectory_dir = trajectory_root / f"trajectory_{timestamp}"
        self.trajectory_dir.mkdir(parents=True, exist_ok=True)

        # Directory where intermediate markdown artifacts live. We no longer write
        # to `pare/scenario_generator/generated_scenarios/`; keep artifacts scoped
        # to the trajectory directory by default.
        self.output_dir = Path(output_dir) if output_dir is not None else self.trajectory_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Directory that holds the single editable working copy plus the final
        # exported scenarios produced by the multi-step generator.
        #
        # IMPORTANT: this directory must live directly under `pare/scenarios/`
        # so that `PARE_SCENARIOS_DIR=generator` can discover and import the
        # working file as `pare.scenarios.generator.<module>`.
        self.seed_scenarios_dir = generator_dir
        self.seed_scenarios_dir.mkdir(parents=True, exist_ok=True)

        # Use the editable_seed_scenario-based working file so Claude Agent can
        # repeatedly edit a single, stable filename. The original seed template
        # remains read-only for reference.
        self.scenario_file = self.seed_scenarios_dir / "editable_seed_scenario.py"

        # Global scenario metadata used for uniqueness checks and analysis.
        # Stored under `pare/scenarios/scenario_metadata.json` so it is shared
        # across runs and not tied to a particular output directory.
        self.scenario_metadata_path = self.repo_root / "scenarios" / "scenario_metadata.json"

        # Dynamic prompt context (selected apps/tools) for this run.
        # IMPORTANT: must be set before any helper that reads `_prompt_context`.
        self._prompt_context: dict[str, str] = prompt_context or {}

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
        self._historical_descriptions = self._read_scenario_metadata()

        # For Step 0/1 prompting we often want to scope uniqueness comparisons to
        # scenarios that use the same core app combination as this run (excluding
        # the always-present PAREAgentUserInterface + HomeScreenSystemApp).
        self.scenario_metadata_path_for_prompt = self.scenario_metadata_path
        self._historical_descriptions_for_prompt = self._historical_descriptions
        filtered_path, filtered_entries = self._maybe_write_filtered_metadata_for_prompt()
        if filtered_path is not None:
            self.scenario_metadata_path_for_prompt = filtered_path
            self._historical_descriptions_for_prompt = filtered_entries

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
                "Debug prompts mode enabled for multi-step scenario generator; all Claude calls "
                "will be skipped. Prompts and planned file operations will be logged instead.",
            )

        # Use the canonical original seed template with explicit start/end markers
        # from the PARE scenarios package so we can safely strip any
        # natural-language preamble/epilogue that Claude might emit around the
        # template body.
        self.seed_template_path = generator_dir / "utils" / "original_seed_scenario.py"
        self.seed_template_text = self._safe_read_text(self.seed_template_path)

        if self.debug_prompts:
            logger.info("Scenario working file: %s", self.scenario_file)
            logger.info("Seed template path: %s", self.seed_template_path)
            logger.info("Scenario metadata path: %s", self.scenario_metadata_path)
            logger.info(
                "Claude filesystem config: read_only_roots=%s, editable_files=%s",
                self.claude_filesystem_config.read_only_roots,
                self.claude_filesystem_config.editable_files,
            )
            if prompt_context is not None:
                logger.info("Selected apps for this run: %s", prompt_context.get("selected_apps", "(unknown)"))

        self.uniqueness_agent = ScenarioUniquenessCheckAgent(
            historical_descriptions=self._historical_descriptions_for_prompt,
            scenario_metadata_path=str(self.scenario_metadata_path_for_prompt),
            debug_prompts=debug_prompts,
            claude_runtime_config=self._claude_config_uniqueness,
        )
        self.step1_agent = StepEditAgent(
            step_name="Step 1: Scenario Description",
            step_kind="description",
            system_prompt=prompt_module.SCENARIO_DESCRIPTION_SYSTEM_PROMPT,
            max_iterations=max_iterations,
            uniqueness_agent=self.uniqueness_agent,
            debug_prompts=debug_prompts,
            claude_runtime_config=self._claude_config_step1,
        )
        self.step2_agent = StepEditAgent(
            step_name="Step 2: Apps & Data Setup",
            step_kind="apps_and_data",
            system_prompt=prompt_module.APPS_AND_DATA_SYSTEM_PROMPT,
            max_iterations=max_iterations,
            debug_prompts=debug_prompts,
            claude_runtime_config=self._claude_config_code_steps,
        )
        self.step3_agent = StepEditAgent(
            step_name="Step 3: Events Flow",
            step_kind="events_flow",
            system_prompt=prompt_module.EVENTS_FLOW_SYSTEM_PROMPT,
            max_iterations=max_iterations,
            debug_prompts=debug_prompts,
            claude_runtime_config=self._claude_config_code_steps,
        )
        self.step4_agent = StepEditAgent(
            step_name="Step 4: Validation Conditions",
            step_kind="validation",
            system_prompt=prompt_module.VALIDATION_SYSTEM_PROMPT,
            max_iterations=max_iterations,
            debug_prompts=debug_prompts,
            claude_runtime_config=self._claude_config_code_steps,
        )

    @classmethod
    def _dedupe_scenario_id(cls, scenario_id: str, existing_ids: set[str]) -> str:
        """Return a scenario_id that does not collide with `existing_ids`.

        Note: we intentionally do NOT enforce the Step 1 <= 40 char constraint here.
        This is a post-processing safety shim to avoid overwriting an existing scenario.
        """
        if scenario_id not in existing_ids:
            return scenario_id

        base = scenario_id
        # Choose smallest suffix that avoids collisions: foo_2, foo_3, ...
        i = 2
        while True:
            suffix = f"_{i}"
            candidate = f"{base}{suffix}"
            if candidate not in existing_ids:
                return candidate
            i += 1

    @staticmethod
    def _dedupe_class_name(class_name: str, existing_class_names: set[str]) -> str:
        """Return a class name that does not collide with `existing_class_names`.

        Uses numeric suffixes to keep the name a valid PascalCase identifier, e.g. Foo2, Foo3.
        """
        if class_name not in existing_class_names:
            return class_name
        i = 2
        while True:
            candidate = f"{class_name}{i}"
            if candidate not in existing_class_names:
                return candidate
            i += 1

    def _ensure_unique_step1_identifiers(self, *, scenario_id: str, class_name: str) -> tuple[str, str, dict[str, Any]]:
        """Ensure Step 1 identifiers won't silently overwrite existing artifacts."""
        existing = self._read_scenario_metadata()
        existing_ids: set[str] = {
            str(entry.get("scenario_id")).strip()
            for entry in existing
            if isinstance(entry, dict) and entry.get("scenario_id")
        }
        existing_class_names: set[str] = {
            str(entry.get("class_name")).strip()
            for entry in existing
            if isinstance(entry, dict) and entry.get("class_name")
        }

        # Also prevent filename collisions in the canonical generated scenarios dir.
        try:
            for path in self.seed_scenarios_dir.glob("*.py"):
                existing_class_names.add(path.stem)
        except Exception:
            logger.exception("Failed to scan existing scenario filenames under %s", self.seed_scenarios_dir)

        original = {"scenario_id": scenario_id, "class_name": class_name}
        new_scenario_id = self._dedupe_scenario_id(scenario_id, existing_ids)
        # If we had to dedupe the id, include it in the "existing_ids" set so class dedupe notes remain consistent.
        existing_ids.add(new_scenario_id)

        new_class_name = self._dedupe_class_name(class_name, existing_class_names)
        notes: dict[str, Any] = {}
        if new_scenario_id != scenario_id:
            notes["scenario_id_deduped_from"] = scenario_id
        if new_class_name != class_name:
            notes["class_name_deduped_from"] = class_name
        if notes:
            notes["original_identifiers"] = original
            notes["deduped_identifiers"] = {"scenario_id": new_scenario_id, "class_name": new_class_name}
            logger.warning(
                "Deduped Step 1 identifiers to avoid overwriting existing scenarios: %s -> %s",
                original,
                notes["deduped_identifiers"],
            )
        return new_scenario_id, new_class_name, notes

    def run(self) -> dict[str, Any]:  # noqa: C901
        """Execute the four-step pipeline and return artifact metadata."""
        logger.info("Starting multi-step scenario generation.")

        try:
            step1_path = self.output_dir / "step1_scenario_description.md"
            resume_mode = self.resume_from_step

            # If resuming from later steps, restore the working scenario file
            # from the appropriate trajectory snapshot when available. This
            # keeps the single editable_seed_scenario.py in sync with the code
            # that previously passed validation for that step.
            if not self.debug_prompts:
                if resume_mode == "step2":
                    # Restore the scenario file as it looked after Step 1
                    # header updates.
                    self._restore_scenario_from_trajectory("step1")
                elif resume_mode == "step3":
                    # Restore the scenario as of the end of Step 2.
                    self._restore_scenario_from_trajectory("step2")
                elif resume_mode == "step4":
                    # Restore the scenario as of the end of Step 3.
                    self._restore_scenario_from_trajectory("step3")

            # For fresh runs (no resume) we start from a pristine copy of the
            # original seed scenario so that Step 1 can update its header
            # (scenario id, class name, and docstring) deterministically.
            if resume_mode not in {"step2", "step3", "step4"} and not self.debug_prompts:
                self._initialize_working_scenario_from_seed()

            if resume_mode in {"step2", "step3", "step4"} and not self.debug_prompts:
                step1 = self._load_existing_step1_result(step1_path)
            else:

                def step1_check(description: str, iteration: int) -> tuple[bool, str]:
                    # This callback itself does not write any files. Step 1 side
                    # effects (updating `valid_descriptions.json` and the
                    # editable_seed_scenario.py header) are applied by the
                    # orchestrator after the step completes.
                    return True, ""

                check1 = None if self.debug_prompts else step1_check

                step1 = self.step1_agent.run(
                    scenario_metadata_path=str(self.scenario_metadata_path_for_prompt),
                    check_callback=check1,
                )
                logger.info("Step 1 completed with %s iterations.", step1.iterations)
                if not self.debug_prompts:
                    scenario_id, class_name, description = self._parse_step1_output(step1.content)
                    # Only persist metadata + update headers when Step 1 produced
                    # a parseable identifier and a non-empty description.
                    if scenario_id is None or class_name is None or not description.strip():
                        logger.warning(
                            "Step 1 output did not include a parseable Scenario ID/Class Name/Description. "
                            "Skipping metadata/header update for this run."
                        )
                    else:
                        # Avoid silent overwrites when the generator proposes identifiers that already exist.
                        scenario_id, class_name, dedupe_notes = self._ensure_unique_step1_identifiers(
                            scenario_id=scenario_id, class_name=class_name
                        )
                        self._append_scenario_metadata(
                            scenario_id=scenario_id,
                            class_name=class_name,
                            description=description,
                        )
                        self._update_scenario_header(
                            scenario_id=scenario_id, class_name=class_name, description=description
                        )
                        self._append_step_trajectory("step1", step1)
                        if dedupe_notes:
                            # Best-effort: persist dedupe info next to the trajectory for debugging.
                            try:
                                (self.trajectory_dir / "step1_identifier_dedupe.json").write_text(
                                    json.dumps(dedupe_notes, indent=2), encoding="utf-8"
                                )
                            except Exception:
                                logger.exception("Failed to write Step 1 identifier dedupe notes")
                        # Snapshot the scenario after Step 1 header updates so users
                        # can inspect the early state if Step 2 fails.
                        self._snapshot_scenario("step1")

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
                if not self.debug_prompts:
                    self._append_step_trajectory("step2", step2)
            else:
                # For fresh runs, Step 1 has already initialized and updated
                # the working scenario file. For resumed runs that reach this
                # branch, use the existing editable_seed_scenario.py on disk.
                scenario_seed_content = self._get_or_initialize_scenario_file()
                check2 = (
                    None
                    if self.debug_prompts
                    else functools.partial(
                        self._step_check_callback,
                        step_label="apps-data-check",
                        guardrail_feedback=(
                            "[apps-data-check] Your previous edits did not yield a "
                            "complete Python scenario file. Use the code editing tools "
                            "to update only the imports and init_and_populate_apps() "
                            "within the existing template, ensuring the file still "
                            "contains the original template start/end markers and "
                            "a @register_scenario(...) decorator."
                        ),
                        require_validation_success=False,
                    )
                )

                step2 = self.step2_agent.run(
                    scenario_description=step1.content,
                    scenario_file_path=str(self.scenario_file),
                    check_callback=check2,
                )
                logger.info("Step 2 completed with %s iterations.", step2.iterations)
                if not self.debug_prompts:
                    self._append_step_trajectory("step2", step2)

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
                if not self.debug_prompts:
                    self._append_step_trajectory("step3", step3)
            else:
                check3 = (
                    None
                    if self.debug_prompts
                    else functools.partial(
                        self._step_check_callback,
                        step_label="events-flow-check",
                        guardrail_feedback=(
                            "[events-flow-check] Your previous edits did not yield a "
                            "complete Python scenario file. Use the code editing tools "
                            "to update only build_events_flow() within the existing "
                            "template, preserving the template markers and "
                            "@register_scenario(...) decorator."
                        ),
                        require_validation_success=False,
                    )
                )

                step3 = self.step3_agent.run(
                    scenario_description=step1.content,
                    apps_and_data=step2.content,
                    scenario_file_path=str(self.scenario_file),
                    check_callback=check3,
                )
                logger.info("Step 3 completed with %s iterations.", step3.iterations)
                if not self.debug_prompts:
                    self._append_step_trajectory("step3", step3)

                scenario_after_step3 = (
                    self._debug_placeholder_content("scenario_after_step3", step3.content)
                    if self.debug_prompts
                    else self._safe_read_text(self.scenario_file)
                )

                # Snapshot the scenario after Step 3 completes successfully.
                if not self.debug_prompts:
                    self._snapshot_scenario("step3")

            check4 = (
                None
                if self.debug_prompts
                else functools.partial(
                    self._step_check_callback,
                    step_label="validation-check",
                    guardrail_feedback=(
                        "[validation-check] Your previous edits did not yield a "
                        "complete Python scenario file. Use the code editing tools "
                        "to focus only on validate() inside the existing template, "
                        "preserving the template markers and @register_scenario(...)."
                    ),
                    require_validation_success=True,
                )
            )

            step4 = self.step4_agent.run(
                scenario_description=step1.content,
                events_flow=step3.content,
                scenario_file_path=str(self.scenario_file),
                check_callback=check4,
            )
            logger.info("Step 4 completed with %s iterations.", step4.iterations)

            if not self.debug_prompts:
                self._append_step_trajectory("step4", step4)
                # Export a class-named copy (guarded by validation success) and
                # reset the working file back to the pristine seed template so
                # the next run starts from a clean slate.
                self._export_final_scenario_and_reset()

            logger.info("Multi-step scenario generation pipeline complete.")
            return {
                "description_path": str(self.scenario_metadata_path),
                "scenario_file_path": str(self.scenario_file),
                "trajectory_dir": str(self.trajectory_dir),
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

    def _maybe_write_filtered_metadata_for_prompt(self) -> tuple[Path | None, list[dict[str, Any]]]:
        """Optionally write a filtered metadata JSON for Step 0/1 prompts.

        Motivation: when generating scenarios for a specific app set (e.g.,
        --apps StatefulCalendarApp StatefulMessagingApp), it can be useful to
        only enforce uniqueness against *scenarios with the same core app
        combination* rather than against scenarios that involve other apps.
        """
        selected = self._parse_selected_apps_from_prompt_context()
        if not selected:
            return None, self._historical_descriptions

        core_selected = selected - self._ALWAYS_INCLUDED_APPS
        if not core_selected:
            return None, self._historical_descriptions

        filtered = self._filter_metadata_by_core_apps(self._historical_descriptions, core_selected)
        # Always write the file when we have an explicit core app selection,
        # even if it results in an empty list. This makes the prompting behavior
        # deterministic and avoids surprising "other app" rejections.
        filtered_path = self.trajectory_dir / "scenario_metadata.filtered.json"
        try:
            filtered_path.write_text(json.dumps(filtered, indent=2), encoding="utf-8")
        except Exception:
            logger.exception(
                "Failed to write filtered scenario metadata to %s; falling back to full metadata", filtered_path
            )
            return None, self._historical_descriptions
        return filtered_path, filtered

    def _parse_selected_apps_from_prompt_context(self) -> set[str]:
        """Parse selected app class names from the provided dynamic prompt context."""
        raw = (self._prompt_context or {}).get("selected_apps", "") or ""
        if not raw.strip():
            return set()
        # The prompt context may be word-wrapped, which can split long class
        # names across newlines (e.g., "StatefulCale\ndarApp"). Normalize by
        # removing all whitespace before parsing.
        compact = re.sub(r"\s+", "", raw)
        tokens: set[str] = set()
        for part in compact.split(","):
            item = part.strip()
            if not item:
                continue
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item):
                tokens.add(item)
        return tokens

    @classmethod
    def _filter_metadata_by_core_apps(
        cls,
        entries: list[dict[str, Any]],
        core_selected: set[str],
    ) -> list[dict[str, Any]]:
        """Return metadata entries whose *core* app set exactly matches `core_selected`."""
        filtered: list[dict[str, Any]] = []
        for entry in entries:
            apps = entry.get("apps") or []
            if not isinstance(apps, list):
                continue
            core = {a for a in apps if isinstance(a, str)} - cls._ALWAYS_INCLUDED_APPS
            if core == core_selected:
                filtered.append(entry)
        return filtered

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

    def _initialize_working_scenario_from_seed(self) -> None:
        """Initialize the editable working scenario file from the original seed."""
        if self.seed_template_text:
            self.scenario_file.write_text(self.seed_template_text, encoding="utf-8")
        else:
            # Ensure the working file exists even if the template is missing.
            self.scenario_file.touch(exist_ok=True)

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

    def _step_check_callback(
        self,
        response: str,
        iteration: int,
        *,
        step_label: str,
        guardrail_feedback: str,
        require_validation_success: bool = False,
    ) -> tuple[bool, str]:
        """Shared `check_callback` implementation for Steps 2-4.

        Claude Agent SDK typically edits scenario files via tools rather than returning full code in the
        assistant message, so this check validates `editable_seed_scenario.py` on disk instead of the
        raw model reply.
        """
        _ = response  # unused: Claude's text reply is not the source of truth for code steps
        scenario_text = self._safe_read_text(self.scenario_file)
        if not self._looks_like_complete_scenario(scenario_text):
            # Structural guardrail only; no runtime feedback available yet.
            return False, guardrail_feedback

        # Run the dynamic scenario check (TwoAgentScenarioRunner) and, if it
        # fails, thread the concrete runtime error back into the feedback so
        # the next iteration has a precise signal about what went wrong.
        result = self._run_step_check(
            step_label,
            self.scenario_file,
            require_validation_success=require_validation_success,
        )

        if result.passed:
            return True, result.feedback

        # For runtime/validation failures, return ONLY the concrete summary from
        # `_run_step_check`. The static guardrail text about "complete Python
        # scenario files" is only relevant when the structural check fails.
        return False, result.feedback

    @staticmethod
    def _sanitize_docstring_text(text: str) -> str:
        """Ensure the description can safely live inside a triple-quoted docstring."""
        return text.replace('"""', '\\"""')

    def _parse_step1_output(self, text: str) -> tuple[str | None, str | None, str]:  # noqa: C901
        """Parse Step 1 agent output into (scenario_id, class_name, description)."""
        raw = text.strip()
        if not raw:
            return None, None, ""

        lines = raw.splitlines()
        scenario_id: str | None = None
        class_name: str | None = None
        description_lines: list[str] = []
        in_description = False
        in_explanation = False

        def _strip_md_label_prefix(s: str) -> str:
            # Normalize common markdown variants like "**Scenario ID:** foo"
            # to "Scenario ID: foo" so parsing is robust.
            s = s.strip()
            # Remove leading list markers (e.g., "-", "*", "1.")
            s = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", s)
            # Remove surrounding **bold** markers around the label portion.
            s = re.sub(r"^\*\*(.+?)\*\*\s*$", r"\1", s)
            return s

        def _match_labeled_value(label: str, s: str) -> str | None:
            # Accept "Label: value" and "**Label:** value" and "Label:** value" variants.
            # Returns the value if matched.
            normalized = s.strip()
            # Handle "**Label:** value" (colon inside the bold span)
            m = re.match(
                rf"^\*\*\s*{re.escape(label)}\s*:\s*\*\*\s*(.+)$",
                normalized,
                flags=re.IGNORECASE,
            )
            if m:
                return m.group(1).strip() or None
            # Handle "**Label**: value" (colon outside the bold span)
            m = re.match(
                rf"^\*\*\s*{re.escape(label)}\s*\*\*\s*:\s*(.+)$",
                normalized,
                flags=re.IGNORECASE,
            )
            if m:
                return m.group(1).strip() or None
            # Handle "Label: value" (with optional bold markers around label)
            m = re.match(rf"^{re.escape(label)}\s*:\s*(.+)$", _strip_md_label_prefix(normalized), flags=re.IGNORECASE)
            if m:
                return m.group(1).strip() or None
            return None

        for _idx, line in enumerate(lines):
            stripped = line.strip()
            lower = stripped.lower()
            if not in_description:
                scenario_id_val = _match_labeled_value("Scenario ID", stripped)
                if scenario_id_val is not None:
                    scenario_id = scenario_id_val
                class_name_val = _match_labeled_value("Class Name", stripped)
                if class_name_val is not None:
                    class_name = class_name_val
                # Description section header: allow "Description:" or "**Description:**"
                if (
                    re.match(r"^\s*\*\*\s*Description\s*:\s*\*\*\s*$", stripped, flags=re.IGNORECASE)
                    or re.match(r"^\s*\*\*\s*Description\s*\*\*\s*:\s*$", stripped, flags=re.IGNORECASE)
                    or (_strip_md_label_prefix(stripped).lower() == "description:")
                ):
                    in_description = True
                    continue
                # Description header with content on same line: "Description: foo"
                desc_inline = _match_labeled_value("Description", stripped)
                if desc_inline is not None:
                    in_description = True
                    description_lines.append(desc_inline)
                    continue
                continue
            if in_description and not in_explanation:
                # Stop the description at the start of an optional Explanation section.
                if (
                    re.match(r"^\s*\*\*\s*Explanation\s*:\s*\*\*\s*$", stripped, flags=re.IGNORECASE)
                    or re.match(r"^\s*\*\*\s*Explanation\s*\*\*\s*:\s*$", stripped, flags=re.IGNORECASE)
                    or re.match(r"^\s*(?:\*\*\s*)?explanation(?:\s*\*\*)?\s*:\s*$", stripped, flags=re.IGNORECASE)
                    or lower.startswith("explanation:")
                ):
                    in_explanation = True
                    continue
                # Safety: some models accidentally paste additional drafts (including new Scenario ID/Class Name blocks)
                # inside the Description section. Stop capturing at the start of a new header to avoid polluting metadata.
                if re.match(r"^\s*\*{0,2}\s*Scenario ID\s*:\s*", stripped, flags=re.IGNORECASE) or re.match(
                    r"^\s*\*{0,2}\s*Class Name\s*:\s*", stripped, flags=re.IGNORECASE
                ):
                    break
                description_lines.append(line)

        if not in_description:
            # Fallback: treat the whole text as description.
            return None, None, raw

        description = "\n".join(description_lines).strip()
        return scenario_id, class_name, description

    def _update_scenario_header(  # noqa: C901
        self,
        *,
        scenario_id: str | None,
        class_name: str | None,
        description: str,
    ) -> None:
        """Apply Step 1 outputs to the working scenario header (id, class, docstring)."""
        if not description.strip():
            return

        original_code = self._safe_read_text(self.scenario_file)
        code = original_code
        if not code.strip():
            if self.seed_template_text:
                code = self.seed_template_text
            else:
                return

        # If the Step 1 agent omitted id or class name, skip header updates to
        # avoid writing partially configured identifiers.
        if scenario_id is None or class_name is None:
            return

        # Update @register_scenario("<id>")
        def _replace_register(match: re.Match[str]) -> str:
            return f'@register_scenario("{scenario_id}")'

        code = re.sub(
            r'@register_scenario\(\s*["\']([^"\']+)["\']\s*\)',
            _replace_register,
            code,
            count=1,
        )

        # Update `class <Name>(PAREScenario):`
        def _replace_class(match: re.Match[str]) -> str:
            return f"class {class_name}(PAREScenario):"

        code = re.sub(
            r"class\s+(\w+)\s*\(PAREScenario\):",
            _replace_class,
            code,
            count=1,
        )

        # Update the class docstring to reflect the full scenario description.
        # Prefer replacing the <<scenario_description>> placeholder (keeps template
        # indentation stable) rather than wholesale replacing the docstring.
        try:
            class_idx = code.index("class ")
        except ValueError:
            class_idx = 0
        doc_start = code.find('"""', class_idx)
        doc_end = code.find('"""', doc_start + 3) if doc_start != -1 else -1
        if doc_start != -1 and doc_end != -1:
            sanitized = self._sanitize_docstring_text(description.strip())
            doc_body = code[doc_start + 3 : doc_end]
            if "<<scenario_description>>" in doc_body:
                new_body = doc_body.replace("<<scenario_description>>", sanitized)
            else:
                new_body = sanitized

            # IMPORTANT: `code[:doc_start]` already contains the indentation
            # prefix for the docstring line, so do NOT prepend indentation again
            # (doing so leads to an `IndentationError` later when class-level
            # fields like `start_time` return to the correct indentation).
            new_doc = f'"""{new_body}"""'
            code = code[:doc_start] + new_doc + code[doc_end + 3 :]

        # Defensive: never persist an invalid Python file; syntax errors here
        # can cascade into confusing registry/runtime failures later.
        try:
            ast.parse(code)
        except SyntaxError as exc:
            # Revert to the original on-disk content (best effort) and fail fast.
            if original_code:
                self.scenario_file.write_text(original_code, encoding="utf-8")
            raise RuntimeError(f"Invalid Python after Step 1 header update: {exc}") from exc

        self.scenario_file.write_text(code, encoding="utf-8")

    def _snapshot_scenario(self, step_label: str) -> None:
        """Save a point-in-time copy of the editable seed scenario after a step.

        For example, after Step 2 and Step 3 complete successfully we capture
        `editable_seed_scenario_step2.py` and `editable_seed_scenario_step3.py`
        under the step_trajectory/trajectory_*/ directory so users can inspect
        or resume from those artifacts if needed.
        """
        try:
            import shutil

            snapshot_name = f"editable_seed_scenario_{step_label}.py"
            snapshot_path = self.trajectory_dir / snapshot_name
            shutil.copy2(self.scenario_file, snapshot_path)
            logger.info("Snapshot for %s written to %s", step_label, snapshot_path)
        except Exception:  # pragma: no cover - snapshot failures are non-fatal
            logger.exception("Failed to snapshot scenario after %s", step_label)

    def _restore_scenario_from_trajectory(self, step_label: str) -> str:
        """Restore the working scenario file from a previously snapshotted step.

        This is used when resuming the pipeline so that we can reuse the
        scenario code as of a particular step (e.g., 'step2' or 'step3').
        If no snapshot is available, the method logs a warning and preserves
        the existing working file contents.
        """
        snapshot_name = f"editable_seed_scenario_{step_label}.py"
        snapshot_path = self.trajectory_dir / snapshot_name
        snapshot_text = self._safe_read_text(snapshot_path)
        if not snapshot_text:
            logger.warning(
                "Requested resume from %s but no snapshot found at %s; continuing with existing scenario file at %s",
                step_label,
                snapshot_path,
                self.scenario_file,
            )
            return self._safe_read_text(self.scenario_file)

        self.scenario_file.write_text(snapshot_text, encoding="utf-8")
        logger.info("Restored scenario file for %s from trajectory snapshot %s", step_label, snapshot_path)
        return snapshot_text

    def _append_step_trajectory(self, step_label: str, step_result: StepResult) -> None:
        """Append a single step's trajectory record to the trajectory directory.

        This writes a JSONL file (`steps.jsonl`) under `trajectory_dir` where
        each line is a JSON object describing one step run, including the full
        LLM conversation and metadata. Failures are logged but do not stop the
        main pipeline.
        """
        try:
            record = {
                "step_label": step_label,
                "timestamp": datetime.utcnow().isoformat(),
                "step": asdict(step_result),
            }
            path = self.trajectory_dir / "steps.jsonl"
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record))
                handle.write("\n")
        except Exception:  # pragma: no cover - trajectory logging is best-effort
            logger.exception("Failed to append step trajectory for %s", step_label)

    def _export_final_scenario_and_reset(self) -> None:
        """Export the final scenario by class name, then reset the working file.

        After all four steps and checks have passed, this method:
        1. Reads `editable_seed_scenario.py` and extracts the PAREScenario class
           name (e.g., `MyScenarioName`).
        2. Copies the final scenario into
           `pare/scenarios/generator/MyScenarioName.py`.
        3. Resets `editable_seed_scenario.py` back to the original seed template
           so the next multi-step run starts from a clean, canonical file.
        """
        code = self._safe_read_text(self.scenario_file)
        if not code.strip():
            logger.warning("Final scenario export skipped: working scenario file is empty.")
            return

        match = re.search(r"class\s+(\w+)\s*\(PAREScenario\):", code)
        if not match:
            logger.warning(
                "Final scenario export skipped: could not parse PAREScenario class name from %s",
                self.scenario_file,
            )
            return

        class_name = match.group(1)
        target_path = self.seed_scenarios_dir / f"{class_name}.py"
        if target_path.exists():
            # Safety guard: avoid silently overwriting an existing scenario file.
            # Prefer adding a numeric suffix to the filename (class name inside the file remains unchanged).
            i = 2
            while True:
                candidate = self.seed_scenarios_dir / f"{class_name}{i}.py"
                if not candidate.exists():
                    logger.warning(
                        "Target scenario file %s already exists; exporting to %s instead to avoid overwrite.",
                        target_path,
                        candidate,
                    )
                    target_path = candidate
                    break
                i += 1

        # Safety guard: never export into the default generation output directory
        # unless the most recent run check reached validation and succeeded.
        if (
            self._last_check_result is None
            or self._last_check_result.runtime_error
            or not self._last_check_result.validation_reached
            or not self._last_check_result.validation_success
        ):
            logger.warning(
                "Skipping final scenario export for class %s: last run check did not validate successfully.",
                class_name,
            )
            # Still reset the working file so subsequent runs start clean.
            self._initialize_working_scenario_from_seed()
            return

        try:
            shutil.copy2(self.scenario_file, target_path)
            logger.info(
                "Exported final scenario for class %s to %s",
                class_name,
                target_path,
            )
        except Exception:  # pragma: no cover - export failures are non-fatal
            logger.exception("Failed to export final scenario for class %s", class_name)

        # Reset the editable working file back to the original seed template so
        # subsequent runs begin from a pristine scenario skeleton.
        try:
            self._initialize_working_scenario_from_seed()
            logger.info("Reset working scenario file %s from original seed template.", self.scenario_file)
        except Exception:  # pragma: no cover - reset failures are non-fatal
            logger.exception("Failed to reset working scenario file %s", self.scenario_file)

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
            history = self._read_scenario_metadata()
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

    def _run_step_check(  # noqa: C901
        self,
        label: str,
        artifact_path: Path,
        require_validation_success: bool = False,
    ) -> RunCheckResult:
        """Run the generated scenario and summarize the result.

        This helper is the canonical integration point between the Claude-backed
        step agents (which edit the scenario file) and the PARE/meta-ARE runner,
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

        # Ensure the PARE scenario registry can see the working scenario file.
        # We do this by updating PARE_SCENARIOS_DIR to include the directory
        # that contains `editable_seed_scenario.py` (or any other artifact
        # passed in). The PARE registry lazily discovers scenarios based on
        # this environment variable when `registry.get_scenario(...)` is first
        # called inside `run_demo`.
        scenarios_dir_name = artifact_path.parent.name
        existing_dirs = os.getenv("PARE_SCENARIOS_DIR", "benchmark")
        dirs = [d.strip() for d in existing_dirs.split(",") if d.strip()]
        if scenarios_dir_name not in dirs:
            dirs.append(scenarios_dir_name)
            os.environ["PARE_SCENARIOS_DIR"] = ",".join(dirs)

        # IMPORTANT: `editable_seed_scenario.py` is imported as a module during
        # PARE scenario discovery. When generating multiple scenarios in the same
        # Python process (e.g., `--num-scenarios > 1`), Python's module cache and
        # the PARE registry's `_scenarios_discovered` flag can prevent the updated
        # decorator/class from being re-imported, leading to:
        #   "No scenario registered with ID '<new_id>'"
        # We force a best-effort refresh of just the working module and trigger
        # the registry to re-discover scenarios.
        try:
            from pare.scenarios.utils.registry import registry as pas_registry

            module_name = f"pare.scenarios.{scenarios_dir_name}.{artifact_path.stem}"
            if module_name in sys.modules:
                del sys.modules[module_name]
            importlib.invalidate_caches()
            if hasattr(pas_registry, "_scenarios_discovered"):
                pas_registry._scenarios_discovered = False
        except Exception:
            logger.exception("Failed to refresh PARE scenario registry/module cache before run check")

        logger.info(
            "Running scenario check '%s' for scenario_id='%s' using artifact '%s' via TwoAgentScenarioRunner",
            label,
            scenario_id,
            artifact_path,
        )
        # Use the two-agent demo runner in oracle mode (no LLM calls) to execute
        # the scenario deterministically and obtain a ScenarioValidationResult.
        try:
            validation_result = run_scenarios(
                scenario_names=[scenario_id],
                oracle_mode=True,
                max_turns=None,
                tool_failure_prob=0.0,
                env_events_per_min=0.0,
                env_events_seed=42,
            )
        except Exception as exc:  # pragma: no cover - runtime failure path
            runtime_error = True
            validation_reached = False
            validation_success = False
            passed = False
            # Ensure we always surface a meaningful message, even when the
            # exception has an empty string representation.
            exc_msg = str(exc).strip() or repr(exc)
            feedback = (
                f"[{label}] FAILED run for scenario '{scenario_id}'.\n"
                f"Runtime error while executing scenario via TwoAgentScenarioRunner: {exc_msg}"
            )
            result = RunCheckResult(
                passed=passed,
                feedback=feedback,
                runtime_error=runtime_error,
                validation_reached=validation_reached,
                validation_success=validation_success,
            )
            self._last_check_result = result
            return result

        # `run_demo` returns the ScenarioValidationResult from the runner.
        runtime_error = validation_result.results[0].exception is not None if validation_result.results else False
        validation_reached = True
        validation_success = getattr(validation_result, "passed", 0) > 0

        passed = True
        if runtime_error or (require_validation_success and not validation_success):
            passed = False

        # Build a concise feedback summary; detailed logs are already emitted by
        # the runner and its logging configuration.
        status_line = "SUCCESS" if validation_success else "FAILED"
        rationale = getattr(validation_result, "rationale", None)
        exception = getattr(validation_result, "exception", None)
        export_path = getattr(validation_result, "export_path", None)
        details: list[str] = [f"Validation: {status_line}"]
        if rationale:
            details.append(f"Rationale: {rationale}")
        if exception:
            details.append(f"Exception: {exception}")
        if export_path:
            details.append(f"Trace export path: {export_path}")
        summary = "\n".join(details) if details else "No additional validation details."

        feedback = f"[{label}] {'PARESED' if passed else 'FAILED'} run for scenario '{scenario_id}'.\n{summary}"
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

    def _read_scenario_metadata(self) -> list[dict[str, Any]]:
        """Return the list of stored scenario metadata entries.

        Each entry is a dict that includes at least `description` and
        `timestamp`, plus any additional fields (scenario_id, class_name, apps,
        file_path, etc.). If the metadata file is missing or malformed, an
        empty list is returned.
        """
        existing_text = self._safe_read_text(self.scenario_metadata_path).strip()
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
            "PARES - Scenario registered successfully."
            if registration_ok
            else "FAILED - Scenario did not reach execution phase."
        )

        runtime_summary = "PARES - No runtime errors detected."
        if runtime_error:
            error_lines = [line for line in lines if "ERROR" in line or "Exception" in line]
            snippet = "\n".join(error_lines[:3]) or "\n".join(lines[-5:])
            runtime_summary = f"FAILED - Runtime issues observed:\n{snippet}"

        validation_summary = "NOT RUN - Validation step not reached."
        if validation_reached and validation_success:
            validation_summary = "PARES - ScenarioValidationResult(success=True)."
        elif validation_reached:
            val_line = find_line("ScenarioValidationResult(") or ""
            validation_summary = f"FAILED - {val_line}"

        return "\n".join([
            f"Registration: {registration_summary}",
            f"Runtime: {runtime_summary}",
            f"Validation: {validation_summary}",
        ])

    def _append_scenario_metadata(
        self,
        *,
        scenario_id: str | None,
        class_name: str | None,
        description: str,
    ) -> None:
        """Append a metadata record for the current scenario.

        This captures description, timestamp, apps used, and optional
        identifiers so downstream analysis and uniqueness checks have a single
        source of truth.
        """
        if not description.strip():
            return

        apps_display = (self._prompt_context or {}).get("selected_apps", "")
        apps: list[str] = []
        if apps_display and apps_display not in {"(none)", "(unknown)"}:
            apps = [item.strip() for item in apps_display.split(",") if item.strip()]

        entry: dict[str, Any] = {
            "scenario_id": scenario_id,
            "class_name": class_name,
            "description": description,
            "apps": apps,
            "timestamp": datetime.utcnow().isoformat(),
        }
        existing = self._read_scenario_metadata()
        existing.append(entry)
        self.scenario_metadata_path.parent.mkdir(parents=True, exist_ok=True)
        self.scenario_metadata_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        self._historical_descriptions = existing

    def _persist_failed_scenario(
        self, reason: str, runtime_error: bool = True, validation_reached: bool = False
    ) -> None:
        """Persist failure details under the trajectory directory.

        NOTE: We intentionally do NOT write into `pare/scenario_generator/generated_scenarios/`
        anymore (that directory is noisy to clean up). The working scenario file
        and per-step snapshots already live under the trajectory directory.
        """
        _ = runtime_error
        _ = validation_reached
        # Snapshot the failed working scenario into the trajectory directory so
        # users can inspect the final on-disk contents that caused the failure
        # (e.g., after Step 2/3 guardrails reject the edits).
        try:
            failed_snapshot = self.trajectory_dir / "editable_seed_scenario_failed.py"
            if self.scenario_file.exists():
                shutil.copy2(self.scenario_file, failed_snapshot)
            (self.trajectory_dir / "failure_reason.txt").write_text(f"{reason}\n", encoding="utf-8")
            logger.info("Snapshot for failed scenario written to %s", failed_snapshot)
        except Exception:  # pragma: no cover - trajectory snapshots are best-effort
            logger.exception("Failed to snapshot failed scenario to trajectory directory")

    def _debug_print(self, message: str) -> None:
        logger.info(message)

    @staticmethod
    def _debug_placeholder_content(label: str, detail: str | None = None) -> str:
        detail_block = f"\n{detail}" if detail else ""
        return f"# [DEBUG PLACEHOLDER] {label}{detail_block}"
