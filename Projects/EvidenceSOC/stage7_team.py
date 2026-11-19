"""Build portable, offline rating forms from the published blinded study."""
import csv
from io import StringIO
import json
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent
ROLES = ("R1", "R2")


def packet(role):
    if role not in ROLES:
        raise ValueError("Unknown reviewer")
    with ZipFile(ROOT / "stage7-blind-review.zip") as z:
        read = lambda name: z.read(f"{role}/{name}").decode("utf-8")
        rows = list(csv.DictReader(StringIO(read("ratings.csv"))))
        evidence = json.loads(read("evidence.json"))
        notes = read("cases.md")
    cases = []
    sections = re.split(r"^# (F\d+)\s*$", notes, flags=re.M)[1:]
    for code, section in zip(sections[::2], sections[1::2], strict=True):
        context, a, b = re.split(r"^## Briefing [AB]\s*$", section, flags=re.M)
        source = evidence[code]["sources"]
        locations = {i: f"{r['file']}:{r['line']}" for i, r in source.items()}
        cases.append({"code": code, "context": context.strip(), "sides": {"A": a.strip(), "B": b.strip()},
                      "timeline": [locations[i] for i in evidence[code]["timeline"]],
                      "sources": {locations[i]: r["raw"] for i, r in source.items()}})
    expected = [(c["code"], side) for c in cases for side in ("A", "B")]
    if expected != [(r["file"], r["side"]) for r in rows] or len(cases) != 20:
        raise ValueError("Packet and rating sheet disagree")
    if len({(r["study"], r["reviewer"]) for r in rows}) != 1 or rows[0]["reviewer"] != role:
        raise ValueError("Reviewer or study mismatch")
    return {"study": rows[0]["study"], "role": role, "fields": list(rows[0]), "cases": cases}


def build():
    for role in ROLES:
        payload = "const packet = " + json.dumps(packet(role), ensure_ascii=True, separators=(",", ":")) + ";\n"
        with ZipFile(ROOT / f"EvidenceSOC-{role}.zip", "w", ZIP_DEFLATED) as z:
            for name, path in [("index.html", "stage7-form.html"), ("form.js", "stage7-form.js"),
                               ("form.css", "stage7-team.css")]:
                z.writestr(name, (ROOT / path).read_bytes())
            z.writestr("packet.js", payload)


if __name__ == "__main__":
    build()
