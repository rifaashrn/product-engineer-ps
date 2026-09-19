import json
import os
from typing import Annotated, Any, Protocol, Union

from pydantic import Field, TypeAdapter, ValidationError

from .schemas import FinalAnswer, ModelDecision, ToolCall
from .tools import TOOLS, known_services


class ModelError(Exception):
    """The model returned something unusable (bad JSON, wrong shape, API error)."""


class ModelUnavailable(ModelError):
    """Rate limit or outage. Retrying immediately would not help."""


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


# --- Parsing: the boundary between model text and our typed decisions ---

_decision_adapter = TypeAdapter(
    Annotated[Union[ToolCall, FinalAnswer], Field(discriminator="type")]
)


def parse_decision(text: str | None) -> ModelDecision:
    """Turn the model's raw text into a validated decision, or raise ModelError."""
    if not text or not text.strip():
        raise ModelError("empty response")
    cleaned = text.strip()
    if cleaned.startswith("```"):  # models sometimes wrap JSON in a code fence
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ModelError(f"reply was not valid JSON: {exc}") from exc
    try:
        return _decision_adapter.validate_python(data)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()
        )
        raise ModelError(f"reply did not match the required format: {details}") from exc


# --- Prompting ---

_SYSTEM_PROMPT_TEMPLATE = """You are an incident investigator. Answer the user's \
question using ONLY evidence returned by tools.

Available tools:
{TOOLS}

Known services (use these exact names): {SERVICES}

On every turn reply with exactly one JSON object and nothing else.

To call a tool:
{"type": "tool_call", "tool": "<tool name>", "arguments": {...}, "rationale": "<one short sentence>"}

When you have enough evidence, give the final answer:
{"type": "final_answer", "evidence": ["<fact taken from a tool result>", ...], "conclusion": "<your inference>", "recommendations": ["<optional next step>"]}

Rules:
- Call one tool per turn.
- Never guess service names; use the known services above.
- If a tool returns an error, read it and try a different approach.
- "evidence" may contain only facts that appear in tool results. Put your own reasoning only in "conclusion".
- Keep "rationale" to one short sentence. Do not include private reasoning."""


def build_system_prompt() -> str:
    lines = []
    for tool in TOOLS.values():
        schema = json.dumps(tool.args_model.model_json_schema()["properties"])
        lines.append(f"- {tool.name}: {tool.description} Arguments: {schema}")
    return (
        _SYSTEM_PROMPT_TEMPLATE
        .replace("{TOOLS}", "\n".join(lines))
        .replace("{SERVICES}", ", ".join(known_services()))
    )


def _to_transcript(messages: list[dict[str, Any]]) -> str:
    lines = [f"[{m['role']}] {m['content']}" for m in messages]
    return "\n".join(lines) + "\n\nReply with your next JSON object."


class GeminiModel:
    """Real model adapter. The loop only sees the ModelAdapter interface."""

    def __init__(self, api_key: str | None = None, model_name: str | None = None) -> None:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise ModelError("google-genai is not installed (pip install google-genai)") from exc

        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ModelError("GEMINI_API_KEY is not set (see .env.example)")
        self._types = types
        self._client = genai.Client(api_key=key)
        self._model_name = model_name or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        self._system_prompt = build_system_prompt()

    def next_decision(self, messages: list[dict[str, Any]]) -> ModelDecision:
        try:
            response = self._client.models.generate_content(
                model=self._model_name,
                contents=_to_transcript(messages),
                config=self._types.GenerateContentConfig(
                    system_instruction=self._system_prompt,
                    response_mime_type="application/json",
                    temperature=0,
                ),
            )
            text = response.text
        except Exception as exc:
            code = getattr(exc, "code", None)
            if code in (429, 503) or "RESOURCE_EXHAUSTED" in str(exc):
                raise ModelUnavailable(
                    f"Gemini is rate-limited or unavailable ({code or 'quota exceeded'})"
                ) from exc
            raise ModelError(f"Gemini API error: {exc}") from exc
        return parse_decision(text)