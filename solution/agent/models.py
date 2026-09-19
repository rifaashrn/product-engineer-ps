from typing import Any, Protocol

from .schemas import ModelDecision


class ModelError(Exception):
    """The model returned something unusable (bad JSON, wrong shape, API error)."""


class ModelAdapter(Protocol):
    def next_decision(self, messages: list[dict[str, Any]]) -> ModelDecision:
        ...


class FakeModel:
    """Replays a scripted list of decisions. Used in tests and offline demos."""

    def __init__(self, script: list[ModelDecision | Exception]) -> None:
        self._script = list(script)
        self.calls = 0  # lets tests prove how many times the model was called

    def next_decision(self, messages: list[dict[str, Any]]) -> ModelDecision:
        self.calls += 1
        if not self._script:
            raise RuntimeError("FakeModel script exhausted")
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item