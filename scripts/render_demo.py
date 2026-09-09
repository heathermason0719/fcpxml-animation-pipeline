#!/usr/bin/env python3
"""Render one complete, evidence-bound 480p A12 Demo."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

try:
    from scripts.assemble_hyperframes import assemble_hyperframes
    from scripts.demo_evidence import capture_demo_inputs, write_demo_generation_evidence
    from scripts.hyperframes_adapter import load_manifest, parse_time, project_dimensions, safe_project_path
    from scripts.manifest_transaction import manifest_commit, optimistic_operation, require_open_invocation
    from scripts.validate_delivery import probe_delivery
    from scripts.workflow_inputs import effective_project_fps
    from scripts.workflow_status import resolve_stage_status
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from assemble_hyperframes import assemble_hyperframes  # type: ignore
    from demo_evidence import capture_demo_inputs, write_demo_generation_evidence  # type: ignore
    from hyperframes_adapter import load_manifest, parse_time, project_dimensions, safe_project_path  # type: ignore
    from manifest_transaction import manifest_commit, optimistic_operation, require_open_invocation  # type: ignore
    from validate_delivery import probe_delivery  # type: ignore
    from workflow_inputs import effective_project_fps  # type: ignore
    from workflow_status import resolve_stage_status  # type: ignore


def _fraction(value: Any) -> Fraction:
    try:
        return Fraction(str(value))
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError(f"invalid Demo media value: {value!r}") from error


def validate_demo_probe(probe: dict[str, Any], *, width: int, height: int, fps: Fraction, duration: Fraction) -> list[str]:
    findings: list[str] = []
    if (probe.get("width"), probe.get("height")) != (width, height):
        findings.append("dimensions_mismatch")
    try:
        actual_fps = _fraction(probe.get("r_frame_rate"))
    except ValueError:
        actual_fps = Fraction(0)
    if actual_fps != fps:
        findings.append("frame_rate_mismatch")
    try:
        actual_duration = _fraction(probe.get("duration"))
    except ValueError:
        actual_duration = Fraction(-1)
    if abs(actual_duration - duration) > Fraction(1, 1) / fps:
        findings.append("duration_mismatch")
    return findings


def _fraction_text(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def build_demo_command(version_root: Path, output: Path, *, fps: Fraction) -> list[str]:
    return [
        "npm", "run", "render", "--", "--format", "mp4", "--composition", "index.html",
        "--output", str(output), "--fps", _fraction_text(fps),
    ]


def _assert_demo_ready(root: Path) -> None:
    status = resolve_stage_status(root)
    if status.get("blockingStage") != "A12":
        raise ValueError("Demo rendering requires current A11 approval")


def _preview_relative(inputs: dict[str, Any]) -> str:
    canonical = json.dumps(inputs, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    identity = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"previews/demo-r{inputs['reworkRevision']:04d}-{identity[:16]}.mp4"


@optimistic_operation
def render_demo(
    version_root: Path,
    *,
    runner: Callable[..., Any] = subprocess.run,
    prober: Callable[[Path], dict[str, Any]] = probe_delivery,
) -> dict[str, Any]:
    root = version_root.expanduser().resolve()
    require_open_invocation(root)
    _assert_demo_ready(root)
    assemble_hyperframes(root)
    manifest = load_manifest(root)
    inputs = capture_demo_inputs(root, manifest)
    relative = _preview_relative(inputs)
    target = safe_project_path(root, relative, must_exist=False)
    if target.exists():
        raise ValueError(f"refusing to overwrite existing Demo preview: {target}")
    width, height = project_dimensions(manifest, "preview")
    fps = effective_project_fps(manifest)
    duration = parse_time(manifest["project"]["source"]["duration"])
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, partial_name = tempfile.mkstemp(prefix=".demo-", suffix=".mp4", dir=target.parent)
    os.close(descriptor)
    partial = Path(partial_name)
    try:
        runner(build_demo_command(root, partial, fps=fps), cwd=root, check=True)
        if not partial.is_file() or partial.is_symlink():
            raise ValueError("Demo renderer did not produce a regular MP4")
        probe = prober(partial)
        findings = validate_demo_probe(probe, width=width, height=height, fps=fps, duration=duration)
        if findings:
            raise ValueError("invalid Demo MP4: " + ", ".join(findings))
        # The final write is optimistic: all semantic and concrete inputs must remain exact.
        with manifest_commit(root):
            _assert_demo_ready(root)
            current = load_manifest(root)
            if capture_demo_inputs(root, current) != inputs:
                raise ValueError("Demo execution inputs changed during rendering")
            if target.exists():
                raise ValueError(f"refusing to overwrite existing Demo preview: {target}")
            published = False
            try:
                os.replace(partial, target)
                published = True
                evidence = write_demo_generation_evidence(root, relative, inputs=inputs, probe=probe)
            except BaseException:
                if published:
                    target.unlink(missing_ok=True)
                raise
        return {"status": "rendered", "preview": relative, "sha256": evidence["sha256"], "generationEvidence": str(Path(relative + ".evidence.json"))}
    finally:
        try:
            partial.unlink()
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the full 480p AfterForge Demo with generation evidence.")
    parser.add_argument("version_root", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(render_demo(args.version_root), ensure_ascii=False, indent=2))
    except (OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
