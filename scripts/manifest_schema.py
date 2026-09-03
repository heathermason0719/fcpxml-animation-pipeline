"""Canonical JSON Schema validation at normal Review write boundaries."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator


@lru_cache(maxsize=1)
def _validator():
    schema = json.loads((Path(__file__).resolve().parents[1] / "references/animation-manifest.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_manifest_schema(manifest):
    error = next(_validator().iter_errors(manifest), None)
    if error is not None:
        location = ".".join(str(item) for item in error.absolute_path) or "manifest"
        raise ValueError(f"manifest schema: {location}: {error.message}")


def save_review_manifest(root, manifest):
    try:
        from scripts.hyperframes_adapter import save_manifest
    except ModuleNotFoundError:  # direct script execution
        from hyperframes_adapter import save_manifest
    validate_manifest_schema(manifest)
    save_manifest(root, manifest)
