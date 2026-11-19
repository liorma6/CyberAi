import csv
from importlib.util import find_spec
from io import BytesIO, StringIO
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from uuid import uuid4
from zipfile import ZipFile

from generate_dataset import generate, write_dataset

HERE = Path(__file__).parent


@unittest.skipUnless(find_spec("sklearn"), "Install requirements-ml.txt for stage 7")
class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.gettempdir()) / f"evidencesoc-study-{uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)

    def test_clean_detector_reproduction(self):
        from experiment_suite import detector_results
        with ZipFile(HERE / "stage7-measurements.zip") as archive:
            recorded = json.loads(archive.read("detectors.json"))
        self.assertEqual([r["dataset_seed"] for r in recorded], [42, 43, 44])
        for reference in recorded:
            seed = reference["dataset_seed"]
            root = self.root / str(seed)
            write_dataset(root, generate(seed))
            rebuilt = detector_results(root)
            for field in ("manifest_sha256", "metrics", "families", "test_events", "test_scenarios"):
                self.assertEqual(rebuilt[field], reference[field], (seed, field))
            self.assertAlmostEqual(rebuilt["threshold"], reference["threshold"], places=10)

    def test_only_verified_event_streams_survive_import_and_restart(self):
        from desk_import import FILES, Imports
        from night_desk import Desk
        files = generate(43)
        def packed():
            stream = BytesIO()
            with ZipFile(stream, "w") as archive:
                for name in FILES:
                    archive.writestr(name, files[name])
                archive.writestr("truth/test.jsonl", "private evaluation labels")
            return stream.getvalue()
        store = Imports(self.root, Desk)
        digest = store.save(packed())
        self.assertEqual(store.save(packed()), digest)
        self.assertFalse((self.root / digest / "truth").exists())
        restored = Imports(self.root, Desk).open(digest)
        self.assertEqual(restored.index["provenance"]["dataset_seed"], 43)
        files["events/test.jsonl"] += b"\n"
        with self.assertRaisesRegex(ValueError, "checksum"):
            store.save(packed())
        with self.assertRaises(KeyError):
            store.open("../other")

    def test_blind_packets_and_scoring_require_two_complete_sheets(self):
        from blind_review import FIELDS, score
        with ZipFile(HERE / "stage7-measurements.zip") as archive:
            key = json.loads(archive.read("key.json"))
        sheets = []
        with ZipFile(HERE / "stage7-blind-review.zip") as packets:
            self.assertFalse(any("key" in name for name in packets.namelist()))
            for reviewer in ("R1", "R2"):
                rows = list(csv.DictReader(StringIO(packets.read(f"{reviewer}/ratings.csv").decode())))
                self.assertEqual(len(rows), 40)
                self.assertTrue(all(not row["usefulness"] and not row["missing_information"] for row in rows))
                file = self.root / (reviewer + ".csv")
                with file.open("w", encoding="utf-8", newline="") as out:
                    writer = csv.DictWriter(out, FIELDS)
                    writer.writeheader()
                    for row in rows:
                        mode = key["reviewers"][reviewer][row["file"]][row["side"]]
                        writer.writerow(row | {"missing_information": 1, "usefulness": 3 if mode == "llama" else 4})
                sheets.append(file)
        result = score(key, sheets)
        self.assertEqual(result["R1"]["llama"]["mean_usefulness"], 3)
        self.assertEqual(result["R2"]["baseline"]["mean_usefulness"], 4)
        with self.assertRaises(ValueError):
            score(key, [sheets[0], sheets[0]])
        lines = sheets[1].read_text().splitlines()
        sheets[1].write_text("\n".join(lines[:-1]))
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            score(key, sheets)
