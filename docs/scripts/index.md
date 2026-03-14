# Scripts Overview

The `scripts/` directory contains operational workflows around running experiments, generating scenarios in batches, and post-processing results.

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

- `scripts/experiments/run_models_sweep.sh`
- `scripts/experiments/model_sweep_tfp.sh`
- `scripts/experiments/model_sweep_env_noise.sh`

## Recommendation

For new workflows, prefer the `pare` CLI where possible:

- `pare benchmark sweep`
- `pare scenarios list`
- `pare scenarios generate`
