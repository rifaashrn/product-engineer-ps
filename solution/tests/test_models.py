import pytest

from solution.agent.models import ModelError, build_system_prompt, parse_decision
from solution.agent.schemas import FinalAnswer, ToolCall


def test_parse_tool_call():
    decision = parse_decision(
        '{"type": "tool_call", "tool": "search_logs", '
        '"arguments": {"service": "checkout-api"}, "rationale": "check errors"}'
    )
    assert isinstance(decision, ToolCall)
    assert decision.tool == "search_logs"


def test_parse_final_answer_inside_code_fence():
    text = '```json\n{"type": "final_answer", "evidence": ["a"], "conclusion": "b"}\n```'
    assert isinstance(parse_decision(text), FinalAnswer)


@pytest.mark.parametrize("bad", [
    "",
    "not json",
    '{"type": "final_answer"}',
    '{"tool": "search_logs"}',
    "[1, 2]",
])
def test_parse_rejects_unusable_output(bad):
    with pytest.raises(ModelError):
        parse_decision(bad)


def test_system_prompt_lists_every_tool():
    prompt = build_system_prompt()
    for name in ("search_logs", "get_metrics", "get_service_status"):
        assert name in prompt