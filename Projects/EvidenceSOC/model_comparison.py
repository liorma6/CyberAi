"""Compare frozen rule and Isolation Forest detectors on a later synthetic test period."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import sklearn

from anomaly_detection import COLUMNS, MODEL_VERSION, fit_detector, later_period, score_events, vector
from rule_baseline import index_truth, metrics, verified_lines
from rule_engine import VERSION as RULE_VERSION


def score_test(root, manifest, detector):
    events, rows, alerts = later_period(root, manifest, "test", detector.history)
    hits = {a["trigger_id"]: [h["rule"] for h in a["hits"]] for a in alerts}
    scores = score_events(detector.forest, rows)
    return [{"event_id": e.id, "utc": e.time.isoformat(), "score": float(score),
             "model_alert": bool(score >= detector.threshold), "rules": hits.get(e.id, []),
             "inputs": dict(zip(COLUMNS, vector(row["features"]), strict=True))}
            for e, row, score in zip(events, rows, scores, strict=True)]


def evaluate(records, truth):
    owners, families, labels = index_truth(truth, [r["event_id"] for r in records])
    selected = {"Rules": {r["event_id"] for r in records if r["rules"]},
                "Isolation Forest": {r["event_id"] for r in records if r["model_alert"]}}
    stats = {key: metrics(ids, owners, labels, len(records)) for key, ids in selected.items()}
    flagged = {key: {owners[e] for e in ids} for key, ids in selected.items()}
    totals = Counter(families.values())
    familystats = {family: {"total": total} for family, total in sorted(totals.items())}
    for name, scenarios in flagged.items():
        counts = Counter(families[s] for s in scenarios)
        for family, row in familystats.items():
            row[name] = counts[family]
    by_id = {r["event_id"]: r for r in records}
    examples = {}
    for row in truth:
        sid = row["scenario_id"]
        rule = sid in flagged["Rules"]
        model = sid in flagged["Isolation Forest"]
        label = labels[sid]
        if rule == model and (rule or label == "benign"):
            continue
        outcome = ("model only" if model else "rules only") if rule != model else "both missed"
        key = f"{outcome}, {label}"
        if key in examples:
            continue
        candidates = [by_id[i] for i in row["event_ids"]]
        eligible = [r for r in candidates if r["model_alert"] or r["rules"]] or candidates
        example = max(eligible, key=lambda r: r["score"])
        examples[key] = {"scenario": sid, "family": families[sid], **example}
    return {"metrics": stats, "families": familystats, "examples": examples}


def run(root, include_scores=False):
    data = (root / "manifest.json").read_bytes()
    manifest = json.loads(data)
    detector = fit_detector(root, manifest)
    records = score_test(root, manifest, detector)
    truth = [json.loads(line) for line in verified_lines(root, manifest, "truth/test.jsonl")]
    result = {"model": MODEL_VERSION, "rules": RULE_VERSION, "sklearn": sklearn.__version__,
              "dataset_seed": manifest["seed"], "manifest_sha256": hashlib.sha256(data).hexdigest(),
              "train_events": detector.training_count,
              "calibration_events": len(detector.history) - detector.training_count,
              "calibration_budget": detector.calibration_budget,
              "calibration_model_alerts": detector.calibration_count_flagged,
              "threshold": detector.threshold, "test_events": len(records), "test_scenarios": len(truth),
              **evaluate(records, truth)}
    if include_scores:
        result["scored_events"] = records
    return result


def markdown(r):
    lines = ["# Isolation Forest and login rules on the held-out period", "",
             f"Dataset seed {r['dataset_seed']}, manifest SHA-256 `{r['manifest_sha256']}`. "
             f"Compared `{r['model']}` (scikit-learn {r['sklearn']}) with `{r['rules']}`.", "",
             f"The forest fitted {r['train_events']} earlier events. On the next {r['calibration_events']} "
             f"events the rules raised {r['calibration_budget']} alerts. The model admitted "
             f"{r['calibration_model_alerts']} events at a threshold of {r['threshold']:.12f}. "
             "Equal scores stay together. Both cutoffs were frozen before test scoring.", "",
             f"The test period contains {r['test_events']} events in {r['test_scenarios']} scenarios. "
             "TP, FP, FN and TN count scenarios. Workload counts individual triggering events.", "",
             "| Detector | TP | FP | FN | TN | Precision | Recall | F1 | Event alerts | False event alerts | False alerts / 1k events |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for name, m in r["metrics"].items():
        lines.append(f"| {name} | {m['tp']} | {m['fp']} | {m['fn']} | {m['tn']} | {m['precision']:.1%} "
                     f"| {m['recall']:.1%} | {m['f1']:.1%} | {m['alert_count']} | {m['false_alerts']} "
                     f"| {m['false_alerts_per_1000']:.2f} |")
    lines.extend(["", "## Scenarios flagged by family", "",
                  "| Scenario family | Total | Rules | Isolation Forest |", "| --- | ---: | ---: | ---: |"])
    for family, row in r["families"].items():
        lines.append(f"| {family} | {row['total']} | {row['Rules']} | {row['Isolation Forest']} |")
    lines.extend(["", "## Cases for analyst review", "",
                  "One example per available outcome. Each event ID resolves to a source login in the test stream. "
                  "For a missed scenario the table shows its highest model score.", "",
                  "| Finding | Scenario family | Scenario | Event | Model score | Rules at event |",
                  "| --- | --- | --- | --- | ---: | --- |"])
    for key, row in r["examples"].items():
        lines.append(f"| {key} | {row['family']} | {row['scenario']} | {row['event_id']} | "
                     f"{row['score']:.6f} | {', '.join(row['rules']) or 'None'} |")
    lines.extend(["", "These results describe one synthetic organization and seed. Approved travel and unusual "
                  "account use intentionally share observable patterns. Travel approval or user confirmation "
                  "can help resolve those cases."])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    fmt = parser.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true", help="Include full-precision metrics and threshold as JSON")
    fmt.add_argument("--scores", action="store_true", help="Also include each test event, model inputs, score and rules in JSON")
    args = parser.parse_args()
    try:
        result = run(args.root, include_scores=args.scores)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
    print(json.dumps(result, indent=2) if args.json or args.scores else markdown(result).rstrip())
