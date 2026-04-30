#!/bin/bash
#
# Asymmetric proactive-agent experiments on the ablation split. Two directions:
#   1. Fix execute=claude-4.5-sonnet, vary observe across 4 models
#   2. Fix observe=claude-4.5-sonnet, vary execute across 4 models
#
# Originally blocks 7-8 of run_all_2026_03_30.sh.
#
# Note: `set -e` is intentionally not used so that a single failed run
# (e.g. transient probe/API failure for one model) does not abort the
# remaining configs. A summary at the end reports how many configs failed.
#
# Usage:
#   ./scripts/experiments/run_asymmetric.sh
#

STARTED_AT=$(date +"%Y-%m-%d %H:%M:%S")
echo "========================================"
echo "Asymmetric proactive-agent experiments"
echo "Started at: $STARTED_AT"
echo "========================================"
echo ""

VARYING_MODELS=(gpt-5 claude-4.5-sonnet gemini-3-pro qwen-3-4b-it)
# 2 directions (fix-exec, fix-obs) x N varying models.
TOTAL_CONFIGS=$(( ${#VARYING_MODELS[@]} * 2 ))

CURRENT=0
FAILED=0
FAILED_CONFIGS=()

# --- Direction 1: fix execute=claude-4.5-sonnet, vary observe ---
for OBSERVE in "${VARYING_MODELS[@]}"; do
  CURRENT=$((CURRENT + 1))
  echo ""
  echo "========================================"
  echo "[$CURRENT/$TOTAL_CONFIGS] split=ablation, fix-exec, user=gpt-5-mini, observe=$OBSERVE, execute=claude-4.5-sonnet"
  echo "========================================"
  if ! uv run pare benchmark run \
      --split ablation \
      --observe-model "$OBSERVE" --execute-model claude-4.5-sonnet \
      --user-model gpt-5-mini --max-turns 10 -omi 5 -emi 10 -umi 1 \
      --runs 4 -c 6 --executor-type thread \
      --experiment-name paper_asymmetric_fix_exec --export --output-dir ./traces --log-level ERROR; then
    FAILED=$((FAILED + 1))
    FAILED_CONFIGS+=("[fix-exec] observe=$OBSERVE")
    echo "WARN: config failed: [fix-exec] observe=$OBSERVE" >&2
  fi
done

# --- Direction 2: fix observe=claude-4.5-sonnet, vary execute ---
for EXECUTE in "${VARYING_MODELS[@]}"; do
  CURRENT=$((CURRENT + 1))
  echo ""
  echo "========================================"
  echo "[$CURRENT/$TOTAL_CONFIGS] split=ablation, fix-obs, user=gpt-5-mini, observe=claude-4.5-sonnet, execute=$EXECUTE"
  echo "========================================"
  if ! uv run pare benchmark run \
      --split ablation \
      --observe-model claude-4.5-sonnet --execute-model "$EXECUTE" \
      --user-model gpt-5-mini --max-turns 10 -omi 5 -emi 10 -umi 1 \
      --runs 4 -c 6 --executor-type thread \
      --experiment-name paper_asymmetric_fix_obs --export --output-dir ./traces --log-level ERROR; then
    FAILED=$((FAILED + 1))
    FAILED_CONFIGS+=("[fix-obs] execute=$EXECUTE")
    echo "WARN: config failed: [fix-obs] execute=$EXECUTE" >&2
  fi
done

FINISHED_AT=$(date +"%Y-%m-%d %H:%M:%S")
echo ""
echo "========================================"
echo "Asymmetric experiments complete"
echo "Started:  $STARTED_AT"
echo "Finished: $FINISHED_AT"
echo "Configs:  $((CURRENT - FAILED))/$TOTAL_CONFIGS succeeded, $FAILED failed"
if (( FAILED > 0 )); then
  echo "Failed configs:"
  for CFG in "${FAILED_CONFIGS[@]}"; do
    echo "  - $CFG"
  done
fi
echo "========================================"
