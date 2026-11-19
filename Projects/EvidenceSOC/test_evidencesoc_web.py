from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from importlib.util import find_spec
import json
from pathlib import Path
from threading import Thread
import unittest
from unittest.mock import Mock, patch

from local_llama import InferenceError


@unittest.skipUnless(find_spec("sklearn"), "Install requirements-ml.txt for EvidenceSOC")
class DeskHttpTests(unittest.TestCase):
    def setUp(self):
        from evidencesoc_web import Desk, Handler

        book = Mock()
        book.cases = {"case-A": ["event-A"]}
        book.findings = {"event-A": {"rule_hits": [{"rule": "R1"}]}}
        book.provenance = {"dataset_seed": 42}
        book.summary.return_value = {"case_id": "case-A"}
        book.detail.return_value = {"case_id": "case-A", "timeline": ["event-A"]}
        self.desk = Desk(book)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, desk=self.desk))
        thread = Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02})
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(self.server.shutdown)

    def request(self, path, method="GET", headers=None):
        conn = HTTPConnection(*self.server.server_address, timeout=5)
        try:
            conn.request(method, path, headers=headers or {})
            response = conn.getresponse()
            return response.status, response.getheader("Content-Type"), response.read()
        finally:
            conn.close()

    def test_queue_assets_and_offline_case(self):
        status, _, data = self.request("/api/cases")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)["cases"][0]["title"], "Repeated sign-in failures")
        for route, file in [("/", "evidencesoc.html"), ("/evidencesoc.js", "evidencesoc.js"),
                            ("/evidencesoc.css", "evidencesoc.css"), ("/evidencesoc.webp", "evidencesoc.webp")]:
            status, _, content = self.request(route)
            self.assertEqual(status, 200)
            self.assertEqual(content, Path(__file__).with_name(file).read_bytes())
        with patch("evidencesoc_web.explain_case", return_value={"source": "template"}) as review:
            status, _, data = self.request("/api/cases/case-A")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(data)["case"]["timeline"], ["event-A"])
            review.assert_called_once_with(self.desk.book.detail.return_value, "baseline")
        self.assertEqual(self.request("/api/cases/unknown")[0], 404)
        self.assertEqual(self.request("/runs/dataset/truth/test.jsonl")[0], 404)

    def test_model_failure_does_not_block_evidence_or_the_next_review(self):
        route = "/api/cases/case-A/briefing"
        headers = {"X-EvidenceSOC": "review"}
        self.assertEqual(self.request(route, "POST")[0], 403)
        self.assertEqual(self.request(route, "POST", {**headers, "Sec-Fetch-Site":"cross-site"})[0], 403)
        with self.desk.model_slot:
            self.assertEqual(self.request(route, "POST", headers)[0], 429)
        with patch("evidencesoc_web.explain_case", side_effect=[InferenceError("Offline"), {"source": "ollama"}]):
            status, _, data = self.request(route, "POST", headers)
            self.assertEqual((status, json.loads(data)), (503, {"error": "Offline"}))
            status, _, data = self.request(route, "POST", headers)
            self.assertEqual((status, json.loads(data)), (200, {"source": "ollama"}))
        self.assertEqual(self.request("/api/cases")[0], 200)

