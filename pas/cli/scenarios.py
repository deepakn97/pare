"""Scenarios CLI command for listing and generating PAS scenarios."""

from __future__ import annotations

import inspect
import json
import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer
from dotenv import load_dotenv

from pas.benchmark.scenario_loader import (
    Split,
    get_splits_dir,
    load_scenario_ids_from_file,
    load_scenarios_by_split,
    load_scenarios_from_registry,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pas.scenarios import PASScenario

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="scenarios",
    help="List registered PAS scenarios and run the multi-step scenario generator",
    no_args_is_help=True,
)


_SCENARIOS_BASE_DIR = Path(__file__).resolve().parents[1] / "scenarios"
_DEFAULT_BENCHMARK_DIR = _SCENARIOS_BASE_DIR / "benchmark"
_SCENARIO_METADATA_PATH = Path(__file__).resolve().parents[1] / "scenarios" / "scenario_metadata.json"


def _expand_csv_list(values: list[str] | None) -> list[str]:
    if not values:
        return []
    expanded: list[str] = []
    for item in values:
        expanded.extend(part.strip() for part in item.split(",") if part.strip())
    return expanded


def _configured_scenarios_dir_inputs(scenarios_dirs: list[str] | None = None) -> list[str]:
    configured = _expand_csv_list(scenarios_dirs)
    if not configured:
        env_value = os.getenv("PAS_SCENARIOS_DIR", "benchmark")
        configured = [part.strip() for part in env_value.split(",") if part.strip()]
    return list(dict.fromkeys(configured or ["benchmark"]))


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


@dataclass(frozen=True)
class BenchmarkScenarioListing:
    """Lightweight representation of a benchmark scenario for CLI listing/output."""

    scenario_id: str
    class_name: str | None
    file_path: Path
    apps: list[str]
    description: str | None


def _reset_pas_registry_discovery_state() -> None:
    from pas.scenarios import registry

    if hasattr(registry, "_scenarios_discovered"):
        registry._scenarios_discovered = False
    scenarios = getattr(registry, "_scenarios", None)
    if isinstance(scenarios, dict):
        scenarios.clear()


def _resolve_registry_dir_name(scenarios_dir: str | Path) -> tuple[Path, str]:
    raw_dir = Path(scenarios_dir)
    candidate_dir = raw_dir if raw_dir.is_absolute() else _SCENARIOS_BASE_DIR / raw_dir
    resolved_dir = candidate_dir.resolve()
    if not resolved_dir.exists():
        raise typer.BadParameter(f"Scenario directory does not exist: {resolved_dir}")
    if not resolved_dir.is_dir():
        raise typer.BadParameter(f"Scenario directory is not a directory: {resolved_dir}")

    try:
        relative_dir = resolved_dir.relative_to(_SCENARIOS_BASE_DIR.resolve())
    except ValueError as exc:
        raise typer.BadParameter(f"Scenario directory must live under {_SCENARIOS_BASE_DIR}") from exc

    return resolved_dir, relative_dir.as_posix()


@contextmanager
def _temporary_scenarios_dirs(scenarios_dirs: list[str] | None = None) -> Iterator[list[Path]]:
    resolved_dirs_with_names = [
        _resolve_registry_dir_name(dir_input) for dir_input in _configured_scenarios_dir_inputs(scenarios_dirs)
    ]
    resolved_dirs = [path for path, _ in resolved_dirs_with_names]
    scenarios_dir_names = [dir_name for _, dir_name in resolved_dirs_with_names]
    previous_dirs = os.environ.get("PAS_SCENARIOS_DIR")

    try:
        os.environ["PAS_SCENARIOS_DIR"] = ",".join(scenarios_dir_names)
        _reset_pas_registry_discovery_state()
        yield resolved_dirs
    finally:
        if previous_dirs is None:
            os.environ.pop("PAS_SCENARIOS_DIR", None)
        else:
            os.environ["PAS_SCENARIOS_DIR"] = previous_dirs
        _reset_pas_registry_discovery_state()


def _scenario_file_belongs_to_dirs(file_path: Path, scenarios_dirs: list[Path]) -> bool:
    resolved_file = file_path.resolve()
    for scenarios_dir in scenarios_dirs:
        try:
            resolved_file.relative_to(scenarios_dir.resolve())
        except ValueError:
            continue
        else:
            return True
    return False


def _load_registered_scenario_ids(scenarios_dirs: list[str] | None = None) -> list[str]:
    from pas.scenarios import registry

    with _temporary_scenarios_dirs(scenarios_dirs):
        return sorted(registry.get_all_scenarios().keys())


def _load_apps_for_listing(scenario_id: str, scenario: PASScenario, metadata: dict[str, dict[str, Any]]) -> list[str]:
    meta = metadata.get(scenario_id, {})
    apps_from_meta = meta.get("apps") if isinstance(meta, dict) else None
    if isinstance(apps_from_meta, list) and all(isinstance(app, str) for app in apps_from_meta):
        return list(apps_from_meta)

    try:
        scenario.init_and_populate_apps(sandbox_dir=Path("sandbox"))
    except Exception as exc:
        logger.warning("Failed to initialize scenario %s for app listing: %s", scenario_id, exc)
        return []

    apps = getattr(scenario, "apps", None)
    if not isinstance(apps, list):
        return []

    app_names = [app.__class__.__name__ for app in apps]
    return sorted(dict.fromkeys(app_names))


def _load_registered_scenario_listings(scenarios_dirs: list[str] | None = None) -> list[BenchmarkScenarioListing]:
    from pas.scenarios import registry

    metadata = _load_scenario_metadata(_SCENARIO_METADATA_PATH)
    with _temporary_scenarios_dirs(scenarios_dirs) as resolved_dirs:
        scenario_ids = sorted(registry.get_all_scenarios().keys())
        scenarios = list(load_scenarios_from_registry(scenario_ids=scenario_ids))

    listings: list[BenchmarkScenarioListing] = []
    for scenario in scenarios:
        scenario_id = getattr(scenario, "scenario_id", None)
        if not isinstance(scenario_id, str) or not scenario_id:
            logger.warning("Skipping scenario instance without scenario_id: %r", scenario)
            continue

        scenario_class = scenario.__class__
        try:
            file_path = Path(inspect.getfile(scenario_class)).resolve()
        except TypeError:
            logger.warning("Skipping scenario %s because its source file could not be determined", scenario_id)
            continue

        if not _scenario_file_belongs_to_dirs(file_path, resolved_dirs):
            continue

        meta = metadata.get(scenario_id, {})
        description = None
        if isinstance(meta, dict) and isinstance(meta.get("description"), str):
            description = meta["description"].strip() or None
        else:
            class_doc = inspect.getdoc(scenario_class)
            if isinstance(class_doc, str):
                description = class_doc.strip() or None

        listings.append(
            BenchmarkScenarioListing(
                scenario_id=scenario_id,
                class_name=getattr(scenario_class, "__name__", None),
                file_path=file_path,
                apps=_load_apps_for_listing(scenario_id, scenario, metadata),
                description=description,
            )
        )

    return listings


@app.callback(invoke_without_command=True)
def scenarios_root(
    ctx: typer.Context,
    list_only: Annotated[
        bool,
        typer.Option("--list", help="Alias for `pas scenarios list`"),
    ] = False,
    scenarios_dirs: Annotated[
        list[str] | None,
        typer.Option(
            "--scenarios-dir",
            "--benchmark-dir",
            help=(
                "Scenario directories under pas/scenarios/ (repeat or comma-separate). "
                "Defaults to PAS_SCENARIOS_DIR or benchmark."
            ),
        ),
    ] = None,
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
    """Handle root-level shortcuts such as `pas scenarios --list`."""
    if ctx.invoked_subcommand is not None:
        return
    if list_only:
        ctx.invoke(
            list_scenarios,
            scenarios_dirs=scenarios_dirs,
            apps=apps,
            id_contains=id_contains,
            limit=limit,
            as_json=as_json,
        )
        return
    typer.echo(ctx.get_help())


def _scenario_to_listing(scenario: PASScenario, metadata: dict[str, dict[str, Any]]) -> BenchmarkScenarioListing:
    scenario_id = str(getattr(scenario, "scenario_id", "")).strip()
    scenario_class = scenario.__class__
    file_path = Path(inspect.getfile(scenario_class)).resolve()
    meta = metadata.get(scenario_id, {})

    description = None
    if isinstance(meta, dict) and isinstance(meta.get("description"), str):
        description = meta["description"].strip() or None
    else:
        class_doc = inspect.getdoc(scenario_class)
        if isinstance(class_doc, str):
            description = class_doc.strip() or None

    return BenchmarkScenarioListing(
        scenario_id=scenario_id,
        class_name=getattr(scenario_class, "__name__", None),
        file_path=file_path,
        apps=_load_apps_for_listing(scenario_id, scenario, metadata),
        description=description,
    )


def _emit_listings(listings: list[BenchmarkScenarioListing], *, as_json: bool) -> None:
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


@app.command("list")
def list_scenarios(
    scenarios_dirs: Annotated[
        list[str] | None,
        typer.Option(
            "--scenarios-dir",
            "--benchmark-dir",
            help=(
                "Scenario directories under pas/scenarios/ (repeat or comma-separate). "
                "Defaults to PAS_SCENARIOS_DIR or benchmark."
            ),
        ),
    ] = None,
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
    """List registered PAS scenarios from configured scenario directories."""
    listings = _load_registered_scenario_listings(scenarios_dirs)

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

    _emit_listings(listings, as_json=as_json)


@app.command("split")
def list_split_scenarios(
    split: Annotated[
        Split,
        typer.Option("--split", help="Benchmark split to list"),
    ] = Split.FULL,
    scenarios_dirs: Annotated[
        list[str] | None,
        typer.Option(
            "--scenarios-dir",
            "--benchmark-dir",
            help=(
                "Scenario directories under pas/scenarios/ (repeat or comma-separate). "
                "Defaults to PAS_SCENARIOS_DIR or benchmark."
            ),
        ),
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
    """List scenarios referenced by a benchmark split file."""
    metadata = _load_scenario_metadata(_SCENARIO_METADATA_PATH)
    with _temporary_scenarios_dirs(scenarios_dirs):
        scenarios = list(load_scenarios_by_split(split=split, limit=limit))
    listings = [_scenario_to_listing(scenario, metadata) for scenario in scenarios]
    _emit_listings(listings, as_json=as_json)


@app.command("check-ids-file")
def check_ids_file(
    file_path: Annotated[
        Path,
        typer.Argument(help="Path to a file containing one scenario ID per line"),
    ],
    scenarios_dirs: Annotated[
        list[str] | None,
        typer.Option(
            "--scenarios-dir",
            "--benchmark-dir",
            help=(
                "Scenario directories under pas/scenarios/ (repeat or comma-separate). "
                "Defaults to PAS_SCENARIOS_DIR or benchmark."
            ),
        ),
    ] = None,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Validate that scenario IDs from a file exist in the configured PAS scenario directories."""
    scenario_ids = load_scenario_ids_from_file(file_path)
    configured_dirs = _configured_scenarios_dir_inputs(scenarios_dirs)
    registered_ids = set(_load_registered_scenario_ids(scenarios_dirs))
    present = [scenario_id for scenario_id in scenario_ids if scenario_id in registered_ids]
    missing = [scenario_id for scenario_id in scenario_ids if scenario_id not in registered_ids]

    if as_json:
        typer.echo(
            json.dumps(
                {
                    "file": str(file_path),
                    "scenarios_dirs": configured_dirs,
                    "total_ids": len(scenario_ids),
                    "present_ids": present,
                    "missing_ids": missing,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        if missing:
            raise typer.Exit(code=1)
        return

    typer.echo(f"Checked {len(scenario_ids)} scenario IDs from {file_path}")
    typer.echo(f"Scenario directories: {', '.join(configured_dirs)}")
    typer.echo(f"Present: {len(present)}")
    typer.echo(f"Missing: {len(missing)}")
    if missing:
        typer.echo("Missing IDs:")
        for scenario_id in missing:
            typer.echo(f"- {scenario_id}")
        raise typer.Exit(code=1)


@app.command("splits")
def show_splits_info(
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Show the benchmark splits directory and available split files."""
    splits_dir = get_splits_dir()
    available = sorted(path.stem for path in splits_dir.glob("*.txt")) if splits_dir.exists() else []

    if as_json:
        typer.echo(
            json.dumps({"splits_dir": str(splits_dir), "available_splits": available}, indent=2, ensure_ascii=False)
        )
        return

    typer.echo(f"Splits directory: {splits_dir}")
    typer.echo(f"Available splits: {', '.join(available) if available else '(none found)'}")


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
