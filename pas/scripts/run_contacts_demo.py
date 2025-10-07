"""Run the contacts follow-up scenario via the generic demo runner."""

from __future__ import annotations

import typing
from typing import Literal

from pas.scenarios import build_contacts_followup_components
from pas.scripts.run_demo import run_proactive_demo


def run_demo(messages: typing.Iterable[str] | None = None, mode: Literal["event", "user"] = "event") -> None:
    """Run the contacts follow-up scenario once and print a summary."""
    run_proactive_demo(build_contacts_followup_components, mode=mode, messages=messages)


if __name__ == "__main__":
    run_demo()
