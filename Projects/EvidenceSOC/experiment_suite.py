"""Run the frozen detector comparison and paired briefing checks on synthetic data."""
import argparse
from collections import defaultdict
from functools import cache
import json
from pathlib import Path

from attack_catalog import SNAPSHOT
from casebook import Casebook
from case_review import explain_case
from generate_dataset import generate, write_dataset
from local_llama import InferenceError
from model_comparison import run
from rule_baseline import index_truth, metrics, verified_lines


def detector_results(root):
    result = run(root, include_scores=True)
    rows = result.pop("scored_events")
    manifest = json.loads((root / "manifest.json").read_bytes())
    truth = [json.loads(line) for line in verified_lines(root, manifest, "truth/test.jsonl")]
    owners, families, labels = index_truth(truth, [r["event_id"] for r in rows])
    selected = {r["event_id"] for r in rows if r["rules"] or r["model_alert"]}
    detected = {owners[i] for i in selected}
    result["metrics"]["Combined"] = metrics(selected, owners, labels, len(rows))
    for family, counts in result["families"].items():
        counts["Combined"] = sum(families[s] == family for s in detected)
    return result


def sample_cases(book, count=20):
    groups = defaultdict(list)
    for key, triggers in book.cases.items():
        findings = [book.findings[t] for t in triggers]
        group = (tuple(sorted({h["rule"] for f in findings for h in f["rule_hits"]})),
                 tuple(sorted({f["model"]["alert"] for f in findings})),
                 tuple(book.summary(key)["technique_candidates"]))
        groups[group].append(key)
    # Round-robin over sorted profiles; within each profile, chronological order.
    selected = [keys[i] for i in range(max(map(len, groups.values()), default=0))
                for _, keys in sorted(groups.items()) if i < len(keys)]
    return selected[:count]


def audit(case, review, replay):
    expected = {}
    for f in case["findings"]:
        key = f["trigger_id"]
        prior = set(f["evidence"]["prior_account_successes"])
        recent = set(f["evidence"]["source_failures_5m"])
        expected[key, "forest"] = prior | recent | {key}
        for h in f["rule_hits"]:
            expected[key, h["rule"]] = prior | {key} if h["rule"] in ("R3", "R4") else set(h["event_ids"])
    presented, supported = set(), 0
    for fact in review["facts"]:
        pair = fact["trigger_id"], fact["signal"]
        refs = set(fact["event_ids"])
        if (refs and refs == expected.get(pair) and refs <= case["sources"].keys()
                and replay(fact["trigger_id"])["verified"]):
            supported += 1
            presented.add(pair)
    primary = review["primary_trigger_id"]
    return {"facts": len(review["facts"]), "supported": supported, "covered": len(presented),
            "available": len(expected), "gap_present": any(
                g["trigger_id"] == primary and g["text"].strip() for g in review["missing_information"]),
            "check": review["recommended_checks"][0]["check"]}


def paired_reviews(book):
    pairs = []
    replay = cache(book.replay)
    for key in sample_cases(book):
        case = book.detail(key)
        row = {"case_id": key}
        for mode in ("baseline", "llama"):
            try:
                review = explain_case(case, mode)["review"]
            except InferenceError as exc:
                row[mode] = {"error": str(exc)}
                continue
            row[mode] = {"audit": audit(case, review, replay), "review": review}
        pairs.append(row)
        print("Paired case", len(pairs), key, flush=True)
    return pairs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("part", choices=("detectors", "briefings"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--runs", type=Path, default=Path("runs"))
    args = parser.parse_args()
    results = []
    for seed in ((42, 43, 44) if args.part == "detectors" else (42,)):
        root = args.runs / f"dataset-v1-seed-{seed}"
        write_dataset(root, generate(seed))
        if args.part == "detectors":
            results.append(detector_results(root))
        else:
            book = Casebook(root, SNAPSHOT)
            results = {"provenance": book.provenance, "cases": paired_reviews(book)}
    args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
