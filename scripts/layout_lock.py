#!/usr/bin/env python3
"""Freeze and verify A11-approved HyperFrames layout dependencies."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

try:
    from scripts.hyperframes_adapter import (
        GENERATED_REVIEW_MARKER,
        cue_adapter,
        find_cue,
        load_manifest,
        project_dimensions,
        safe_project_path,
        save_manifest,
    )
except ModuleNotFoundError:
    from hyperframes_adapter import (  # type: ignore
        GENERATED_REVIEW_MARKER,
        cue_adapter,
        find_cue,
        load_manifest,
        project_dimensions,
        safe_project_path,
        save_manifest,
    )


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


def _projection_spec(manifest: dict[str, Any]) -> dict[str, Any]:
    preview_width, preview_height = project_dimensions(manifest, "preview")
    delivery_width, delivery_height = project_dimensions(manifest, "delivery")
    return {
        "mode": "delivery-to-preview-axis-scale",
        "previewWidth": preview_width,
        "previewHeight": preview_height,
        "deliveryWidth": delivery_width,
        "deliveryHeight": delivery_height,
    }


def _review_projection_record(version_root: Path, adapter: dict[str, Any]) -> dict[str, str]:
    relative = adapter["reviewSrc"]
    path = safe_project_path(version_root, relative)
    content = path.read_text(encoding="utf-8")
    if GENERATED_REVIEW_MARKER not in content:
        raise ValueError(f"review projection is not generated: {relative}")
    return {"path": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _review_frame_set_hash(frames: list[dict[str, str]]) -> str:
    aggregate = hashlib.sha256()
    for frame in frames:
        for key in ("id", "role", "label", "path", "sha256"):
            aggregate.update(frame[key].encode("utf-8"))
            aggregate.update(b"\0")
        aggregate.update(b"\n")
    return aggregate.hexdigest()


def _copy_review_frame(
    root: Path,
    composition_id: str,
    frame_id: str,
    role: str,
    label: str,
    source: Path,
) -> dict[str, str]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", frame_id):
        raise ValueError(f"invalid review frame id: {frame_id}")
    if not isinstance(label, str) or not label.strip():
        raise ValueError(f"review frame label cannot be empty: {frame_id}")
    resolved_source = source.expanduser().resolve()
    if not resolved_source.is_file() or resolved_source.is_symlink():
        raise ValueError(f"review frame is not a regular file: {resolved_source}")
    suffix = resolved_source.suffix.lower() or ".png"
    name = composition_id if role == "hero" else f"{composition_id}--{frame_id}"
    relative = f"approvals/a11/{name}{suffix}"
    target = safe_project_path(root, relative, must_exist=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    if resolved_source != target:
        shutil.copy2(resolved_source, target)
    return {
        "id": frame_id,
        "role": role,
        "label": label.strip(),
        "path": relative,
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }


def freeze_layout(
    version_root: Path,
    cue_id: str,
    approved_poster: Path,
    *,
    hero_id: str = "hero",
    hero_label: str = "主审帧",
    auxiliary_frames: list[tuple[str, str, Path]] | None = None,
) -> dict[str, Any]:
    root = version_root.expanduser().resolve()
    manifest = load_manifest(root)
    cue = find_cue(manifest, cue_id)
    if cue.get("productionMode") != "animation":
        raise ValueError(f"source-only cue has no layout to freeze: {cue_id}")
    adapter = cue_adapter(cue)
    records, aggregate = _dependency_records(root, adapter)
    review_projection = _review_projection_record(root, adapter)
    current_lock_revision = int((adapter.get("layoutLock") or {}).get("revision", 0))
    preserved_revision = int(adapter.get("layoutRevision", 0))
    revision = max(current_lock_revision, preserved_revision) + 1
    review_frames = [
        _copy_review_frame(
            root,
            adapter["compositionId"],
            hero_id,
            "hero",
            hero_label,
            approved_poster,
        )
    ]
    for frame_id, label, source in auxiliary_frames or []:
        review_frames.append(
            _copy_review_frame(
                root,
                adapter["compositionId"],
                frame_id,
                "auxiliary",
                label,
                source,
            )
        )
    frame_ids = [frame["id"] for frame in review_frames]
    if len(frame_ids) != len(set(frame_ids)):
        raise ValueError("review frame ids must be unique within a cue")
    poster_relative = review_frames[0]["path"]
    poster_hash = review_frames[0]["sha256"]
    adapter["layoutLock"] = {
        "revision": revision,
        "algorithm": "sha256",
        "files": records,
        "aggregateSha256": aggregate,
        "reviewProjection": review_projection,
        "projectionSpec": _projection_spec(manifest),
        "approvedPoster": poster_relative,
        "approvedPosterSha256": poster_hash,
        "reviewFrames": review_frames,
        "reviewFrameSetSha256": _review_frame_set_hash(review_frames),
    }
    adapter["layoutRevision"] = revision
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
            review_projection = _review_projection_record(root, adapter)
            poster = safe_project_path(root, lock["approvedPoster"])
            poster_hash = hashlib.sha256(poster.read_bytes()).hexdigest()
            review_frames = lock.get("reviewFrames")
            frames_valid = True
            if review_frames is not None:
                if not isinstance(review_frames, list) or not review_frames:
                    raise ValueError("reviewFrames must be a non-empty list")
                frame_ids: list[str] = []
                hero_count = 0
                for frame in review_frames:
                    if not isinstance(frame, dict):
                        raise ValueError("reviewFrames entries must be objects")
                    frame_ids.append(frame["id"])
                    hero_count += frame["role"] == "hero"
                    frame_path = safe_project_path(root, frame["path"])
                    frames_valid = frames_valid and hashlib.sha256(frame_path.read_bytes()).hexdigest() == frame["sha256"]
                frames_valid = (
                    frames_valid
                    and len(frame_ids) == len(set(frame_ids))
                    and hero_count == 1
                    and review_frames[0]["role"] == "hero"
                    and review_frames[0]["path"] == lock["approvedPoster"]
                    and review_frames[0]["sha256"] == lock["approvedPosterSha256"]
                    and _review_frame_set_hash(review_frames) == lock.get("reviewFrameSetSha256")
                )
            valid = (
                aggregate == lock.get("aggregateSha256")
                and review_projection == lock.get("reviewProjection")
                and _projection_spec(manifest) == lock.get("projectionSpec")
                and poster_hash == lock.get("approvedPosterSha256")
                and frames_valid
            )
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
    freeze.add_argument("--hero-id", default="hero")
    freeze.add_argument("--hero-label", default="主审帧")
    freeze.add_argument(
        "--auxiliary-frame",
        action="append",
        default=[],
        metavar="ID=LABEL=PATH",
        help="Add a locked auxiliary storyboard frame; may be repeated.",
    )
    verify = subparsers.add_parser("verify")
    verify.add_argument("version_root", type=Path)
    approve = subparsers.add_parser("approve")
    approve.add_argument("version_root", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "freeze":
            auxiliary_frames = []
            for raw in args.auxiliary_frame:
                parts = raw.split("=", 2)
                if len(parts) != 3:
                    raise ValueError("--auxiliary-frame must use ID=LABEL=PATH")
                auxiliary_frames.append((parts[0], parts[1], Path(parts[2])))
            result = freeze_layout(
                args.version_root,
                args.cue_id,
                args.approved_poster,
                hero_id=args.hero_id,
                hero_label=args.hero_label,
                auxiliary_frames=auxiliary_frames,
            )
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
