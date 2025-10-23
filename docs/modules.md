# API Reference Overview

This section provides comprehensive API documentation for all PAS modules, automatically generated from the codebase.

## Core Modules

### [System & Session](api/system.md)
Runtime orchestration, session management, and proactive execution helpers.

- `ProactiveSession` – Main orchestration loop
- `Runtime` – Stack initialization helpers
- `NotificationSystem` – Event broadcasting
- `Proactive` – Proactive execution helpers

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

## Agent Components

### [User Proxy](api/user_proxy.md)
User simulation with ReAct-based reasoning.

- `StatefulUserAgent` – ReAct agent implementation built on Meta ARE's BaseAgent
- `StatefulUserAgentRuntime` – Runtime coordinator for the user agent
- `PasJsonActionExecutor` – Custom action executor with event synchronization

### [Proactive Agent](api/proactive_agent.md)
Proactive goal inference and autonomous task execution.

- `LLMBasedProactiveAgent` – Core proactive agent
- `LiteLLMClient` – LLM client wrapper
- `ReActAdapter` – ReAct planning adapter

## Scenario System

### [Scenarios](api/scenarios.md)
Scenario builders and configuration for proactive experiments.

- `base` – Base scenario builder (`build_proactive_stack`)
- `types` – Type definitions (`OracleAction`, etc.)
- `contacts_followup` – Example scenario

### [Scenario Generator](api/scenario_generator.md)
Automated scenario generation pipeline.

- `ScenarioGeneratingAgent` – Main generator class

## Utilities

### [Adapters & Validation](api/adapters.md)
Meta-ARE adapter and oracle-based validation.

- `meta_adapter` – Convert Meta-ARE scenarios to PAS
- `oracles` – Oracle tracking for validation

### [Logging](api/logging.md)
Logging utilities and configuration.

- `logging_utils` – Logging configuration helpers
