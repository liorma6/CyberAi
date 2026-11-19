"""Correlate detector triggers into evidence cases and replay individual findings."""
import argparse
from bisect import bisect_left
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from anomaly_detection import COLUMNS, MODEL_VERSION, fit_detector, later_period, score_events, vector
from attack_catalog import CACHE, REPOSITORY, read_catalog
from case_review import explain_case
from evidence import WINDOW, parse_events
from local_llama import InferenceError
from rule_baseline import verified_lines
from rule_engine import RULES, VERSION, analyze


def hypotheses(event, hits):
    rules = {h["rule"] for h in hits}
    candidates = []
    if rules & {"R1", "R2"}:
        candidates.append({"technique_id": "T1110", "status": "candidate",
                           "supporting_rules": sorted(rules & {"R1", "R2"}),
                           "reason": "A concentrated sequence of failed authentications meets a rule threshold.",
                           "alternative": "User retries or several users behind a shared gateway.",
                           "missing": "Identity-provider details and account-owner context for these attempts."})
    if event.outcome == "success" and len(rules & {"R1", "R3", "R4"}) >= 2:
        candidates.append({"technique_id": "T1078", "status": "candidate",
                           "supporting_rules": sorted(rules & {"R1", "R3", "R4"}),
                           "reason": "A successful sign-in satisfies multiple account-specific rules.",
                           "alternative": "A legitimate user travelling, changing devices or working a different shift.",
                           "missing": "User confirmation or independent session or MFA evidence of misuse."})
    return candidates


def findings_for(history, events, rows, alerts, detector):
    scores = dict(zip((e.id for e in events), score_events(detector.forest, rows), strict=True))
    features = {row["event_id"]: row["features"] for row in rows}
    hits_by_id = {a["trigger_id"]: a["hits"] for a in alerts}
    stream = history + events
    times = [e.time for e in stream]
    successes, failures = defaultdict(list), defaultdict(list)
    findings = {}
    for rank, event in enumerate(stream):
        score = scores.get(event.id)
        hits = hits_by_id.get(event.id, [])
        if score is not None and (hits or score >= detector.threshold):
            first = bisect_left(times, event.time - WINDOW, 0, rank)
            ip_failures = failures[event.ip]
            recent = ip_failures[bisect_left(ip_failures, first):]
            f = features[event.id]
            findings[event.id] = {
                "trigger_id": event.id, "features": f, "rule_hits": hits,
                "model": {"score": float(score), "threshold": detector.threshold,
                          "alert": bool(score >= detector.threshold),
                          "inputs": dict(zip(COLUMNS, vector(f), strict=True))},
                "evidence": {"prior_account_successes": [stream[i].id for i in successes[event.account]],
                             "source_failures_5m": [stream[i].id for i in recent]},
                "attack_candidates": hypotheses(event, hits),
            }
        if event.outcome == "success":
            successes[event.account].append(rank)
        else:
            failures[event.ip].append(rank)
    return findings


def correlate(findings, by_id):
    """Connect adjacent triggers on a matching account/IP or triggers sharing concrete rule evidence."""
    neighbors = defaultdict(set)
    last_pair, last_evidence = {}, {}
    for key, finding in findings.items():
        event = by_id[key]
        pair = event.account, event.ip
        previous = last_pair.get(pair)
        linked = set()
        if previous is not None and event.time - by_id[previous].time <= WINDOW:
            linked.add(previous)
        last_pair[pair] = key
        references = {key}
        for hit in finding["rule_hits"]:
            references.update(hit["event_ids"])
        for ref in references:
            if ref in last_evidence:
                linked.add(last_evidence[ref])
            last_evidence[ref] = key
        neighbors[key].update(linked)
        for other in linked:
            neighbors[other].add(key)
    order = {key: i for i, key in enumerate(findings)}
    seen, cases = set(), {}
    for first in findings:
        if first in seen:
            continue
        stack, component = [first], []
        seen.add(first)
        while stack:
            key = stack.pop()
            component.append(key)
            for other in neighbors[key] - seen:
                seen.add(other)
                stack.append(other)
        cases["case-" + first] = sorted(component, key=order.__getitem__)
    return cases


def source_index(root, manifest):
    index = {}
    for period in ("train", "calibration", "test"):
        filename = f"events/{period}.jsonl"
        for number, line in enumerate(verified_lines(root, manifest, filename), start=1):
            if line.strip():
                raw = json.loads(line)
                index[raw["id"]] = {"file": filename, "line": number, "raw": raw}
    return index


class Casebook:
    def __init__(self, root, cache=CACHE):
        data = (root / "manifest.json").read_bytes()
        manifest = json.loads(data)
        self.detector = fit_detector(root, manifest)
        events, rows, alerts = later_period(root, manifest, "test", self.detector.history)
        stream = self.detector.history + events
        self.by_id = {e.id: e for e in stream}
        self.order = {e.id: i for i, e in enumerate(stream)}
        self.source = source_index(root, manifest)
        self.findings = findings_for(self.detector.history, events, rows, alerts, self.detector)
        self.cases = correlate(self.findings, self.by_id)
        self.catalog = read_catalog(cache)
        self.provenance = {"schema": "evidence-cases-v1", "rules": VERSION, "model": MODEL_VERSION,
                           "dataset_seed": manifest["seed"], "manifest_sha256": hashlib.sha256(data).hexdigest(),
                           "event_stream_sha256": {k: v for k, v in manifest["sha256"].items() if k.startswith("events/")},
                           "attack_revision": self.catalog["revision"],
                           "attack_source": REPOSITORY + "/tree/" + self.catalog["revision"]}

    def summary(self, case_id):
        ids = self.cases[case_id]
        directly_cited = set(ids)
        for key in ids:
            for hit in self.findings[key]["rule_hits"]:
                directly_cited.update(hit["event_ids"])
        return {"case_id": case_id, "trigger_count": len(ids),
                "first_trigger_utc": self.by_id[ids[0]].time.isoformat(),
                "last_trigger_utc": self.by_id[ids[-1]].time.isoformat(),
                "accounts": sorted({self.by_id[i].account for i in directly_cited}),
                "source_ips": sorted({self.by_id[i].ip for i in directly_cited}),
                "technique_candidates": sorted({c["technique_id"] for i in ids
                                                for c in self.findings[i]["attack_candidates"]})}

    def detail(self, case_id):
        ids = self.cases[case_id]
        timeline, historical = set(ids), set()
        findings = [self.findings[key] for key in ids]
        for finding in findings:
            timeline.update(finding["evidence"]["source_failures_5m"])
            historical.update(finding["evidence"]["prior_account_successes"])
        summary = self.summary(case_id)
        return {**summary, "timeline": sorted(timeline, key=self.order.__getitem__), "findings": findings,
                "rule_definitions": {h["rule"]: RULES[h["rule"]] for f in findings for h in f["rule_hits"]},
                "attack_catalog": {t: self.catalog["techniques"][t] for t in summary["technique_candidates"]},
                "sources": {i: self.source[i] for i in sorted(timeline | historical, key=self.order.__getitem__)}}

    def replay(self, key):
        finding = self.findings[key]
        evidence = finding["evidence"]
        ids = sorted(set(evidence["source_failures_5m"]) | set(evidence["prior_account_successes"]),
                     key=self.order.__getitem__)
        # Reparse original source fields. File order within a timestamp follows the recorded stream rank.
        prior = parse_events(json.dumps(self.source[i]["raw"]) for i in ids) if ids else []
        current = parse_events([json.dumps(self.source[key]["raw"])])
        rows, alerts = analyze(current, prior)
        f = rows[0]["features"]
        score = float(score_events(self.detector.forest, rows)[0])
        hits = alerts[0]["hits"] if alerts else []
        checks = {"features": f == finding["features"], "rule_hits": hits == finding["rule_hits"],
                  "model_inputs": dict(zip(COLUMNS, vector(f), strict=True)) == finding["model"]["inputs"],
                  "model_score": score == finding["model"]["score"],
                  "model_decision": (score >= self.detector.threshold) == finding["model"]["alert"],
                  "attack_candidates": hypotheses(current[0], hits) == finding["attack_candidates"]}
        return {"trigger_id": key, "checks": checks, "verified": all(checks.values()),
                "source_records_used": len(prior) + 1, "score": score, "threshold": self.detector.threshold,
                "rules": [h["rule"] for h in hits]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    view = parser.add_mutually_exclusive_group()
    view.add_argument("--case", metavar="CASE_ID", help="Print one case including its raw source records")
    view.add_argument("--replay", metavar="EVENT_ID", help="Recompute one trigger using its cited records")
    parser.add_argument("--explain", nargs="?", const="llama", choices=("llama", "baseline"),
                        help="Add a local Llama review or a deterministic baseline to --case")
    parser.add_argument("--attack-cache", type=Path, default=CACHE)
    args = parser.parse_args()
    if args.explain and not args.case:
        parser.error("--explain requires --case CASE_ID")
    try:
        book = Casebook(args.dataset, args.attack_cache)
        exit_code = 0
        if args.case:
            result = {"case": book.detail(args.case)}
            if args.explain:
                try:
                    result["explanation"] = explain_case(result["case"], args.explain)
                except InferenceError as exc:
                    result["explanation"] = {"source": "unavailable", "error": str(exc)}
                    exit_code = 2
        elif args.replay:
            result = {"replay": book.replay(args.replay)}
            exit_code = 0 if result["replay"]["verified"] else 1
        else:
            result = {"case_count": len(book.cases), "trigger_count": len(book.findings),
                      "cases": [book.summary(k) for k in book.cases]}
        print(json.dumps({"provenance": book.provenance, **result}, indent=2))
        return exit_code
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Cannot build the evidence casebook: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
