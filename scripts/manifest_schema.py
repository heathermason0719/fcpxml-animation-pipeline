"""Canonical JSON Schema validation at normal Review write boundaries."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator


@lru_cache(maxsize=2)
def _validator(version="2.0"):
    name = "legacy/animation-manifest-v2.schema.json" if version == "2.0" else "animation-manifest.schema.json"
    schema = json.loads((Path(__file__).resolve().parents[1] / "references" / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_manifest_schema(manifest):
    if manifest.get("schemaVersion") not in {"2.0", "3.0"}:
        raise ValueError("unsupported manifest schemaVersion")
    error = next(_validator(manifest["schemaVersion"]).iter_errors(manifest), None)
    if error is not None:
        location = ".".join(str(item) for item in error.absolute_path) or "manifest"
        raise ValueError(f"manifest schema: {location}: {error.message}")


def save_review_manifest(root, manifest):
    try:
        from scripts.hyperframes_adapter import save_manifest
    except ModuleNotFoundError:  # direct script execution
        from hyperframes_adapter import save_manifest
    try:
        from scripts.workflow_status import resolve_stage_status
    except ModuleNotFoundError:
        from workflow_status import resolve_stage_status
    previous = resolve_stage_status(root)
    if previous.get("blockingStage") is None and "D5" in previous.get("completedStages", []):
        raise ValueError("closed invocation is read-only; begin rework before changing Review evidence")
    validate_manifest_schema(manifest)
    save_manifest(root, manifest)
