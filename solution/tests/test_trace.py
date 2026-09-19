from solution.agent.trace import Trace


def test_trace_redacts_secrets():
    trace = Trace()
    event = trace.add(1, "error", message="request failed, api_key=abc123secret")
    assert "abc123secret" not in event.data["message"]
    assert "[REDACTED]" in event.data["message"]