from solution.agent.loop import run_agent
from solution.agent.models import FakeModel, ModelError, ModelUnavailable
from solution.agent.schemas import FinalAnswer, ToolCall


def call(tool: str, **arguments) -> ToolCall:
    return ToolCall(tool=tool, arguments=arguments, rationale="test")


def answer() -> FinalAnswer:
    return FinalAnswer(evidence=["some evidence"], conclusion="some conclusion")


def kinds(result) -> list[str]:
    return [event.kind for event in result.trace.events]


def test_multi_step_investigation_produces_ordered_trace():
    model = FakeModel([
        call("search_logs", service="checkout-api", keyword="timeout"),
        call("get_metrics", service="payments-db", metric="connection_pool_usage_pct"),
        FinalAnswer(
            evidence=["checkout-api logs show timeouts to payments-db",
                      "payments-db pool usage reached 100%"],
            conclusion="Checkout fails because the payments-db pool is exhausted.",
        ),
    ])

    result = run_agent("Why is checkout failing?", model)

    assert result.stop_reason == "final_answer"
    assert model.calls == 3
    assert kinds(result) == [
        "objective",
        "model_decision", "tool_call", "tool_result",
        "model_decision", "tool_call", "tool_result",
        "model_decision", "final_answer",
    ]
    tool_results = [e for e in result.trace.events if e.kind == "tool_result"]
    assert tool_results[0].data["tool"] == "search_logs"
    assert len(tool_results[0].data["result"]) >= 1
    assert "exhausted" in result.final_answer.conclusion


def test_tool_failure_is_visible_and_agent_can_recover():
    model = FakeModel([
        call("get_service_status", service="billing-worker"),  # always fails
        call("get_service_status", service="checkout-api"),    # works
        answer(),
    ])

    result = run_agent("Check the service status", model)

    assert result.stop_reason == "final_answer"
    errors = [e for e in result.trace.events if e.kind == "error"]
    assert len(errors) == 1
    assert errors[0].data["source"] == "tool"
    assert "timed out" in errors[0].data["message"]


def test_repeated_failures_stop_the_run():
    model = FakeModel([call("get_service_status", service="billing-worker")] * 5)

    result = run_agent("Check status", model, max_steps=10, max_consecutive_failures=3)

    assert result.stop_reason == "too_many_failures"
    assert model.calls == 3
    assert kinds(result)[-1] == "stopped"


def test_step_limit_stops_without_extra_calls():
    model = FakeModel([call("search_logs", service="checkout-api")] * 10)

    result = run_agent("Investigate forever", model, max_steps=2)

    assert result.stop_reason == "max_steps_reached"
    assert model.calls == 2  # no third model call
    assert len([e for e in result.trace.events if e.kind == "tool_call"]) == 2
    assert kinds(result)[-1] == "stopped"


def test_invalid_model_output_is_logged_and_retried():
    model = FakeModel([ModelError("not valid JSON"), answer()])

    result = run_agent("Anything", model)

    assert result.stop_reason == "final_answer"
    errors = [e for e in result.trace.events if e.kind == "error"]
    assert errors[0].data["source"] == "model"

def test_model_unavailable_stops_immediately():
    model = FakeModel([ModelUnavailable("rate limited"), answer()])

    result = run_agent("Anything", model)

    assert result.stop_reason == "model_unavailable"
    assert model.calls == 1  # no pointless immediate retry
    assert kinds(result)[-1] == "stopped"