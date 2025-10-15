# proactiveGoalInference

[![Release](https://img.shields.io/github/v/release/deepakn97/proactiveGoalInference)](https://img.shields.io/github/v/release/deepakn97/proactiveGoalInference)
[![Build status](https://img.shields.io/github/actions/workflow/status/deepakn97/proactiveGoalInference/main.yml?branch=main)](https://github.com/deepakn97/proactiveGoalInference/actions/workflows/main.yml?query=branch%3Amain)
[![Commit activity](https://img.shields.io/github/commit-activity/m/deepakn97/proactiveGoalInference)](https://img.shields.io/github/commit-activity/m/deepakn97/proactiveGoalInference)
[![License](https://img.shields.io/github/license/deepakn97/proactiveGoalInference)](https://img.shields.io/github/license/deepakn97/proactiveGoalInference)

This repository contains code for the Proactive Goal Inference Agent project in collaboration with Apple.

## Contacts App Navigation

StatefulContactsApp layers a mobile-style navigation model over the native Meta-ARE contacts application so tooling aligns with the same surface the proactive agent observes.

- `ContactsList` is the initial state and surfaces the native `get_contacts`, `search_contacts`, `get_contact`, `get_current_user_details`, and `add_new_contact` tools through user-facing wrappers. This lets the user simulation scroll, search, view their own contact card, open, or create contacts while remaining in list context.
- `ContactDetail` captures the currently selected `contact_id` and provides focused access to `get_contact`, as well as destructive actions like `delete_contact`. It also offers a user flow entry point into editing without exposing list-only interactions.
- `ContactEdit` introduces a dedicated edit surface. It uses the underlying `edit_contact` API to persist updates and relies on navigation stack/go_back to exit, ensuring the native write tool is connected to an explicit UI state.

All states rely on StatefulApp's navigation stack so `go_back` is only surfaced when history exists, mirroring the messaging app behaviour and keeping the original user tools available from at least one screen.
