# Summary and Deduplication

This page documents the current summary and deduplication modules used by the scenario generator.

## Summary Generation Agent

::: pas.scenarios.generator.agent.summary_generating_agent

## Deduplication Utility

::: pas.scenarios.generator.utils.deduplicate_scenarios

## How It Fits the Generator Flow

During generation, candidate scenarios are compared against historical metadata and deduplication rules so new scenarios stay semantically distinct.

Related files:

- `pas/scenarios/scenario_metadata.json`
- `pas/scenarios/generator/agent/scenario_uniqueness_agent.py`
