"""Run from the project folder with python -m evidencesoc."""
import argparse
import json
from pathlib import Path

from evidence import build_cases, read_events
from local_llama import InferenceError, MODEL, explain

DEMO = Path(__file__).with_name("demo.jsonl")


def main():
    parser = argparse.ArgumentParser(description="Build evidence-linked login cases from JSON Lines.")
    parser.add_argument("events", nargs="?", type=Path, default=DEMO)
    parser.add_argument("--explain", action="store_true", help="Request and validate a local Llama review.")
    parser.add_argument("--model", default=MODEL)
    args = parser.parse_args()
    try:
        events = read_events(args.events)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Cannot read event file: {exc}\n")
    cases = build_cases(events)
    failed = False
    if args.explain:
        for case in cases:
            try:
                case["explanation"] = explain(case, args.model)
            except InferenceError as exc:
                failed = True
                case["explanation"] = {"source": "unavailable", "error": str(exc)}
    print(json.dumps({"event_count": len(events), "case_count": len(cases), "cases": cases}, indent=2))
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
