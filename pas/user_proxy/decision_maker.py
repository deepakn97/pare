"""LLM-backed decision maker for system-level user confirmations."""

from __future__ import annotations

import json
import re
import typing
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from logging import Logger

    from pas.proactive.agent import LLMClientProtocol


class DecisionMakerProtocol(Protocol):
    """Contract for components that turn a system prompt into a bool decision."""

    def decide(
        self,
        prompt: str,
        *,
        accept_tokens: typing.Iterable[str],
        decline_tokens: typing.Iterable[str],
        capture_decision: bool = True,
    ) -> tuple[bool | None, str]:
        """Return (decision, raw_response). ``decision`` is ``True``/``False`` or ``None``."""


class LLMDecisionMaker(DecisionMakerProtocol):
    """Use an LLM to answer yes/no style questions with JSON output."""

    _JSON_PATTERN = re.compile(r"\{.*\}", re.DOTALL)

    def __init__(self, llm: LLMClientProtocol, *, logger: Logger, system_prompt: str | None = None) -> None:
        """Initialise the decision maker with the backing LLM and logger."""
        self._llm = llm
        self._logger = logger
        self._system_prompt = system_prompt or (
            "You are the phone owner responding to a proactive assistant. "
            "Read the prompt and output JSON with a single key 'decision' whose value is "
            "either 'accept', 'decline', or another token you deem appropriate. Do not add prose."
        )

    def decide(
        self,
        prompt: str,
        *,
        accept_tokens: typing.Iterable[str],
        decline_tokens: typing.Iterable[str],
        capture_decision: bool = True,
    ) -> tuple[bool | None, str]:
        """Return the parsed decision (`True`/`False`/`None`) and raw response."""
        accept = {token.strip().lower() for token in accept_tokens if token.strip()}
        decline = {token.strip().lower() for token in decline_tokens if token.strip()}

        lines: list[str] = [self._system_prompt, "Context:", prompt.strip(), ""]
        token_lines: list[str] = []
        if accept:
            token_lines.append(f"Acceptance tokens: {sorted(accept)}")
        if decline:
            token_lines.append(f"Decline tokens: {sorted(decline)}")
        instruction = 'Respond with JSON, e.g. {"decision": "accept"}. If unsure, set decision to \'unsure\'.'
        if token_lines:
            instruction = instruction + " Allowed tokens -> " + "; ".join(token_lines)
        lines.append(instruction)
        request = "\n".join(lines)

        self._logger.debug("Decision prompt:\n%s", request)
        response = self._llm.complete(request)
        self._logger.debug("Decision raw response: %s", response)

        decision = self._parse_decision(response, accept, decline)
        if not capture_decision:
            return None, response
        return decision, response

    def _parse_decision(self, response: str, accept: set[str], decline: set[str]) -> bool | None:
        text = response.strip()
        choice = self._extract_choice(text)
        if choice is not None:
            return self._normalise_choice(choice, accept, decline)
        return self._match_tokens(text.lower(), accept, decline)

    def _extract_choice(self, text: str) -> str | None:
        match = self._JSON_PATTERN.search(text)
        if not match:
            return None
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        raw = payload.get("decision")
        if isinstance(raw, str):
            return raw.strip().lower()
        return None

    def _match_tokens(self, lowered: str, accept: set[str], decline: set[str]) -> bool | None:
        if accept and any(token in lowered for token in accept):
            return True
        if decline and any(token in lowered for token in decline):
            return False
        return None

    def _normalise_choice(self, choice: str, accept: set[str], decline: set[str]) -> bool | None:
        if choice in accept or (choice == "accept" and not accept):
            return True
        if choice in decline or (choice == "decline" and not decline):
            return False
        if choice == "unsure":
            return None
        if accept and not decline and choice in {"yes", "ok", "received"}:
            return True
        if decline and not accept and choice in {"no"}:
            return False
        return None


__all__ = ["DecisionMakerProtocol", "LLMDecisionMaker"]
