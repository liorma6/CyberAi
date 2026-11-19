import json
import unittest
from datetime import datetime, UTC, timedelta
from pathlib import Path
from unittest.mock import patch

from evidence import Event, build_cases, parse_events, read_events
from local_llama import InferenceError, explain, validate_review


class EvidenceTests(unittest.TestCase):
    def test_time_window_and_entity_isolation(self):
        now = datetime(2026, 1, 1, 9, tzinfo=UTC)
        def record(i, seconds, account="alice", ip="192.0.2.1", outcome="failure"):
            return Event(i, now + timedelta(seconds=seconds), account, ip, outcome)
        entries = [record("outside", -301), record("boundary", -300), record("other", -60, "bob"),
                   record("other-ip", -30, ip="192.0.2.2"), record("f2", -10), record("f3", -1),
                   record("ok", 0, outcome="success"), record("retry", 1, outcome="success")]
        cases = build_cases(entries)
        self.assertEqual([row["case_id"] for row in cases], ["case-ok"])
        self.assertEqual([row["id"] for row in cases[0]["events"]], ["boundary", "f2", "f3", "ok"])

    def test_fixture_and_grounding(self):
        cases = build_cases(read_events(Path(__file__).with_name("demo.jsonl")))
        self.assertEqual([c["case_id"] for c in cases], ["case-E04", "case-E05"])
        review = {"reason": "overnight_utc", "event_ids": ["E05"], "next_check": "check_shift_schedule"}
        validate_review(cases[1], review)
        for unsupported in (review | {"event_ids": ["E04"]}, review | {"reason": "failure_burst"},
                            review | {"event_ids": ["E05", "E05"]}, review | {"next_check": "verify_account_owner"}):
            with self.assertRaises(InferenceError):
                validate_review(cases[1], unsupported)

    def test_records_are_sorted_and_duplicate_ids_rejected(self):
        rows = Path(__file__).with_name("demo.jsonl").read_text().splitlines()
        self.assertEqual(parse_events(reversed(rows))[0].id, "E01")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse_events(rows + [rows[0]])

    def test_adapter_distinguishes_review_and_placement(self):
        case = build_cases(read_events(Path(__file__).with_name("demo.jsonl")))[1]
        answer = {"reason": "overnight_utc", "event_ids": ["E05"], "next_check": "check_shift_schedule"}
        chat = {"message": {"content": json.dumps(answer)}, "eval_count": 20}
        with patch("local_llama.api", side_effect=[chat, InferenceError("placement unavailable")]):
            result = explain(case)
        self.assertEqual(result["review"]["event_ids"], ["E05"])
        self.assertIsNone(result["metrics"]["vram_bytes"])
        self.assertIn("placement", result["metrics"]["placement_error"])
        with patch("local_llama.api", return_value={"message": {"content": "unusable"}}):
            with self.assertRaises(InferenceError):
                explain(case)
