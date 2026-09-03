#!/usr/bin/env python3
"""Register verified native delivery movies in animation-manifest.json."""

from __future__ import annotations

try:
    from scripts.manifest_transaction import manifest_commit, optimistic_operation
except ModuleNotFoundError:  # direct script execution
    from manifest_transaction import manifest_commit, optimistic_operation

import argparse
import hashlib
import json
import re
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

try:
    from scripts.hyperframes_adapter import load_manifest, parse_time, project_dimensions, safe_project_path, save_manifest
    from scripts.layout_lock import verify_layouts
    from scripts.validate_delivery import DeliveryExpectation, validate_probe
    from scripts.workflow_status import evidence_fingerprint, resolve_stage_status
    from scripts.workflow_inputs import effective_project_fps, require_current_input_evidence
except ModuleNotFoundError:
    from hyperframes_adapter import load_manifest, parse_time, project_dimensions, safe_project_path, save_manifest  # type: ignore
    from layout_lock import verify_layouts  # type: ignore
    from validate_delivery import DeliveryExpectation, validate_probe  # type: ignore
    from workflow_status import evidence_fingerprint, resolve_stage_status  # type: ignore
    from workflow_inputs import effective_project_fps, require_current_input_evidence  # type: ignore


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fraction(value: Any) -> Fraction:
    try:
        return Fraction(str(value))
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError(f"invalid rational value: {value!r}") from error


def _fraction_text(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def _project_fps(manifest: dict[str, Any]) -> Fraction:
    return effective_project_fps(manifest)


def _stable_file_name(cue_id: str) -> str:
    if not isinstance(cue_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", cue_id):
        raise ValueError(f"unsafe cue id for delivery file name: {cue_id!r}")
    return f"AF__{cue_id.replace('_', '-')}.mov"


def probe_delivery_asset(path: Path) -> dict[str, Any]:
    target = path.expanduser().resolve()
    if not target.is_file() or target.is_symlink():
        raise ValueError(f"missing regular delivery movie: {target}")
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,codec_name,profile,width,height,pix_fmt,r_frame_rate,duration",
        "-of",
        "json",
        str(target),
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    payload = json.loads(completed.stdout)
    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise ValueError(f"ffprobe did not return streams: {target}")
    videos = [stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"]
    audios = [stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "audio"]
    if len(videos) != 1:
        raise ValueError(f"delivery movie must contain exactly one video stream: {target}")
    return {**videos[0], "audio_streams": len(audios)}


@optimistic_operation
def register_delivery_assets(
    version_root: Path,
    *,
    prober: Callable[[Path], dict[str, Any]] = probe_delivery_asset,
) -> dict[str, Any]:
    root = version_root.expanduser().resolve()
    manifest = load_manifest(root)
    require_current_input_evidence(root, manifest)
    stage_status = resolve_stage_status(root)
    if stage_status.get("evidence", {}).get("D2") not in {"current", "compatible-historical"}:
        raise ValueError(
            "delivery asset registration requires current D2 render evidence; "
            f"blocked at {stage_status.get('blockingStage')}"
        )
    lock_result = verify_layouts(root)
    if lock_result["status"] != "valid":
        raise ValueError(f"layout locks are invalid: {lock_result['invalidCueIds']}")
    ledger_path = root / "delivery/render-ledger.json"
    if not ledger_path.is_file() or ledger_path.is_symlink():
        raise ValueError(f"missing regular render ledger: {ledger_path}")
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if ledger.get("status") != "rendered" or not isinstance(ledger.get("items"), list):
        raise ValueError("render ledger must have status rendered and an items array")

    animated = [cue for cue in manifest["cues"] if cue.get("productionMode") == "animation"]
    source_only = [cue for cue in manifest["cues"] if cue.get("productionMode") == "source-only"]
    unsupported = [cue.get("id") for cue in manifest["cues"] if cue.get("productionMode") not in {"animation", "source-only"}]
    if unsupported:
        raise ValueError(f"unsupported productionMode for cues: {unsupported}")
    stale_source_assets = [cue.get("id") for cue in source_only if "deliveryAsset" in cue]
    if stale_source_assets:
        raise ValueError(f"source-only cues must not have deliveryAsset: {stale_source_assets}")

    items_by_cue: dict[str, list[dict[str, Any]]] = {}
    for item in ledger["items"]:
        if not isinstance(item, dict) or not isinstance(item.get("cueId"), str):
            raise ValueError("every render ledger item must declare cueId")
        items_by_cue.setdefault(item["cueId"], []).append(item)
    animated_ids = {cue["id"] for cue in animated}
    unknown_ledger = sorted(set(items_by_cue) - animated_ids)
    if unknown_ledger:
        raise ValueError(f"ledger contains unknown or source-only cues: {unknown_ledger}")

    width, height = project_dimensions(manifest, "delivery")
    fps = _project_fps(manifest)
    registrations: dict[str, dict[str, Any]] = {}
    for cue in animated:
        cue_id = cue["id"]
        matches = items_by_cue.get(cue_id, [])
        if len(matches) != 1:
            raise ValueError(f"expected exactly one ledger item for {cue_id}, found {len(matches)}")
        item = matches[0]
        output = safe_project_path(root, item.get("output"))
        job = item.get("job")
        if not isinstance(job, dict):
            raise ValueError(f"ledger job is missing for {cue_id}")
        duration = parse_time(cue["resolvedTimeline"]["duration"])
        if (
            int(job.get("width", 0)) != width
            or int(job.get("height", 0)) != height
            or _fraction(job.get("fps")) != fps
            or _fraction(job.get("duration")) != duration
        ):
            raise ValueError(f"ledger job does not match manifest delivery contract for {cue_id}")
        probe = prober(output)
        if int(probe.get("audio_streams", -1)) != 0:
            raise ValueError(f"delivery asset contains audio for {cue_id}")
        findings = validate_probe(probe, DeliveryExpectation(width, height, fps, duration))
        if findings:
            raise ValueError(f"delivery validation failed for {cue_id}: {', '.join(findings)}")
        registrations[cue_id] = {
            "fileName": _stable_file_name(cue_id),
            "sha256": _sha256(output),
            "width": width,
            "height": height,
            "frameRate": _fraction_text(fps),
            "duration": f"{_fraction_text(duration)}s",
            "codec": "prores_4444",
            "hasAlpha": True,
        }

    for cue in animated:
        cue["deliveryAsset"] = registrations[cue["id"]]
    workflow = manifest["workflow"]
    workflow.setdefault("stageEvidence", {})["D3"] = {
        "stageId": "D3",
        "contractVersion": workflow["stageContractVersion"],
        "semanticVersion": 1,
        "status": "registered",
        "renderLedgerSha256": _sha256(ledger_path),
        "assetFingerprint": evidence_fingerprint(
            {cue_id: registrations[cue_id] for cue_id in sorted(registrations)}
        ),
    }
    with manifest_commit(root):
        if resolve_stage_status(root).get("evidence", {}).get("D2") not in {"current", "compatible-historical"}:
            raise ValueError("delivery registration requires current D2 evidence after media probing")
        require_current_input_evidence(root, manifest)
        save_manifest(root, manifest)
    return {
        "status": "registered",
        "versionRoot": str(root),
        "registeredCueIds": sorted(registrations),
        "sourceOnlyCueIds": sorted(cue["id"] for cue in source_only),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="验证正式透明 MOV 并注册 deliveryAsset。")
    parser.add_argument("version_root", type=Path)
    args = parser.parse_args()
    try:
        result = register_delivery_assets(args.version_root)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
