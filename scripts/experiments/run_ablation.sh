#!/bin/bash
#
# Run the ablation split with tool-failure-probability and env-events-per-min
# noise sweeps. Per the original sweep semantics, tfp and epm are treated as
# independent noise dimensions (never combined together) -- each value produces
# a separate run.
#
# Usage:
#   ./scripts/experiments/run_ablation.sh
#

STARTED_AT=$(date +"%Y-%m-%d %H:%M:%S")
echo "========================================"
echo "Ablation benchmark rerun"
echo "Started at: $STARTED_AT"
echo "========================================"
echo ""

MODELS=(qwen-3-4b-it gemma-3-4b-it llama-3.2-3b-it claude-4.5-sonnet gpt-5 gemini-3-pro gemini-3-flash)
TFP_VALUES=(0.1 0.2 0.4)
EPM_VALUES=(2 4 6)
# Per model: 1 no-noise + |tfp| + |epm| configs.
TOTAL_CONFIGS=$((${#MODELS[@]} * (1 + ${#TFP_VALUES[@]} + ${#EPM_VALUES[@]})))

CURRENT=0
FAILED=0
FAILED_CONFIGS=()

for MODEL in "${MODELS[@]}"; do
  # No-noise baseline (covers original -tfp 0.0 / -epm 0 entries, which both
  # collapse to the same (None, None) noise config).
  CURRENT=$((CURRENT + 1))
  echo ""
  echo "========================================"
  echo "[$CURRENT/$TOTAL_CONFIGS] split=ablation, user=gpt-5-mini, observe=$MODEL, execute=$MODEL, noise=none"
  echo "========================================"
  if ! uv run pare benchmark run \
    --split ablation \
    --observe-model "$MODEL" --execute-model "$MODEL" \
    --user-model gpt-5-mini --max-turns 10 -omi 5 -emi 10 -umi 1 \
    --runs 4 -c 6 --executor-type thread \
    --experiment-name paper_benchmark --export --output-dir ./traces --log-level ERROR; then
    FAILED=$((FAILED + 1))
    FAILED_CONFIGS+=("$MODEL no-noise")
    echo "WARN: config failed: $MODEL no-noise" >&2
  fi

  # Tool failure probability sweep
  for TFP in "${TFP_VALUES[@]}"; do
    CURRENT=$((CURRENT + 1))
    echo ""
    echo "========================================"
    echo "[$CURRENT/$TOTAL_CONFIGS] split=ablation, user=gpt-5-mini, observe=$MODEL, execute=$MODEL, noise=tfp_$TFP"
    echo "========================================"
    if ! uv run pare benchmark run \
      --split ablation \
      --observe-model "$MODEL" --execute-model "$MODEL" \
      --user-model gpt-5-mini --max-turns 10 -omi 5 -emi 10 -umi 1 \
      -tfp "$TFP" \
      --runs 4 -c 6 --executor-type thread \
      --experiment-name paper_benchmark --export --output-dir ./traces --log-level ERROR; then
      FAILED=$((FAILED + 1))
      FAILED_CONFIGS+=("$MODEL tfp=$TFP")
      echo "WARN: config failed: $MODEL tfp=$TFP" >&2
    fi
  done

  # Environmental events per minute sweep
  for EPM in "${EPM_VALUES[@]}"; do
    CURRENT=$((CURRENT + 1))
    echo ""
    echo "========================================"
    echo "[$CURRENT/$TOTAL_CONFIGS] split=ablation, user=gpt-5-mini, observe=$MODEL, execute=$MODEL, noise=epm_$EPM"
    echo "========================================"
    if ! uv run pare benchmark run \
      --split ablation \
      --observe-model "$MODEL" --execute-model "$MODEL" \
      --user-model gpt-5-mini --max-turns 10 -omi 5 -emi 10 -umi 1 \
      -epm "$EPM" --env-events-seed 42 \
      --runs 4 -c 6 --executor-type thread \
      --experiment-name paper_benchmark --export --output-dir ./traces --log-level ERROR; then
      FAILED=$((FAILED + 1))
      FAILED_CONFIGS+=("$MODEL epm=$EPM")
      echo "WARN: config failed: $MODEL epm=$EPM" >&2
    fi
  done
done

FINISHED_AT=$(date +"%Y-%m-%d %H:%M:%S")
echo ""
echo "========================================"
echo "Ablation benchmark complete"
echo "Started:  $STARTED_AT"
echo "Finished: $FINISHED_AT"
echo "Configs:  $((CURRENT - FAILED))/$TOTAL_CONFIGS succeeded, $FAILED failed"
if ((FAILED > 0)); then
  echo "Failed configs:"
  for CFG in "${FAILED_CONFIGS[@]}"; do
    echo "  - $CFG"
  done
fi
echo "========================================"
