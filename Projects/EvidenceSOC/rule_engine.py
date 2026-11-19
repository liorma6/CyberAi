"""Point-in-time authentication features and the versioned rule baseline."""
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field

from evidence import Event, WINDOW, MIN_FAILURES

VERSION = "rules-v1"
RULES = {
    "R1": "Five failures on one account and IP, or success after at least three failures",
    "R2": "First failure bringing an IP to four distinct failed accounts in five minutes",
    "R3": "Successful sign-in with a new device and new country after five known observations of each",
    "R4": "Successful sign-in in a rare UTC hour after ten prior successes",
}


@dataclass
class Profile:
    total: int = 0
    hours: list = field(default_factory=lambda: [0] * 24)
    devices: set = field(default_factory=set)
    countries: set = field(default_factory=set)
    device_samples: int = 0
    country_samples: int = 0
    first_id: str | None = None
    last_id: str | None = None

    def add(self, event):
        self.total += 1
        self.hours[event.time.hour] += 1
        self.first_id = self.first_id or event.id
        self.last_id = event.id
        if event.device is not None:
            self.devices.add(event.device)
            self.device_samples += 1
        if event.country is not None:
            self.countries.add(event.country)
            self.country_samples += 1


@dataclass(frozen=True)
class Features:
    success: bool
    hour_utc: int
    prior_pair_failures_5m: int
    prior_source_accounts_5m: int
    source_accounts_with_current_5m: int
    prior_successes: int
    device_samples: int
    country_samples: int
    new_device: bool | None
    new_country: bool | None
    prior_hour_band_count: int


class RuleEngine:
    def __init__(self):
        self.profiles = defaultdict(Profile)
        self.recent = deque()
        self.by_ip = defaultdict(deque)
        self.last_time = None

    def observe(self, event: Event):
        """Score one event, then update history. The input order breaks UTC time ties."""
        if self.last_time is not None and event.time < self.last_time:
            raise ValueError("Events must be in chronological order")
        self.last_time = event.time
        while self.recent and event.time - self.recent[0].time > WINDOW:
            expired = self.recent.popleft()
            queue = self.by_ip[expired.ip]
            queue.popleft()
            if not queue:
                del self.by_ip[expired.ip]
        same_ip = self.by_ip.get(event.ip, ())
        pair = [e for e in same_ip if e.account == event.account]
        users = {e.account for e in same_ip}
        success = event.outcome == "success"
        after = len(users) + int(not success and event.account not in users)
        profile = self.profiles[event.account]
        hour = event.time.hour
        band = sum(profile.hours[h % 24] for h in (hour - 1, hour, hour + 1))
        f = Features(success, hour, len(pair), len(users), after, profile.total,
                     profile.device_samples, profile.country_samples,
                     event.device not in profile.devices if event.device and profile.device_samples else None,
                     event.country not in profile.countries if event.country and profile.country_samples else None,
                     band)
        hits = []
        if (success and len(pair) >= MIN_FAILURES) or (not success and len(pair) == 4):
            hits.append({"rule": "R1", "event_ids": [e.id for e in pair] + [event.id]})
        if not success and len(users) < 4 <= after:
            hits.append({"rule": "R2", "event_ids": [e.id for e in same_ip] + [event.id]})
        # These two rules reference the prefix of the account's successful logins.
        # Counts and endpoints let the analyst reconstruct a negative observation.
        scope = {"account": event.account, "outcome": "success", "before_event": event.id,
                 "first_prior_id": profile.first_id, "last_prior_id": profile.last_id}
        if success and min(f.device_samples, f.country_samples) >= 5 and f.new_device and f.new_country:
            hits.append({"rule": "R3", "event_ids": [event.id], "history": scope})
        if success and profile.total >= 10 and band * 20 < profile.total:
            hits.append({"rule": "R4", "event_ids": [event.id], "history": scope})
        if success:
            profile.add(event)
        else:
            self.recent.append(event)
            self.by_ip[event.ip].append(event)
        return f, hits


def analyze(events, history=()):
    """Return one feature row per scored event and at most one alert per event."""
    engine = RuleEngine()
    ids = set()
    for event in history:
        if event.id in ids:
            raise ValueError(f"Repeated event ID in history: {event.id}")
        ids.add(event.id)
        engine.observe(event)
    rows, alerts = [], []
    for event in events:
        if event.id in ids:
            raise ValueError(f"Repeated event ID: {event.id}")
        ids.add(event.id)
        features, hits = engine.observe(event)
        row = {"event_id": event.id, "features": asdict(features)}
        rows.append(row)
        if hits:
            alerts.append({"trigger_id": event.id, "time": event.time.isoformat(), "account": event.account,
                           "ip": event.ip, "features": row["features"], "hits": hits})
    return rows, alerts
