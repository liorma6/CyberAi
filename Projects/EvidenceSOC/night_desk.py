"""Serve the analyst's case files and local Llama reviews on loopback."""
import argparse
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import BoundedSemaphore
from urllib.parse import urlsplit

from casebook import Casebook
from case_review import explain_case
from local_llama import InferenceError

ASSETS = {
    "/": ("night-desk.html", "text/html; charset=utf-8"),
    "/Night-Desk.html": ("night-desk.html", "text/html; charset=utf-8"),
    "/night-desk.css": ("night-desk.css", "text/css; charset=utf-8"),
    "/night-desk.js": ("night-desk.js", "text/javascript; charset=utf-8"),
    "/night-desk.webp": ("night-desk.webp", "image/webp"),
}
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
    def __init__(self, *args, desk, **kwargs):
        self.desk = desk
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

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ASSETS:
            name, kind = ASSETS[path]
            self.send_body(200, kind, Path(__file__).with_name(name).read_bytes())
        elif path == "/api/cases":
            self.json(200, self.desk.index)
        elif path.startswith("/api/cases/") and path[11:] in self.desk.book.cases:
            self.json(200, self.desk.case(path[11:]))
        else:
            self.json(404, {"error": "Case or resource not found."})

    def do_POST(self):
        case_path, _, action = urlsplit(self.path).path.rpartition("/")
        key = case_path.removeprefix("/api/cases/")
        if case_path == key or key not in self.desk.book.cases or action != "briefing":
            self.json(404, {"error": "Case or resource not found."})
            return
        # Only the local desk may initiate model work. No request body is needed.
        if (self.headers.get("X-Night-Desk") != "review"
                or self.headers.get("Sec-Fetch-Site") == "cross-site"):
            self.json(403, {"error": "Request a briefing from Night Desk."})
            return
        if not self.desk.model_slot.acquire(blocking=False):
            self.json(429, {"error": "Llama is reviewing another case. Try again shortly."})
            return
        try:
            result = explain_case(self.desk.book.detail(key), "llama")
        except InferenceError as exc:
            self.json(503, {"error": str(exc)})
        else:
            self.json(200, result)
        finally:
            self.desk.model_slot.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, nargs="?", default=Path("runs/dataset-v1-seed-42"))
    parser.add_argument("--port", type=int, default=8798)
    args = parser.parse_args()
    try:
        desk = Desk(Casebook(args.dataset))
        with ThreadingHTTPServer(("127.0.0.1", args.port), partial(Handler, desk=desk)) as server:
            print(f"Night Desk ready at http://127.0.0.1:{server.server_port}/", flush=True)
            server.serve_forever()
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Cannot open Night Desk: {exc}\n")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
