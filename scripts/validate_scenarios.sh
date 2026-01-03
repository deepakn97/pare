#!/bin/bash

# Script to validate all scenarios in a directory by running them in oracle mode
# Usage: ./scripts/validate_scenarios.sh <scenarios_directory>

set -euo pipefail

# Check if directory argument is provided
if [ $# -eq 0 ]; then
    echo "Usage: $0 <scenarios_directory>"
    echo "Example: $0 pas/scenarios/user_scenarios"
    exit 1
fi

SCENARIOS_DIR="$1"

# Check if directory exists
if [ ! -d "$SCENARIOS_DIR" ]; then
    echo "Error: Directory '$SCENARIOS_DIR' does not exist"
    exit 1
fi

# Arrays to track results
declare -a PASSED_SCENARIOS
declare -a FAILED_SCENARIOS

# Find all scenario files and extract scenario names
echo "Discovering scenarios in $SCENARIOS_DIR..."
echo "========================================"

# Find all .py files, extract scenario names from @register_scenario decorator
SCENARIO_FILES=$(find "$SCENARIOS_DIR" -name "*.py" -not -name "__*")

for file in $SCENARIO_FILES; do
    # Extract scenario name from @register_scenario("scenario_name")
    SCENARIO_NAME=$(grep -o '@register_scenario("[^"]*")' "$file" 2>/dev/null | sed 's/@register_scenario("//;s/")//' || true)

    if [ -z "$SCENARIO_NAME" ]; then
        continue
    fi

    # Run the scenario in oracle mode and capture output (suppressed)
    OUTPUT=$(uv run python scripts/run_scenarios.py \
        --scenarios "$SCENARIO_NAME" \
        --user-model "gpt-4o-mini" \
        --proactive-model "gpt-4o" \
        --max-turns 10 \
        --output-dir results/validation \
        --oracle 2>&1)

    # Check if validation succeeded
    if echo "$OUTPUT" | grep -q "Validation: SUCCESS"; then
        echo "✅ $SCENARIO_NAME"
        PASSED_SCENARIOS+=("$SCENARIO_NAME")
    else
        echo "❌ $SCENARIO_NAME"
        FAILED_SCENARIOS+=("$SCENARIO_NAME")
    fi
done

# Print summary
echo ""
echo "========================================"
echo "VALIDATION SUMMARY"
echo "========================================"
echo "Total scenarios: $((${#PASSED_SCENARIOS[@]} + ${#FAILED_SCENARIOS[@]}))"
echo "Passed: ${#PASSED_SCENARIOS[@]}"
echo "Failed: ${#FAILED_SCENARIOS[@]}"
echo ""

if [ ${#FAILED_SCENARIOS[@]} -eq 0 ]; then
    echo "🎉 All scenarios passed!"
    exit 0
else
    echo "❌ Failed scenarios:"
    for scenario in "${FAILED_SCENARIOS[@]}"; do
        echo "  - $scenario"
    done
    exit 1
fi
