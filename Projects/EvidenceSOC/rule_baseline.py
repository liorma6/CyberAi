"""Evaluate rules-v1 on calibration. The held-out period is never opened here."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from evidence import parse_events
from rule_engine import RULES, VERSION, analyze


def index_truth(truth, event_ids):
    owners, families, labels = {}, {}, {}
    for row in truth:
        scenario = row["scenario_id"]
        if scenario in labels or row["label"] not in ("suspicious", "benign") or not row["event_ids"]:
            raise ValueError(f"Invalid truth record: {scenario}")
        families[scenario] = row["kind"]
        labels[scenario] = row["label"]
        for event_id in row["event_ids"]:
            if event_id in owners:
                raise ValueError(f"Multiple truth assignments for {event_id}")
            owners[event_id] = scenario
    if set(owners) != set(event_ids):
        raise ValueError("Scored events and truth keys differ")
    return owners, families, labels


def metrics(triggers, owners, labels, event_count):
    detected = {owners[e] for e in triggers}
    positives = {s for s, label in labels.items() if label == "suspicious"}
    tp, fp, fn = len(detected & positives), len(detected - positives), len(positives - detected)
    false_alerts = sum(labels[owners[e]] == "benign" for e in triggers)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": len(labels) - tp - fp - fn,
            "precision": tp / (tp + fp) if tp + fp else 0.0,
            "recall": tp / (tp + fn) if tp + fn else 0.0,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0,
            "alert_count": len(triggers), "false_alerts": false_alerts,
            "false_alerts_per_1000": 1000 * false_alerts / event_count}


def evaluate(alerts, truth, events):
    owners, families, labels = index_truth(truth, [e.id for e in events])
    by_rule = {rule: set() for rule in RULES}
    triggers = set()
    for alert in alerts:
        event_id = alert["trigger_id"]
        triggers.add(event_id)
        for hit in alert["hits"]:
            by_rule[hit["rule"]].add(event_id)
    score = metrics(triggers, owners, labels, len(events))
    per_rule = {r: metrics(ids, owners, labels, len(events)) for r, ids in by_rule.items()}
    detected = {owners[e] for e in triggers}
    groups = Counter((labels[s], family) for s, family in families.items())
    flagged = Counter((labels[s], families[s]) for s in detected)
    table = [{"label": label, "family": family, "total": count, "flagged": flagged[label, family]}
             for (label, family), count in sorted(groups.items())]
    samples = {}
    for key, label in (("true_positive", "suspicious"), ("false_positive", "benign")):
        selected = next((a for a in alerts if labels[owners[a["trigger_id"]]] == label), None)
        if selected:
            sid = owners[selected["trigger_id"]]
            samples[key] = {"scenario_id": sid, "family": families[sid], "trigger_id": selected["trigger_id"],
                            "rules": [h["rule"] for h in selected["hits"]]}
    missed = next((row for row in truth if row["label"] == "suspicious"
                   and row["scenario_id"] not in detected), None)
    if missed:
        samples["false_negative"] = {"scenario_id": missed["scenario_id"], "family": missed["kind"],
                                     "event_ids": missed["event_ids"]}
    return {"overall": score, "per_rule": per_rule, "families": table, "examples": samples}


def verified_lines(root, manifest, name):
    data = (root / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest["sha256"][name]:
        raise ValueError(f"Checksum mismatch: {name}")
    return data.decode("utf-8").splitlines()


def run(root):
    manifest_data = (root / "manifest.json").read_bytes()
    manifest = json.loads(manifest_data)
    history = parse_events(verified_lines(root, manifest, "events/train.jsonl"))
    events = parse_events(verified_lines(root, manifest, "events/calibration.jsonl"))
    if history[-1].time >= events[0].time:
        raise ValueError("Training and calibration periods must be strictly separated")
    _, alerts = analyze(events, history)
    truth = [json.loads(line) for line in verified_lines(root, manifest, "truth/calibration.jsonl")]
    return {"version": VERSION, "seed": manifest["seed"],
            "manifest_sha256": hashlib.sha256(manifest_data).hexdigest(),
            "history_events": len(history), "calibration_events": len(events), "scenarios": len(truth),
            **evaluate(alerts, truth, events)}


def markdown(report):
    m = report["overall"]
    lines = [
        "# Rule baseline on calibration",
        "",
        f"Rule set `{report['version']}`, dataset seed {report['seed']}. Manifest SHA-256 "
        f"`{report['manifest_sha256']}`.",
        "",
        f"History contains {report['history_events']} training events. The next "
        f"{report['calibration_events']} events belong to {report['scenarios']} labeled scenarios. "
        "One alert is counted per trigger event. A scenario is flagged if it owns at least one "
        "trigger. Supporting records can belong to earlier scenarios and do not earn detection credit.",
        "",
        "| Rule | TP | FP | FN | TN | Precision | Recall | F1 | Alerts | False alerts / 1k events |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key, stats in [("Union", m), *report["per_rule"].items()]:
        lines.append(f"| {key} | {stats['tp']} | {stats['fp']} | {stats['fn']} | {stats['tn']} "
                     f"| {stats['precision']:.1%} | {stats['recall']:.1%} | {stats['f1']:.1%} "
                     f"| {stats['alert_count']} | {stats['false_alerts_per_1000']:.2f} |")
    lines.extend(["", f"The union produced {m['false_alerts']} false alerts across {m['fp']} benign scenarios. "
                  "Individual rule rows overlap.", "", "| Scenario family | Label | Flagged | Total |",
                  "| --- | --- | ---: | ---: |"])
    for row in report["families"]:
        lines.append(f"| {row['family']} | {row['label']} | {row['flagged']} | {row['total']} |")
    lines.extend(["", "## Audit examples", "",
                  "The first matching example in input order is shown for each available outcome.", ""])
    for outcome, row in report["examples"].items():
        ids = row.get("event_ids", [row.get("trigger_id")])
        lines.append(f"- {outcome}, {row['family']}, scenario `{row['scenario_id']}`, "
                     f"events {', '.join(ids)}" + (f", rules {', '.join(row['rules'])}." if "rules" in row else "."))
    lines.extend(["", "These are descriptive calibration results for synthetic data. "
                  "The test period remains reserved for the later comparison."])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--json", action="store_true", help="Output machine-readable results")
    args = parser.parse_args()
    report = run(args.root)
    print(json.dumps(report, indent=2) if args.json else markdown(report), end="\n" if args.json else "")
