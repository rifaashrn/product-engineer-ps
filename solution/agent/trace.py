import re
from pathlib import Path
from typing import Any

from .schemas import TraceEvent

_REDACTION_RULES = [
    (re.compile(r"AIza[0-9A-Za-z_\-]{20,}"), "[REDACTED]"),
    (re.compile(r"sk-[0-9A-Za-z_\-]{20,}"), "[REDACTED]"),
    (re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\b(\s*[:=]\s*)\S+"),
     r"\1\2[REDACTED]"),
]


def redact(value: Any) -> Any:
    """Recursively scrub secret-looking strings."""
    if isinstance(value, str):
        for pattern, replacement in _REDACTION_RULES:
            value = pattern.sub(replacement, value)
        return value
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


class Trace:
    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def add(self, step: int, kind: str, **data: Any) -> TraceEvent:
        event = TraceEvent(step=step, kind=kind, data=redact(data))
        self.events.append(event)
        return event

    def save(self, path: Path) -> None:
        """Write one JSON event per line (JSONL)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for event in self.events:
                f.write(event.model_dump_json() + "\n")