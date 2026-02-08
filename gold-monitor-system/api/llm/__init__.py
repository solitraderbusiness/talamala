"""
LLM integration for generating Persian alert text via OpenRouter.

The LLM is used ONLY for text generation (summaries, explanations, questions).
It must NEVER determine severity, importance, or time horizon — those are set
exclusively by the deterministic rule engine.
"""

from api.llm.openrouter_client import OpenRouterClient

__all__ = ["OpenRouterClient"]
