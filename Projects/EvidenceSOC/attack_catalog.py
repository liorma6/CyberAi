"""Read the pinned Enterprise ATT&CK metadata or update the local cache from official STIX."""
import argparse
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from urllib.request import urlopen

SNAPSHOT = Path(__file__).with_name("attack-snapshot.json")
CACHE = Path("runs/attack-cache.json")
REPOSITORY = "https://github.com/mitre/cti"
OBJECTS = {
    "T1110": "attack-pattern--a93494bb-4b80-4ea1-8695-3236a49916fd",
    "T1078": "attack-pattern--b17a1a56-e99c-403c-8948-561df0cffe81",
}


def validate(catalog):
    if not re.fullmatch(r"[0-9a-f]{40}", catalog["revision"]):
        raise ValueError("Expected an immutable MITRE repository revision")
    for tid, stix_id in OBJECTS.items():
        entry = catalog["techniques"][tid]
        if (entry["stix_id"] != stix_id or not entry["name"] or not entry["modified"]
                or not entry["version"] or entry["url"].rstrip("/") != f"https://attack.mitre.org/techniques/{tid}"):
            raise ValueError(f"Invalid ATT&CK entry for {tid}")
    return catalog


def read_catalog(cache=CACHE):
    source = cache if cache.is_file() else SNAPSHOT
    return validate(json.loads(source.read_text(encoding="utf-8")))


def fetch_json(url):
    with urlopen(url, timeout=15) as response:
        return json.load(response)


def refresh(cache=CACHE, fetch=fetch_json):
    revision = fetch("https://api.github.com/repos/mitre/cti/commits/master")["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Invalid MITRE revision")
    techniques = {}
    for tid, stix_id in OBJECTS.items():
        url = f"https://raw.githubusercontent.com/mitre/cti/{revision}/enterprise-attack/attack-pattern/{stix_id}.json"
        bundle = fetch(url)
        matches = [obj for obj in bundle["objects"] if obj.get("type") == "attack-pattern"
                   and obj["id"] == stix_id and not obj.get("revoked") and not obj.get("x_mitre_deprecated")]
        if len(matches) != 1:
            raise ValueError(f"Missing active STIX object for {tid}")
        obj = matches[0]
        ref = next((r for r in obj["external_references"] if r.get("source_name") == "mitre-attack"
                    and r.get("external_id") == tid), None)
        if ref is None:
            raise ValueError(f"Missing official reference for {tid}")
        techniques[tid] = {"name": obj["name"], "stix_id": stix_id, "version": obj["x_mitre_version"],
                           "modified": obj["modified"], "url": ref["url"]}
    catalog = validate({"revision": revision, "techniques": techniques})
    cache.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=cache.parent, delete=False) as stream:
        tmp = Path(stream.name)
    try:
        tmp.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
        tmp.replace(cache)
    finally:
        tmp.unlink(missing_ok=True)
    return catalog


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=CACHE)
    args = parser.parse_args()
    try:
        result = refresh(args.cache)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"Could not refresh ATT&CK metadata: {exc}\n")
    print(f"Cached MITRE revision {result['revision']} at {args.cache}")
