import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from .demo import SCRIPTS
from .loop import RunResult, run_agent
from .models import FakeModel, GeminiModel, ModelError

DEFAULT_RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"


def _print_trace(result: RunResult) -> None:
    print("TRACE")
    for event in result.trace.events:
        text = json.dumps(event.data, default=str)
        if len(text) > 160:
            text = text[:160] + "..."
        print(f"  [{event.step}] {event.kind:<15} {text}")


def _print_answer(result: RunResult) -> None:
    answer = result.final_answer
    if answer is None:
        print(f"\nSTOPPED: {result.stop_reason} (after {result.steps_used} steps)")
        return
    print("\nEVIDENCE (from tool results)")
    for item in answer.evidence:
        print(f"  - {item}")
    print("\nCONCLUSION (the agent's inference)")
    print(f"  {answer.conclusion}")
    if answer.recommendations:
        print("\nRECOMMENDATIONS")
        for item in answer.recommendations:
            print(f"  - {item}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Observable incident-investigation agent")
    parser.add_argument("objective", nargs="?", default="Why is checkout failing?")
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--fake", choices=sorted(SCRIPTS),
                        help="Replay a scripted fake model instead of calling Gemini")
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR,
                        help="Where to save the JSONL trace")
    args = parser.parse_args(argv)

    load_dotenv()
    try:
        model = FakeModel(SCRIPTS[args.fake]) if args.fake else GeminiModel()
    except ModelError as exc:
        print(f"Setup error: {exc}", file=sys.stderr)
        return 2

    result = run_agent(args.objective, model, max_steps=args.max_steps)

    _print_trace(result)
    _print_answer(result)

    path = args.runs_dir / f"run-{datetime.now():%Y%m%d-%H%M%S}.jsonl"
    result.trace.save(path)
    print(f"\nTrace saved to {path}")
    return 0 if result.stop_reason == "final_answer" else 1


if __name__ == "__main__":
    sys.exit(main())