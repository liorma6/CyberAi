"""Print a descriptive profile of training and calibration data before model fitting."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from evidence import read_events

KINDS = ("routine_login", "password_mistake", "approved_travel", "shared_gateway",
         "guess_sequence", "multi_account_failures", "unusual_account_use")


def profile(root, split):
    events = read_events(root / "events" / f"{split}.jsonl")
    lookup = {e.id: e for e in events}
    kinds, labels = Counter(), Counter()
    signatures = Counter()
    with (root / "truth" / f"{split}.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            truth = json.loads(line)
            group = [lookup[key] for key in truth["event_ids"]]
            kind, label = truth["kind"], truth["label"]
            kinds[kind] += 1
            labels[label] += 1
            if any(e.outcome == "success" and (e.time.hour >= 22 or e.time.hour < 5) for e in group):
                signatures["Overnight success (UTC)", label] += 1
            if len({e.account for e in group if e.outcome == "failure"}) >= 3:
                signatures["Failures on at least three accounts", label] += 1
            if (sum(e.outcome == "failure" for e in group) >= 3 and group[-1].outcome == "success"
                    and len({e.account for e in group}) == 1):
                signatures["Three or more failures then a success on one account", label] += 1
    return {"events": len(events), "accounts": len({e.account for e in events}),
            "failures": sum(e.outcome == "failure" for e in events),
            "scenarios": sum(kinds.values()), "kinds": kinds, "labels": labels, "signatures": signatures}


def render(root):
    manifest_data = (root / "manifest.json").read_bytes()
    manifest = json.loads(manifest_data)
    for name, digest in manifest["sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Checksum mismatch: {name}")
    stats = {name: profile(root, name) for name in ("train", "calibration")}
    lines = [
        "# Authentication dataset profile",
        "",
        f"Generator version {manifest['version']}, seed {manifest['seed']}. "
        f"Manifest SHA-256: `{hashlib.sha256(manifest_data).hexdigest()}`.",
        "",
        "| Period | First day (UTC) | End (exclusive) | Events | Scenarios |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    for split, p in manifest["periods"].items():
        lines.append(f"| {split} | {p['from_utc']} | {p['until_utc_exclusive']} "
                     f"| {p['event_count']} | {p['scenario_count']} |")
    lines.extend(["", "| Measure | Train | Calibration |",
                  "| --- | ---: | ---: |"])
    for key, label in (("accounts", "Distinct accounts"), ("failures", "Failed login events")):
        lines.append(f"| {label} | {stats['train'][key]} | {stats['calibration'][key]} |")
    for kind in KINDS:
        lines.append(f"| {kind} scenarios | {stats['train']['kinds'][kind]} "
                     f"| {stats['calibration']['kinds'][kind]} |")
    lines.extend(["", "## Overlap in calibration", "",
                  "Counts are scenarios grouped using evaluation IDs. Rows can overlap. "
                  "These counts describe the input before fitting detectors.", "",
                  "| Observed in a scenario | Benign | Suspicious |", "| --- | ---: | ---: |"])
    signatures = stats["calibration"]["signatures"]
    for key in sorted({key for key, label in signatures}):
        lines.append(f"| {key} | {signatures[key, 'benign']} | {signatures[key, 'suspicious']} |")
    cal = stats["calibration"]
    lines.extend(["", f"Suspicious calibration scenarios: {cal['labels']['suspicious']} "
                  f"of {cal['scenarios']} ({cal['labels']['suspicious']/cal['scenarios']:.1%}). "
                  "The test period contributes only its manifest counts and file-integrity checks to this report."])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Directory containing manifest.json")
    args = parser.parse_args()
    print(render(args.root), end="")
