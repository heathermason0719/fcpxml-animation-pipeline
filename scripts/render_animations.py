#!/usr/bin/env python3
"""Render locked animated cues at their native delivery dimensions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Sequence

try:
    from scripts.hyperframes_adapter import (
        cue_adapter,
        delivery_projection_src,
        load_manifest,
        parse_time,
        project_dimensions,
        safe_project_path,
    )
    from scripts.layout_lock import verify_layouts
    from scripts.sync_delivery import sync_delivery
    from scripts.validate_delivery import DeliveryExpectation, probe_delivery, validate_probe
    from scripts.validate_hyperframes_adapter import validate_project
    from scripts.workflow_status import resolve_stage_status
    from scripts.workflow_inputs import effective_project_fps, require_current_input_evidence
    from scripts.manifest_transaction import manifest_commit, optimistic_operation
except ModuleNotFoundError:
    from hyperframes_adapter import (  # type: ignore
        cue_adapter,
        delivery_projection_src,
        load_manifest,
        parse_time,
        project_dimensions,
        safe_project_path,
    )
    from layout_lock import verify_layouts  # type: ignore
    from sync_delivery import sync_delivery  # type: ignore
    from validate_delivery import DeliveryExpectation, probe_delivery, validate_probe  # type: ignore
    from validate_hyperframes_adapter import validate_project  # type: ignore
    from workflow_status import resolve_stage_status  # type: ignore
    from workflow_inputs import effective_project_fps, require_current_input_evidence  # type: ignore
    from manifest_transaction import manifest_commit, optimistic_operation  # type: ignore


@dataclass(frozen=True)
class RenderJob:
    cue_id: str
    composition_src: str
    output_name: str
    width: int
    height: int
    fps: Fraction
    duration: Fraction


def _project_fps(manifest: dict[str, Any]) -> Fraction:
    return effective_project_fps(manifest)


def _fraction_text(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def build_render_jobs(version_root: Path) -> list[RenderJob]:
    root = version_root.expanduser().resolve()
    manifest = load_manifest(root)
    width, height = project_dimensions(manifest, "delivery")
    fps = _project_fps(manifest)
    jobs: list[RenderJob] = []
    for cue in manifest["cues"]:
        if cue.get("productionMode") == "source-only":
            continue
        if cue.get("productionMode") != "animation":
            raise ValueError(f"unsupported productionMode for {cue.get('id')}")
        adapter = cue_adapter(cue)
        composition_src = delivery_projection_src(adapter)
        safe_project_path(root, composition_src, must_exist=False)
        basename = Path(adapter["compositionSrc"]).stem
        jobs.append(
            RenderJob(
                cue_id=cue["id"],
                composition_src=composition_src,
                output_name=f"{basename}.mov",
                width=width,
                height=height,
                fps=fps,
                duration=parse_time(cue["resolvedTimeline"]["duration"]),
            )
        )
    return jobs


def build_render_command(version_root: Path, job: RenderJob, temporary_output: Path) -> list[str]:
    root = version_root.expanduser().resolve()
    output = temporary_output.expanduser().resolve()
    try:
        output.relative_to(root)
    except ValueError as error:
        raise ValueError("render output must stay inside the Vn root") from error
    return [
        "npm",
        "run",
        "render",
        "--",
        "--composition",
        job.composition_src,
        "--format",
        "mov",
        "--fps",
        _fraction_text(job.fps),
        "--quality",
        "high",
        "--no-best-effort",
        "--output",
        str(output),
    ]


def _canonical_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _assert_final_render_ready(root: Path, selected: Sequence[RenderJob]) -> dict[str, Any]:
    stage_status = resolve_stage_status(root)
    if stage_status.get("nextEligibleStage") != "D2":
        raise ValueError(
            "native rendering requires current A13 approval, independent A14 authorization "
            "and current input fingerprint evidence; "
            f"blocked at {stage_status.get('blockingStage')}"
        )
    manifest = load_manifest(root)
    inputs = require_current_input_evidence(root, manifest)
    adapter_result = validate_project(root)
    if adapter_result["status"] != "valid":
        raise ValueError(f"HyperFrames adapter is invalid: {adapter_result['findings']}")
    lock_result = verify_layouts(root)
    if lock_result["status"] != "valid":
        raise ValueError(f"layout locks are invalid: {lock_result['invalidCueIds']}")
    manifest = load_manifest(root)
    cues = {cue["id"]: cue for cue in manifest["cues"]}
    missing = [job.cue_id for job in selected if not cue_adapter(cues[job.cue_id]).get("layoutLock")]
    if missing:
        raise ValueError(f"final rendering requires approved layout locks: {', '.join(missing)}")
    a14 = manifest["workflow"]["stageEvidence"]["A14"]
    return {
        "authorizationFingerprint": _canonical_sha256(a14),
        **inputs,
    }


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


@optimistic_operation
def render_animations(
    version_root: Path,
    cue_ids: list[str] | None = None,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    prober: Callable[[Path], dict[str, Any]] = probe_delivery,
) -> dict[str, Any]:
    root = version_root.expanduser().resolve()
    jobs = build_render_jobs(root)
    if cue_ids is not None:
        requested = set(cue_ids)
        known = {job.cue_id for job in jobs}
        unknown = sorted(requested - known)
        if unknown:
            raise ValueError(f"unknown or source-only cue ids: {', '.join(unknown)}")
        jobs = [job for job in jobs if job.cue_id in requested]
    with manifest_commit(root):
        gate = _assert_final_render_ready(root, jobs)
        sync_delivery(root)
    partial_parent = root / "delivery/.partial"
    output_root = root / "delivery/prores4444"
    partial_parent.mkdir(parents=True, exist_ok=True)
    partial_root = Path(tempfile.mkdtemp(prefix="render-", dir=partial_parent))
    output_root.mkdir(parents=True, exist_ok=True)
    rendered: list[dict[str, Any]] = []
    for job in jobs:
        with manifest_commit(root):
            if _assert_final_render_ready(root, jobs) != gate:
                raise ValueError("native render authorization or inputs changed")
        final_output = output_root / job.output_name
        if final_output.exists():
            raise ValueError(f"refusing to overwrite existing delivery: {final_output}")
        temporary_output = partial_root / job.output_name
        command = build_render_command(root, job, temporary_output)
        runner(command, cwd=root, check=True, capture_output=True, text=True)
        probe = prober(temporary_output)
        expectation = DeliveryExpectation(job.width, job.height, job.fps, job.duration)
        findings = validate_probe(probe, expectation)
        if findings:
            raise ValueError(f"delivery validation failed for {job.cue_id}: {', '.join(findings)}")
        rendered.append(
            {
                "cueId": job.cue_id,
                "output": str(final_output.relative_to(root)),
                "sha256": hashlib.sha256(temporary_output.read_bytes()).hexdigest(),
                "job": {**asdict(job), "fps": _fraction_text(job.fps), "duration": _fraction_text(job.duration)},
                "probe": probe,
            }
        )
    # A long render never holds the Review lock. Publish only while its original
    # manifest revision, semantic inputs and authorization are still current.
    with manifest_commit(root):
        if _assert_final_render_ready(root, jobs) != gate:
            raise ValueError("native render authorization or inputs changed")
        if any((output_root / job.output_name).exists() for job in jobs):
            raise ValueError("refusing to overwrite delivery published during rendering")
        manifest = load_manifest(root)
        ledger = {
            "stageId": "D2",
            "contractVersion": manifest["workflow"]["stageContractVersion"],
            "semanticVersion": 1,
            "status": "rendered",
            **gate,
            "items": rendered,
        }
        for job in jobs:
            os.replace(partial_root / job.output_name, output_root / job.output_name)
        _write_json_atomic(root / "delivery/render-ledger.json", ledger)
    return ledger


def main() -> int:
    parser = argparse.ArgumentParser(description="原生渲染已批准的透明 ProRes 4444 animated cues。")
    parser.add_argument("version_root", type=Path)
    parser.add_argument("--cue", action="append", dest="cue_ids")
    args = parser.parse_args()
    try:
        result = render_animations(args.version_root, args.cue_ids)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
