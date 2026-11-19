"""Convert synthetic authentication events into traceable observations."""
import ipaddress
import json
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

WINDOW = timedelta(minutes=5)
MIN_FAILURES = 3


@dataclass(frozen=True)
class Event:
    id: str
    time: datetime
    account: str
    ip: str
    outcome: str
    device: str | None = None
    country: str | None = None


def read_events(path: Path) -> list[Event]:
    with path.open(encoding="utf-8-sig") as stream:
        return parse_events(stream)


def parse_events(lines: Iterable[str]) -> list[Event]:
    events = []
    seen = set()
    required = {"id", "time", "account", "ip", "outcome"}
    for line_no, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if not isinstance(row, dict) or not required <= row.keys() <= required | {"device", "country"}:
                raise ValueError("expected id, time, account, ip and outcome; optional device, country")
            if not all(isinstance(v, str) and v.strip() for v in row.values()):
                raise ValueError("expected nonempty string fields")
            when = datetime.fromisoformat(row["time"])
            if when.tzinfo is None:
                raise ValueError("provide a UTC offset")
            if row["outcome"] not in {"success", "failure"}:
                raise ValueError("unknown outcome")
            if "country" in row and not (len(row["country"]) == 2 and row["country"].isascii()
                                         and row["country"].isalpha() and row["country"].isupper()):
                raise ValueError("country must be a two-letter uppercase code")
            if row["id"] in seen:
                raise ValueError("duplicate event ID")
            event = Event(**(row | {"time": when.astimezone(UTC), "ip": str(ipaddress.ip_address(row["ip"]))}))
        except ValueError as exc:
            raise ValueError(f"line {line_no}: {exc}") from exc
        seen.add(event.id)
        events.append(event)
    if not events:
        raise ValueError("empty event file")
    # File order breaks ties for observations with identical timestamps.
    return sorted(events, key=lambda event: event.time)


def build_cases(events: list[Event]) -> list[dict]:
    pending = defaultdict(deque)
    cases = []
    for event in events:
        key = (event.account, event.ip)
        recent = pending[key]
        while recent and event.time - recent[0].time > WINDOW:
            recent.popleft()
        if event.outcome == "failure":
            recent.append(event)
            continue
        observations = []
        if len(recent) >= MIN_FAILURES:
            observations.append({
                "kind": "failure_burst", "count": len(recent),
                "window_seconds": int(WINDOW.total_seconds()),
                "event_ids": [e.id for e in recent],
            })
        if event.time.hour < 5 or event.time.hour >= 22:
            observations.append({"kind": "overnight_utc", "event_ids": [event.id]})
        if observations:
            observations.append({"kind": "successful_login", "event_ids": [event.id]})
            source = [*recent, event] if observations[0]["kind"] == "failure_burst" else [event]
            cases.append({
                "case_id": f"case-{event.id}", "account": event.account,
                "observations": observations,
                "events": [{k: v for k, v in vars(e).items() if v is not None}
                           | {"time": e.time.isoformat()} for e in source],
            })
        del pending[key]
    return cases
