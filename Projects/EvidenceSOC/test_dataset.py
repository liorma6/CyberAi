import hashlib
import json
from pathlib import Path
import shutil
from tempfile import gettempdir
import unittest
from uuid import uuid4
from collections import Counter
from datetime import date

from dataset_profile import render
from evidence import build_cases, parse_events
from generate_dataset import DEFAULT_SEED, POSITIVE, generate, write_dataset


def records(data):
    return [json.loads(line) for line in data.splitlines()]


class DatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = generate(DEFAULT_SEED)

    def test_same_seed_same_bytes_different_seed_changes_data(self):
        self.assertEqual(self.files, generate(DEFAULT_SEED))
        self.assertNotEqual(self.files["events/train.jsonl"], generate(DEFAULT_SEED + 1)["events/train.jsonl"])
        manifest = json.loads(self.files["manifest.json"])
        for name, digest in manifest["sha256"].items():
            self.assertEqual(hashlib.sha256(self.files[name]).hexdigest(), digest)

    def test_splits_are_chronological_and_every_event_has_one_truth_owner(self):
        manifest = json.loads(self.files["manifest.json"])
        event_ids, scenario_ids = set(), set()
        country_by_ip = {}
        previous_end = None
        for split in ("train", "calibration", "test"):
            period = manifest["periods"][split]
            start, end = map(date.fromisoformat, (period["from_utc"], period["until_utc_exclusive"]))
            if previous_end:
                self.assertEqual(previous_end, start)
            previous_end = end
            rows = records(self.files[f"events/{split}.jsonl"])
            for row in rows:
                self.assertEqual(country_by_ip.setdefault(row["ip"], row["country"]), row["country"])
            times = [row["time"] for row in rows]
            self.assertEqual(times, sorted(times))
            self.assertTrue(all(start.isoformat() <= t[:10] < end.isoformat() for t in times))
            ids = {row["id"] for row in rows}
            self.assertEqual(len(ids), len(rows))
            self.assertTrue(ids.isdisjoint(event_ids))
            event_ids.update(ids)
            truth = records(self.files[f"truth/{split}.jsonl"])
            self.assertEqual(len(rows), period["event_count"])
            self.assertEqual(len(truth), period["scenario_count"])
            self.assertEqual(Counter(e for s in truth for e in s["event_ids"]), Counter(ids))
            for s in truth:
                self.assertNotIn(s["scenario_id"], scenario_ids)
                scenario_ids.add(s["scenario_id"])
            self.assertTrue(all(set(row) == {"id", "time", "account", "ip", "device", "country", "outcome"}
                                for row in rows))
            kinds = {s["kind"] for s in truth if s["label"] == "suspicious"}
            self.assertEqual(kinds, set() if split == "train" else set(POSITIVE))

    def test_synthetic_records_reach_the_existing_case_builder(self):
        data = self.files["events/calibration.jsonl"].decode().splitlines()
        events = parse_events(data)
        lookup = {e.id: e for e in events}
        cases = build_cases(events)
        self.assertTrue(cases)
        for case in cases:
            self.assertTrue(all(e["device"] == lookup[e["id"]].device and e["country"] == lookup[e["id"]].country
                                for e in case["events"]))
        polluted = json.loads(data[0]) | {"label": "benign"}
        with self.assertRaises(ValueError):
            parse_events([json.dumps(polluted)])

    def test_published_profile_matches_regeneration_and_tampering_is_detected(self):
        parent = Path(gettempdir()) / f"evidencesoc-test-{uuid4().hex}"
        parent.mkdir()
        self.addCleanup(shutil.rmtree, parent)
        root = parent / "dataset"
        write_dataset(root, self.files)
        expected = Path(__file__).with_name("DATASET-PROFILE.md").read_text(encoding="utf-8")
        self.assertEqual(render(root), expected)
        write_dataset(root, self.files)
        events = root / "events" / "calibration.jsonl"
        events.write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
            render(root)
        with self.assertRaisesRegex(ValueError, "Existing output differs"):
            write_dataset(root, self.files)
        self.assertEqual(events.read_bytes(), b"corrupt")
