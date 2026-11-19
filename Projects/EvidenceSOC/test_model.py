from importlib.util import find_spec
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from uuid import uuid4

from generate_dataset import generate


@unittest.skipUnless(find_spec("sklearn"), "Install requirements-ml.txt for stage 3")
class ForestTests(unittest.TestCase):
    def test_equal_scores_share_one_decision(self):
        from anomaly_detection import budget_threshold
        scores = [0.9, 0.8, 0.8, 0.1]
        for budget, count in ((0, 0), (1, 1), (2, 1), (3, 3), (4, 4)):
            threshold = budget_threshold(scores, budget)
            self.assertEqual(sum(s >= threshold for s in scores), count)

    def test_only_prior_events_needed_to_freeze_and_score(self):
        from anomaly_detection import COLUMNS, fit_detector
        from model_comparison import score_test

        root = Path(tempfile.gettempdir()) / f"evidencesoc-forest-{uuid4().hex}"
        root.mkdir()
        self.addCleanup(shutil.rmtree, root)
        files = generate(42)
        manifest = json.loads(files["manifest.json"])
        (root / "events").mkdir()
        for name in ("events/train.jsonl", "events/calibration.jsonl"):
            (root / name).write_bytes(files[name])
        detector = fit_detector(root, manifest)
        self.assertEqual(detector.training_count, 2877)
        self.assertEqual(detector.calibration_budget, 178)
        self.assertLessEqual(detector.calibration_count_flagged, detector.calibration_budget)
        name = "events/test.jsonl"
        (root / name).write_bytes(files[name])
        records = score_test(root, manifest, detector)
        self.assertTrue(all(tuple(r["inputs"]) == COLUMNS for r in records))
        self.assertTrue(all(r["model_alert"] == (r["score"] >= detector.threshold) for r in records))
        (root / name).write_bytes(files[name] + b" ")
        with self.assertRaisesRegex(ValueError, "Checksum"):
            score_test(root, manifest, detector)

    def test_report_matches_frozen_results(self):
        from model_comparison import markdown, run
        root = Path(tempfile.gettempdir()) / f"evidencesoc-holdout-{uuid4().hex}"
        root.mkdir()
        self.addCleanup(shutil.rmtree, root)
        for name, data in generate(42).items():
            path = root / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(data)
        report = run(root, include_scores=True)
        self.assertEqual(len(report["scored_events"]), report["test_events"])
        self.assertEqual(markdown(report), Path(__file__).with_name("MODEL-COMPARISON.md").read_text(encoding="utf-8"))
