# Scenario Summary Generation and Deduplication

This document describes the scenario summary generation system, which creates natural language summaries of scenario code and validates them against existing summaries to prevent duplicates.

## Overview

The summary generation system consists of three main components:

1. **SummaryGeneratingAgent**: An LLM-based agent that generates concise summaries of scenario code
2. **generate_scenario_summaries.py**: A batch script to generate summaries for multiple scenario files
3. **validate_and_add_scenario_summary.py**: A validation script that checks new summaries against existing ones using similarity metrics

## SummaryGeneratingAgent

The `SummaryGeneratingAgent` is a specialized agent that analyzes scenario Python code and generates human-readable summaries.

### Location

`pas/scenario_generator/agent/summary_generating_agent.py`

### Features

- **Automatic Summary Generation**: Uses LLM to analyze scenario code and create concise summaries
- **Scenario ID Extraction**: Automatically extracts scenario IDs from `@register_scenario` decorators
- **Output Cleaning**: Removes markdown formatting and common prefixes from LLM output
- **Error Handling**: Gracefully handles failures and returns `None` when generation fails

### API

#### `__init__(llm_engine: LLMEngine)`

Initialize the summary generating agent.

**Parameters:**
- `llm_engine`: The LLM engine to use for summary generation

#### `generate_summary(scenario_code: str) -> str | None`

Generate a summary for the given scenario code.

**Parameters:**
- `scenario_code`: The scenario Python code as a string

**Returns:**
- The generated summary text, or `None` if generation failed

**Example:**
```python
from are.simulation.agents.llm.llm_engine_builder import LLMEngineBuilder
from are.simulation.agents.are_simulation_agent_config import LLMEngineConfig
from pas.scenario_generator.agent.summary_generating_agent import SummaryGeneratingAgent

config = LLMEngineConfig(model_name="gpt-4o-mini", provider="openai")
engine = LLMEngineBuilder().create_engine(engine_config=config)
agent = SummaryGeneratingAgent(engine)

scenario_code = """
@register_scenario("meeting_invite_coordination")
class MeetingInviteCoordination(Scenario):
    # ... scenario code ...
"""

summary = agent.generate_summary(scenario_code)
```

#### `generate_summary_from_file(file_path: Path | str) -> tuple[str | None, str | None]`

Generate a summary for a scenario file and extract its scenario ID.

**Parameters:**
- `file_path`: Path to the scenario Python file

**Returns:**
- Tuple of `(scenario_id, summary)`. Returns `(None, None)` if extraction/generation fails.

**Example:**
```python
scenario_id, summary = agent.generate_summary_from_file("path/to/scenario.py")
if scenario_id and summary:
    print(f"Scenario: {scenario_id}")
    print(f"Summary: {summary}")
```

### Summary Format

Summaries are 2-4 sentences that describe:
- The primary objective/goal of the scenario
- The applications used
- The main workflow and interaction patterns
- Key validation criteria

## generate_scenario_summaries.py

A command-line script for batch generating summaries for scenario files.

### Location

`pas/scenario_generator/utils/generate_scenario_summaries.py`

### Usage

#### Generate Summary for a Single File

```bash
uv run python pas/scenario_generator/utils/generate_scenario_summaries.py \
  --file pas/scenarios/generated_scenarios/meeting_invite_coordination.py
```

#### Generate Summaries for All Scenarios

```bash
uv run python pas/scenario_generator/utils/generate_scenario_summaries.py --all
```

This recursively searches all subdirectories in `generated_scenarios/` for Python files.

#### Force Regeneration of Existing Summaries

```bash
uv run python pas/scenario_generator/utils/generate_scenario_summaries.py --all --force
```

#### Custom LLM Configuration

```bash
uv run python pas/scenario_generator/utils/generate_scenario_summaries.py \
  --file scenario.py \
  --model gpt-4 \
  --provider openai
```

#### Custom Output File

```bash
uv run python pas/scenario_generator/utils/generate_scenario_summaries.py \
  --all \
  --output custom_summaries.json
```

### Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--file FILE_PATH` | Path to a single scenario file | None |
| `--all` | Generate summaries for all scenario files | False |
| `--force` | Force regeneration of existing summaries | False |
| `--model MODEL` | LLM model to use | `gpt-4o-mini` |
| `--provider PROVIDER` | LLM provider | `openai` |
| `--endpoint ENDPOINT` | Optional endpoint URL | None |
| `--output OUTPUT_FILE` | Path to output JSON file | `generated_scenarios/scenario_summaries.json` |

### Output Format

The script saves summaries to a JSON file with the following structure:

```json
{
  "scenario_id_1": "Summary text for scenario 1...",
  "scenario_id_2": "Summary text for scenario 2...",
  ...
}
```

## validate_and_add_scenario_summary.py

A validation script that generates a summary for a scenario file, compares it against existing summaries using similarity metrics, and adds it to the JSON file only if it passes all threshold checks.

### Location

`pas/scenario_generator/utils/validate_and_add_scenario_summary.py`

### Usage

#### Basic Validation and Addition

```bash
uv run python pas/scenario_generator/utils/validate_and_add_scenario_summary.py \
  --file pas/scenarios/generated_scenarios/new_scenario.py
```

#### Custom Similarity Thresholds

```bash
uv run python pas/scenario_generator/utils/validate_and_add_scenario_summary.py \
  --file scenario.py \
  --difflib-threshold 0.75 \
  --jaccard-threshold 0.75 \
  --cosine-threshold 0.90
```

#### Using in Scripts

The script prints "True" to stdout if validation passes and the summary is added, or "False" if validation fails:

```bash
if uv run python pas/scenario_generator/utils/validate_and_add_scenario_summary.py \
  --file scenario.py; then
  echo "Summary added successfully!"
else
  echo "Summary too similar to existing ones"
fi
```

### Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--file FILE_PATH` | Path to the scenario file (required) | None |
| `--difflib-threshold FLOAT` | Threshold for difflib_ratio | `0.8` |
| `--jaccard-threshold FLOAT` | Threshold for jaccard_shingles | `0.8` |
| `--cosine-threshold FLOAT` | Threshold for cosine_tokens | `0.94` |
| `--k INT` | Shingle size for Jaccard similarity | `3` |
| `--model MODEL` | LLM model to use | `gpt-4o-mini` |
| `--provider PROVIDER` | LLM provider | `openai` |
| `--endpoint ENDPOINT` | Optional endpoint URL | None |
| `--output OUTPUT_FILE` | Path to output JSON file | `generated_scenarios/scenario_summaries.json` |

### Similarity Metrics

The script uses three similarity metrics to compare summaries:

#### 1. difflib_ratio

**Description**: Structural/sequential similarity using the longest matching subsequence algorithm.

**Threshold**: Default `0.8`

**Interpretation**: Measures how similar the overall structure and sequence of words are between two summaries. Higher values indicate more structural similarity.

#### 2. jaccard_shingles

**Description**: Pattern similarity based on overlapping k-gram token shingles (default k=3).

**Threshold**: Default `0.8`

**Interpretation**: Measures the overlap of token patterns between summaries. More robust to minor edits than difflib. Higher values indicate more pattern overlap.

#### 3. cosine_tokens

**Description**: Vocabulary similarity based on token frequency (bag-of-words approach).

**Threshold**: Default `0.94`

**Interpretation**: Measures how similar the vocabulary usage is between summaries. Uses a higher threshold because summaries naturally share common words. Higher values indicate more vocabulary overlap.

### Validation Logic

For a new summary to be accepted:

1. **Summary Generation**: The script generates a summary for the input scenario file
2. **Comparison**: The new summary is compared against ALL existing summaries in the JSON file
3. **Threshold Check**: For each existing summary, all three metrics must be below their respective thresholds:
   - `difflib_ratio < difflib_threshold`
   - `jaccard_shingles < jaccard_threshold`
   - `cosine_tokens < cosine_threshold`
4. **Addition**: If all comparisons pass, the summary is added to the JSON file
5. **Return Value**: Returns `True` if added, `False` if validation failed

### Output

The script provides detailed logging:

- **For each comparison**: Logs the scenario ID and all three metric values
- **For violations**: Logs a warning with the scenario ID and which thresholds were exceeded
- **Final result**: Prints "True" or "False" to stdout

**Example Output:**
```
INFO:__main__:Generating summary for scenario.py...
INFO:__main__:Generated summary for scenario 'new_scenario': Summary text...
INFO:__main__:Validating summary against existing summaries...
INFO:__main__:Comparing with 'meeting_invite_coordination': difflib_ratio=0.1234, jaccard_shingles=0.2345, cosine_tokens=0.3456
INFO:__main__:Comparing with 'weekend_grocery_pickup': difflib_ratio=0.4567, jaccard_shingles=0.5678, cosine_tokens=0.6789
WARNING:__main__:  ⚠️  VIOLATION: Summary too similar to existing scenario 'weekend_grocery_pickup' (exceeds thresholds: difflib≥0.8, jaccard≥0.8, cosine≥0.94)
False
```

## Integration with Scenario Generation

The summary system is integrated into the scenario generation workflow:

1. **During Generation**: The `SeedScenarioGeneratingAgent` uses summaries from `scenario_summaries.json` to provide context when detecting duplicate scenarios
2. **Similarity Detection**: When a generated scenario is flagged as too similar to an existing one, the summary of the similar scenario is included in the error message to help the LLM understand what needs to be changed

## File Structure

```
pas/
├── scenario_generator/
│   ├── agent/
│   │   └── summary_generating_agent.py      # SummaryGeneratingAgent class
│   ├── prompt/
│   │   └── summary_generator_prompts.py    # Prompt templates
│   └── utils/
│       ├── generate_scenario_summaries.py   # Batch generation script
│       └── validate_and_add_scenario_summary.py  # Validation script
└── scenarios/
    └── generated_scenarios/
        └── scenario_summaries.json          # Summary storage (generated)
```

## Best Practices

1. **Initial Setup**: Run `generate_scenario_summaries.py --all` to create initial summaries for all existing scenarios
2. **New Scenarios**: Use `validate_and_add_scenario_summary.py` when adding new scenarios to ensure they're unique
3. **Threshold Tuning**: Adjust thresholds based on your needs:
   - Lower thresholds (0.7-0.75) for stricter deduplication
   - Higher thresholds (0.85-0.9) for more lenient deduplication
4. **Regular Updates**: Periodically regenerate summaries with `--force` to ensure they're up-to-date with code changes

## Error Handling

All components include comprehensive error handling:

- **File Not Found**: Scripts check for file existence and provide clear error messages
- **LLM Failures**: Summary generation failures are logged and return `None`
- **JSON Errors**: Invalid JSON files are handled gracefully with fallback to empty dictionaries
- **Missing Scenario IDs**: If scenario ID extraction fails, the filename is used as a fallback

## Dependencies

- `are.simulation.agents.llm.llm_engine`: LLM engine for summary generation
- `are.simulation.agents.are_simulation_agent_config`: LLM configuration
- Standard library: `json`, `pathlib`, `logging`, `difflib`, `re`, `collections`
