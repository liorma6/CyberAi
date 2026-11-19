from contextlib import redirect_stdout
from importlib.util import find_spec
from io import StringIO
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from attack_catalog import SNAPSHOT
from case_review import explain_case, render, review_leads
from generate_dataset import generate
from local_llama import InferenceError


@unittest.skipUnless(find_spec("sklearn"), "Install requirements-ml.txt for casebook integration")
class CaseReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from casebook import Casebook
        root = Path(tempfile.gettempdir()) / f"evidencesoc-review-{uuid4().hex}"
        root.mkdir()
        cls.addClassCleanup(shutil.rmtree, root)
        for name, data in generate(42).items():
            if name.startswith("truth/"):
                continue
            path = root / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(data)
        cls.book = Casebook(root, SNAPSHOT)
        cls.case = cls.book.detail("case-e-51d9170e7544d3e64f6f727a")

    def test_every_baseline_is_grounded_and_runs_offline(self):
        with patch("local_llama.api", side_effect=AssertionError("Unexpected inference")):
            for case_id in self.book.cases:
                case = self.book.detail(case_id)
                answer = explain_case(case, "baseline")
                self.assertEqual(answer["source"], "template")
                review = answer["review"]
                self.assertEqual(review["case_id"], case_id)
                findings = {f["trigger_id"]: f for f in case["findings"]}
                for fact in review["facts"]:
                    key = fact["trigger_id"]
                    self.assertIn(key, fact["event_ids"])
                    self.assertTrue(set(fact["event_ids"]) <= case["sources"].keys())
                    self.assertIn(fact["signal"], ["forest", *(h["rule"] for h in findings[key]["rule_hits"])])
                for hypothesis in review["hypotheses"]:
                    finding = findings[hypothesis["trigger_id"]]
                    self.assertIn(hypothesis["technique_id"], [c["technique_id"] for c in finding["attack_candidates"]])
                    self.assertEqual(hypothesis["status"], "candidate")
                    self.assertTrue(hypothesis["alternative"])

    def test_wrong_references_checks_and_extra_claims_are_rejected(self):
        leads = review_leads(self.case)
        primary = next(k for k, v in leads.items() if not v["hypothesis"])
        valid = {"primary": primary, "context": "none", "check": "owner"}
        for bad in (valid | {"primary": "outside-case"}, valid | {"context": "outside-case"},
                    valid | {"context": primary}, valid | {"check": "shift"},
                    valid | {"summary": "compromise confirmed"}, valid | {"primary": [primary]}, {}):
            with self.subTest(bad=bad), self.assertRaises(InferenceError):
                render(self.case, leads, bad)
        damaged = self.case | {"sources": {}}
        with self.assertRaisesRegex(InferenceError, "source records"):
            explain_case(damaged, "baseline")

    def test_selected_facts_link_to_the_correct_rule_evidence(self):
        leads = review_leads(self.case)
        primary = next(k for k, v in leads.items() if v["hypothesis"] and v["hypothesis"]["technique_id"] == "T1078")
        choice = {"primary": primary, "context": "none", "check": "shift"}
        raw = {"message": {"content": json.dumps(choice)}, "eval_count": 23}
        with patch("local_llama.api", side_effect=[raw, {"models": []}]) as api:
            answer = explain_case(self.case)
        prompt = json.loads(api.call_args_list[0].args[1]["messages"][1]["content"])
        self.assertNotIn("sources", prompt)
        self.assertNotIn(self.case["findings"][0]["trigger_id"], json.dumps(prompt))
        self.assertEqual(answer["source"], "ollama")
        review = answer["review"]
        facts = {f["signal"]: f for f in review["facts"]}
        finding = self.case["findings"][-1]
        self.assertEqual(len(facts["R4"]["event_ids"]), 83)
        self.assertEqual(facts["R1"]["event_ids"], finding["rule_hits"][0]["event_ids"])
        self.assertEqual(review["primary_trigger_id"], finding["trigger_id"])
        self.assertEqual(review["hypotheses"][0]["basis"], ["R1", "R4"])
        self.assertEqual(review["recommended_checks"][0]["check"], "shift")
        self.assertTrue(review["missing_information"])

    def test_score_alone_cannot_create_an_attack_hypothesis(self):
        case = self.book.detail("case-e-79fb464e10cff03f69f0517b")
        review = explain_case(case, "baseline")["review"]
        self.assertEqual(review["hypotheses"], [])
        self.assertEqual([f["signal"] for f in review["facts"]], ["forest"])
        self.assertIn("score alone", review["missing_information"][0]["text"])

    def test_cli_keeps_entire_case_on_inference_failure(self):
        import casebook
        for response in (InferenceError("unavailable"), {"message": {"content": "invalid JSON"}},
                         {"done_reason": "length", "message": {"content": "{}"}},
                         {"message": {"content": '{"primary":"L999","primary":"L1","context":"none","check":"owner"}'}},
                         {"message": {"content": '{"primary":"L999","context":"none","check":"owner"}'}}):
            out = StringIO()
            with (patch("sys.argv", ["casebook", "dataset", "--case", self.case["case_id"], "--explain"]),
                  patch("casebook.Casebook", return_value=self.book),
                  patch("local_llama.api", side_effect=[response]), redirect_stdout(out)):
                self.assertEqual(casebook.main(), 2)
            bundle = json.loads(out.getvalue())
            self.assertEqual(bundle["case"], self.case)
            self.assertEqual(bundle["explanation"]["source"], "unavailable")
            self.assertNotIn("review", bundle["explanation"])
