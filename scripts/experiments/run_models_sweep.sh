#!/bin/bash
#
# Run PAS scenarios across multiple proactive models.
#
# Usage:
#   ./scripts/run_models_sweep.sh --models model1 model2 model3
#   ./scripts/run_models_sweep.sh --models models.txt
#   ./scripts/run_models_sweep.sh --models gpt-4o claude-3-5-sonnet --max-turns 5
#
# Examples:
#   ./scripts/run_models_sweep.sh --models gpt-4o-mini gpt-4o claude-3-5-sonnet
#   ./scripts/run_models_sweep.sh --models models.txt --oracle
#   ./scripts/run_models_sweep.sh --models llama-3.3-70B --experiment-name llama_test

set -e  # Exit on error

# Default values
USER_MODEL="gpt-5"
MAX_TURNS=10
USER_MAX_ITERATIONS=1
OBSERVE_MAX_ITERATIONS=10
EXECUTE_MAX_ITERATIONS=10
TRACES_DIR="traces"
TOOL_FAILURE_PROB=0.0
ENV_EVENTS_PER_MIN=0.0
ENV_EVENTS_SEED=42
EXPERIMENT_NAME="models_sweep"
ORACLE_MODE=""
STOP_ON_FAILURE=""
SCENARIOS=""
MODELS=()

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --models)
            shift
            # Collect all arguments until next flag or end
            while [[ $# -gt 0 && ! "$1" =~ ^-- ]]; do
                MODELS+=("$1")
                shift
            done
            ;;
        --user-model)
            USER_MODEL="$2"
            shift 2
            ;;
        --max-turns)
            MAX_TURNS="$2"
            shift 2
            ;;
        --user-max-iterations)
            USER_MAX_ITERATIONS="$2"
            shift 2
            ;;
        --observe-max-iterations)
            OBSERVE_MAX_ITERATIONS="$2"
            shift 2
            ;;
        --execute-max-iterations)
            EXECUTE_MAX_ITERATIONS="$2"
            shift 2
            ;;
        --traces-dir)
            TRACES_DIR="$2"
            shift 2
            ;;
        --tool-failure-prob)
            TOOL_FAILURE_PROB="$2"
            shift 2
            ;;
        --env-events-per-min)
            ENV_EVENTS_PER_MIN="$2"
            shift 2
            ;;
        --env-events-seed)
            ENV_EVENTS_SEED="$2"
            shift 2
            ;;
        --experiment-name)
            EXPERIMENT_NAME="$2"
            shift 2
            ;;
        --oracle)
            ORACLE_MODE="--oracle"
            shift
            ;;
        --stop-on-failure)
            STOP_ON_FAILURE="--stop-on-failure"
            shift
            ;;
        --scenarios)
            SCENARIOS="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 --models <model1 model2 ... | models_file.txt> [OPTIONS]"
            echo ""
            echo "Run PAS scenarios across multiple proactive models."
            echo ""
            echo "Options:"
            echo "  --models MODELS          Model names or path to file with model names (one per line)"
            echo "  --user-model MODEL       User agent model (default: gpt-5)"
            echo "  --max-turns N            Maximum turns per scenario (default: 10)"
            echo "  --user-max-iterations N  User agent max iterations (default: 1)"
            echo "  --observe-max-iterations N  Observe agent max iterations (default: 10)"
            echo "  --execute-max-iterations N  Execute agent max iterations (default: 10)"
            echo "  --traces-dir DIR         Base traces directory (default: traces)"
            echo "  --tool-failure-prob P    Tool failure probability (default: 0.0)"
            echo "  --env-events-per-min N   Environmental noise rate (default: 0.0)"
            echo "  --env-events-seed N      Random seed for noise (default: 42)"
            echo "  --experiment-name NAME   Experiment name prefix (default: models_sweep)"
            echo "  --oracle                 Run in oracle mode"
            echo "  --stop-on-failure        Stop on first scenario failure"
            echo "  --scenarios FILE|IDs     Scenario IDs or path to file with scenario IDs"
            echo "  -h, --help               Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 --models gpt-4o-mini gpt-4o claude-3-5-sonnet"
            echo "  $0 --models models.txt --oracle"
            echo "  $0 --models llama-3.3-70B --experiment-name llama_test --max-turns 5"
            exit 0
            ;;
        -*)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# If first "model" is a file, load models from it
if [[ ${#MODELS[@]} -eq 1 && -f "${MODELS[0]}" ]]; then
    MODELS_FILE="${MODELS[0]}"
    MODELS=()
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Skip empty lines and comments
        [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
        MODELS+=("$line")
    done < "$MODELS_FILE"
fi

# Check if we have any models to run
if [[ ${#MODELS[@]} -eq 0 ]]; then
    echo "Error: No models specified. Use --models to provide model names or a file path."
    echo "Use --help for usage information."
    exit 1
fi

echo "========================================"
echo "PAS Models Sweep"
echo "========================================"
echo "User model: $USER_MODEL"
echo "Proactive models: ${MODELS[*]}"
echo "Max turns: $MAX_TURNS"
echo "Traces directory: $TRACES_DIR"
echo "Experiment name: $EXPERIMENT_NAME"
if [[ -n "$SCENARIOS" ]]; then
    echo "Scenarios: $SCENARIOS"
fi
echo "========================================"
echo ""

# Run for each model
TOTAL_MODELS=${#MODELS[@]}
CURRENT=0

for MODEL in "${MODELS[@]}"; do
    CURRENT=$((CURRENT + 1))
    echo ""
    echo "========================================"
    echo "Running with proactive model: $MODEL"
    echo "Progress: $CURRENT / $TOTAL_MODELS"
    echo "========================================"
    echo ""

    # Build scenarios argument if provided
    SCENARIOS_ARG=""
    if [[ -n "$SCENARIOS" ]]; then
        SCENARIOS_ARG="--scenarios $SCENARIOS"
    fi

    # Run the script (model is now a separate directory level, so don't include in experiment name)
    uv run python scripts/run_scenarios.py \
        --user-model "$USER_MODEL" \
        --proactive-model "$MODEL" \
        --max-turns "$MAX_TURNS" \
        --user-max-iterations "$USER_MAX_ITERATIONS" \
        --observe-max-iterations "$OBSERVE_MAX_ITERATIONS" \
        --execute-max-iterations "$EXECUTE_MAX_ITERATIONS" \
        --traces-dir "$TRACES_DIR" \
        --tool-failure-prob "$TOOL_FAILURE_PROB" \
        --env-events-per-min "$ENV_EVENTS_PER_MIN" \
        --env-events-seed "$ENV_EVENTS_SEED" \
        --experiment-name "$EXPERIMENT_NAME" \
        $ORACLE_MODE \
        $STOP_ON_FAILURE \
        $SCENARIOS_ARG

    echo ""
    echo "Completed model: $MODEL"
done

# Print final summary
echo ""
echo "========================================"
echo "MODELS SWEEP COMPLETE"
echo "========================================"
echo "Total models: $TOTAL_MODELS"
echo ""
