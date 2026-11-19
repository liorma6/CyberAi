from datetime import UTC, datetime, timedelta
from importlib.util import find_spec
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from uuid import uuid4

from attack_catalog import OBJECTS, SNAPSHOT, read_catalog, refresh
from generate_dataset import generate


def workspace(test):
    path = Path(tempfile.gettempdir()) / f"evidence-casebook-{uuid4().hex}"
    path.mkdir()
    test.addCleanup(shutil.rmtree, path)
    return path


class CatalogTests(unittest.TestCase):
    def test_refresh_uses_one_revision_and_preserves_last_complete_cache(self):
        cache = workspace(self) / "current.json"
        shipped = read_catalog(cache)
        revision = "a" * 40
        requests = []

        def official(url):
            requests.append(url)
            if url.endswith("/commits/master"):
                return {"sha": revision}
            tid = next(key for key, value in OBJECTS.items() if url.endswith(f"/{value}.json"))
            entry = shipped["techniques"][tid]
            return {"objects": [{"type": "attack-pattern", "id": entry["stix_id"], "name": entry["name"],
                                 "modified": entry["modified"], "x_mitre_version": entry["version"],
                                 "external_references": [{"source_name": "mitre-attack",
                                                          "external_id": tid, "url": entry["url"]}]}]}

        latest = refresh(cache, official)
        self.assertEqual(latest["revision"], revision)
        self.assertEqual(read_catalog(cache), latest)
        self.assertTrue(all(f"/{revision}/enterprise-attack/" in u for u in requests[1:]))
        previous = cache.read_bytes()

        def incomplete(url):
            if url.endswith(OBJECTS["T1078"] + ".json"):
                return {"objects": []}
            return official(url)

        with self.assertRaisesRegex(ValueError, "Missing active"):
            refresh(cache, incomplete)
        self.assertEqual(cache.read_bytes(), previous)


@unittest.skipUnless(find_spec("sklearn"), "Install requirements-ml.txt for stage 4")
class CaseTests(unittest.TestCase):
    def test_conditional_mapping(self):
        from casebook import hypotheses
        from evidence import Event
        e = Event("e", datetime.now(UTC), "a", "192.0.2.1", "success")
        def mapped(event, *rules):
            return {x["technique_id"] for x in hypotheses(event, [{"rule": r} for r in rules])}
        self.assertEqual(mapped(e), set())
        self.assertEqual(mapped(e, "R4"), set())
        self.assertEqual(mapped(e, "R3", "R4"), {"T1078"})
        self.assertEqual(mapped(e, "R1", "R4"), {"T1110", "T1078"})
        failed = Event("f", e.time, e.account, e.ip, "failure")
        self.assertEqual(mapped(failed, "R2"), {"T1110"})
        self.assertNotIn("T1078", mapped(failed, "R1", "R4"))

    def test_grouping_requires_actor_pair_or_shared_direct_evidence(self):
        from casebook import correlate
        from evidence import Event
        start = datetime(2026, 10, 1, tzinfo=UTC)
        rows = [("z", 0, "a", "ip1"), ("b", 300, "a", "ip1"), ("c", 300, "b", "ip1"),
                ("d", 301, "c", "ip1"), ("e", 601, "a", "ip1"), ("f", 602, "a", "ip2")]
        by_id = {i: Event(i, start + timedelta(seconds=t), a, ip, "failure") for i, t, a, ip in rows}
        findings = {key: {"rule_hits": [], "evidence": {"prior_account_successes": ["old"]}} for key in by_id}
        findings["c"]["rule_hits"] = [{"rule": "R2", "event_ids": ["b", "c"]}]
        self.assertEqual(correlate(findings, by_id), {"case-z": ["z", "b", "c"], "case-d": ["d"],
                                                     "case-e": ["e"], "case-f": ["f"]})

    def test_all_findings_match_detectors_and_replay_from_raw_event_lines(self):
        from casebook import Casebook
        from model_comparison import score_test
        root = workspace(self)
        generated = generate(42)
        for name, data in generated.items():
            if name.startswith("truth/"):
                continue
            path = root / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(data)
        book = Casebook(root, SNAPSHOT)
        expected = score_test(root, json.loads(generated["manifest.json"]), book.detector)
        triggers = {r["event_id"] for r in expected if r["model_alert"] or r["rules"]}
        case_ids = [key for group in book.cases.values() for key in group]
        self.assertEqual(set(case_ids), triggers)
        self.assertEqual(len(case_ids), len(triggers))
        self.assertEqual((len(triggers), len(book.cases)), (261, 192))
        multi_account_case = next(case for case, ids in book.cases.items()
                                  if any(h["rule"] == "R2" for i in ids for h in book.findings[i]["rule_hits"]))
        self.assertGreaterEqual(len(book.summary(multi_account_case)["accounts"]), 4)
        for item in expected:
            if item["event_id"] in triggers:
                finding = book.findings[item["event_id"]]
                self.assertEqual(item["score"], finding["model"]["score"])
                self.assertEqual(item["rules"], [h["rule"] for h in finding["rule_hits"]])
                self.assertTrue(book.replay(item["event_id"])["verified"], item["event_id"])
        case = book.detail("case-e-51d9170e7544d3e64f6f727a")
        self.assertEqual([case["sources"][i]["line"] for i in case["timeline"]], list(range(92, 97)))
        self.assertEqual(case["technique_candidates"], ["T1078", "T1110"])
        for key, source in case["sources"].items():
            raw = json.loads(generated[source["file"]].splitlines()[source["line"] - 1])
            self.assertEqual((raw["id"], raw), (key, source["raw"]))
        trigger = case["findings"][-1]
        trigger["features"]["prior_successes"] += 1
        self.assertFalse(book.replay(trigger["trigger_id"])["verified"])
