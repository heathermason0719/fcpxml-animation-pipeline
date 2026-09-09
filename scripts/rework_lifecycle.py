#!/usr/bin/env python3
"""Archive a closed invocation and open the next linear rework revision."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts.hyperframes_adapter import load_manifest, save_manifest, safe_project_path
    from scripts.hyperframes_runtime import read_runtime_pin
    from scripts.manifest_schema import validate_manifest_schema
    from scripts.manifest_transaction import manifest_commit, optimistic_operation
    from scripts.rework_state import rework_revision, revision_label, delivery_directory
    from scripts.workflow_status import resolve_stage_status
except ModuleNotFoundError:
    from hyperframes_adapter import load_manifest, save_manifest, safe_project_path
    from hyperframes_runtime import read_runtime_pin
    from manifest_schema import validate_manifest_schema
    from manifest_transaction import manifest_commit, optimistic_operation
    from rework_state import rework_revision, revision_label, delivery_directory
    from workflow_status import resolve_stage_status


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _assert_closed(root: Path) -> dict:
    status = resolve_stage_status(root)
    if status.get("blockingStage") is not None or "D5" not in status.get("completedStages", []):
        raise ValueError("rework requires a closed invocation with valid delivery acceptance")
    return status


def _snapshot_files(root: Path, manifest: dict) -> dict[str, Path]:
    """Copy the active evidence and inputs, never recursively copy history/caches."""
    ignored = {"rework", ".git", ".venv", "node_modules", "__pycache__", ".cache", ".partial"}
    active_delivery = delivery_directory(root, manifest).relative_to(root)
    paths = {}
    for directory, folders, names in os.walk(root, followlinks=False):
        folder = Path(directory)
        folders[:] = sorted(name for name in folders if name not in ignored)
        for name in folders:
            if (folder / name).is_symlink():
                raise ValueError(f"archive input directory is a symlink: {folder / name}")
        for name in sorted(names):
            if name in {".afterforge-manifest.lock", ".DS_Store"} or name.endswith((".pyc", ".log")):
                continue
            path = folder / name
            relative = path.relative_to(root)
            if relative.parts[0] == "delivery":
                if rework_revision(manifest) == 0:
                    if len(relative.parts) > 1 and relative.parts[1] == "revisions":
                        continue
                elif active_delivery not in relative.parents:
                    continue
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"archive input is not a regular file: {relative}")
            paths[relative.as_posix()] = path
    return paths


def _archive_matches_staging(archive: Path, staging: Path) -> bool:
    """Permit retry only for an exact, complete orphan from this closed snapshot."""
    if archive.is_symlink() or not archive.is_dir():
        return False
    if any(path.is_symlink() for path in archive.rglob("*")):
        return False
    expected_snapshot = staging / "snapshot.json"
    actual_snapshot = archive / "snapshot.json"
    if not actual_snapshot.is_file() or actual_snapshot.is_symlink() or _sha(actual_snapshot) != _sha(expected_snapshot):
        return False
    try:
        inventory = json.loads(actual_snapshot.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    if not isinstance(inventory.get("files"), dict):
        return False
    expected_files = {
        path.relative_to(staging).as_posix()
        for path in staging.rglob("*") if path.is_file() and not path.is_symlink()
    }
    actual_files = {
        path.relative_to(archive).as_posix()
        for path in archive.rglob("*") if path.is_file() and not path.is_symlink()
    }
    if actual_files != expected_files:
        return False
    for relative in expected_files:
        if _sha(archive / relative) != _sha(staging / relative):
            return False
    archived_files = {f"files/{relative}" for relative in inventory["files"]}
    return archived_files | {"snapshot.json", "files/.afterforge-archived"} == expected_files


def verify_rework_history(version_root: Path) -> dict:
    root = version_root.expanduser().resolve()
    manifest = load_manifest(root)
    revision = rework_revision(manifest)
    archives = manifest.get("workflow", {}).get("rework", {}).get("archives", [])
    if not isinstance(archives, list) or len(archives) != revision:
        raise ValueError("rework archive chain is incomplete")
    for number, record in enumerate(archives):
        expected = f"rework/history/{revision_label(number)}"
        if record.get("revision") != number or record.get("path") != expected:
            raise ValueError("rework archive chain is inconsistent")
        archive = safe_project_path(root, expected, must_exist=False)
        if not archive.is_dir():
            raise ValueError("rework archive directory is missing")
        inventory_path = safe_project_path(root, f"{expected}/snapshot.json")
        if _sha(inventory_path) != record.get("snapshotSha256"):
            raise ValueError("rework archive inventory hash mismatch")
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        if inventory.get("revision") != number or not isinstance(inventory.get("files"), dict):
            raise ValueError("rework archive inventory is invalid")
        for relative, digest in inventory["files"].items():
            path = safe_project_path(archive / "files", relative)
            if path.is_symlink() or not path.is_file() or _sha(path) != digest:
                raise ValueError(f"rework archive file mismatch: {relative}")
        if inventory["files"].get("animation-manifest.json") != record.get("manifestSha256"):
            raise ValueError("rework archive manifest binding mismatch")
    return {"status": "valid", "revision": revision, "archiveCount": len(archives)}


@optimistic_operation
def begin_rework(version_root: Path, changes: dict[str, list[str]], reason: str) -> dict:
    root = version_root.expanduser().resolve()
    manifest = load_manifest(root)
    old_revision = rework_revision(manifest)
    closed_status = _assert_closed(root)
    verify_rework_history(root)
    runtime = read_runtime_pin(root)
    animated = {cue["id"] for cue in manifest["cues"] if cue.get("productionMode") == "animation"}
    if not isinstance(changes, dict) or not changes or any(cue_id not in animated for cue_id in changes):
        raise ValueError("rework must identify at least one existing animated cue")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("rework reason is required")
    for scopes in changes.values():
        if not isinstance(scopes, list) or not scopes or any(scope not in {"static", "motion"} for scope in scopes) or len(scopes) != len(set(scopes)):
            raise ValueError("rework impact scopes must be static, motion or both")
    next_revision = old_revision + 1
    archive_relative = f"rework/history/{revision_label(old_revision)}"
    archive = safe_project_path(root, archive_relative, must_exist=False)
    paths = _snapshot_files(root, manifest)
    temporary_parent = safe_project_path(root, "rework/.partial", must_exist=False)
    temporary_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="archive-", dir=temporary_parent))
    installed = False
    try:
        hashes = {}
        for relative, source in paths.items():
            target = staging / "files" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            hashes[relative] = _sha(target)
        inventory = {
            "schemaVersion": 1, "revision": old_revision,
            "sourceVersion": manifest["sourceVersion"], "runtimeVersion": runtime,
            "closedStatus": closed_status, "files": hashes,
        }
        (staging / "snapshot.json").write_bytes(_json_bytes(inventory))
        # Controlled writers refuse to operate on an archived working copy.
        (staging / "files/.afterforge-archived").write_text("Historical evidence; read only.\n", encoding="utf-8")
        current = copy.deepcopy(manifest)
        workflow = current["workflow"]
        archives = copy.deepcopy(workflow.get("rework", {}).get("archives", []))
        archives.append({
            "revision": old_revision, "path": archive_relative,
            "snapshotSha256": _sha(staging / "snapshot.json"),
            "manifestSha256": hashes["animation-manifest.json"],
        })
        workflow["rework"] = {
            "schemaVersion": 1, "revision": next_revision, "archives": archives,
            "reason": reason.strip(), "changes": {key: sorted(value) for key, value in changes.items()},
            "openedAt": datetime.now(timezone.utc).isoformat(),
        }
        evidence = workflow["stageEvidence"]
        static = {key for key, scopes in changes.items() if "static" in scopes}
        if static:
            evidence["A11"]["status"] = "invalidated"
            for cue_id in static:
                evidence["A11"]["cueApprovals"][cue_id].update({
                    "status": "invalidated", "invalidatedByReworkRevision": next_revision,
                })
        for stage in list(evidence):
            if stage in {"A12", "A13", "A14"} or stage.startswith("D"):
                del evidence[stage]
        evidence["A13"] = {
            "stageId": "A13", "contractVersion": workflow["stageContractVersion"],
            "semanticVersion": 1, "status": "pending", "comments": [],
            "reworkRevision": next_revision,
        }
        workflow["activeReviewContext"] = "A11" if static else None
        for cue in current["cues"]:
            cue.pop("deliveryAsset", None)
        validate_manifest_schema(current)
        with manifest_commit(root):
            if _assert_closed(root) != closed_status or read_runtime_pin(root) != runtime:
                raise ValueError("closed invocation changed during rework preparation")
            actual = _snapshot_files(root, manifest)
            if set(actual) != set(paths) or any(_sha(actual[key]) != digest for key, digest in hashes.items()):
                raise ValueError("rework inputs changed during archive preparation")
            archive.parent.mkdir(parents=True, exist_ok=True)
            if archive.exists() or archive.is_symlink():
                if not _archive_matches_staging(archive, staging):
                    raise ValueError("existing rework archive does not match current closed snapshot")
                shutil.rmtree(staging)
            else:
                os.rename(staging, archive)
            installed = True
            save_manifest(root, current)
        return {
            "status": "reopened", "revision": next_revision, "archive": archive_relative,
            "runtimeVersion": runtime, "staticCueIds": sorted(static),
            "nextEligibleStage": "A11" if static else "A12",
        }
    finally:
        if not installed and staging.exists():
            shutil.rmtree(staging)


def main() -> int:
    parser = argparse.ArgumentParser(description="重开已闭环 Vn，或只读核验其返工归档。")
    parser.add_argument("action", choices=("begin", "verify"))
    parser.add_argument("version_root", type=Path)
    parser.add_argument("--change", action="append", default=[], metavar="CUE:static,motion")
    parser.add_argument("--reason")
    args = parser.parse_args()
    try:
        if args.action == "verify":
            result = verify_rework_history(args.version_root)
        else:
            changes = {}
            for value in args.change:
                cue_id, scopes = value.split(":", 1)
                if cue_id in changes:
                    raise ValueError("duplicate rework cue")
                changes[cue_id] = scopes.split(",")
            result = begin_rework(args.version_root, changes, args.reason)
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
