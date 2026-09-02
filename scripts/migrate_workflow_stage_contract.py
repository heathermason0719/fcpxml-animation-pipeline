#!/usr/bin/env python3
"""Explicitly attach the canonical workflow contract to one legacy Vn."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from scripts.hyperframes_adapter import load_manifest, safe_project_path, save_manifest
    from scripts.workflow_stages import load_stage_contract
    from scripts.workflow_status import current_input_fingerprint
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from hyperframes_adapter import load_manifest, safe_project_path, save_manifest  # type: ignore
    from workflow_stages import load_stage_contract  # type: ignore
    from workflow_status import current_input_fingerprint  # type: ignore


def _migrate_legacy_demo(root: Path, manifest: dict[str, Any]) -> dict[str, Any] | None:
    legacy = manifest.get("reviews", {}).get("a12")
    if not isinstance(legacy, dict) or not isinstance(legacy.get("preview"), str):
        return None
    try:
        preview = safe_project_path(root, legacy["preview"])
        actual_hash = hashlib.sha256(preview.read_bytes()).hexdigest()
        input_fingerprint = current_input_fingerprint(root, manifest)
    except (OSError, ValueError, KeyError):
        return None
    declared_hash = legacy.get("sha256")
    if declared_hash is not None and declared_hash != actual_hash:
        return None
    contract_version = manifest["workflow"]["stageContractVersion"]
    media = {
        key: value
        for key, value in legacy.items()
        if key not in {"status", "preview", "sha256", "animatedCueIds"}
    }
    evidence: dict[str, Any] = {
        "stageId": "A12",
        "contractVersion": contract_version,
        "semanticVersion": 1,
        "status": "ready",
        "preview": legacy["preview"],
        "sha256": actual_hash,
        "inputFingerprint": input_fingerprint,
        "migrationSource": "legacy-reviews.a12",
    }
    if media:
        evidence["media"] = media
    return evidence


def migrate_workflow_stage_contract(version_root: Path) -> dict[str, Any]:
    root = Path(version_root).expanduser().resolve()
    manifest = load_manifest(root)
    contract = load_stage_contract()
    workflow = manifest.get("workflow")
    if isinstance(workflow, dict):
        if workflow.get("stageContractVersion") == contract["contractVersion"]:
            return {"status": "already-current", "versionRoot": str(root)}
        raise ValueError(
            "Vn already declares a different workflow stage contract; explicit semantic migration is required"
        )
    if workflow is not None:
        raise ValueError("workflow must be absent or an object")

    legacy_reviews = manifest.get("reviews")
    preserved = sorted(legacy_reviews) if isinstance(legacy_reviews, dict) else []
    manifest["workflow"] = {
        "stageContractVersion": contract["contractVersion"],
        "roundTripRequired": True,
        "migration": {
            "source": "legacy-unversioned",
            "legacyReviewsPreserved": bool(preserved),
        },
        "stageEvidence": {},
        "activeReviewContext": "A11",
    }
    demo = _migrate_legacy_demo(root, manifest)
    if demo is not None:
        manifest["workflow"]["stageEvidence"]["A12"] = demo
    save_manifest(root, manifest)
    return {
        "status": "migrated",
        "versionRoot": str(root),
        "stageContractVersion": contract["contractVersion"],
        "preservedLegacyReviewStages": preserved,
        "migratedDemoEvidence": demo is not None,
        "requiresUserReview": ["A11", "A13", "A14"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="将一个 legacy Vn 显式迁移到当前 workflow stage contract。")
    parser.add_argument("version_root", type=Path)
    args = parser.parse_args()
    try:
        result = migrate_workflow_stage_contract(args.version_root)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
