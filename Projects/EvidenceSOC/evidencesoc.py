"""Run from the project folder with python -m evidencesoc."""
import argparse
import json
from pathlib import Path

from evidence import build_cases, read_events
from local_llama import InferenceError, MODEL, explain
from rule_engine import VERSION, analyze

DEMO = Path(__file__).with_name("demo.jsonl")


def main():
    parser = argparse.ArgumentParser(description="Build evidence-linked login cases from JSON Lines.")
    parser.add_argument("events", nargs="?", type=Path, default=DEMO)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--explain", action="store_true", help="Request and validate a local Llama review.")
    mode.add_argument("--rules", action="store_true", help="Run the versioned rule baseline.")
    parser.add_argument("--history", type=Path, help="Earlier, unscored log events for --rules.")
    parser.add_argument("--feature-rows", action="store_true", help="Include all event features with --rules.")
    parser.add_argument("--model", default=MODEL)
    args = parser.parse_args()
    if (args.history or args.feature_rows) and not args.rules:
        parser.error("--history and --feature-rows require --rules")
    try:
        events = read_events(args.events)
        if args.rules:
            history = read_events(args.history) if args.history else []
            rows, alerts = analyze(events, history)
            report = {"rule_version": VERSION, "event_count": len(rows), "alert_count": len(alerts),
                      "alerts": alerts}
            if args.feature_rows:
                report["feature_rows"] = rows
            print(json.dumps(report, indent=2))
            return 0
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
