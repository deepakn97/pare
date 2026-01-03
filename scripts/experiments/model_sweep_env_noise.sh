#!/bin/bash
#
# Run model sweep across different environmental noise levels.
#
# This script runs the models sweep on noise_subset.txt scenarios
# with env-events-per-min of 2, 4, 6, and 8.
#
# Run from project root: ./scripts/experiments/model_sweep_env_noise.sh

set -e  # Exit on error

echo "========================================"
echo "Environmental Noise Level Sweep"
echo "========================================"
echo "Models file: data/models.txt"
echo "Scenarios file: data/noise_subset.txt"
echo "User model: gpt-5-mini"
echo "Env events per minute: 2, 4, 6, 8"
echo "========================================"
echo ""

# Run with env-events-per-min=2
echo "========================================"
echo "Running with env-events-per-min=2"
echo "========================================"
./scripts/experiments/run_models_sweep.sh \
    --models data/models.txt \
    --scenarios data/noise_subset.txt \
    --user-model gpt-5-mini \
    --observe-max-iterations 5 \
    --env-events-per-min 2 \
    --env-events-seed 42 \
    --experiment-name "paper_draft"

# Run with env-events-per-min=4
echo "========================================"
echo "Running with env-events-per-min=4"
echo "========================================"
./scripts/experiments/run_models_sweep.sh \
    --models data/models.txt \
    --scenarios data/noise_subset.txt \
    --user-model gpt-5-mini \
    --observe-max-iterations 5 \
    --env-events-per-min 4 \
    --env-events-seed 42 \
    --experiment-name "paper_draft"

# Run with env-events-per-min=6
echo "========================================"
echo "Running with env-events-per-min=6"
echo "========================================"
./scripts/experiments/run_models_sweep.sh \
    --models data/models.txt \
    --scenarios data/noise_subset.txt \
    --user-model gpt-5-mini \
    --observe-max-iterations 5 \
    --env-events-per-min 6 \
    --env-events-seed 42 \
    --experiment-name "paper_draft"

# Run with env-events-per-min=8
echo "========================================"
echo "Running with env-events-per-min=8"
echo "========================================"
./scripts/experiments/run_models_sweep.sh \
    --models data/models.txt \
    --scenarios data/noise_subset.txt \
    --user-model gpt-5-mini \
    --observe-max-iterations 5 \
    --env-events-per-min 8 \
    --env-events-seed 42 \
    --experiment-name "paper_draft"

echo ""
echo "========================================"
echo "ENVIRONMENTAL NOISE SWEEP COMPLETE"
echo "========================================"
