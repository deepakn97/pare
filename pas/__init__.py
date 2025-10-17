"""Core modules for the Proactive Agent System."""

from __future__ import annotations

from .llm_adapter import LLMClientProtocol, PasLLMEngine

__all__ = ["LLMClientProtocol", "PasLLMEngine"]
__version__ = "0.1.0"
