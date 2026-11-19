"""Train and calibrate Isolation Forest using only the two earlier event periods."""
from collections import Counter
from dataclasses import dataclass
from math import inf, nextafter

from sklearn.ensemble import IsolationForest

from evidence import parse_events
from rule_baseline import verified_lines
from rule_engine import analyze

MODEL_VERSION = "iforest-v1"
COLUMNS = ("success", "prior_pair_failures_5m", "source_accounts_with_current_5m",
           "new_device", "new_country", "personal_hour_share")


def vector(f):
    # One uniform pseudo-observation gives accounts with no history a neutral 3/24 share.
    share = (f["prior_hour_band_count"] + 3 / 24) / (f["prior_successes"] + 1)
    return (int(f["success"]), f["prior_pair_failures_5m"], f["source_accounts_with_current_5m"],
            -1 if f["new_device"] is None else int(f["new_device"]),
            -1 if f["new_country"] is None else int(f["new_country"]), share)


def budget_threshold(scores, budget):
    """Lowest admitted score, keeping ties together and the calibration count within budget."""
    groups = Counter(map(float, scores))
    if not groups or not 0 <= budget <= len(scores):
        raise ValueError("Expected calibration scores and a valid alert budget")
    remaining = budget
    threshold = nextafter(max(groups), inf)
    for score, count in sorted(groups.items(), reverse=True):
        if count > remaining:
            break
        threshold = score
        remaining -= count
    return threshold


def score_events(forest, rows):
    return -forest.score_samples([vector(row["features"]) for row in rows])


def later_period(root, manifest, name, history):
    events = parse_events(verified_lines(root, manifest, f"events/{name}.jsonl"))
    if history[-1].time >= events[0].time:
        raise ValueError(f"Overlapping chronological boundary at {name}")
    rows, alerts = analyze(events, history)
    return events, rows, alerts


@dataclass
class CalibratedDetector:
    forest: IsolationForest
    threshold: float
    history: list
    training_count: int
    calibration_budget: int
    calibration_count_flagged: int


def fit_detector(root, manifest):
    train = parse_events(verified_lines(root, manifest, "events/train.jsonl"))
    training_rows, _ = analyze(train)
    forest = IsolationForest(n_estimators=200, max_samples=256, random_state=42,
                             contamination="auto", n_jobs=1)
    forest.fit([vector(row["features"]) for row in training_rows])
    calibration, rows, alerts = later_period(root, manifest, "calibration", train)
    scores = score_events(forest, rows)
    threshold = budget_threshold(scores, len(alerts))
    return CalibratedDetector(forest, threshold, train + calibration, len(train),
                              len(alerts), int(sum(scores >= threshold)))
