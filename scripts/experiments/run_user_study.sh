#!/bin/bash
#
# User-model study: cross 4 user models with 4 proactive models on the
# ablation split. Each (user_model, proactive_model) pair is one run.
#
# Originally blocks 3-6 of run_all_2026_03_30.sh.
#
# Note: `set -e` is intentionally not used so that a single failed run
# (e.g. transient probe/API failure for one model) does not abort the
# remaining configs. A summary at the end reports how many configs failed.
#
# Usage:
#   ./scripts/experiments/run_user_study.sh
#

STARTED_AT=$(date +"%Y-%m-%d %H:%M:%S")
echo "========================================"
echo "User model study"
echo "Started at: $STARTED_AT"
echo "========================================"
echo ""

USER_MODELS=(claude-4.5-sonnet gpt-5-mini qwen-3-4b-it gemini-3-flash)
PROACTIVE_MODELS=(claude-4.5-sonnet gemini-3-flash qwen-3-4b-it gpt-5)
TOTAL_CONFIGS=$(( ${#USER_MODELS[@]} * ${#PROACTIVE_MODELS[@]} ))

CURRENT=0
FAILED=0
FAILED_CONFIGS=()

for USER_MODEL in "${USER_MODELS[@]}"; do
  for PROACTIVE_MODEL in "${PROACTIVE_MODELS[@]}"; do
    CURRENT=$((CURRENT + 1))
    echo ""
    echo "========================================"
    echo "[$CURRENT/$TOTAL_CONFIGS] split=ablation, user=$USER_MODEL, observe=$PROACTIVE_MODEL, execute=$PROACTIVE_MODEL"
    echo "========================================"
    if ! uv run pare benchmark run \
        --split ablation \
        --observe-model "$PROACTIVE_MODEL" --execute-model "$PROACTIVE_MODEL" \
        --user-model "$USER_MODEL" --max-turns 10 -omi 5 -emi 10 -umi 1 \
        --runs 4 -c 6 --executor-type thread \
        --experiment-name paper_user_model_study --export --output-dir ./traces --log-level ERROR; then
      FAILED=$((FAILED + 1))
      FAILED_CONFIGS+=("user=$USER_MODEL proactive=$PROACTIVE_MODEL")
      echo "WARN: config failed: user=$USER_MODEL proactive=$PROACTIVE_MODEL" >&2
    fi
  done
done

FINISHED_AT=$(date +"%Y-%m-%d %H:%M:%S")
echo ""
echo "========================================"
echo "User model study complete"
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
