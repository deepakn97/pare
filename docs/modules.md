# API Reference Overview

This section provides comprehensive API documentation for all PAS modules, automatically generated from the codebase.

## Core Modules

### [Environment](api/environment.md)
State-aware environment wrapper that monitors events and triggers navigation transitions.

- `StateAwareEnvironmentWrapper` – Core environment wrapper

### [Stateful Apps](api/apps.md)
Stateful wrappers around Meta-ARE mobile apps with navigation state machines.

- `core` – Base classes (`AppState`, `StatefulApp`)
- `contacts` – Contacts app and states
- `email` – Email app and states
- `calendar` – Calendar app and states
- `messaging` – Messaging app and states
- `proactive_agent_ui` – Proactive agent user interface
- `system` – System-level apps

## Scenario System

### [Scenarios](api/scenarios.md)
Scenario builders and configuration for proactive experiments.

- `base` – Base scenario builder (`build_proactive_stack`)
- `types` – Type definitions (`OracleAction`, etc.)
- `contacts_followup` – Example scenario

### [Scenario Generator](api/scenario_generator.md)
Automated scenario generation pipeline.

- `ScenarioGeneratingAgent` – Main generator class
