from .schemas import FinalAnswer, ToolCall


def _call(tool: str, rationale: str, **arguments) -> ToolCall:
    return ToolCall(tool=tool, arguments=arguments, rationale=rationale)


SCRIPTS = {
    # Two sources needed: logs point at the database, metrics confirm it.
    "multi": [
        _call("search_logs", "Look for errors in checkout-api",
              service="checkout-api", keyword="timeout"),
        _call("get_metrics", "The errors point at payments-db, so check its pool usage",
              service="payments-db", metric="connection_pool_usage_pct"),
        FinalAnswer(
            evidence=[
                "checkout-api logged 'Timeout connecting to payments-db after 5000ms' "
                "at 14:02:11Z and 14:02:19Z",
                "payments-db connection pool usage was 100% at 14:00Z and 14:05Z",
            ],
            conclusion="Checkout is failing because payments-db ran out of connections, "
                       "so checkout-api requests to it time out.",
            recommendations=[
                "Find what is holding connections open",
                "Raise the pool size or cap connections as a temporary mitigation",
            ],
        ),
    ],
    # First tool call fails on purpose; the agent recovers with another call.
    "failure": [
        _call("get_service_status", "Check billing-worker", service="billing-worker"),
        _call("get_service_status", "That tool failed; check payments-db instead",
              service="payments-db"),
        FinalAnswer(
            evidence=[
                "get_service_status failed for billing-worker: status backend timed out",
                "payments-db status is degraded: Connection pool saturated",
            ],
            conclusion="billing-worker's status is unknown because the tool failed. "
                       "payments-db is degraded.",
            recommendations=["Retry the billing-worker status check later"],
        ),
    ],
    # A model that never finishes: the step limit must stop it.
    "limit": [_call("search_logs", "Keep looking", service="checkout-api")] * 20,
}