#!/usr/bin/env python3
"""Freeze and verify A11-approved HyperFrames layout dependencies."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

try:
    from scripts.hyperframes_adapter import cue_adapter, find_cue, load_manifest, safe_project_path, save_manifest
except ModuleNotFoundError:
    from hyperframes_adapter import cue_adapter, find_cue, load_manifest, safe_project_path, save_manifest  # type: ignore


def _dependency_records(version_root: Path, adapter: dict[str, Any]) -> tuple[list[dict[str, str]], str]:
    dependencies = adapter.get("layoutDependencies")
    if not isinstance(dependencies, list) or not dependencies:
        raise ValueError("layoutDependencies must be a non-empty list")
    if len(dependencies) != len(set(dependencies)):
        raise ValueError("layoutDependencies contains duplicate paths")
    records: list[dict[str, str]] = []
    aggregate = hashlib.sha256()
    for relative in sorted(dependencies):
        path = safe_project_path(version_root, relative)
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        records.append({"path": relative, "sha256": file_hash})
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(file_hash.encode("ascii"))
        aggregate.update(b"\n")
    return records, aggregate.hexdigest()


def freeze_layout(version_root: Path, cue_id: str, approved_poster: Path) -> dict[str, Any]:
    root = version_root.expanduser().resolve()
    manifest = load_manifest(root)
    cue = find_cue(manifest, cue_id)
    if cue.get("productionMode") != "animation":
        raise ValueError(f"source-only cue has no layout to freeze: {cue_id}")
    adapter = cue_adapter(cue)
    poster_source = approved_poster.expanduser().resolve()
    if not poster_source.is_file() or poster_source.is_symlink():
        raise ValueError(f"approved poster is not a regular file: {poster_source}")
    records, aggregate = _dependency_records(root, adapter)
    revision = int((adapter.get("layoutLock") or {}).get("revision", 0)) + 1
    suffix = poster_source.suffix.lower() or ".png"
    poster_relative = f"approvals/a11/{adapter['compositionId']}{suffix}"
    poster_target = safe_project_path(root, poster_relative, must_exist=False)
    poster_target.parent.mkdir(parents=True, exist_ok=True)
    if poster_source != poster_target:
        shutil.copy2(poster_source, poster_target)
    poster_hash = hashlib.sha256(poster_target.read_bytes()).hexdigest()
    adapter["layoutLock"] = {
        "revision": revision,
        "algorithm": "sha256",
        "files": records,
        "aggregateSha256": aggregate,
        "approvedPoster": poster_relative,
        "approvedPosterSha256": poster_hash,
    }
    cue["workflowState"] = "layout-approved"
    _approve_a11_if_complete(manifest)
    save_manifest(root, manifest)
    return {"status": "frozen", "cueId": cue_id, "revision": revision, "aggregateSha256": aggregate}


def _approve_a11_if_complete(manifest: dict[str, Any]) -> bool:
    animated = [cue for cue in manifest["cues"] if cue.get("productionMode") == "animation"]
    if not animated or any(not cue_adapter(cue).get("layoutLock") for cue in animated):
        return False
    review = manifest.setdefault("reviews", {}).setdefault("a11", {})
    review["status"] = "approved"
    review["approvedCueIds"] = [cue["id"] for cue in animated]
    return True


def approve_a11(version_root: Path) -> dict[str, Any]:
    root = version_root.expanduser().resolve()
    manifest = load_manifest(root)
    verification = verify_layouts(root)
    if verification["status"] != "valid":
        raise ValueError("cannot approve A11 while a layout lock is invalid")
    if not _approve_a11_if_complete(manifest):
        raise ValueError("cannot approve A11 until every animated cue has a layout lock")
    save_manifest(root, manifest)
    return {"status": "approved", "cueIds": manifest["reviews"]["a11"]["approvedCueIds"]}


def verify_layouts(version_root: Path) -> dict[str, Any]:
    root = version_root.expanduser().resolve()
    manifest = load_manifest(root)
    invalid: list[str] = []
    checked: list[str] = []
    details: list[dict[str, str]] = []
    for cue in manifest["cues"]:
        if cue.get("productionMode") != "animation":
            continue
        adapter = cue_adapter(cue)
        lock = adapter.get("layoutLock")
        if not lock:
            continue
        checked.append(cue["id"])
        try:
            _, aggregate = _dependency_records(root, adapter)
            poster = safe_project_path(root, lock["approvedPoster"])
            poster_hash = hashlib.sha256(poster.read_bytes()).hexdigest()
            valid = aggregate == lock.get("aggregateSha256") and poster_hash == lock.get("approvedPosterSha256")
        except (KeyError, OSError, ValueError) as error:
            valid = False
            details.append({"cueId": cue["id"], "error": str(error)})
        if not valid:
            invalid.append(cue["id"])
    return {
        "status": "invalid" if invalid else "valid",
        "checkedCueIds": checked,
        "invalidCueIds": invalid,
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="冻结或验证 A11 layout lock。")
    subparsers = parser.add_subparsers(dest="command", required=True)
    freeze = subparsers.add_parser("freeze")
    freeze.add_argument("version_root", type=Path)
    freeze.add_argument("cue_id")
    freeze.add_argument("approved_poster", type=Path)
    verify = subparsers.add_parser("verify")
    verify.add_argument("version_root", type=Path)
    approve = subparsers.add_parser("approve")
    approve.add_argument("version_root", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "freeze":
            result = freeze_layout(args.version_root, args.cue_id, args.approved_poster)
        elif args.command == "verify":
            result = verify_layouts(args.version_root)
        else:
            result = approve_a11(args.version_root)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"frozen", "valid", "approved"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
