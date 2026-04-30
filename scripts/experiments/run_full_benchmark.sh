#!/bin/bash
#
# Run the full benchmark split across the paper's evaluation model set.
# One pare benchmark run invocation per (observe, execute) model pair.
#
# Originally block 1 of run_all_2026_03_30.sh.
#
# Note: `set -e` is intentionally not used so that a single failed run
# (e.g. transient probe/API failure for one model) does not abort the
# remaining configs. A summary at the end reports how many configs failed.
#
# Usage:
#   ./scripts/experiments/run_full_benchmark.sh
#

STARTED_AT=$(date +"%Y-%m-%d %H:%M:%S")
echo "========================================"
echo "Full benchmark rerun"
echo "Started at: $STARTED_AT"
echo "========================================"
echo ""

MODELS=(qwen-3-4b-it gemma-3-4b-it llama-3.2-3b-it claude-4.5-sonnet gpt-5 gemini-3-pro gemini-3-flash)
TOTAL_CONFIGS=${#MODELS[@]}

CURRENT=0
FAILED=0
FAILED_CONFIGS=()

for MODEL in "${MODELS[@]}"; do
  CURRENT=$((CURRENT + 1))
  echo ""
  echo "========================================"
  echo "[$CURRENT/$TOTAL_CONFIGS] split=full, user=gpt-5-mini, observe=$MODEL, execute=$MODEL"
  echo "========================================"
  if ! uv run pare benchmark run \
      --split full \
      --observe-model "$MODEL" --execute-model "$MODEL" \
      --user-model gpt-5-mini --max-turns 10 -omi 5 -emi 10 -umi 1 \
      --runs 4 -c 6 --executor-type thread \
      --experiment-name paper_benchmark --export --output-dir ./traces --log-level ERROR; then
    FAILED=$((FAILED + 1))
    FAILED_CONFIGS+=("$MODEL")
    echo "WARN: config failed: $MODEL" >&2
  fi
done

FINISHED_AT=$(date +"%Y-%m-%d %H:%M:%S")
echo ""
echo "========================================"
echo "Full benchmark complete"
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
