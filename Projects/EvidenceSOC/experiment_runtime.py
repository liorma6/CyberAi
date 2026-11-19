"""Measure matched EvidenceSOC reviews on a local CPU and GPU."""
import argparse
import json
from pathlib import Path
import time

from case_review import explain_case
from casebook import Casebook
from local_llama import MODEL, api

CASES = ("case-e-51d9170e7544d3e64f6f727a", "case-e-bc6037889442ae6b5b330f17",
         "case-e-79fb464e10cff03f69f0517b")


def resident():
    return next((m for m in api("/api/ps")["models"] if m.get("name") == MODEL), None)


def unload():
    if resident() is None:
        return
    api("/api/generate", {"model": MODEL, "stream": False, "keep_alive": 0})
    for _ in range(100):
        if resident() is None:
            return
        time.sleep(0.1)
    raise RuntimeError("Target model still resident")


def measure(root):
    book = Casebook(root)
    cases = [book.detail(key) for key in CASES]
    rows = []
    version = api("/api/version")["version"]
    try:
        for block, device in enumerate(("cpu", "gpu", "gpu", "cpu"), 1):
            unload()
            warm = cases if block <= 2 else list(reversed(cases))
            for phase, case in [("cold", cases[0]), *(("warm", item) for item in warm)]:
                answer = explain_case(case, num_gpu=0 if device == "cpu" else None)
                metrics = answer["metrics"]
                vram = metrics["vram_bytes"]
                if (vram is None or (vram == 0) != (device == "cpu")
                        or not metrics["model_digest"] or not metrics["generation_ns"]):
                    raise RuntimeError(f"Unverified {device} placement or measurements: {metrics}")
                rows.append({"block": block, "phase": phase, "device": device, "case_id": case["case_id"],
                             "check": answer["review"]["recommended_checks"][0]["check"], **metrics})
                print(block, device, phase, metrics["wall_seconds"], vram, flush=True)
        if len({r["model_digest"] for r in rows}) != 1:
            raise ValueError("Model digest changed between requests")
    finally:
        unload()
    return {"model": MODEL, "ollama": version, "manifest_sha256": book.provenance["manifest_sha256"],
            "rows": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="Canonical seed-42 dataset")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(measure(args.dataset), indent=2) + "\n", encoding="utf-8")
