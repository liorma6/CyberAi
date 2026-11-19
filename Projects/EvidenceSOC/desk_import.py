"""Import the manifest and event streams of a generated EvidenceSOC dataset."""
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import shutil
from threading import Lock
from uuid import uuid4
from zipfile import ZipFile

from casebook import Casebook

FILES = ("manifest.json", "events/train.jsonl", "events/calibration.jsonl", "events/test.jsonl")
LIMIT = 12 * 1024 * 1024


class Imports:
    def __init__(self, root, make_desk):
        self.root = Path(root)
        self.make_desk = make_desk
        self.lock = Lock()
        self.open = lru_cache(maxsize=1)(self._open)

    def _open(self, digest):
        if not re.fullmatch(r"[a-f0-9]{64}", digest) or not (self.root / digest).is_dir():
            raise KeyError("Unknown imported dataset")
        return self.make_desk(Casebook(self.root / digest))

    def save(self, body):
        with ZipFile(BytesIO(body)) as archive:
            files = archive.namelist()
            if any(files.count(name) != 1 for name in FILES):
                raise ValueError("Include manifest.json and the three events/ streams at the ZIP root.")
            if sum(archive.getinfo(name).file_size for name in FILES) > LIMIT:
                raise ValueError("Dataset exceeds the 12 MiB import limit.")
            data = {name: archive.read(name) for name in FILES}
        manifest = json.loads(data["manifest.json"])
        if not isinstance(manifest, dict) or manifest.get("version") != 1 or type(manifest.get("seed")) is not int:
            raise ValueError("Expected a version 1 dataset manifest and integer seed.")
        for name in FILES[1:]:
            if sha256(data[name]).hexdigest() != manifest["sha256"][name] or not data[name].strip():
                raise ValueError(f"Missing events or checksum mismatch in {name}")
        digest = sha256(data["manifest.json"]).hexdigest()
        self.root.mkdir(parents=True, exist_ok=True)
        with self.lock:
            target = self.root / digest
            if target.is_dir():
                return digest
            staged = self.root / f".import-{uuid4().hex}"
            try:
                (staged / "events").mkdir(parents=True)
                for name, content in data.items():
                    (staged / name).write_bytes(content)
                Casebook(staged)
                try:
                    staged.rename(target)
                except FileExistsError:
                    if not target.is_dir():
                        raise
            finally:
                if staged.exists():
                    shutil.rmtree(staged)
        return digest
