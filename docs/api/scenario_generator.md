# Scenario Generator API

Automated scenario generation pipeline that creates new scenarios by analyzing existing examples and using LLM agents to generate, validate, and repair scenario code.

## Overview

The Scenario Generator is a sophisticated pipeline that leverages Large Language Models (LLMs) to automatically generate new proactive scenarios based on existing examples. It includes multiple validation and repair mechanisms to ensure generated scenarios are syntactically correct and properly structured.

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

### Import Management
- **Automatic import discovery**: Scans the entire codebase to build comprehensive import instructions
- **Context-aware imports**: Extracts imports from example scenarios to ensure proper context
- **Dynamic import validation**: Verifies all imports in generated scenarios are valid and accessible

## Command Line Interface

### Basic Usage

```bash
python pas/scenario_generator/scenario_generator.py \
    -s scenario_tutorial_proactive_confirm \
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
    --simulated_generation_time_mode <measured|fixed>
```

### Parameters

- **`-s, --scenario`**: Scenario IDs to use as examples (can add multiple example scenarios)
- **`-a, --agent`**: Agent type to use (default: "scenario_generator")
- ** `--model`**: LLM model name (default: "gpt-5-chat-latest")
- ** `--provider`**: LLM provider (default: "openai")
- ** `--endpoint`**: Custom API endpoint (optional)
- ** `--max_turns`**: Maximum conversation turns (optional)
- ** `--simulated_generation_time_mode`**: Time simulation mode ("measured" or "fixed")

## Output

Generated scenarios are saved to:
```
/pas/scenarios/generated_scenarios/
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

## Architecture

### Core Components

#### ScenarioGeneratingAgent
The main agent responsible for:
- Analyzing example scenarios
- Generating new scenario code
- Validating syntax and imports
- Repairing detected issues

#### Validation Functions
- `_validate_syntax()`: Compile-time Python syntax validation
- `_validate_imports()`: Import statement validation against available modules
- `_fix_generated_file_linting_issues()`: Common formatting issue fixes

#### Import Management
- `_extract_imports_from_scenarios()`: Extract imports from example scenarios
- `list_all_app_imports.py`: Build comprehensive import catalogs
- Dynamic import resolution and validation

## Configuration

The system is highly configurable through the LLM engine configuration:
- Multiple model providers (OpenAI, local models via Ollama, etc.)
- Custom endpoints for different API services
- Adjustable iteration limits and validation thresholds
- Simulated time modes for testing and development

## Scenario Generator Code Entry Point

::: pas.scenario_generator.scenario_generator
