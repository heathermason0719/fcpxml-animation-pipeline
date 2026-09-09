"""Evidence shared by the A12 Demo renderer and its registration gate."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

try:
    from scripts.hyperframes_adapter import cue_adapter, safe_project_path
    from scripts.manifest_transaction import manifest_commit, require_open_invocation
    from scripts.rework_state import rework_revision
    from scripts.workflow_inputs import input_fingerprint_evidence
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from hyperframes_adapter import cue_adapter, safe_project_path  # type: ignore
    from manifest_transaction import manifest_commit, require_open_invocation  # type: ignore
    from rework_state import rework_revision  # type: ignore
    from workflow_inputs import input_fingerprint_evidence  # type: ignore


DEMO_EVIDENCE_VERSION = 1


def _sha256(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"missing regular Demo input: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def evidence_path(version_root: Path, preview_relative: str) -> Path:
    root = version_root.expanduser().resolve()
    preview = safe_project_path(root, preview_relative, must_exist=False)
    return Path(f"{preview}.evidence.json")


def require_current_a11_approval(version_root: Path) -> None:
    """A producer may create current A12 proof only after A11 is current."""
    try:
        from scripts.workflow_status import resolve_stage_status
    except ModuleNotFoundError:  # pragma: no cover - direct script execution
        from workflow_status import resolve_stage_status  # type: ignore
    status = resolve_stage_status(version_root)
    if status.get("evidence", {}).get("A11") != "current":
        raise ValueError("Demo generation requires current A11 approval")


def _source_only_media(root: Path, manifest: dict[str, Any], rough_relative: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for cue in manifest["cues"]:
        if cue.get("productionMode") != "source-only":
            continue
        adapter = cue.get("renderAdapters", {}).get("hyperframes", {})
        if not isinstance(adapter, dict):
            adapter = {}
        relative = next(
            (adapter[key] for key in ("sourceMediaSrc", "sourceVideoSrc", "mediaSrc") if isinstance(adapter.get(key), str)),
            rough_relative,
        )
        path = safe_project_path(root, relative)
        records.append({"cueId": cue["id"], "path": relative, "sha256": _sha256(path)})
    return records


def capture_demo_inputs(version_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Capture semantic and concrete files that define one composited Demo."""
    root = version_root.expanduser().resolve()
    project_adapter = manifest["project"].get("renderAdapters", {}).get("hyperframes", {})
    if not isinstance(project_adapter, dict):
        raise ValueError("project renderAdapters.hyperframes must be an object")
    rough_relative = project_adapter.get("previewMediaSrc", "assets/media/rough-cut.m4v")
    if not isinstance(rough_relative, str):
        raise ValueError("previewMediaSrc must be a path")
    rough = safe_project_path(root, rough_relative)
    files = {
        "packageJson": {"path": "package.json", "sha256": _sha256(root / "package.json")},
        "hyperframesConfig": {"path": "hyperframes.json", "sha256": _sha256(root / "hyperframes.json")},
        "index": {"path": "index.html", "sha256": _sha256(root / "index.html")},
        "gsap": {"path": "assets/vendor/gsap.min.js", "sha256": _sha256(root / "assets/vendor/gsap.min.js")},
        "roughCut": {"path": rough_relative, "sha256": _sha256(rough)},
    }
    return {
        "evidenceVersion": DEMO_EVIDENCE_VERSION,
        **input_fingerprint_evidence(root, manifest),
        "reworkRevision": rework_revision(manifest),
        "hostInputs": files,
        "sourceOnlyReferenceVideos": _source_only_media(root, manifest, rough_relative),
    }


def write_demo_generation_evidence(
    version_root: Path,
    preview_relative: str,
    *,
    inputs: dict[str, Any],
    probe: dict[str, Any],
) -> dict[str, Any]:
    """Atomically record a renderer-produced preview and its frozen inputs."""
    root = version_root.expanduser().resolve()
    with manifest_commit(root):
        require_open_invocation(root)
        require_current_a11_approval(root)
        preview = safe_project_path(root, preview_relative)
        evidence = {
            "kind": "afterforge-demo-generation",
            "evidenceVersion": DEMO_EVIDENCE_VERSION,
            "preview": preview_relative,
            "sha256": _sha256(preview),
            "inputs": inputs,
            "probe": probe,
        }
        target = evidence_path(root, preview_relative)
        if target.exists():
            raise ValueError(f"refusing to overwrite Demo generation evidence: {target}")
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(evidence, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temporary_name, target)
        except BaseException:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise
        return evidence


def require_matching_demo_generation_evidence(
    version_root: Path, manifest: dict[str, Any], preview_relative: str
) -> dict[str, Any]:
    """Reject registration unless the preview was generated from live inputs."""
    root = version_root.expanduser().resolve()
    target = evidence_path(root, preview_relative)
    if not target.is_file() or target.is_symlink():
        raise ValueError("Demo registration requires matching generation evidence")
    try:
        evidence = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("invalid Demo generation evidence") from error
    preview = safe_project_path(root, preview_relative)
    inputs = capture_demo_inputs(root, manifest)
    if (
        not isinstance(evidence, dict)
        or evidence.get("kind") != "afterforge-demo-generation"
        or evidence.get("evidenceVersion") != DEMO_EVIDENCE_VERSION
        or evidence.get("preview") != preview_relative
        or evidence.get("sha256") != _sha256(preview)
        or evidence.get("inputs") != inputs
    ):
        raise ValueError("Demo generation evidence does not match current execution inputs")
    return evidence
