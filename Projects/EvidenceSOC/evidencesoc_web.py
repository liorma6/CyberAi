"""Serve the analyst's case files and local Llama reviews on loopback."""
import argparse
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import BoundedSemaphore
from urllib.parse import parse_qs, urlsplit
from zipfile import BadZipFile, ZipFile

from casebook import Casebook
from case_review import explain_case
from desk_import import Imports, LIMIT
from local_llama import InferenceError
from stage7_team import ROLES

ASSETS = {
    "/": ("evidencesoc.html", "text/html; charset=utf-8"),
    "/EvidenceSOC.html": ("evidencesoc.html", "text/html; charset=utf-8"),
    "/evidencesoc.css": ("evidencesoc.css", "text/css; charset=utf-8"),
    "/evidencesoc.js": ("evidencesoc.js", "text/javascript; charset=utf-8"),
    "/evidencesoc.webp": ("evidencesoc.webp", "image/webp"),
    "/stage7/": ("stage7-team.html", "text/html; charset=utf-8"),
    "/stage7/team.css": ("stage7-team.css", "text/css; charset=utf-8"),
    **{f"/stage7/EvidenceSOC-{role}.zip": (f"EvidenceSOC-{role}.zip", "application/zip") for role in ROLES},
}
FORM_TYPES = {"index.html": "text/html; charset=utf-8", "form.css": "text/css; charset=utf-8",
              "form.js": "text/javascript; charset=utf-8", "packet.js": "text/javascript; charset=utf-8"}
TITLES = {
    "R1": "Repeated sign-in failures", "R2": "Failures across accounts",
    "R3": "Unfamiliar device and country", "R4": "Unusual sign-in hour",
}


class Desk:
    def __init__(self, book):
        self.book = book
        self.model_slot = BoundedSemaphore(1)
        cases = []
        for number, key in enumerate(book.cases, 1):
            summary = book.summary(key)
            rules = sorted({hit["rule"] for trigger in book.cases[key]
                            for hit in book.findings[trigger]["rule_hits"]})
            cases.append({**summary, "number": number, "rules": rules,
                          "title": TITLES[rules[0]] if rules else "Unusual login pattern"})
        self.index = {"cases": cases, "trigger_count": len(book.findings),
                      "provenance": book.provenance}

    def case(self, key):
        case = self.book.detail(key)
        return {"case": case, "baseline": explain_case(case, "baseline")}


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, desk, imports=None, **kwargs):
        self.desk = desk
        self.imports = imports
        self.model_slot = desk.model_slot
        super().__init__(*args, **kwargs)

    def send_body(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def json(self, status, value):
        self.send_body(status, "application/json", json.dumps(value, allow_nan=False).encode())

    def select_dataset(self):
        selected = parse_qs(urlsplit(self.path).query).get("dataset")
        if selected is None:
            return True
        try:
            if self.imports is None or len(selected) != 1:
                raise KeyError
            self.desk = self.imports.open(selected[0])
        except (KeyError, OSError, ValueError):
            self.json(404, {"error": "Imported dataset unavailable. Import its ZIP again."})
            return False
        return True

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/Night-Desk.html":
            self.send_response(308)
            self.send_header("Location", "/" + ("?" + urlsplit(self.path).query if urlsplit(self.path).query else ""))
            self.end_headers()
            return
        if path.startswith("/stage7/"):
            parts = path.split("/")
            if len(parts) == 4 and parts[2] in ROLES and (parts[3] or "index.html") in FORM_TYPES:
                name = parts[3] or "index.html"
                with ZipFile(Path(__file__).with_name(f"EvidenceSOC-{parts[2]}.zip")) as packet:
                    self.send_body(200, FORM_TYPES[name], packet.read(name))
                return
        if path in ASSETS:
            name, kind = ASSETS[path]
            self.send_body(200, kind, Path(__file__).with_name(name).read_bytes())
        elif not self.select_dataset():
            return
        elif path == "/api/cases":
            self.json(200, self.desk.index)
        elif path.startswith("/api/cases/") and path[11:] in self.desk.book.cases:
            self.json(200, self.desk.case(path[11:]))
        else:
            self.json(404, {"error": "Case or resource not found."})

    def do_POST(self):
        if urlsplit(self.path).path == "/api/import" and self.imports is not None:
            if self.headers.get("X-EvidenceSOC") != "import" or self.headers.get("Sec-Fetch-Site") == "cross-site":
                self.json(403, {"error": "Import from the local desk."})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= LIMIT:
                    self.json(413, {"error": "Choose a ZIP of up to 12 MiB."})
                    return
                digest = self.imports.save(self.rfile.read(size))
            except (BadZipFile, ValueError, TypeError, KeyError, IndexError, AttributeError, RuntimeError, OSError):
                self.json(400, {"error": "Cannot import dataset. Check the manifest, checksums and event streams."})
                return
            self.json(201, {"dataset": digest})
            return
        if not self.select_dataset():
            return
        case_path, _, action = urlsplit(self.path).path.rpartition("/")
        key = case_path.removeprefix("/api/cases/")
        if case_path == key or key not in self.desk.book.cases or action != "briefing":
            self.json(404, {"error": "Case or resource not found."})
            return
        # Only the local desk may initiate model work. No request body is needed.
        if (self.headers.get("X-EvidenceSOC") != "review"
                or self.headers.get("Sec-Fetch-Site") == "cross-site"):
            self.json(403, {"error": "Request a briefing from EvidenceSOC."})
            return
        if not self.model_slot.acquire(blocking=False):
            self.json(429, {"error": "Llama is reviewing another case. Try again shortly."})
            return
        try:
            result = explain_case(self.desk.book.detail(key), "llama")
        except InferenceError as exc:
            self.json(503, {"error": str(exc)})
        else:
            self.json(200, result)
        finally:
            self.model_slot.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, nargs="?", default=Path("runs/dataset-v1-seed-42"))
    parser.add_argument("--port", type=int, default=8798)
    args = parser.parse_args()
    try:
        desk = Desk(Casebook(args.dataset))
        handler = partial(Handler, desk=desk, imports=Imports(Path("runs/desk-imports"), Desk))
        with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
            print(f"EvidenceSOC ready at http://127.0.0.1:{server.server_port}/", flush=True)
            server.serve_forever()
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Cannot open EvidenceSOC: {exc}\n")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
