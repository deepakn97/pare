#!/bin/bash
#
# Run all experiments planned for 2026-03-30.
# Runs sequentially to avoid API rate limit conflicts.
#
# Usage:
#   ./scripts/experiments/run_all_2026_03_30.sh
#

set -e

STARTED_AT=$(date +"%Y-%m-%d %H:%M:%S")
echo "========================================"
echo "PARE Experiment Batch - 2026-03-30"
echo "Started at: $STARTED_AT"
echo "========================================"
echo ""

# --- 1. Full benchmark rerun ---
echo "[1/8] Full benchmark rerun"
echo "========================================"
uv run pare benchmark sweep \
  --split full \
  --observe-model qwen-3-4b-it,gemma-3-4b-it,llama-3.2-3b-it,claude-4.5-sonnet,gpt-5,gemini-3-pro,gemini-3-flash \
  --execute-model qwen-3-4b-it,gemma-3-4b-it,llama-3.2-3b-it,claude-4.5-sonnet,gpt-5,gemini-3-pro,gemini-3-flash \
  --user-model gpt-5-mini --max-turns 10 -omi 5 -emi 10 -umi 1 \
  --runs 4 -c 6 --executor-type thread \
  --experiment-name paper_benchmark --export --output-dir ./traces --log-level WARNING
echo "[1/8] Full benchmark rerun -- DONE"
echo ""

# --- 2. Ablation benchmark rerun ---
echo "[2/8] Ablation benchmark rerun"
echo "========================================"
uv run pare benchmark sweep \
  --split ablation \
  --observe-model qwen-3-4b-it,gemma-3-4b-it,llama-3.2-3b-it,claude-4.5-sonnet,gpt-5,gemini-3-pro,gemini-3-flash \
  --execute-model qwen-3-4b-it,gemma-3-4b-it,llama-3.2-3b-it,claude-4.5-sonnet,gpt-5,gemini-3-pro,gemini-3-flash \
  --user-model gpt-5-mini --max-turns 10 -omi 5 -emi 10 -umi 1 \
  -tfp 0.0 -tfp 0.1 -tfp 0.2 -tfp 0.4 \
  -epm 0 -epm 2 -epm 4 -epm 6 --env-events-seed 42 \
  --runs 4 -c 6 --executor-type thread \
  --experiment-name paper_benchmark --export --output-dir ./traces --log-level WARNING
echo "[2/8] Ablation benchmark rerun -- DONE"
echo ""

# --- 3. User model study: claude-4.5-sonnet as user ---
echo "[3/8] User model study: claude-4.5-sonnet as user"
echo "========================================"
uv run pare benchmark sweep \
  --split ablation \
  --observe-model claude-4.5-sonnet,gemini-3-flash,qwen-3-4b-it,gpt-5 \
  --execute-model claude-4.5-sonnet,gemini-3-flash,qwen-3-4b-it,gpt-5 \
  --user-model claude-4.5-sonnet --max-turns 10 -omi 5 -emi 10 -umi 1 \
  --runs 4 -c 6 --executor-type thread \
  --experiment-name paper_user_model_study --export --output-dir ./traces --log-level WARNING
echo "[3/8] User model study: claude-4.5-sonnet -- DONE"
echo ""

# --- 4. User model study: gpt-5-mini as user ---
echo "[4/8] User model study: gpt-5-mini as user"
echo "========================================"
uv run pare benchmark sweep \
  --split ablation \
  --observe-model claude-4.5-sonnet,gemini-3-flash,qwen-3-4b-it,gpt-5 \
  --execute-model claude-4.5-sonnet,gemini-3-flash,qwen-3-4b-it,gpt-5 \
  --user-model gpt-5-mini --max-turns 10 -omi 5 -emi 10 -umi 1 \
  --runs 4 -c 6 --executor-type thread \
  --experiment-name paper_user_model_study --export --output-dir ./traces --log-level WARNING
echo "[4/8] User model study: gpt-5-mini -- DONE"
echo ""

# --- 5. User model study: qwen-3-4b-it as user ---
echo "[5/8] User model study: qwen-3-4b-it as user"
echo "========================================"
uv run pare benchmark sweep \
  --split ablation \
  --observe-model claude-4.5-sonnet,gemini-3-flash,qwen-3-4b-it,gpt-5 \
  --execute-model claude-4.5-sonnet,gemini-3-flash,qwen-3-4b-it,gpt-5 \
  --user-model qwen-3-4b-it --max-turns 10 -omi 5 -emi 10 -umi 1 \
  --runs 4 -c 6 --executor-type thread \
  --experiment-name paper_user_model_study --export --output-dir ./traces --log-level WARNING
echo "[5/8] User model study: qwen-3-4b-it -- DONE"
echo ""

# --- 6. User model study: gemini-3-flash as user ---
echo "[6/8] User model study: gemini-3-flash as user"
echo "========================================"
uv run pare benchmark sweep \
  --split ablation \
  --observe-model claude-4.5-sonnet,gemini-3-flash,qwen-3-4b-it,gpt-5 \
  --execute-model claude-4.5-sonnet,gemini-3-flash,qwen-3-4b-it,gpt-5 \
  --user-model gemini-3-flash --max-turns 10 -omi 5 -emi 10 -umi 1 \
  --runs 4 -c 6 --executor-type thread \
  --experiment-name paper_user_model_study --export --output-dir ./traces --log-level WARNING
echo "[6/8] User model study: gemini-3-flash -- DONE"
echo ""

# --- 7. Asymmetric: fix execute to claude-sonnet, vary observe ---
echo "[7/8] Asymmetric: fix execute, vary observe"
echo "========================================"
uv run pare benchmark sweep \
  --split ablation \
  --observe-model gpt-5,claude-4.5-sonnet,gemini-3-pro,qwen-3-4b-it \
  --execute-model claude-4.5-sonnet,claude-4.5-sonnet,claude-4.5-sonnet,claude-4.5-sonnet \
  --user-model gpt-5-mini --max-turns 10 -omi 5 -emi 10 -umi 1 \
  --runs 4 -c 6 --executor-type thread \
  --experiment-name paper_asymmetric_fix_exec --export --output-dir ./traces --log-level WARNING
echo "[7/8] Asymmetric: fix execute -- DONE"
echo ""

# --- 8. Asymmetric: fix observe to claude-sonnet, vary execute ---
echo "[8/8] Asymmetric: fix observe, vary execute"
echo "========================================"
uv run pare benchmark sweep \
  --split ablation \
  --observe-model claude-4.5-sonnet,claude-4.5-sonnet,claude-4.5-sonnet,claude-4.5-sonnet \
  --execute-model gpt-5,claude-4.5-sonnet,gemini-3-pro,qwen-3-4b-it \
  --user-model gpt-5-mini --max-turns 10 -omi 5 -emi 10 -umi 1 \
  --runs 4 -c 6 --executor-type thread \
  --experiment-name paper_asymmetric_fix_obs --export --output-dir ./traces --log-level WARNING
echo "[8/8] Asymmetric: fix observe -- DONE"
echo ""

# --- Summary ---
FINISHED_AT=$(date +"%Y-%m-%d %H:%M:%S")
echo "========================================"
echo "All experiments complete"
echo "Started:  $STARTED_AT"
echo "Finished: $FINISHED_AT"
echo "========================================"
