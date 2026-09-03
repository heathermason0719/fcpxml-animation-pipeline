"""Cooperative per-Vn isolation and optimistic commits for repository writers.

The stable sidecar survives atomic manifest replacement. Long operations capture a
revision then release the lock; only their final publication/registration holds it.
Direct file editors are outside this cooperative protocol.
"""
from __future__ import annotations

import fcntl
import hashlib
import os
import threading
import time
from contextlib import contextmanager
from functools import wraps
from pathlib import Path

_locks_guard = threading.Lock()
_locks = {}
_local = threading.local()


def _root(value):
    return Path(value).expanduser().resolve()


def manifest_revision(root):
    return hashlib.sha256((_root(root) / "animation-manifest.json").read_bytes()).hexdigest()


def _state(name):
    if not hasattr(_local, name):
        setattr(_local, name, {})
    return getattr(_local, name)


@contextmanager
def manifest_transaction(root, *, expected_sha256=None, timeout=2.0):
    root = _root(root)
    held = _state("held")
    if root in held:
        if expected_sha256 is not None and manifest_revision(root) != expected_sha256:
            raise ValueError("stale Review state; refresh before submitting")
        yield
        return
    with _locks_guard:
        lock = _locks.setdefault(root, threading.RLock())
    if not lock.acquire(timeout=timeout):
        raise ValueError("Review state busy; retry after the current operation")
    descriptor = None
    try:
        descriptor = os.open(root / ".afterforge-manifest.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise ValueError("Review state busy; retry after the current operation")
                time.sleep(0.01)
        held[root] = True
        if expected_sha256 is not None and manifest_revision(root) != expected_sha256:
            raise ValueError("stale Review state; refresh before submitting")
        yield
    finally:
        held.pop(root, None)
        if descriptor is not None:
            os.close(descriptor)
        lock.release()


@contextmanager
def manifest_commit(root):
    root = _root(root)
    operation = _state("operations").get(root)
    with manifest_transaction(root, expected_sha256=operation["revision"] if operation else None):
        yield


def note_manifest_write(root):
    root = _root(root)
    operation = _state("operations").get(root)
    if operation is not None:
        operation["revision"] = manifest_revision(root)


def manifest_mutation(function):
    """Serialize short mutations and exclusive multi-file migration/rollback."""
    @wraps(function)
    def wrapped(version_root, *args, **kwargs):
        with manifest_commit(version_root):
            return function(version_root, *args, **kwargs)
    return wrapped


def optimistic_operation(function):
    """Probe/prepare outside the lock, reject obsolete commits and results."""
    @wraps(function)
    def wrapped(version_root, *args, **kwargs):
        root = _root(version_root)
        operations = _state("operations")
        if root in operations:
            return function(version_root, *args, **kwargs)
        with manifest_transaction(root):
            operations[root] = {"revision": manifest_revision(root)}
        try:
            result = function(version_root, *args, **kwargs)
            with manifest_commit(root):
                return result
        finally:
            operations.pop(root, None)
    return wrapped
