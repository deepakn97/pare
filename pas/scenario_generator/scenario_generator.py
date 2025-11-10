import argparse
import ast
import json
import logging
import sys

from are.simulation.agents.are_simulation_agent_config import LLMEngineConfig
from are.simulation.agents.llm.llm_engine_builder import LLMEngineBuilder
from are.simulation.scenarios import Scenario

from pas.scenario_generator.agent.scenario_generating_agent import ScenarioGeneratingAgent
from pas.scenario_generator.agent.seed_scenario_generating_agent import SeedScenarioGeneratingAgent
from pas.scenario_generator.utils.list_all_app_imports import make_import_instructions, scan_package

logger = logging.getLogger(__name__)


def generate_scenarios_from_example(
    scenario_list: list[Scenario], model: str, provider: str | None = None, endpoint: str | None = None
) -> str | None:
    """Runner that builds the "scenario_generator" agent and runs it once to write new scenario.py files based on the provided scenario class."""
    # scan the apps package and make the import instructions
    # 1) Build catalog once per run (fast; static; safe)
    catalog = scan_package("are.simulation.apps", include_sigs=True, doclen=140)
    # 2) Create import instructions text (token-bounded)
    import_instructions = make_import_instructions(catalog, max_mods=18, max_per_mod=10, include_sigs=True)

    # 3) Augment with imports extracted from the input scenario modules
    extracted = _extract_imports_from_scenarios(scenario_list)
    logger.info(f"==== Extracted imports: {extracted}")
    if extracted:
        import_instructions = (
            import_instructions + "\n\n# Additional imports found in input scenarios\n" + "\n".join(sorted(extracted))
        )
    logger.info(f"Import instructions: {import_instructions}")

    # Create LLM engine
    config = LLMEngineConfig(model_name=model, provider=provider, endpoint=endpoint)
    engine = LLMEngineBuilder().create_engine(engine_config=config)

    # Create a minimal BaseAgent configured for scenario generation (no repo config types)
    # Wire minimal generator (no BaseAgent needed)
    gen_agent = ScenarioGeneratingAgent(
        llm_engine=engine, tools=[], max_iterations=15, import_instructions=import_instructions
    )

    logger.info("Running minimal scenario generator agent")
    # result = None
    result = gen_agent.scenario_generation_run(scenario_list)
    logger.info("Scenario generation completed")
    if result is not None:
        return result.output
    else:
        return None


def generate_scenarios_from_example_seed(
    app_def_scenario: Scenario,
    example_scenarios: list[Scenario],
    model: str,
    provider: str | None = None,
    endpoint: str | None = None,
    total_scenarios: int = 1,
    apps_per_scenario: int = 4,
    selected_apps: list[str] | None = None,
) -> str | None:
    """Runner that builds the SeedScenarioGeneratingAgent and generates scenarios using only tools from the app definition scenario.

    Args:
        app_def_scenario: Scenario that defines the available apps and tools
        example_scenarios: List of example scenarios for reference (not used for tools)
        model: LLM model to use
        provider: Provider to use
        endpoint: Optional endpoint URL
        total_scenarios: Number of scenarios to generate
        apps_per_scenario: Number of apps to use per scenario

    Args:
        selected_apps: Optional explicit app class names to use for all scenarios. When provided,
            bypasses app combination generation and always uses this set.

    Returns:
        Generated scenario code or None if generation failed
    """
    # Get tools from the app definition scenario (not from example scenarios)
    catalog = scan_package("are.simulation.apps", include_sigs=True, doclen=140)
    import_instructions = make_import_instructions(catalog, max_mods=18, max_per_mod=10, include_sigs=True)

    # Extract imports from app definition scenario and example scenarios
    extracted = _extract_imports_from_scenarios([app_def_scenario, *example_scenarios])
    logger.info(f"==== Extracted imports: {extracted}")
    if extracted:
        import_instructions = (
            import_instructions
            + "\n\n# Additional imports found in app definition and example scenarios\n"
            + "\n".join(sorted(extracted))
        )
    logger.info(f"Import instructions: {import_instructions}")

    # Create LLM engine
    config = LLMEngineConfig(model_name=model, provider=provider, endpoint=endpoint)
    engine = LLMEngineBuilder().create_engine(engine_config=config)

    # Create SeedScenarioGeneratingAgent with tools from app definition scenario only
    seed_agent = SeedScenarioGeneratingAgent(
        llm_engine=engine,
        tools=[],
        max_iterations=15,
        import_instructions=import_instructions,
        app_def_scenario=app_def_scenario,
    )

    logger.info("Running SeedScenarioGeneratingAgent")
    result = seed_agent.scenario_generation_run(
        example_scenarios,
        app_def_scenario,
        total_scenarios=total_scenarios,
        apps_per_scenario=apps_per_scenario,
        selected_apps=selected_apps,
    )
    logger.info("Seed scenario generation completed")
    if result is not None:
        return result.output
    else:
        return None


__all__ = ["generate_scenarios_from_example", "generate_scenarios_from_example_seed"]


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser("generate-scenario")

    # Generation mode selection
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Use regular ScenarioGeneratingAgent instead of SeedScenarioGeneratingAgent (default)",
    )

    # Required arguments for both modes
    parser.add_argument(
        "-s",
        "--scenario",
        dest="scenario_id_list",
        nargs="+",
        default=[
            "scenario_tutorial_proactive_confirm",
            # "scenario_tutorial_proactive_reject",
            "scenario_find_image_file",
        ],
    )

    # App definition scenario (required for seed mode, which is the default)
    parser.add_argument(
        "--app-def-scenario",
        dest="app_def_scenario",
        default="scenario_with_all_apps_init",
        help="Scenario ID that defines the available apps (required for seed mode, which is the default)",
    )

    # Optional arguments
    parser.add_argument("-a", "--agent", dest="agent", default="scenario_generator")
    parser.add_argument("--model", dest="model", default="gpt-5-chat-latest")
    parser.add_argument("--provider", dest="provider", default="openai")
    parser.add_argument("--endpoint", dest="endpoint", default=None)
    parser.add_argument("--max_turns", dest="max_turns", type=int, default=None)
    parser.add_argument(
        "--simulated_generation_time_mode", dest="sim_mode", default="measured", choices=["measured", "fixed"]
    )

    # Multi-scenario generation arguments
    parser.add_argument(
        "--total-scenarios",
        dest="total_scenarios",
        type=int,
        default=1,
        help="Total number of scenarios to generate (default: 1)",
    )
    parser.add_argument(
        "--apps-per-scenario",
        dest="apps_per_scenario",
        type=int,
        default=2,
        help="Number of apps (excluding AgentUserInterface) to use per scenario (default: 4)",
    )
    # Explicit app scaling (bypass app combination agent)
    parser.add_argument(
        "--scale",
        dest="scale_apps",
        nargs="*",
        default=None,
        help=(
            "Explicit list of app class names to use for all generated scenarios "
            "(default: None). "
            "AgentUserInterface and SystemApp are always included by default."
        ),
    )

    args = parser.parse_args()

    # Import our custom scenarios to register them
    from are.simulation.scenarios.utils.constants import ALL_SCENARIOS

    # Validate arguments based on mode
    if not args.no_seed and args.app_def_scenario not in ALL_SCENARIOS:
        parser.error(f"App definition scenario '{args.app_def_scenario}' not found in registered scenarios")

    scenario_list = []
    app_def_scenario = None

    logger.info(f"ALL_SCENARIOS: {ALL_SCENARIOS}")

    if not args.no_seed:
        # SEED MODE: Use SeedScenarioGeneratingAgent (default)
        logger.info("Using SeedScenarioGeneratingAgent mode")

        # Load the app definition scenario (defines available tools)
        if args.app_def_scenario not in ALL_SCENARIOS:
            raise ValueError(f"App definition scenario '{args.app_def_scenario}' not found in registered scenarios")
        app_def_scenario_type = ALL_SCENARIOS[args.app_def_scenario]
        app_def_scenario = app_def_scenario_type()
        app_def_scenario.initialize()
        logger.info(f"Loaded app definition scenario: {app_def_scenario.__class__.__name__}")

        # Load example scenarios (for reference only, not for tools)
        for scenario_id in args.scenario_id_list:
            if scenario_id not in ALL_SCENARIOS:
                logger.warning(f"Example scenario '{scenario_id}' not found in registered scenarios")
                continue
            scenario_type = ALL_SCENARIOS[scenario_id]
            scenario = scenario_type()
            scenario.initialize()
            scenario_list.append(scenario)
            logger.info(f"Loaded example scenario: {scenario.__class__.__name__}")

        logger.info("generate_scenarios_from_example (seed mode) started")
        print(f"app_def_scenario: {app_def_scenario}")
        print(f"example_scenarios: {scenario_list}")

        output = generate_scenarios_from_example_seed(
            app_def_scenario=app_def_scenario,
            example_scenarios=scenario_list,
            model=args.model,
            provider=args.provider,
            endpoint=args.endpoint,
            total_scenarios=args.total_scenarios,
            apps_per_scenario=args.apps_per_scenario,
            # Pass explicit apps if provided by --scale
            selected_apps=args.scale_apps,
        )

    else:
        # REGULAR MODE: Use regular ScenarioGeneratingAgent
        logger.info("Using regular ScenarioGeneratingAgent mode")

        # Load all scenarios as before
        for scenario_id in args.scenario_id_list:
            if scenario_id not in ALL_SCENARIOS:
                raise ValueError(f"Scenario '{scenario_id}' not found in registered scenarios")
            scenario_type = ALL_SCENARIOS[scenario_id]
            scenario = scenario_type()
            scenario.initialize()
            scenario_list.append(scenario)
            logger.info(f"scenario_type: {scenario_type}")

        logger.info("generate_scenarios_from_example started")
        print(f"scenario_list: {scenario_list}")

        output = generate_scenarios_from_example(
            scenario_list=scenario_list, model=args.model, provider=args.provider, endpoint=args.endpoint
        )

    logger.info("generate_scenarios_from_example finished")
    if output is not None:
        try:
            print(output)
        except Exception:
            print(json.dumps({"output": str(output)}))


def _get_module_file_path(scenario: Scenario) -> str | None:
    """Get the file path for a scenario's module."""
    try:
        mod_name = scenario.__class__.__module__
        mod = sys.modules.get(mod_name)
        if mod is None or not hasattr(mod, "__file__") or mod.__file__ is None:
            # Try to import the module explicitly
            mod = __import__(mod_name, fromlist=["*"])
        file_path = getattr(mod, "__file__", None)
    except Exception as e:
        logger.warning(f"Failed to get module file path for {scenario.__class__.__module__}: {e}")
        return None
    else:
        return file_path


def _extract_imports_from_file(file_path: str) -> set[str]:
    """Extract import statements from a single file."""
    imports: set[str] = set()
    try:
        with open(file_path, encoding="utf-8") as f:
            code = f.read()
        tree = ast.parse(code, filename=file_path)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    if name:
                        imports.add(f"import {name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module
                if module is None:
                    continue  # skip relative or unknown
                for alias in node.names:
                    name = alias.name
                    if name:
                        imports.add(f"from {module} import {name}")
    except Exception as e:
        logger.warning(f"Failed to parse {file_path}: {e}")

    return imports


def _extract_imports_from_scenarios(scenarios: list[Scenario]) -> list[str]:
    """Extract 'from X import Y' and 'import X' statements from the source files.

    of the provided scenario classes.

    """
    all_imports: set[str] = set()
    for sc in scenarios:
        file_path = _get_module_file_path(sc)
        if not file_path:
            continue

        imports = _extract_imports_from_file(file_path)
        all_imports.update(imports)

    return list(all_imports)


if __name__ == "__main__":
    main()
