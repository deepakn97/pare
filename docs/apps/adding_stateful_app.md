# Adding a Stateful App

This guide describes the current PARE app-extension pattern under `pare/apps`.

## 1) Create the App Package

Create:

```text
pare/apps/<app_name>/
  __init__.py
  app.py
  states.py
```

Follow existing apps (for example `pare/apps/contacts` or `pare/apps/apartment`) as templates.

## 2) Define States

In `states.py`, define `AppState` subclasses with `@user_tool()` methods and optional `@pare_event_registered(...)` metadata.

Use this pattern:

- one class per UI state/screen
- explicit transition intent in method names
- clear docstrings (used by docs and generation prompts)

## 3) Implement `Stateful<App>` Wrapper

In `app.py`:

- subclass `StatefulApp` + the underlying app class
- call `load_root_state()` during initialization
- implement `create_root_state()`
- implement `handle_state_transition(event)` to drive navigation stack updates

## 4) Export and Register

Update package exports:

- `pare/apps/<app_name>/__init__.py`
- `pare/apps/__init__.py`

Include the app in `ALL_APPS` (in `pare/apps/__init__.py`) so shared exports and app inventories stay current.

If the new app should also be available to the scenario generator prompt context, update:

- `pare/scenarios/generator/utils/apps_init_instructions.py`

The generator currently builds its app/tool context from `ScenarioWithAllPAREApps`, so adding an app to `ALL_APPS` alone is not sufficient for generator visibility.

## 5) Add Documentation

- Create `docs/apps/<app_name>.md`
- Link it in `docs/apps/index.md`
- Add it to `mkdocs.yml` nav

## 6) Test

Add tests for:

- root state initialization
- tool availability per state
- navigation transitions in `handle_state_transition`

A practical template is to mirror test coverage style used for existing stateful apps in `tests/`.
