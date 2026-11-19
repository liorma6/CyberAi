"""Prepare two blinded reviewer packets and score their completed CSVs."""
import argparse
import csv
from io import StringIO
import json
from pathlib import Path
import random
import secrets
from statistics import mean
from zipfile import ZIP_DEFLATED, ZipFile

from attack_catalog import SNAPSHOT
from casebook import Casebook

FIELDS = ["study", "reviewer", "file", "side", "missing_information", "usefulness", "comment"]
GUIDE = """# Independent review

Work alone and review only your assigned packet. Open cases.md and the accompanying source records.
For each of the 20 files read both briefings, inspect the cited evidence, and fill in the two rows in ratings.csv.
The source file and line appear beside each citation. Supporting history is in evidence.json.
Assess the help each briefing offers an analyst before an identity owner or provider has answered.
An unavailable briefing receives a zero for missing information and a one for usefulness.

Missing information (0–2): 0 = absent or misleading, 1 = generic but plausible, 2 = names a specific unresolved fact that matters to this investigation.
Usefulness (1–5): 1 = unusable, 2 = substantial rework, 3 = adequate starting point, 4 = actionable with minor checking, 5 = actionable and well prioritized with an appropriate caveat.
Equal scores are allowed. Note an example supporting your rating. Return your own completed ratings.csv to the study organizer before reading the results or discussing ratings.
"""


def text_review(output, case):
    if "error" in output:
        return ["Briefing unavailable."]
    review = output["review"]
    lines = []
    for fact in review["facts"]:
        refs = [case["sources"][i] for i in fact["event_ids"]]
        lines.extend([fact["text"], "Sources: " + ", ".join(f"{r['file']}:{r['line']}" for r in refs), ""])
    for h in review["hypotheses"]:
        lines.append(f"Candidate {h['technique_id']}: {h['reason']} Alternative: {h['alternative']}")
    if not review["hypotheses"]:
        lines.append("No supported technique hypothesis was selected.")
    for title, items in [("Missing information", review["missing_information"]),
                         ("Follow-up", review["recommended_checks"])]:
        lines.extend(f"{title}: {item['text']}" for item in items)
    return lines


def prepare(pairs, book, packets, key_file):
    if len(pairs) != 20 or len({p["case_id"] for p in pairs}) != 20:
        raise ValueError("Expected 20 distinct paired cases")
    study = secrets.token_hex(8)
    key = {"study": study, "reviewers": {}}
    rng = random.SystemRandom()
    with ZipFile(packets, "x", ZIP_DEFLATED) as archive:
        for reviewer in ("R1", "R2"):
            order = list(pairs)
            rng.shuffle(order)
            first = ["llama"] * 10 + ["baseline"] * 10
            rng.shuffle(first)
            assignments = {}
            sheet = StringIO(newline="")
            writer = csv.DictWriter(sheet, FIELDS)
            writer.writeheader()
            lines, evidence = [], {}
            for number, (pair, a) in enumerate(zip(order, first, strict=True), 1):
                code = f"F{number:02d}"
                case = book.detail(pair["case_id"])
                if case["case_id"] != pair["case_id"]:
                    raise ValueError("Mismatched case")
                assignments[code] = {"case": case["case_id"], "A": a, "B": "baseline" if a == "llama" else "llama"}
                evidence[code] = {"timeline": case["timeline"], "findings": case["findings"], "sources": case["sources"]}
                lines.extend([f"# {code}", "", f"{case['first_trigger_utc']} UTC. Accounts: {', '.join(case['accounts'])}.", ""])
                for side in ("A", "B"):
                    lines.extend([f"## Briefing {side}", "", *text_review(pair[assignments[code][side]], case), ""])
                    writer.writerow(dict(study=study, reviewer=reviewer, file=code, side=side))
            key["reviewers"][reviewer] = assignments
            for name, data in [("README.md", GUIDE), ("cases.md", "\n".join(lines)),
                               ("evidence.json", json.dumps(evidence, indent=2)), ("ratings.csv", sheet.getvalue())]:
                archive.writestr(f"{reviewer}/{name}", data.encode("utf-8"))
    key_file.write_text(json.dumps(key, indent=2) + "\n", encoding="utf-8")


def score(key, sheets):
    if len(sheets) != 2:
        raise ValueError("Two reviewer sheets are required")
    results = {}
    preferences = {}
    for sheet in sheets:
        with sheet.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        reviewer = rows[0]["reviewer"] if rows else ""
        if reviewer not in key["reviewers"] or reviewer in results:
            raise ValueError("Two different assigned reviewer sheets are required")
        mapping = key["reviewers"][reviewer]
        expected = {(file, side) for file in mapping for side in ("A", "B")}
        scores = {"baseline": [], "llama": []}
        paired = {}
        for row in rows:
            pair = (row["file"], row["side"])
            if row["study"] != key["study"] or row["reviewer"] != reviewer or pair not in expected:
                raise ValueError("Unexpected study, file, reviewer, duplicate, or side")
            expected.remove(pair)
            gap, use = int(row["missing_information"]), int(row["usefulness"])
            if gap not in range(3) or use not in range(1, 6):
                raise ValueError("Rating out of range")
            assignment = mapping[pair[0]]
            mode = assignment[pair[1]]
            scores[mode].append((gap, use))
            paired.setdefault(assignment["case"], {})[mode] = use
        if expected:
            raise ValueError("Incomplete reviewer sheet")
        results[reviewer] = {mode: {"cases": len(values), "mean_gap": mean(v[0] for v in values),
                                    "mean_usefulness": mean(v[1] for v in values)} for mode, values in scores.items()}
        preferences[reviewer] = {case: (v["llama"] > v["baseline"]) - (v["llama"] < v["baseline"])
                                 for case, v in paired.items()}
        results[reviewer]["paired_usefulness"] = {
            label: list(preferences[reviewer].values()).count(sign)
            for sign, label in [(-1, "template_preferred"), (0, "ties"), (1, "llama_preferred")]}
    results["preference_disagreements"] = [case for case, vote in preferences["R1"].items()
                                          if vote != preferences["R2"][case]]
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    for arg in ("briefings", "dataset", "packets", "key"):
        prep.add_argument(arg, type=Path)
    grade = commands.add_parser("score")
    grade.add_argument("key", type=Path)
    grade.add_argument("sheets", nargs=2, type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        data = json.loads(args.briefings.read_bytes())
        book = Casebook(args.dataset, SNAPSHOT)
        if book.provenance != data["provenance"]:
            parser.error("Briefings and casebook provenance differ")
        prepare(data["cases"], book, args.packets, args.key)
    else:
        print(json.dumps(score(json.loads(args.key.read_bytes()), args.sheets), indent=2))
