from __future__ import annotations

from pas.scenarios import build_contacts_followup_components
from pas.scripts.run_demo import run_proactive_demo

# Equivalent CLI: python -m pas.scripts.run_demo \
#   --builder pas.scenarios.contacts_followup.build_contacts_followup_components
if __name__ == "__main__":
    run_proactive_demo(build_contacts_followup_components)
