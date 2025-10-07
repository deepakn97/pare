from __future__ import annotations

import logging
from dataclasses import dataclass

from pas.user_proxy.decision_maker import LLMDecisionMaker


@dataclass
class StubLLM:
    """Queue-backed stub that mimics the LLM interface."""

    responses: list[str]
    last_prompt: str | None = None

    def complete(self, prompt: str) -> str:
        """Return the next queued response for ``prompt``."""
        self.last_prompt = prompt
        if not self.responses:
            raise RuntimeError("StubLLM exhausted")
        return self.responses.pop(0)


def _logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def test_llm_decision_maker_parses_json_accept() -> None:
    """LLMDecisionMaker should parse explicit accept decisions."""
    llm = StubLLM(['{"decision": "accept"}'])
    maker = LLMDecisionMaker(llm, logger=_logger("tests.decision.accept"))
    decision, raw = maker.decide("Allow the assistant?", accept_tokens={"accept"}, decline_tokens={"decline"})
    assert decision is True
    assert "decision" in raw
