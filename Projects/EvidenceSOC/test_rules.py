from datetime import UTC, datetime, timedelta
from pathlib import Path
import shutil
from tempfile import gettempdir
import unittest
from uuid import uuid4

from evidence import Event
from generate_dataset import generate
from rule_baseline import evaluate, markdown, run
from rule_engine import analyze, RuleEngine

START = datetime(2026, 9, 1, 0, tzinfo=UTC)


def login(i, seconds, account="a", outcome="failure", ip="192.0.2.4", device="D1", country="IL"):
    return Event(str(i), START + timedelta(seconds=seconds), account, ip, outcome, device, country)


class RuleTests(unittest.TestCase):
    def test_pair_threshold_expiry_and_evidence(self):
        history = [login("old", -301), login("boundary", -300), login("f2", -50),
                   login("other-account", -40, "b"), login("other-ip", -30, ip="192.0.2.8"),
                   login("f3", -20)]
        rows, alerts = analyze([login("ok", 0, outcome="success")], history)
        self.assertEqual(rows[0]["features"]["prior_pair_failures_5m"], 3)
        self.assertEqual(alerts[0]["hits"], [{"rule": "R1", "event_ids": ["boundary", "f2", "f3", "ok"]}])
        self.assertEqual(analyze([login("ok", 1, outcome="success")], history)[1], [])
        _, repeated = analyze([login(i, i) for i in range(6)])
        self.assertEqual([a["trigger_id"] for a in repeated], ["4"])

    def test_distinct_accounts_and_first_crossing(self):
        samples = [login(i, i, account=a) for i, a in enumerate("aabcdde")]
        rows, alerts = analyze(samples)
        self.assertEqual(rows[4]["features"]["prior_source_accounts_5m"], 3)
        self.assertEqual([a["trigger_id"] for a in alerts], ["4"])
        self.assertEqual(alerts[0]["hits"][0]["event_ids"], list("01234"))

    def test_prefix_only_and_observed_device_country_history(self):
        history = [login(i, i, outcome="success") for i in range(5)]
        target = login("new", 10, outcome="success", device="D2", country="DE")
        later = login("again", 11, outcome="success", device="D2", country="DE")
        rows, alerts = analyze([target, later], history)
        self.assertEqual(analyze([target], history), (rows[:1], alerts))
        self.assertEqual([h["rule"] for h in alerts[0]["hits"]], ["R3"])
        self.assertEqual(alerts[0]["hits"][0]["history"]["last_prior_id"], "4")
        self.assertFalse(rows[1]["features"]["new_device"])
        missing_history = [login(i, i, outcome="success", device=None) for i in range(5)]
        self.assertIsNone(analyze([target], missing_history)[0][0]["features"]["new_device"])
        with self.assertRaisesRegex(ValueError, "Repeated"):
            analyze([target], [target])

    def test_hour_band_wraps_and_threshold_is_strict(self):
        engine = RuleEngine()
        for i in range(19):
            engine.observe(login(i, 10 * 3600 + i, outcome="success"))
        engine.observe(login("late", 23 * 3600, outcome="success"))
        f, hits = engine.observe(login("midnight", 86400, outcome="success"))
        self.assertEqual((f.prior_successes, f.prior_hour_band_count, hits), (20, 1, []))
        _, hits = engine.observe(login("morning", 86400 + 4 * 3600, outcome="success"))
        self.assertEqual([h["rule"] for h in hits], ["R4"])
        with self.assertRaisesRegex(ValueError, "chronological"):
            engine.observe(login("past", 5))

    def test_supporting_evidence_cannot_receive_detection_credit(self):
        events = [login(i, i) for i in range(4)]
        truth = [{"scenario_id": "ben", "kind": "mistake", "label": "benign", "event_ids": ["0", "1"]},
                 {"scenario_id": "pos", "kind": "sequence", "label": "suspicious", "event_ids": ["2"]},
                 {"scenario_id": "miss", "kind": "sequence", "label": "suspicious", "event_ids": ["3"]}]
        alerts = [{"trigger_id": "0", "hits": [{"rule": "R1", "event_ids": ["3", "0"]}]},
                  {"trigger_id": "1", "hits": [{"rule": "R1", "event_ids": ["1"]}]},
                  {"trigger_id": "2", "hits": [{"rule": "R2", "event_ids": ["2"]},
                                               {"rule": "R3", "event_ids": ["2"]}]}]
        result = evaluate(alerts, truth, events)["overall"]
        self.assertEqual([result[k] for k in ("tp", "fp", "fn", "tn", "alert_count", "false_alerts")],
                         [1, 1, 1, 0, 3, 2])
        self.assertEqual(result["false_alerts_per_1000"], 500)

    def test_canonical_report_without_test_files_or_training_labels(self):
        root = Path(gettempdir()) / f"evidencesoc-rules-{uuid4().hex}"
        root.mkdir()
        self.addCleanup(shutil.rmtree, root)
        files = generate(42)
        for name in ("manifest.json", "events/train.jsonl", "events/calibration.jsonl", "truth/calibration.jsonl"):
            path = root / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(files[name])
        self.assertEqual(markdown(run(root)), Path(__file__).with_name("RULE-BASELINE.md").read_text(encoding="utf-8"))
