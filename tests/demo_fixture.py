"""Explicit non-media producer fixtures for A12 registration tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.assemble_hyperframes import assemble_hyperframes
from scripts.demo_evidence import capture_demo_inputs, write_demo_generation_evidence


def write_simulated_demo_evidence(
    version_root: Path, preview_relative: str, *, probe: dict[str, Any] | None = None
) -> dict[str, Any]:
    root = version_root.expanduser().resolve()
    # Mirror the production boundary: generated host first, then frozen inputs.
    assemble_hyperframes(root)
    manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
    return write_demo_generation_evidence(
        root,
        preview_relative,
        inputs=capture_demo_inputs(root, manifest),
        probe=probe or {"simulated": True},
    )
