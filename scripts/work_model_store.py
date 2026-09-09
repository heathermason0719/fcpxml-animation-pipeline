"""Storage boundaries for the work model; no creative or approval decisions."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from contextvars import ContextVar
from contextlib import contextmanager
from functools import wraps
from datetime import datetime, timezone
from pathlib import Path

from scripts.manifest_schema import validate_manifest_schema
from scripts.manifest_transaction import manifest_transaction

_hashes = ContextVar("afterforge_verified_hashes", default=None)


@contextmanager
def verification_scope():
    if _hashes.get() is not None:
        yield
        return
    token = _hashes.set({})
    try:
        yield
    finally:
        _hashes.reset(token)


def verified_operation(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with verification_scope():
            return function(*args, **kwargs)
    return wrapped


def fresh_hashes():
    if _hashes.get() is not None:
        _hashes.get().clear()


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def sha(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"missing regular input: {path}")
    stamp = path.stat()
    key = (str(path.resolve()), stamp.st_size, stamp.st_mtime_ns, stamp.st_ctime_ns, stamp.st_ino)
    cache = _hashes.get()
    if cache is not None and key in cache:
        return cache[key]
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    value = result.hexdigest()
    if cache is not None:
        cache[key] = value
    return value


def safe(root, relative, *, exists=True):
    root = Path(root).resolve()
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError("path must be nonempty and relative")
    parts = Path(relative).parts
    if any(part in {"..", "."} for part in parts):
        raise ValueError("path cannot traverse parent directories")
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("symlink paths are not supported")
    if not current.resolve().is_relative_to(root):
        raise ValueError("path escapes root")
    if exists and not current.exists():
        raise ValueError(f"missing input: {relative}")
    return current


def atomic_json(path, value):
    atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


def atomic_bytes(path, data):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("refusing symlink destination")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def load(root, *, writable=False):
    root = Path(root).expanduser().resolve()
    path = safe(root, "animation-manifest.json")
    data = json.loads(path.read_text())
    if writable and (data.get("schemaVersion") != "3.0" or (root / ".afterforge-archived").exists()):
        raise ValueError("legacy or archived work is read-only; create a new v3 copy")
    if data.get("schemaVersion") == "3.0":
        validate_manifest_schema(data)
    return data


def save(root, manifest):
    validate_manifest_schema(manifest)
    atomic_json(Path(root) / "animation-manifest.json", manifest)


def layout(root):
    """Find the explicit project marker instead of guessing parent counts."""
    root = Path(root).expanduser().resolve()
    for ancestor in [root, *root.parents]:
        marker = ancestor / "工程" / "project.json"
        if marker.is_file() and not marker.is_symlink():
            index = json.loads(marker.read_text())
            if index.get("schemaVersion") != "2.0":
                raise ValueError("unsupported project layout")
            if root != ancestor and root != ancestor / "工程":
                declared = {safe(ancestor, v["root"]) for ep in index["episodes"] for v in ep["versions"]}
                if root not in declared:
                    raise ValueError("version not registered in project index")
            return ancestor, index
    raise ValueError("missing work-model project index")


def request_check(owner, request):
    if not isinstance(request, dict):
        raise ValueError("request must be an object")
    key = request.get("requestId")
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", key):
        raise ValueError("invalid requestId")
    previous = owner.get("requests", {}).get(key)
    if previous:
        if previous["hash"] != digest(request):
            raise ValueError("requestId was already used with another request")
        return previous["result"]
    revision = owner.get("editRevision", owner.get("revision", 0))
    if type(request.get("expectedRevision")) is not int or request["expectedRevision"] != revision:
        raise ValueError("stale revision; refresh without discarding your draft")
    return None


def remember(owner, request, result):
    owner.setdefault("requests", {})[request["requestId"]] = {"hash": digest(request), "result": result}


def project_lock(afterforge):
    return manifest_transaction(Path(afterforge) / "工程")


def user_source(value):
    if not isinstance(value, dict) or value.get("channel") not in {"chat", "review"}:
        raise ValueError("user decision requires chat or review source")
    if not isinstance(value.get("text"), str) or not value["text"].strip():
        raise ValueError("user decision requires explicit original text")
    if not isinstance(value.get("reference"), str) or not value["reference"].strip():
        raise ValueError("user decision requires source reference")
    return value
