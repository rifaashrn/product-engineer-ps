import pytest

from solution.agent.tools import ToolError, run_tool


def test_search_logs_returns_matching_entries():
    result = run_tool("search_logs", {"service": "checkout-api", "keyword": "timeout"})
    assert len(result) >= 1
    assert all(entry["service"] == "checkout-api" for entry in result)


def test_unknown_tool_is_rejected():
    with pytest.raises(ToolError, match="Unknown tool"):
        run_tool("delete_database", {})


def test_missing_argument_is_rejected():
    with pytest.raises(ToolError, match="Invalid arguments"):
        run_tool("get_metrics", {"service": "payments-db"})


def test_failing_tool_raises_tool_error():
    with pytest.raises(ToolError, match="timed out"):
        run_tool("get_service_status", {"service": "billing-worker"})