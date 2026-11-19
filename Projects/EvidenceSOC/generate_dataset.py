"""Generate the versioned, offline EvidenceSOC authentication corpus."""
import argparse
import hashlib
import json
import random
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from uuid import uuid4

VERSION = 1
DEFAULT_SEED = 42
START = date(2026, 9, 7)
PERIODS = (("train", 28), ("calibration", 14), ("test", 14))
COUNTRIES = ("IL", "DE", "GB", "US")
GATEWAYS = tuple(f"198.51.100.{i}" for i in range(1, 13))
REMOTE = tuple(f"203.0.113.{i}" for i in range(1, 41))
NETWORK_COUNTRY = {ip: COUNTRIES[i % len(COUNTRIES)] for pool in (GATEWAYS, REMOTE)
                   for i, ip in enumerate(pool)}
POSITIVE = ("guess_sequence", "multi_account_failures", "unusual_account_use")


@dataclass(frozen=True)
class Profile:
    account: str
    device: str
    country: str
    ip: str
    hour: int


def identifier(rng, prefix):
    return f"{prefix}-{rng.getrandbits(96):024x}"


def make_profiles(rng):
    profiles = []
    for i in range(48):
        # Persistent day, evening and night schedules with shared gateways.
        hour = rng.choice((8, 9, 10, 11, 13, 15, 18, 23))
        ip = rng.choice(GATEWAYS)
        profiles.append(Profile(f"acct-{i + 1:03}", identifier(rng, "d"), NETWORK_COUNTRY[ip], ip, hour))
    return profiles


def event(rng, day, second, user, outcome, *, ip=None, device=None):
    stamp = datetime.combine(day, time.min, UTC) + timedelta(seconds=second)
    source = ip or user.ip
    return {"id": identifier(rng, "e"), "time": stamp.isoformat().replace("+00:00", "Z"),
            "account": user.account, "ip": source, "outcome": outcome,
            "device": device or user.device, "country": NETWORK_COUNTRY[source]}


def retry_sequence(rng, day, start, user, kind):
    failures = rng.randint(1, 5) if kind == "password_mistake" else rng.randint(2, 8)
    ip = rng.choice(REMOTE) if rng.random() < 0.35 else user.ip
    rows = []
    for _ in range(failures):
        rows.append(event(rng, day, start, user, "failure", ip=ip))
        start += rng.randint(5, 33)
    if kind == "password_mistake" or rng.random() < 0.7:
        rows.append(event(rng, day, start, user, "success", ip=ip))
    return rows


def multi_user_sequence(rng, day, start, profiles, kind):
    # Group membership is known only to the offline evaluator.
    users = rng.sample(profiles, rng.randint(3, 8))
    ip = rng.choice(GATEWAYS + REMOTE)
    rows = []
    for user in users:
        rows.append(event(rng, day, start, user, "failure", ip=ip))
        start += rng.randint(4, 24)
    if kind == "shared_gateway" or rng.random() < 0.4:
        rows.append(event(rng, day, start, rng.choice(users), "success", ip=ip))
    return rows


def remote_signin(rng, day, start, user):
    ip = rng.choice([source for source in REMOTE if NETWORK_COUNTRY[source] != user.country])
    device = identifier(rng, "d") if rng.random() < 0.7 else user.device
    return [event(rng, day, start, user, "success", ip=ip, device=device)]


def episodes(rng, day, profiles, split):
    for user in profiles:
        if rng.random() < (0.48 if day.weekday() >= 5 else 0.12):
            continue
        for _ in range(rng.randint(1, 3)):
            # Reserve enough room for a complete sequence on its UTC calendar day.
            second = (user.hour * 3600 + rng.randint(-5400, 5400)) % 86400
            while second >= 86000:
                second = (user.hour * 3600 + rng.randint(-5400, 5400)) % 86400
            if rng.random() < 0.09:
                yield "password_mistake", retry_sequence(rng, day, second, user, "password_mistake")
            else:
                yield "routine_login", [event(rng, day, second, user, "success")]
    for _ in range(rng.randint(1, 3)):
        start = rng.randint(0, 85999)
        yield "approved_travel", remote_signin(rng, day, start, rng.choice(profiles))
    yield "shared_gateway", multi_user_sequence(rng, day, rng.randint(0, 85999), profiles, "shared_gateway")
    if split != "train":
        for kind in POSITIVE:
            for _ in range(rng.randint(1, 2)):
                user = rng.choice(profiles)
                start = rng.randint(0, 85999)
                if kind == "guess_sequence":
                    rows = retry_sequence(rng, day, start, user, kind)
                elif kind == "multi_account_failures":
                    rows = multi_user_sequence(rng, day, start, profiles, kind)
                else:
                    rows = remote_signin(rng, day, start, user)
                yield kind, rows


def json_lines(records):
    return "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records).encode()


def generate(seed):
    rng = random.Random(seed)
    profiles = make_profiles(rng)
    day = START
    files = {}
    periods = {}
    for split, days in PERIODS:
        begin = day
        logs, truth = [], []
        for _ in range(days):
            for kind, rows in episodes(rng, day, profiles, split):
                logs.extend(rows)
                truth.append({"scenario_id": identifier(rng, "s"), "kind": kind,
                              "label": "suspicious" if kind in POSITIVE else "benign",
                              "event_ids": [r["id"] for r in rows]})
            day += timedelta(days=1)
        logs.sort(key=lambda r: (r["time"], r["id"]))
        files[f"events/{split}.jsonl"] = json_lines(logs)
        files[f"truth/{split}.jsonl"] = json_lines(truth)
        periods[split] = {"from_utc": begin.isoformat(), "until_utc_exclusive": day.isoformat(),
                          "event_count": len(logs), "scenario_count": len(truth)}
    manifest = {"version": VERSION, "seed": seed, "periods": periods,
                "sha256": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    files["manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    return files


def write_dataset(output, files):
    output = output.resolve()
    if output.exists():
        if output.is_dir() and all((output / name).is_file() and (output / name).read_bytes() == data
                                   for name, data in files.items()):
            return
        raise ValueError(f"Existing output differs or is incomplete: {output}. Choose a new directory.")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.parent / f".evidencesoc-{uuid4().hex}"
    staging.mkdir()
    try:
        for name, data in files.items():
            target = staging / name
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(data)
        staging.rename(output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    output = args.out or Path("runs") / f"dataset-v{VERSION}-seed-{args.seed}"
    try:
        files = generate(args.seed)
        write_dataset(output, files)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
    print(output.resolve())


if __name__ == "__main__":
    main()
