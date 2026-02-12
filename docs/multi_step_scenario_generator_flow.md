### Multi-Step Scenario Generator: Code Execution Flow

This document describes the **code-level execution flow** for the multi-step scenario generator, starting from the CLI entry point and following each method/class involved in the pipeline.

The examples assume a command like:

```bash
python -m pas.scenarios.generator.scenario_generator \
  --debug-prompts \
  --max-iterations 3
```

The `--resume-from-step` flag only changes which steps are *skipped* or *resumed from disk*; the structural call graph remains the same.

---

### 1. Entry Point: `scenario_generator.py`

**Module:** `pas.scenarios.generator.scenario_generator`
**Function:** `main()`

1. **Argument parsing**
   - Builds an `argparse.ArgumentParser` with flags:
     - `--output-dir`
     - `--max-iterations`
     - `--resume-from-step2` (**deprecated**)
     - `--resume-from-step` (`step2 | step3 | step4`)
     - `--debug-prompts`
     - `--apps` (selected app class names)
   - Example snippet:
     - Parser creation and flags: `main()`
     - Parsed values: `args = parser.parse_args()`

2. **App definition scenario & prompt context**
   - Instantiates `ScenarioWithAllPASApps` and calls `initialize()` to construct a canonical set of app instances for prompt context.
   - Builds `app_instances` from `scenario.apps`.
   - Calls:
     - `determine_selected_apps(app_instances, args.selected_apps)`
     - `prepare_prompt_context_data(app_def_scenario, selected_apps)`
   - The resulting `prompt_context` dict is later passed into the orchestrator and into `configure_dynamic_context(...)` to materialize the dynamic prompt blocks.

3. **Orchestrator construction**
   - Creates the orchestrator:

   ```python
   agent = MultiStepScenarioGeneratingAgentsOrchestrator(
       output_dir=args.output_dir,
       max_iterations=args.max_iterations,
       prompt_context=prompt_context,
       debug_prompts=args.debug_prompts,
       resume_from_step2=args.resume_from_step2,
       resume_from_step=args.resume_from_step,
   )
   ```

4. **Pipeline execution**
   - Calls `result = agent.run()`.
   - Serializes the returned dict to JSON for the CLI output.

---

### 2. Orchestrator Setup: `ScenarioGeneratingAgentOrchestrator.__init__`

**Module:** `pas.scenarios.generator.agent.scenario_generating_agent_orchestrator`
**Class:** `ScenarioGeneratingAgentOrchestrator`

Key responsibilities:

1. **Path and repo setup**
   - Computes `base_dir` (scenario generator root) and `self.repo_root`.
   - Sets:
     - `self.output_dir` (CLI `--output-dir`; defaults to `base_dir / "generated_scenarios"`).
     - `self.scenario_file` (single working file that Claude edits, now under `pas/scenarios/default_generation_output/editable_seed_scenario.py`).
     - `self.generated_dir`, `success_dir`, `failed_dir`, `failed_no_runtime_dir`.
     - `self.scenario_metadata_path` (`pas/scenarios/scenario_metadata.json`) which stores description, apps used, and other metadata for each scenario.

2. **Filesystem policy for Claude Agent SDK**
   - Builds `ClaudeFilesystemConfig`:
     - `read_only_roots = [self.repo_root]`
     - `editable_files = [self.scenario_file]` (only `editable_seed_scenario.py` is writable).
   - This is wired into the `ClaudeAgentRuntimeConfig` objects and enforced via a `PreToolUse` hook in `claude_backend.py` so that only `Write(file_path=editable_seed_scenario.py)` is allowed.

3. **Per-step Claude runtime configuration**
   - Constructs three `ClaudeAgentRuntimeConfig` instances:
     - `_claude_config_uniqueness` (Step 0): `allowed_tools=["Read"]`
     - `_claude_config_step1` (Step 1): `allowed_tools=["Read"]`
     - `_claude_config_code_steps` (Steps 2–4): `allowed_tools=["Read", "Write"]`
   - All share the same `cwd=self.repo_root` and `filesystem=self.claude_filesystem_config`.

4. **Prompt context wiring**
   - If `prompt_context` is provided:

   ```python
   configure_dynamic_context(**prompt_context)
   ```

   - This mutates module-level globals in `prompts.py` to embed:
     - Selected apps
     - Import instructions
     - Allowed tool APIs
     - App initialization blueprint

5. **Seed template configuration**
   - Uses the canonical seed template with template markers:

   ```python
   self.seed_template_path = base_dir / "example_proactive_scenarios" / "original_seed_scenario.py"
   self.seed_template_text = self._safe_read_text(self.seed_template_path)
   ```

   - Template is **read-only**; `editable_seed_scenario.py` is the working copy.

6. **Step agents**
   - Instantiates:
     - `ScenarioUniquenessCheckAgent`
     - Four configured instances of `StepEditAgent`:
       - Step 1 (Scenario Description): `step_kind="description"`
       - Step 2 (Apps & Data Setup): `step_kind="apps_and_data"`
       - Step 3 (Events Flow): `step_kind="events_flow"`
       - Step 4 (Validation): `step_kind="validation"`
   - Each `StepEditAgent` instance receives:
     - A step-specific system prompt from `prompts.py`.
     - `max_iterations`
     - `debug_prompts`
     - The appropriate `ClaudeAgentRuntimeConfig`.

---

### 3. High-Level Pipeline: `ScenarioGeneratingAgentOrchestrator.run`

**Method:** `ScenarioGeneratingAgentOrchestrator.run(self) -> dict[str, Any]`
**Decorator:** `# noqa: C901` (complex, but intentionally centralized)

#### 3.1. Resume mode selection

- Reads `self.resume_from_step` (normalized from CLI flags).
- `resume_mode in {"step2", "step3", "step4"}`:
  - Step 1 description is loaded via `_load_existing_step1_result(step1_path)`.
- Else:
  - Step 1 is run fresh (see below).

#### 3.2. Step 1 – Scenario Description

1. **When not resuming from step2/3/4:**

   - Defines a trivial `step1_check` that always passes (Step 1 only influences `valid_descriptions.json`).
   - Calls:

   ```python
   history_block = self.uniqueness_agent.get_recent_history()
   step1 = self.step1_agent.run(
       historical_descriptions=history_block,
       check_callback=step1_check if not debug_prompts else None,
   )
   ```

2. **Internals – `ScenarioDescriptionAgent.run`**

   - Builds `user_prompt = SCENARIO_DESCRIPTION_USER_PROMPT.format(...)`.
   - Delegates to `BaseStepAgent._run_with_prompt(...)`.

3. **`BaseStepAgent._run_with_prompt` flow (common to all steps)**

   - Builds the conversation:

     ```python
     conversation = [
         {"role": "system", "content": self.system_prompt},
         {"role": "user", "content": user_prompt},
     ]
     ```

   - For each `iteration` up to `max_iterations`:
     1. Calls `response = self._invoke_llm(conversation, iteration)`.
     2. If a `uniqueness_agent` is attached (only Step 1):
        - Calls `uniqueness_agent.evaluate(response)` and may append feedback and retry.
     3. Calls the step-specific `check_callback(response, iteration)` (for Steps 2–4 this runs scenario checks).
     4. If `check_passed` is `False`, appends feedback as a new user turn and loops.
     5. On success, returns a `StepResult` with:
        - `content` (raw Claude text),
        - `iterations` used,
        - `notes` (e.g. uniqueness verdict, check feedback),
        - full conversation transcript.

4. **LLM plumbing – `BaseStepAgent._invoke_llm` → `run_claude_conversation`**

   - For every step, `_invoke_llm` simply calls:

   ```python
   return run_claude_conversation(
       conversation,
       system_prompt=self.system_prompt,
       config=self._claude_config,
       step_tag=self.name,
       iteration=iteration,
   )
   ```

   - `run_claude_conversation` (in `claude_backend.py`) wraps the synchronous API over:
     - `ClaudeSDKClient`
     - `ClaudeAgentOptions` with:
       - `system_prompt`
       - `permission_mode`
       - `cwd`
       - `allowed_tools`
       - `hooks` (`PreToolUse` guard for filesystem).
     - It streams `AssistantMessage` blocks and concatenates all `TextBlock.text` values into the final string response.
   - This is where the Agent SDK is actually invoked; everything else is orchestration and validation.

5. **Post-Step 1**
   - On success, `_append_scenario_metadata(...)` stores a metadata record (scenario id, class name, description, apps used, timestamp) in `scenario_metadata.json` as a new historical entry.

#### 3.3. Step 2 – Apps & Data Setup

1. **Resume behavior**
   - If `resume_mode in {"step3", "step4"}`:
     - Skips generation, reads `editable_seed_scenario.py` from disk, and wraps it in a `StepResult` named `"Step 2: Apps & Data Setup (resumed)"`.

2. **Fresh Step 2 run**

   - Seeds the working file from the pristine template:

   ```python
   if not self.debug_prompts and self.seed_template_text:
       self.scenario_file.write_text(self.seed_template_text, encoding="utf-8")
       scenario_seed_content = self.seed_template_text
   else:
       scenario_seed_content = self._get_or_initialize_scenario_file()
   ```

   - Defines `step2_check`:

   ```python
   def step2_check(code: str, iteration: int) -> tuple[bool, str]:
       self._write_output(
           content=code,
           path=self.scenario_file,
           header="Step 2 - init_and_populate_apps plan",
           append=False,
           include_header=False,
       )
       result = self._run_step_check("apps-data-check", self.scenario_file)
       return result.passed, result.feedback
   ```

   - Calls:

   ```python
   step2 = self.step2_agent.run(
       scenario_description=step1.content,
       scenario_file_path=str(self.scenario_file),
       scenario_file_contents=sceanrio_seed_content,
       check_callback=step2_check,
   )
   ```

3. **`_write_output` and template trimming**

   - `self._write_output` normalizes the content and, if writing to `self.scenario_file`, strips any text outside the seed template:

   ```python
   if path == self.scenario_file:
       normalized = self._strip_outside_template_markers(normalized)
   ```

   - This keeps only the region between:
     - `"""start of the template to build scenario for Proactive Agent."""`
     - `"""end of the template to build scenario for Proactive Agent."""`

4. **Scenario check – `_run_step_check("apps-data-check", ...)`**

   - Reads the Python file, extracts `scenario_id` via `_extract_scenario_id(...)`.
   - Constructs a `python -m ... utils/run_scenario.py` command with:
     - `-s scenario_id`
     - `--temp-file` pointing at `editable_seed_scenario.py`
     - Provider `"mock"`.
   - Runs it via `subprocess.run`, captures stdout/stderr.
   - Analyzes:
     - Registration status,
     - Runtime errors,
     - Validation reach/success.
   - Returns a `RunCheckResult` with a summarized feedback string; this feeds into:
     - `step2_check` → `BaseStepAgent._run_with_prompt` → Step 2 retries or succeeds.

5. **Snapshot after Step 2**
   - On success, `self._snapshot_scenario("step2")` copies:
     - `editable_seed_scenario.py` → `editable_seed_scenario_step2.py`

#### 3.4. Step 3 – Events Flow

1. **Resume behavior**
   - If `resume_mode == "step4"`:
     - Skips Step 3 generation and reads current `editable_seed_scenario.py` as `"Step 3: Events Flow (resumed)"`.

2. **Fresh Step 3 run**

   - Defines `step3_check` with a **shape guard**:

   ```python
   def step3_check(code: str, iteration: int) -> tuple[bool, str]:
       # Guardrail: don't let natural-language thoughts clobber the scenario file.
       if not self._looks_like_complete_scenario(code):
           feedback = (
               "[events-flow-check] Your previous reply did not look like a "
               "complete Python scenario file. Reply with ONLY the full updated "
               "file contents between the template markers, with no natural-language explanation."
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
   ```

   - Calls:

   ```python
   step3 = self.step3_agent.run(
       scenario_description=step1.content,
       apps_and_data=step2.content,
       scenario_file_contents=scenario_after_step2,
       check_callback=step3_check,
   )
   ```

3. **Snapshot after Step 3**
   - On success, `_snapshot_scenario("step3")`:
     - `editable_seed_scenario.py` → `editable_seed_scenario_step3.py`

#### 3.5. Step 4 – Validation

1. **Validation check with shape guard**

   - `step4_check` mirrors Step 3’s guard to prevent natural-language-only responses:

   ```python
   def step4_check(code: str, iteration: int) -> tuple[bool, str]:
       if not self._looks_like_complete_scenario(code):
           feedback = (
               "[validation-check] Your previous reply did not look like a "
               "complete Python scenario file. Reply with ONLY the full updated "
               "file contents between the template markers, with no natural-language explanation."
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
   ```

2. **Step 4 agent run**

   - Calls:

   ```python
   step4 = self.step4_agent.run(
       scenario_description=step1.content,
       events_flow=step3.content,
       scenario_file_contents=scenario_after_step3,
       check_callback=step4_check,
   )
   ```

3. **Persist success / failure**
   - On full success:
     - `_persist_scenario(self.success_dir)` copies `editable_seed_scenario.py` into `successful_scenarios/scenario_<timestamp>.py`.
   - On exceptions:
     - `_persist_failed_scenario(reason, runtime_error, validation_reached)` appends a failure reason to `editable_seed_scenario.py` and copies it into:
       - `failed_scenarios/` (runtime errors) or
       - `failed_scenarios_no_runtime_errors/` (validation-only failures).

---

### 4. Step Agent Responsibilities (`step_agents.py`)

Each concrete step agent (`ScenarioDescriptionAgent`, `AppsAndDataSetupAgent`, `EventsFlowAgent`, `ValidationAgent`) is a thin wrapper around `BaseStepAgent`. Their core responsibilities are:

- **Selecting the correct system prompt** (from `prompt_context`, i.e., `prompts.py`).
- **Building the user prompt** with the appropriate inputs:
  - Step 1: `historical_descriptions`
  - Step 2: `scenario_description`, `scenario_file_path`, `scenario_file_contents`
  - Step 3: `scenario_description`, `apps_and_data`, `scenario_file_contents`
  - Step 4: `scenario_description`, `events_flow`, `scenario_file_contents`
- **Delegating to `_run_with_prompt(...)`** with the step-specific `check_callback` provided by the orchestrator.

They do **not** perform any file I/O or scenario execution themselves; those responsibilities are centralized in the orchestrator helpers:

- `_write_output`
- `_run_step_check`
- `_snapshot_scenario`
- `_persist_scenario` / `_persist_failed_scenario`

---

### 5. Summary: End-to-End Flow (Code-Centric)

1. `python -m pas.scenarios.generator.scenario_generator`
   → `main()` parses args, prepares `prompt_context`, constructs `ScenarioGeneratingAgentOrchestrator`.

2. `ScenarioGeneratingAgentOrchestrator.__init__`
   → Configures paths, Claude filesystem policy, per-step runtime configs, dynamic prompts, and step agents.

3. `orchestrator.run()`:
   - Step 1:
     - `ScenarioDescriptionAgent.run` → `_run_with_prompt` → `run_claude_conversation` → Claude Agent SDK.
   - Step 2:
     - Seed `editable_seed_scenario.py` from `original_seed_scenario.py`.
     - `AppsAndDataSetupAgent.run` → `_run_with_prompt` with `step2_check`.
     - `step2_check` → `_write_output` → `_run_step_check("apps-data-check")` → `run_scenario.py`.
     - Snapshot `editable_seed_scenario_step2.py`.
   - Step 3:
     - `EventsFlowAgent.run` → `_run_with_prompt` with `step3_check`.
     - `step3_check` validates response shape, writes, then `_run_step_check("events-flow-check")`.
     - Snapshot `editable_seed_scenario_step3.py`.
   - Step 4:
     - `ValidationAgent.run` → `_run_with_prompt` with `step4_check`.
     - `step4_check` validates response shape, writes, then `_run_step_check("validation-check", require_validation_success=True)`.
   - On success: `_persist_scenario(success_dir)`; on failure: `_persist_failed_scenario(...)`.

This flow ensures:

- **Claude Agent SDK** is the only component that interacts with the model and filesystem tools (`Read`, `Write`).
- **The orchestrator** owns all coordination, file writes, and scenario checks.
- **Step agents** focus purely on building prompts, interpreting feedback, and retrying within the configured iteration budget.
