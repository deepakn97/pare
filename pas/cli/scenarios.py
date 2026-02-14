"""Scenarios CLI command for listing and generating PAS scenarios."""

from __future__ import annotations

import ast
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="scenarios",
    help="List available benchmark scenarios and run the multi-step scenario generator",
    no_args_is_help=True,
)


_DEFAULT_BENCHMARK_DIR = Path(__file__).resolve().parents[1] / "scenarios" / "benchmark"
_SCENARIO_METADATA_PATH = Path(__file__).resolve().parents[1] / "scenarios" / "scenario_metadata.json"


def _expand_csv_list(values: list[str] | None) -> list[str]:
    if not values:
        return []
    expanded: list[str] = []
    for item in values:
        expanded.extend(part.strip() for part in item.split(",") if part.strip())
    return expanded


def _load_scenario_metadata(path: Path) -> dict[str, dict[str, Any]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse scenario metadata JSON at %s: %s", path, exc)
        return {}
    if not isinstance(raw, list):
        return {}
    mapping: dict[str, dict[str, Any]] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        scenario_id = entry.get("scenario_id")
        if isinstance(scenario_id, str) and scenario_id:
            mapping[scenario_id] = entry
    return mapping


def _decorator_name(expr: ast.expr) -> str | None:
    """Return decorator function name for `@name(...)` or `@mod.name(...)`."""
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        return expr.attr
    return None


@dataclass(frozen=True)
class BenchmarkScenarioListing:
    """Lightweight representation of a benchmark scenario for CLI listing/output."""

    scenario_id: str
    class_name: str | None
    file_path: Path
    apps: list[str]
    description: str | None


_APP_TOKEN_RE = re.compile(r"\b(Stateful[A-Za-z0-9_]+App|PASAgentUserInterface|HomeScreenSystemApp)\b")


def _extract_scenarios_from_file(  # noqa: C901
    py_file: Path, metadata: dict[str, dict[str, Any]]
) -> list[BenchmarkScenarioListing]:
    source = py_file.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(py_file))
    except SyntaxError as exc:
        logger.warning("Skipping %s due to syntax error: %s", py_file, exc)
        return []

    results: list[BenchmarkScenarioListing] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        scenario_id: str | None = None
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            name = _decorator_name(decorator.func)
            if name != "register_scenario":
                continue
            if not decorator.args:
                continue
            first = decorator.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                scenario_id = first.value
                break
        if not scenario_id:
            continue

        meta = metadata.get(scenario_id, {})
        apps_from_meta = meta.get("apps") if isinstance(meta, dict) else None
        if isinstance(apps_from_meta, list) and all(isinstance(a, str) for a in apps_from_meta):
            apps = list(apps_from_meta)
        else:
            apps = sorted(set(_APP_TOKEN_RE.findall(source)))

        doc = ast.get_docstring(node)
        description = None
        if isinstance(meta, dict) and isinstance(meta.get("description"), str):
            description = meta["description"].strip() or None
        elif isinstance(doc, str):
            description = doc.strip() or None

        results.append(
            BenchmarkScenarioListing(
                scenario_id=scenario_id,
                class_name=node.name or None,
                file_path=py_file,
                apps=apps,
                description=description,
            )
        )
    return results


def _load_benchmark_scenarios(benchmark_dir: Path) -> list[BenchmarkScenarioListing]:
    metadata = _load_scenario_metadata(_SCENARIO_METADATA_PATH)
    if not benchmark_dir.exists():
        raise typer.BadParameter(f"Benchmark directory does not exist: {benchmark_dir}")

    listings: list[BenchmarkScenarioListing] = []
    for py_file in sorted(benchmark_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        listings.extend(_extract_scenarios_from_file(py_file, metadata))
    return listings


@app.command("list")
def list_scenarios(  # noqa: C901
    benchmark_dir: Annotated[
        Path,
        typer.Option("--benchmark-dir", help="Directory containing benchmark scenario .py files"),
    ] = _DEFAULT_BENCHMARK_DIR,
    apps: Annotated[
        list[str] | None,
        typer.Option("--apps", "-a", help="Filter by required apps (repeat or comma-separate)"),
    ] = None,
    id_contains: Annotated[
        str | None,
        typer.Option("--id-contains", help="Only include scenario_ids containing this substring"),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option("--limit", help="Optional limit on number of results shown"),
    ] = None,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """List all scenarios under `pas/scenarios/benchmark` with optional filters."""
    listings = _load_benchmark_scenarios(benchmark_dir)

    required_apps = set(_expand_csv_list(apps))
    if id_contains:
        needle = id_contains.lower()
        listings = [s for s in listings if needle in s.scenario_id.lower()]

    if required_apps:
        filtered: list[BenchmarkScenarioListing] = []
        for item in listings:
            item_apps = set(item.apps)
            if required_apps.issubset(item_apps):
                filtered.append(item)
        listings = filtered

    if limit is not None:
        listings = listings[: max(0, limit)]

    if as_json:
        payload = [
            {
                "scenario_id": s.scenario_id,
                "class_name": s.class_name,
                "file": str(s.file_path),
                "apps": s.apps,
                "description": s.description,
            }
            for s in listings
        ]
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    if not listings:
        typer.echo("No scenarios found.")
        return

    for item in listings:
        if item.class_name:
            header = f"Scenario ID: {item.scenario_id}  |  Class Name: {item.class_name}"
        else:
            header = f"Scenario ID: {item.scenario_id}"
        typer.echo(header)
        typer.echo(f"  File Path: {item.file_path}")
        typer.echo(f"  Apps used: {', '.join(item.apps) if item.apps else '(unknown)'}")
        if item.description:
            first_line = item.description.splitlines()[0].strip()
            if first_line:
                typer.echo(f"  Description: {first_line}")
        typer.echo("")


@app.command()
def generate(  # noqa: C901
    output_dir: Annotated[
        Path | None,
        typer.Option("--output-dir", help="Directory where intermediate step files should be written"),
    ] = None,
    model: Annotated[
        str,
        typer.Option("--model", help="(Currently unused) Kept for parity with legacy generator CLI"),
    ] = "gpt-5-mini-2025-08-07",
    provider: Annotated[
        str,
        typer.Option("--provider", help="(Currently unused) Kept for parity with legacy generator CLI"),
    ] = "openai",
    endpoint: Annotated[
        str | None,
        typer.Option("--endpoint", help="(Currently unused) Optional custom endpoint for the provider"),
    ] = None,
    max_iterations: Annotated[
        int,
        typer.Option("--max-iterations", help="Maximum number of attempts per step"),
    ] = 2,
    resume_from_step2: Annotated[
        bool,
        typer.Option("--resume-from-step2", help="[DEPRECATED] Prefer --resume-from-step step2"),
    ] = False,
    resume_from_step: Annotated[
        str | None,
        typer.Option("--resume-from-step", help="Resume from a specific step (step2|step3|step4)"),
    ] = None,
    trajectory_dir: Annotated[
        Path | None,
        typer.Option(
            "--trajectory-dir", help="Optional path to an existing trajectory dir (or base dir for multiple runs)"
        ),
    ] = None,
    num_scenarios: Annotated[
        int,
        typer.Option("--num-scenarios", help="Number of distinct scenarios to generate in this invocation"),
    ] = 1,
    debug_prompts: Annotated[
        bool,
        typer.Option("--debug-prompts", help="If set, skip LLM calls and print prompts for all agents instead"),
    ] = False,
    apps: Annotated[
        list[str] | None,
        typer.Option(
            "--apps",
            "-a",
            help=(
                "Explicit list of app class names to include (repeat or comma-separate). "
                "PASAgentUserInterface and HomeScreenSystemApp are always available."
            ),
        ),
    ] = None,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Output results as JSON (compact by default)"),
    ] = False,
    full_json: Annotated[
        bool,
        typer.Option("--full-json", help="When using --json, include large fields like step conversations"),
    ] = False,
) -> None:
    """Run the multi-step scenario generator."""
    from pas.scenarios.generator.agent.scenario_generating_agent_orchestrator import ScenarioGeneratingAgentOrchestrator
    from pas.scenarios.generator.scenario_generator import determine_selected_apps, prepare_prompt_context_data
    from pas.scenarios.generator.utils.apps_init_instructions import ScenarioWithAllPASApps

    logging.basicConfig(level=logging.INFO)

    # For now, the multi-step generator uses Claude Agent SDK and ignores model/provider/endpoint.
    if model or provider or endpoint:
        logger.debug(
            "Generator CLI params (currently unused): model=%s provider=%s endpoint=%s", model, provider, endpoint
        )

    if resume_from_step is not None and resume_from_step not in {"step2", "step3", "step4"}:
        raise typer.BadParameter("--resume-from-step must be one of: step2, step3, step4")

    # Load environment variables (keys, etc.).
    load_dotenv()

    requested_apps = (
        _expand_csv_list(apps)
        if apps is not None
        else [
            "StatefulMessagingApp",
            "StatefulContactsApp",
            "StatefulCalendarApp",
            "StatefulEmailApp",
        ]
    )

    app_def_scenario = ScenarioWithAllPASApps()
    app_def_scenario.initialize()
    app_instances = {app.__class__.__name__: app for app in getattr(app_def_scenario, "apps", [])}
    selected_apps = determine_selected_apps(app_instances, requested_apps)
    if not selected_apps:
        logger.warning("No selectable apps found; continuing with system apps only.")
    prompt_context = prepare_prompt_context_data(app_def_scenario, selected_apps)

    if resume_from_step2 and resume_from_step is None:
        logger.warning("--resume-from-step2 is deprecated; prefer --resume-from-step step2 instead.")

    total = max(1, num_scenarios)
    results: list[dict[str, Any]] = []
    for idx in range(total):
        run_trajectory_dir = trajectory_dir
        if trajectory_dir is not None and total > 1:
            run_trajectory_dir = trajectory_dir / f"run_{idx + 1}"

        agent = ScenarioGeneratingAgentOrchestrator(
            output_dir=output_dir,
            max_iterations=max_iterations,
            trajectory_dir=run_trajectory_dir,
            prompt_context=prompt_context,
            debug_prompts=debug_prompts,
            resume_from_step2=resume_from_step2,
            resume_from_step=resume_from_step,
        )
        try:
            result = agent.run()
        except Exception as exc:
            logger.exception("Scenario generation failed for run %s/%s.", idx + 1, total)
            results.append({
                "run_index": idx + 1,
                "status": "failed",
                "error": str(exc),
                "trajectory_dir": str(run_trajectory_dir) if run_trajectory_dir is not None else None,
            })
            continue

        results.append({
            "run_index": idx + 1,
            "status": "success",
            **result,
        })

    if as_json:
        payload: list[dict[str, Any]] = []
        for item in results:
            if full_json:
                payload.append(item)
                continue
            # Drop extremely large fields (notably step agent conversations/prompts)
            compact = dict(item)
            step_results = compact.get("step_results")
            if isinstance(step_results, list):
                compact_steps: list[Any] = []
                for step in step_results:
                    if isinstance(step, dict):
                        s = dict(step)
                        s.pop("conversation", None)
                        compact_steps.append(s)
                    else:
                        # StepResult dataclass / object: best-effort string, but avoid exploding logs
                        compact_steps.append(str(step))
                compact["step_results"] = compact_steps
            compact.pop("conversation", None)
            payload.append(compact)
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    else:
        failed = [r for r in results if r.get("status") != "success"]
        typer.echo(f"Completed {total} scenario runs: {total - len(failed)} success, {len(failed)} failed.")
        for item in results:
            trajectory = item.get("trajectory_dir")
            trajectory_suffix = f" (trajectory_dir={trajectory})" if trajectory else ""
            typer.echo(f"- run {item.get('run_index')}: {item.get('status')}{trajectory_suffix}")

    if any(r.get("status") != "success" for r in results):
        raise typer.Exit(code=1)
