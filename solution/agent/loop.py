import json
from dataclasses import dataclass

from .models import ModelAdapter, ModelError, ModelUnavailable
from .schemas import FinalAnswer
from .tools import run_tool
from .trace import Trace


@dataclass
class RunResult:
    # "final_answer" | "max_steps_reached" | "too_many_failures" | "model_unavailable"
    stop_reason: str
    final_answer: FinalAnswer | None
    trace: Trace
    steps_used: int


def _stop(trace: Trace, step: int, reason: str, message: str) -> RunResult:
    trace.add(step, "stopped", reason=reason, message=message)
    return RunResult(reason, None, trace, step)


def run_agent(
    objective: str,
    model: ModelAdapter,
    max_steps: int = 8,
    max_consecutive_failures: int = 3,
) -> RunResult:
    """Run the agent loop. One step = one model call (and at most one tool call)."""
    if max_steps < 1:
        raise ValueError("max_steps must be at least 1")

    trace = Trace()
    trace.add(0, "objective", text=objective)
    messages: list[dict[str, str]] = [{"role": "user", "content": objective}]
    failures = 0

    # The range() is the hard limit: when it runs out we exit without
    # making another model or tool call.
    for step in range(1, max_steps + 1):
        # 1. Ask the model what to do next.
        try:
            decision = model.next_decision(messages)
        except ModelUnavailable as exc:
            # Rate limit or outage: retrying immediately cannot help, so stop now.
            trace.add(step, "error", source="model", message=str(exc))
            return _stop(trace, step, "model_unavailable",
                         "Model unavailable; stopping instead of retrying immediately.")
        except ModelError as exc:
            failures += 1
            trace.add(step, "error", source="model", message=str(exc))
            messages.append({
                "role": "user",
                "content": f"Your last reply was unusable: {exc}. "
                           "Reply again in the required format.",
            })
            if failures >= max_consecutive_failures:
                return _stop(trace, step, "too_many_failures",
                             f"{failures} consecutive failures.")
            continue

        # 2. A final answer ends the run.
        if isinstance(decision, FinalAnswer):
            trace.add(step, "model_decision", action="final_answer")
            trace.add(step, "final_answer", **decision.model_dump(exclude={"type"}))
            return RunResult("final_answer", decision, trace, step)

        # 3. Otherwise the model wants a tool. Log the decision, then run it.
        trace.add(step, "model_decision", action="call_tool",
                  tool=decision.tool, rationale=decision.rationale)
        messages.append({"role": "assistant", "content": decision.model_dump_json()})
        trace.add(step, "tool_call", tool=decision.tool, arguments=decision.arguments)

        try:
            result = run_tool(decision.tool, decision.arguments)
            payload = json.dumps(result)  # a malformed result is a tool failure too
        except Exception as exc:  # tool boundary: nothing a tool does may crash the loop
            failures += 1
            message = f"{type(exc).__name__}: {exc}"
            trace.add(step, "error", source="tool", tool=decision.tool, message=message)
            # Feed the error back so the model can recover with another tool.
            messages.append({"role": "tool", "content": f"ERROR: {message}"})
            if failures >= max_consecutive_failures:
                return _stop(trace, step, "too_many_failures",
                             f"{failures} consecutive failures.")
            continue

        # 4. Success: record the evidence and give it back to the model.
        failures = 0
        trace.add(step, "tool_result", tool=decision.tool, result=result)
        messages.append({"role": "tool", "content": payload})

    return _stop(trace, max_steps, "max_steps_reached",
                 f"Reached the limit of {max_steps} steps without a final answer.")