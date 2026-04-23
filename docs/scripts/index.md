# Scripts Overview

Most users should start with the `pare` CLI. The `scripts/` directory is for batch workflows, review-set preparation, and post-processing after benchmark runs.

## When To Use Scripts

Use the scripts in this folder when you need to:

- run repeatable experiment wrappers beyond a single CLI invocation
- batch-generate scenarios or distribute them to reviewers
- aggregate results and produce analysis artifacts
- inspect dataset or app-usage coverage across many runs

If you only want to run the benchmark once, start here instead:

```bash
uv run pare benchmark run --split full --observe-model gpt-5 --execute-model gpt-5
```

## Core Scripts

- `scripts/run_scenarios.py`: run one/all registered scenarios and write trace summaries.
- `scripts/run_scenario_generator_batch.py`: batch wrapper for the scenario generator.
- `scripts/create_review_csvs.py`: distribute generated scenarios into reviewer buckets.

## Analysis Scripts

- `scripts/analyze_metrics.py`: aggregate traces into evaluation metrics.
- `scripts/analyze_app_usage.py`: inspect app coverage across scenarios.
- `scripts/create_stratified_sample.py`: build app-balanced benchmark splits.
- `scripts/plots/plot_ablation_robustness.py`: generate robustness plots from combined benchmark results.

## Experiment Wrappers

Bash wrappers for sweeping over multiple model configurations. Each iteration calls `pare benchmark run` with a different config:

- `scripts/experiments/run_models_sweep.sh`
- `scripts/experiments/model_sweep_tfp.sh`
- `scripts/experiments/model_sweep_env_noise.sh`

## Recommendation

For new workflows, prefer the `pare` CLI where possible:

- `pare benchmark run`
- `pare benchmark report`
- `pare scenarios list`
- `pare scenarios generate`
