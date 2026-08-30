#!/usr/bin/env python3
"""Validate the single-source HyperFrames adapter contract."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from scripts.hyperframes_adapter import (
        GENERATED_REVIEW_MARKER,
        composition_dimensions,
        cue_adapter,
        load_manifest,
        project_dimensions,
        safe_project_path,
    )
    from scripts.layout_lock import verify_layouts
except ModuleNotFoundError:
    from hyperframes_adapter import (  # type: ignore
        GENERATED_REVIEW_MARKER,
        composition_dimensions,
        cue_adapter,
        load_manifest,
        project_dimensions,
        safe_project_path,
    )
    from layout_lock import verify_layouts  # type: ignore


MOTION_LAYOUT_PROPERTY = re.compile(
    r"\b(?:top|right|bottom|left|width|height|minWidth|maxWidth|minHeight|maxHeight|margin|padding|gap|fontSize|fontFamily|fontWeight|lineHeight|letterSpacing|display)\s*:"
)
LOCAL_REFERENCE = re.compile(r"(?:src\s*=\s*[\"']([^\"']+)[\"']|url\(\s*[\"']?([^\"')]+))")


def _finding(code: str, cue_id: str | None, message: str, path: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"code": code, "message": message}
    if cue_id is not None:
        result["cueId"] = cue_id
    if path is not None:
        result["path"] = path
    return result


def _local_references(html: str) -> set[str]:
    references: set[str] = set()
    for match in LOCAL_REFERENCE.finditer(html):
        value = match.group(1) or match.group(2)
        if not value or value.startswith(("http://", "https://", "data:", "#")):
            continue
        references.add(value)
    return references


def validate_project(version_root: Path) -> dict[str, Any]:
    root = version_root.expanduser().resolve()
    findings: list[dict[str, Any]] = []
    try:
        manifest = load_manifest(root)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return {"status": "invalid", "findings": [_finding("manifest_invalid", None, str(error))]}
    seen_ids: set[str] = set()
    try:
        delivery_dimensions = project_dimensions(manifest, "delivery")
    except ValueError as error:
        return {"status": "invalid", "findings": [_finding("manifest_invalid", None, str(error))]}
    allowed_states = {"design-draft", "layout-built", "layout-approved", "motion-built", "motion-approved", "rendered"}
    for cue in manifest["cues"]:
        cue_id = cue.get("id")
        if not isinstance(cue_id, str) or cue_id in seen_ids:
            findings.append(_finding("cue_id_invalid", cue_id, "cue id must be a unique string"))
            continue
        seen_ids.add(cue_id)
        if cue.get("workflowState") not in allowed_states:
            findings.append(_finding("workflow_state_invalid", cue_id, "unsupported workflowState"))
        mode = cue.get("productionMode")
        try:
            adapter = cue_adapter(cue)
        except ValueError as error:
            findings.append(_finding("adapter_missing", cue_id, str(error)))
            continue
        for key in ("reviewSrc", "stillSrc"):
            try:
                safe_project_path(root, adapter[key])
            except (KeyError, ValueError) as error:
                findings.append(_finding("adapter_path_invalid", cue_id, str(error), adapter.get(key)))
        if mode == "source-only":
            forbidden = [key for key in ("compositionId", "compositionSrc", "motionSrc", "layoutDependencies", "layoutLock") if key in adapter]
            if forbidden:
                findings.append(_finding("source_only_has_animation", cue_id, f"source-only adapter contains: {', '.join(forbidden)}"))
            continue
        if mode != "animation":
            findings.append(_finding("production_mode_invalid", cue_id, "productionMode must be animation or source-only"))
            continue
        try:
            composition_path = safe_project_path(root, adapter["compositionSrc"])
            motion_path = safe_project_path(root, adapter["motionSrc"])
            review_path = safe_project_path(root, adapter["reviewSrc"])
        except (KeyError, ValueError) as error:
            findings.append(_finding("animation_path_invalid", cue_id, str(error)))
            continue
        composition = composition_path.read_text(encoding="utf-8")
        motion = motion_path.read_text(encoding="utf-8")
        review = review_path.read_text(encoding="utf-8")
        composition_id = adapter.get("compositionId")
        if f'data-composition-id="{composition_id}"' not in composition:
            findings.append(_finding("composition_id_mismatch", cue_id, "composition id does not match manifest", adapter["compositionSrc"]))
        try:
            actual_dimensions = composition_dimensions(composition)
        except ValueError as error:
            findings.append(_finding("composition_dimensions_invalid", cue_id, str(error), adapter["compositionSrc"]))
        else:
            if actual_dimensions != delivery_dimensions:
                findings.append(
                    _finding(
                        "composition_dimensions_mismatch",
                        cue_id,
                        f"canonical composition dimensions {actual_dimensions[0]}x{actual_dimensions[1]} do not match delivery {delivery_dimensions[0]}x{delivery_dimensions[1]}",
                        adapter["compositionSrc"],
                    )
                )
        if f'window.__timelines["{composition_id}"]' not in motion and f"window.__timelines['{composition_id}']" not in motion:
            findings.append(_finding("timeline_id_mismatch", cue_id, "motion timeline key does not match composition id", adapter["motionSrc"]))
        if adapter["motionSrc"] not in composition:
            findings.append(_finding("motion_not_linked", cue_id, "canonical composition does not reference motionSrc", adapter["compositionSrc"]))
        if GENERATED_REVIEW_MARKER not in review or adapter["compositionSrc"] not in review:
            findings.append(_finding("review_projection_invalid", cue_id, "review projection is not generated from canonical composition", adapter["reviewSrc"]))
        if MOTION_LAYOUT_PROPERTY.search(motion):
            findings.append(_finding("motion_layout_property", cue_id, "motion file contains a layout-affecting property", adapter["motionSrc"]))
        dependencies = set(adapter.get("layoutDependencies") or [])
        unlisted = sorted(_local_references(composition) - {adapter["motionSrc"]} - dependencies)
        if unlisted:
            findings.append(_finding("layout_dependency_unlisted", cue_id, f"unlisted local dependencies: {', '.join(unlisted)}", adapter["compositionSrc"]))
    layout_result = verify_layouts(root)
    for cue_id in layout_result["invalidCueIds"]:
        findings.append(_finding("layout_lock_mismatch", cue_id, "approved layout dependencies changed"))
    index_path = root / "index.html"
    if index_path.is_file():
        index = index_path.read_text(encoding="utf-8")
        for cue in manifest["cues"]:
            adapter = cue_adapter(cue)
            if cue.get("productionMode") == "animation" and adapter["compositionSrc"] not in index:
                findings.append(_finding("index_missing_animation", cue["id"], "index does not mount canonical composition", "index.html"))
            if cue.get("productionMode") == "source-only" and adapter.get("compositionId") and adapter["compositionId"] in index:
                findings.append(_finding("index_mounts_source_only", cue["id"], "index mounts a source-only cue", "index.html"))
    return {"status": "invalid" if findings else "valid", "findings": findings}


def main() -> int:
    parser = argparse.ArgumentParser(description="验证单一布局源 HyperFrames adapter。")
    parser.add_argument("version_root", type=Path)
    args = parser.parse_args()
    result = validate_project(args.version_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "valid" else 2


if __name__ == "__main__":
    raise SystemExit(main())
