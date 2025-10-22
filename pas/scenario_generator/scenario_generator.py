import argparse
import ast
import json
import logging
import sys

from are.simulation.agents.are_simulation_agent_config import LLMEngineConfig
from are.simulation.agents.llm.llm_engine_builder import LLMEngineBuilder
from are.simulation.scenarios import Scenario

from pas.scenario_generator.agent.scenario_generating_agent import ScenarioGeneratingAgent
from pas.scenario_generator.example_proactive_scenarios import scenario as _proactive_scenarios  # noqa: F401
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
    system_prompt = ""  # ScenarioGeneratingAgent will populate tools/time placeholders
    # Wire minimal generator (no BaseAgent needed)
    gen_agent = ScenarioGeneratingAgent(
        llm_engine=engine, tools=[], max_iterations=5, import_instructions=import_instructions
    )

    logger.info("Running minimal scenario generator agent")
    # result = None
    result = gen_agent.scenario_generation_run(scenario_list)
    logger.info("Scenario generation completed")
    if result is not None:
        return result.output
    else:
        return None


__all__ = ["generate_scenarios_from_example"]


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser("generate-scenario")
    # parser.add_argument("-s", "--scenario", dest="scenario_id_list", required=True)
    # are/simulation/scenario_generator.py
    parser.add_argument(
        "-s", "--scenario", dest="scenario_id_list", nargs="+", default=["scenario_tutorial_proactive_confirm"]
    )
    parser.add_argument("-a", "--agent", dest="agent", default="scenario_generator")
    parser.add_argument("--model", dest="model", default="gpt-5-chat-latest")
    parser.add_argument("--provider", dest="provider", default="openai")
    parser.add_argument("--endpoint", dest="endpoint", default=None)
    parser.add_argument("--max_turns", dest="max_turns", type=int, default=None)
    parser.add_argument(
        "--simulated_generation_time_mode", dest="sim_mode", default="measured", choices=["measured", "fixed"]
    )
    args = parser.parse_args()

    # Use the same loading path as are-run
    # Build config for MultiScenarioRunner but with single ID
    # This ensures discovery/registration side effects happen

    # Import our custom scenarios to register them

    # Now fetch the scenario class from registry
    from are.simulation.scenarios.utils.constants import ALL_SCENARIOS

    scenario_list = []
    for scenario_id in args.scenario_id_list:
        scenario_type = ALL_SCENARIOS[scenario_id]
        scenario = scenario_type()
        scenario.initialize()
        scenario_list.append(scenario)
        # logger.info(f"9999scenario: {scenario}")
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
