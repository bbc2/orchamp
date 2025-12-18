"""
Content-addressable storage with reference tracking and garbage collection.
"""

import base64
import hashlib
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


def compute_hash(data: bytes) -> str:
    """
    Compute SHA-256 hash of data, return hex string.
    """

    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class StoredObject:
    """
    Object stored in the content store.
    """

    value: bytes
    refs: tuple[str, ...]


@dataclass(frozen=True)
class RootEntry:
    """
    Entry in the root store.
    """

    content_hash: str
    expires_at: float


class ContentStore(ABC):
    """
    Content-addressable store with reference tracking.
    """

    @abstractmethod
    def get(self, hash: str) -> StoredObject | None:
        """
        Get object by content hash.
        """

        ...

    @abstractmethod
    def put(self, hash: str, value: bytes, refs: Iterable[str] = ()) -> None:
        """
        Store value with optional references to other hashes.
        """

        ...

    @abstractmethod
    def delete(self, hash: str) -> None:
        """
        Delete object by hash.
        """

        ...

    @abstractmethod
    def keys(self) -> Iterable[str]:
        """
        All stored hashes.
        """

        ...


class RootStore(ABC):
    """
    TTL-based root references into the content store.
    """

    @abstractmethod
    def get(self, key: str) -> RootEntry | None:
        """
        Get entry for key, None if missing or expired.
        """

        ...

    @abstractmethod
    def set(self, key: str, content_hash: str, ttl: int) -> None:
        """
        Set root key → hash with TTL in seconds.
        """

        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        """
        Delete an entry.
        """

        ...

    @abstractmethod
    def all_live_hashes(self) -> Iterable[str]:
        """
        All non-expired root hashes (for GC mark phase).
        """

        ...


def collect_garbage(roots: RootStore, content: ContentStore) -> int:
    """
    Remove unreachable objects from the content store.

    Returns number of objects deleted.
    """

    live: set[str] = set()
    queue = list(roots.all_live_hashes())

    while queue:
        h = queue.pop()

        if h in live:
            continue

        live.add(h)
        obj = content.get(h)

        if obj:
            queue.extend(obj.refs)

    deleted = 0

    for h in list(content.keys()):
        if h not in live:
            content.delete(h)
            deleted += 1

    return deleted


class DiskContentStore(ContentStore):
    """
    Disk-backed content store using JSON files.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.mkdir(parents=True, exist_ok=True)

    def _object_path(self, hash: str) -> Path:
        return self._path / f"{hash}.json"

    def get(self, hash: str) -> StoredObject | None:
        path = self._object_path(hash)

        if not path.exists():
            return None

        data = json.load(path.open(encoding="utf-8"))
        return StoredObject(
            value=base64.b64decode(data["value"]),
            refs=tuple(data["refs"]),
        )

    def put(self, hash: str, value: bytes, refs: Iterable[str] = ()) -> None:
        path = self._object_path(hash)
        data = {
            "value": base64.b64encode(value).decode("ascii"),
            "refs": list(refs),
        }
        json.dump(data, path.open("w", encoding="utf-8"))

    def delete(self, hash: str) -> None:
        path = self._object_path(hash)
        path.unlink(missing_ok=True)

    def keys(self) -> Iterable[str]:
        for path in self._path.glob("*.json"):
            yield path.stem


class DiskRootStore(RootStore):
    """
    Disk-backed root store using a single JSON file.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, dict]:
        if not self._path.exists():
            return {}

        return json.loads(self._path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, dict]) -> None:
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get(self, key: str) -> RootEntry | None:
        data = self._load()
        entry = data.get(key)

        if entry is None:
            return None

        if time.time() > entry["expires_at"]:
            return None

        return RootEntry(
            content_hash=entry["content_hash"],
            expires_at=entry["expires_at"],
        )

    def set(self, key: str, content_hash: str, ttl: int) -> None:
        data = self._load()
        data[key] = {
            "content_hash": content_hash,
            "expires_at": time.time() + ttl,
        }
        self._save(data)

    def delete(self, key: str) -> None:
        data = self._load()

        if key in data:
            del data[key]
            self._save(data)

    def all_live_hashes(self) -> Iterable[str]:
        now = time.time()
        data = self._load()

        for entry in data.values():
            if entry["expires_at"] > now:
                yield entry["content_hash"]
