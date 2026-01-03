#!/bin/bash
#
# Run model sweep across different tool failure probabilities.
#
# This script runs the models sweep on noise_subset.txt scenarios
# with tool failure probabilities of 0.2, 0.4, and 0.6.
#
# Run from project root: ./scripts/experiments/model_sweep_tfp.sh

set -e  # Exit on error

echo "========================================"
echo "Tool Failure Probability Sweep"
echo "========================================"
echo "Models file: data/models.txt"
echo "Scenarios file: data/noise_subset.txt"
echo "User model: gpt-5-mini"
echo "Tool failure probabilities: 0.2, 0.4, 0.6"
echo "========================================"
echo ""

# Run with tfp=0.2
echo "========================================"
echo "Running with tool-failure-prob=0.2"
echo "========================================"
./scripts/experiments/run_models_sweep.sh \
    --models data/models.txt \
    --scenarios data/noise_subset.txt \
    --user-model gpt-5-mini \
    --observe-max-iterations 5 \
    --tool-failure-prob 0.2 \
    --env-events-seed 42 \
    --experiment-name "paper_draft"

# Run with tfp=0.4
echo "========================================"
echo "Running with tool-failure-prob=0.4"
echo "========================================"
./scripts/experiments/run_models_sweep.sh \
    --models data/models.txt \
    --scenarios data/noise_subset.txt \
    --user-model gpt-5-mini \
    --observe-max-iterations 5 \
    --tool-failure-prob 0.4 \
    --env-events-seed 42 \
    --experiment-name "paper_draft"

# Run with tfp=0.6
echo "========================================"
echo "Running with tool-failure-prob=0.6"
echo "========================================"
./scripts/experiments/run_models_sweep.sh \
    --models data/models.txt \
    --scenarios data/noise_subset.txt \
    --user-model gpt-5-mini \
    --observe-max-iterations 5 \
    --tool-failure-prob 0.6 \
    --env-events-seed 42 \
    --experiment-name "paper_draft"

echo ""
echo "========================================"
echo "TOOL FAILURE PROBABILITY SWEEP COMPLETE"
echo "========================================"
