# Automated Scenario Generation

Automated scenario generation pipeline that creates new scenarios by analyzing existing examples and using LLM agents to generate, validate, and repair scenario code. The system supports two generation modes: **Standard Mode** and **Seed Mode**.

## Overview

The Scenario Generator is a sophisticated pipeline that leverages Large Language Models (LLMs) to automatically generate new proactive scenarios. It includes multiple validation and repair mechanisms to ensure generated scenarios are syntactically correct and properly structured.

### Standard Mode
Generates scenarios by analyzing existing example scenarios and extracting available tools from them.

### Seed Mode (Advanced)
Generates scenarios using tools from a dedicated "app definition scenario" (typically `scenario_with_all_apps_init`), allowing for more comprehensive and diverse scenario generation with strict tool constraints and sophisticated app combination selection.

## Key Features

### Multi-Iteration Generation Process
The generator uses a **multi-iteration approach**:
1. **First iteration**: Generate the initial scenario code
2. **Subsequent iterations**: Validate, detect issues, and repair problems
3. **Final output**: Clean, validated scenario ready for use

### Built-in Validation & Repair
- **Syntax validation**: Automatic Python syntax checking with compile-time error detection
- **Import validation**: Ensures all required imports are available and correctly formatted
- **Linting fixes**: Automatic correction of common formatting issues (e.g., `true`/`false` vs `True`/`False`)
- **Error recovery**: Failed generations are automatically sent back to the LLM for repair

### Standard Mode Features
- **Example-based tool extraction**: Analyzes provided example scenarios to determine available tools
- **Single scenario generation**: Generates one scenario per run
- **Flexible tool usage**: No strict constraints on which tools must be used

### Seed Mode Features (Advanced)
- **App definition scenario**: Uses a dedicated scenario (e.g., `scenario_with_all_apps_init`) to define available tools
- **Batch generation**: Generates multiple scenarios with different app combinations in a single run
- **Intelligent app combination selection**: Uses LLM-powered reasoning to select optimal app combinations
- **Comprehensive tool usage validation**: Ensures all apps are used in each generated scenario
- **Proactive interaction pattern validation**: Enforces agent proposal → user response → agent action pattern
- **Meaningful user responses**: Validates that user responses are contextual and detailed (not just "yes")
- **Strict tool constraints**: Generated scenarios can only use tools from the selected app combination

## Command Line Interface

### Standard Mode Usage

```bash
# Generate a single scenario using example scenarios as reference
python pas/scenario_generator/scenario_generator.py \
    -s scenario_tutorial_proactive_confirm \
    --model gpt-5-chat-latest \
    --provider openai
```

### Seed Mode Usage

```bash
# Generate multiple scenarios using seed mode with app combinations
python pas/scenario_generator/scenario_generator.py \
    --total-scenarios 5 \
    --apps-per-scenario 3 \
    --app-def-scenario scenario_with_all_apps_init \
    --model gpt-5-chat-latest \
    --provider openai
```

### All Parameters

```bash
python pas/scenario_generator/scenario_generator.py \
    -s <scenario_id> \
    -a <agent_name> \
    --model <model_name> \
    --provider <provider_name> \
    --endpoint <endpoint_url> \
    --max_turns <number> \
    --simulated_generation_time_mode <measured|fixed> \
    --total-scenarios <number> \
    --apps-per-scenario <number> \
    --app-def-scenario <scenario_id> \
    --scale <AppClass1> <AppClass2> ...
```

### Parameters

#### Standard Mode Parameters
- **`-s, --scenario`**: Scenario IDs to use as examples (can add multiple example scenarios)
- **`-a, --agent`**: Agent type to use (default: "scenario_generator")
- ** `--model`**: LLM model name (default: "gpt-5-chat-latest")
- ** `--provider`**: LLM provider (default: "openai")
- ** `--endpoint`**: Custom API endpoint (optional)
- ** `--max_turns`**: Maximum conversation turns (optional)
- ** `--simulated_generation_time_mode`**: Time simulation mode ("measured" or "fixed")

#### Seed Mode Parameters
- **`--total-scenarios`**: Number of scenarios to generate in batch mode (default: 1)
- **`--apps-per-scenario`**: Number of apps to use per scenario (excluding AgentUserInterface) (default: 4)
- **`--app-def-scenario`**: App definition scenario to extract tools from (default: "scenario_with_all_apps_init")
- **`--scale`**: Optional explicit list of app class names to use for all generated scenarios. When omitted or set to none (default), the generator uses intelligent app-combination selection. When provided, the generator bypasses the combination agent and always uses the same set you pass (AgentUserInterface and SystemApp are always included by default).

Example:

```bash
python pas/scenario_generator/scenario_generator.py \
  --total-scenarios 3 \
  --scale ApartmentListingApp ContactsApp ReminderApp
```

## Output

Generated scenarios are saved to:
```
pas/scenarios/generated_scenarios/
```

## Utility Scripts

### Scenario Deduplication

Compare similarity between scenarios using multiple algorithms:

```bash
python pas/scenario_generator/utils/deduplicate_scenarios.py \
    pas/scenarios/base.py \
    pas/scenarios/contacts_followup.py \
    --threshold 0.88 \
    --metric max \
    --k 3
```

**Metrics Available:**
- `difflib_ratio`: Text similarity ratio
- `jaccard_shingles`: Jaccard similarity using k-shingles
- `cosine_tokens`: Cosine similarity of token vectors

**Output Example:**
```
=== Similarity Scores ===
difflib_ratio   : 0.2482
jaccard_shingles: 0.0675 (k=3)
cosine_tokens   : 0.5174
len(tokens)     : 317 vs 397

Decision:
metric=max score=0.5174 threshold=0.88
=> Different enough ❌
```

### Import Analysis

List all available app imports for agent instructions:

```bash
python pas/scenario_generator/utils/list_all_app_imports.py
```

This utility scans the entire `are.simulation.apps` package and generates comprehensive import instructions that help the LLM agent understand what APIs and classes are available.

## Seed Scenario Generator (Advanced)

The **Seed Scenario Generator** is an advanced generation mode that provides sophisticated scenario creation capabilities beyond the standard generator.

### Key Capabilities

#### Intelligent App Combination Selection
- **LLM-powered reasoning**: Uses a dedicated `AppCombinationAgent` to intelligently select app combinations
- **Batch generation**: Generates multiple scenarios with distinct app combinations in a single run
- **Uniqueness enforcement**: Ensures each generated scenario uses a different combination of apps
- **Diversity optimization**: Maximizes the variety of app combinations across the generated batch

#### Comprehensive Tool Usage Validation
- **All-apps requirement**: Each scenario must use all apps from its selected combination (at least one tool per app)
- **Tool coverage analysis**: Validates that every available tool category is utilized
- **App interaction validation**: Ensures realistic and meaningful app interactions

#### Proactive Interaction Pattern Enforcement
- **Mandatory pattern**: Every scenario must include agent proposal → user response → agent action
- **Meaningful responses**: User responses must be contextual and detailed (e.g., "Yes, please share it with Jordan")
- **Proposal validation**: Agent proposals must include questions seeking user permission
- **Action execution**: Agent must execute the proposed actions after user approval

#### Strict Tool Constraints
- **Combination-specific tools**: Each scenario can only use tools from its assigned app combination
- **Dynamic import generation**: Import statements are generated dynamically based on selected apps
- **Tool availability validation**: Ensures all used tools are available in the selected app combination

### Generation Process

1. **App Combination Generation**: `AppCombinationAgent` generates all required app combinations upfront
2. **Tool Extraction**: Extracts tools from the app definition scenario
3. **Batch Scenario Generation**: Iterates through each app combination to generate scenarios
4. **Multi-level Validation**:
   - Syntax and import validation
   - Comprehensive tool usage validation
   - Proactive interaction pattern validation
   - Similarity validation against existing scenarios
5. **Iterative Repair**: Failed scenarios are automatically repaired through multiple iterations

### Example Usage

```bash
# Generate 3 scenarios, each using 4 apps, with meaningful user interactions
python pas/scenario_generator/scenario_generator.py \
    --total-scenarios 3 \
    --apps-per-scenario 4 \
    --app-def-scenario scenario_with_all_apps_init
```

## Architecture

### Core Components

#### ScenarioGeneratingAgent (Standard Mode)
The main agent for standard scenario generation:
- Analyzing example scenarios
- Generating new scenario code
- Validating syntax and imports
- Repairing detected issues

#### SeedScenarioGeneratingAgent (Advanced Mode)
The advanced agent for seed-based generation:
- **App combination management**: Coordinates with `AppCombinationAgent` for intelligent app selection
- **Batch processing**: Manages generation of multiple scenarios with different app combinations
- **Advanced validation**: Implements comprehensive validation including proactive interaction patterns
- **Dynamic tool management**: Generates scenario-specific import instructions and tool constraints
- **Multi-level repair**: Sophisticated iterative repair process with multiple validation layers

#### AppCombinationAgent
Specialized agent for intelligent app combination selection:
- **LLM reasoning**: Uses natural language processing to evaluate app compatibility
- **Batch optimization**: Generates all combinations upfront to ensure diversity
- **Scenario guidance**: Provides descriptive summaries for each app combination
- **Uniqueness enforcement**: Tracks and avoids duplicate combinations

### Validation Functions

#### Standard Mode
- `_validate_syntax()`: Compile-time Python syntax validation
- `_validate_imports()`: Import statement validation against available modules
- `_fix_generated_file_linting_issues()`: Common formatting issue fixes

#### Seed Mode (Additional)
- `_validate_comprehensive_tool_usage()`: Ensures all apps are used in each scenario
- `_validate_proactive_interaction_pattern()`: Validates agent proposal → user response → agent action pattern
- `_validate_similarity_against_existing()`: Prevents duplicate scenario generation
- `_generate_import_instructions_for_selected_apps()`: Creates dynamic import statements for selected apps

### Import Management
- **Standard mode**: `_extract_imports_from_scenarios()` - Extract imports from example scenarios
- **Seed mode**: Dynamic import generation based on selected app combinations
- **`list_all_app_imports.py`**: Build comprehensive import catalogs for all available apps
- **Dynamic import resolution and validation**: Context-aware import management

## Prompt Templates

The system uses specialized prompt templates for different generation tasks:

### Standard Mode Prompts
- **System Prompt**: `SYSTEM_PROMPT_TEMPLATE` - Core instructions for scenario generation
- **Task Prompts**: Dynamic task generation based on example scenarios

### Seed Mode Prompts
- **Seed Scenario Generator**: `SEED_SCENARIO_GENERATOR_SYSTEM_PROMPT_TEMPLATE` - Advanced instructions for comprehensive scenario generation
- **App Combination Agent**: `create_app_combination_prompt()` - Specialized prompts for intelligent app combination selection
- **Proactive Interaction Guidelines**: Detailed instructions for mandatory agent-user interaction patterns

### Prompt Features
- **Comprehensive tool documentation**: Detailed descriptions of all available tools and their parameters
- **App interaction guidance**: Instructions for realistic app usage and combinations
- **Novelty requirements**: Anti-duplication measures to ensure scenario diversity
- **Validation criteria**: Clear guidelines for what constitutes a valid scenario

## Configuration

The system is highly configurable through the LLM engine configuration:
- **Multiple model providers**: OpenAI, local models via Ollama, and other LLM services
- **Custom endpoints**: Flexible API endpoint configuration for different services
- **Adjustable iteration limits**: Configurable maximum number of repair iterations
- **Validation thresholds**: Customizable similarity thresholds for duplicate detection
- **Simulated time modes**: Options for testing and development environments
- **Batch generation settings**: Configurable scenario count and app combination parameters

## Mode Selection

The system automatically selects the appropriate generation mode based on command-line arguments:

### Automatic Mode Selection
- **Standard Mode**: Used when `-s/--scenario` is provided with example scenario IDs
- **Seed Mode**: Used when `--total-scenarios` and `--app-def-scenario` are provided
- **Default behavior**: Seed mode is the default when no specific example scenarios are provided

### Migration Guide

**From Standard to Seed Mode:**
```bash
# Old way (Standard Mode)
python pas/scenario_generator/scenario_generator.py -s scenario_tutorial_proactive_confirm

# New way (Seed Mode)
python pas/scenario_generator/scenario_generator.py --total-scenarios 1 --apps-per-scenario 4
```

**Recommended Usage:**
- Use **Standard Mode** for quick prototyping and simple scenario generation
- Use **Seed Mode** for comprehensive scenario generation, batch processing, and advanced validation requirements
