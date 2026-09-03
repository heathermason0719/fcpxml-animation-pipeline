"""Versioned semantic execution inputs; legacy hashes are history, not new authority."""

from __future__ import annotations

import hashlib
import json
from fractions import Fraction
from pathlib import Path
from typing import Any, Sequence

try:
    from scripts.hyperframes_adapter import cue_adapter, parse_time, safe_project_path
    from scripts.hyperframes_runtime import read_runtime_pin
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from hyperframes_adapter import cue_adapter, parse_time, safe_project_path  # type: ignore
    from hyperframes_runtime import read_runtime_pin  # type: ignore


INPUT_FINGERPRINT_VERSION = 2


def evidence_fingerprint_version(evidence: dict[str, Any]) -> int:
    version = evidence.get("inputFingerprintVersion", 1)
    if type(version) is not int or version not in (1, INPUT_FINGERPRINT_VERSION):
        raise ValueError("unsupported input fingerprint version")
    return version


def _fraction_text(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def effective_project_fps(manifest: dict[str, Any]) -> Fraction:
    """Source time base is authoritative; a declared render rate must agree exactly."""
    source = manifest["project"]["source"]
    frame_duration = parse_time(source["frameDuration"])
    if frame_duration <= 0:
        raise ValueError("project frame duration must be positive")
    fps = 1 / frame_duration
    if source.get("frameRate") is not None:
        try:
            declared = Fraction(str(source["frameRate"]))
        except (ValueError, ZeroDivisionError) as error:
            raise ValueError("invalid project frame rate") from error
        if declared != fps:
            raise ValueError("inconsistent project frameRate and frameDuration")
    return fps


def input_fingerprint(root: Path, manifest: dict[str, Any], version: int = INPUT_FINGERPRINT_VERSION) -> str:
    evidence_fingerprint_version({"inputFingerprintVersion": version})
    records: list[dict[str, Any]] = []
    # v1 intentionally preserves its original sorted-cue and raw-spec algorithm.
    cues = sorted(manifest["cues"], key=lambda item: item["id"]) if version == 1 else manifest["cues"]
    for cue in cues:
        if cue.get("productionMode") != "animation":
            continue
        adapter = cue_adapter(cue)
        lock = adapter.get("layoutLock")
        if not isinstance(lock, dict):
            raise ValueError(f"animated cue lacks layout lock: {cue['id']}")
        motion_path = safe_project_path(root, adapter["motionSrc"])
        record = {
            "cueId": cue["id"],
            "layoutRevision": lock.get("revision"),
            "layoutAggregateSha256": lock.get("aggregateSha256"),
            "approvedPosterSha256": lock.get("approvedPosterSha256"),
            "reviewProjectionSha256": lock.get("reviewProjection", {}).get("sha256"),
            "motionSha256": hashlib.sha256(motion_path.read_bytes()).hexdigest(),
        }
        if version == 2:
            record["resolvedTimeline"] = {
                field: _fraction_text(parse_time(cue["resolvedTimeline"][field]))
                for field in ("start", "duration")
            }
        records.append(record)
    payload = {
        "hyperframesRuntimeVersion": read_runtime_pin(root),
        "preview": manifest["project"]["preview"],
        "delivery": manifest["project"]["delivery"],
        "cues": records,
    }
    if version == 2:
        source = manifest["project"]["source"]
        payload.update({
            "inputFingerprintVersion": version,
            "sourceDuration": _fraction_text(parse_time(source["duration"])),
            "sourceFrameDuration": _fraction_text(parse_time(source["frameDuration"])),
            "renderFps": _fraction_text(effective_project_fps(manifest)),
        })
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def input_fingerprint_evidence(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "inputFingerprintVersion": INPUT_FINGERPRINT_VERSION,
        "inputFingerprint": input_fingerprint(root, manifest),
    }


def require_current_input_evidence(
    root: Path,
    manifest: dict[str, Any],
    stages: Sequence[str] = ("A12", "A13", "A14"),
) -> dict[str, Any]:
    """Additional write gate; does not replace stage approval/artifact validation."""
    current = input_fingerprint_evidence(root, manifest)
    evidence = manifest.get("workflow", {}).get("stageEvidence", {})
    for stage in stages:
        record = evidence.get(stage)
        if not isinstance(record, dict) or evidence_fingerprint_version(record) != INPUT_FINGERPRINT_VERSION:
            raise ValueError(f"{stage} requires current input fingerprint evidence: explicit evidence migration or new review required")
        if record.get("inputFingerprint") != current["inputFingerprint"]:
            raise ValueError(f"{stage} input fingerprint does not match current execution inputs")
    return current
