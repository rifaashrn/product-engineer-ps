from datetime import datetime, timezone
from typing import Any, Literal, Union

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """The model asks us to run a tool."""
    type: Literal["tool_call"] = "tool_call"
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""  # one short sentence, NOT hidden reasoning


class FinalAnswer(BaseModel):
    """The model is done. Evidence and conclusions are kept separate."""
    type: Literal["final_answer"] = "final_answer"
    evidence: list[str]       # facts that came from tool results
    conclusion: str           # the agent's own inference
    recommendations: list[str] = Field(default_factory=list)


ModelDecision = Union[ToolCall, FinalAnswer]


class TraceEvent(BaseModel):
    step: int
    kind: Literal[
        "objective", "model_decision", "tool_call", "tool_result",
        "error", "final_answer", "stopped",
    ]
    data: dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))