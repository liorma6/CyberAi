"""Capture an independent stage 7 rerun from a fresh checkout."""
from datetime import datetime, timezone
from pathlib import Path
import platform
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main():
    folder = ROOT / "runs" / "stage7-reproduction"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    log = folder / f"reproduction-{stamp}.txt"
    print(f"EvidenceSOC: {log}", flush=True)
    with log.open("w", encoding="utf-8") as out:
        def record(line):
            print(line, flush=True)
            print(line, file=out, flush=True)

        def run(*args):
            record("$ " + shlex.join(map(str, args)))
            completed = subprocess.run(args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, encoding="utf-8", errors="replace")
            record(completed.stdout.rstrip())
            completed.check_returncode()
            return completed.stdout.strip()

        record(f"EvidenceSOC stage 7 | {stamp} | {platform.platform()} | Python {platform.python_version()}")
        try:
            if sys.version_info[:2] not in ((3, 13), (3, 14)):
                raise ValueError("Run with Python 3.13 or 3.14.")
            run("git", "rev-parse", "HEAD")
            if run("git", "status", "--porcelain", "--untracked-files=no"):
                raise ValueError("Tracked files differ from the commit. Use a fresh checkout.")
            env = folder / "venv"
            run(sys.executable, "-m", "venv", str(env))
            python = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
            run(str(python), "-m", "pip", "install", "-r", "requirements-ml.txt")
            run(str(python), "-m", "unittest", "-v")
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            record(f"FAIL | {exc}")
            return 1
        record("PASS | Full suite including clean regeneration and detector comparisons for seeds 42, 43 and 44.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
