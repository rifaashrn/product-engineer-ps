import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class ToolError(Exception):
    """Raised when a tool fails or is called incorrectly."""


def _load(filename: str) -> Any:
    return json.loads((DATA_DIR / filename).read_text(encoding="utf-8"))


def known_services() -> list[str]:
    return sorted(_load("status.json"))


def _require_known_service(service: str) -> None:
    # An unknown name must be an error, not an empty result: "no logs" and
    # "that service does not exist" mean very different things as evidence.
    known = known_services()
    if service not in known:
        raise ToolError(f"Unknown service '{service}'. Known services: {known}")


# --- Argument schemas: what each tool accepts ---

class SearchLogsArgs(BaseModel):
    service: str
    keyword: str = ""


class GetMetricsArgs(BaseModel):
    service: str
    metric: str


class GetServiceStatusArgs(BaseModel):
    service: str


# --- The tools themselves ---

def search_logs(args: SearchLogsArgs) -> list[dict]:
    _require_known_service(args.service)
    keyword = args.keyword.lower()
    return [
        entry for entry in _load("logs.json")
        if entry["service"] == args.service and keyword in entry["message"].lower()
    ]


def get_metrics(args: GetMetricsArgs) -> list[dict]:
    _require_known_service(args.service)
    service_metrics = _load("metrics.json").get(args.service)
    if service_metrics is None:
        raise ToolError(f"No metrics are recorded for {args.service}")
    series = service_metrics.get(args.metric)
    if series is None:
        raise ToolError(
            f"Unknown metric '{args.metric}' for {args.service}. "
            f"Available: {sorted(service_metrics)}"
        )
    return series


def get_service_status(args: GetServiceStatusArgs) -> dict:
    # Deliberately broken so we can demo tool-failure handling (AC4).
    if args.service == "billing-worker":
        raise ToolError("Status backend timed out for billing-worker")
    _require_known_service(args.service)
    return _load("status.json")[args.service]


# --- Registry: one place that knows every tool ---

@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    func: Callable[[Any], Any]


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        Tool("search_logs", "Search application logs for a service by keyword.",
             SearchLogsArgs, search_logs),
        Tool("get_metrics", "Get a metric time series for a service.",
             GetMetricsArgs, get_metrics),
        Tool("get_service_status", "Get the current status of a service.",
             GetServiceStatusArgs, get_service_status),
    ]
}


def run_tool(name: str, arguments: dict[str, Any]) -> Any:
    """Validate the model's request, then run the tool."""
    tool = TOOLS.get(name)
    if tool is None:
        raise ToolError(f"Unknown tool '{name}'. Available: {sorted(TOOLS)}")
    try:
        args = tool.args_model.model_validate(arguments)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()
        )
        raise ToolError(f"Invalid arguments for '{name}': {details}") from exc
    return tool.func(args)