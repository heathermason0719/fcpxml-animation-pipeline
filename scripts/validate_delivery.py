#!/usr/bin/env python3
"""Validate native transparent HyperFrames delivery movies with ffprobe."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DeliveryExpectation:
    width: int
    height: int
    fps: Fraction
    duration: Fraction


def _fraction(value: Any) -> Fraction:
    try:
        return Fraction(str(value))
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError(f"invalid rational value: {value!r}") from error


def _has_alpha(pixel_format: str) -> bool:
    return pixel_format.startswith(("yuva", "gbrap", "rgba", "argb", "bgra", "abgr", "ya"))


def validate_probe(probe: dict[str, Any], expected: DeliveryExpectation) -> list[str]:
    findings: list[str] = []
    if (probe.get("width"), probe.get("height")) != (expected.width, expected.height):
        findings.append("dimensions_mismatch")
    if probe.get("codec_name") != "prores" or "4444" not in str(probe.get("profile", "")):
        findings.append("codec_mismatch")
    if not _has_alpha(str(probe.get("pix_fmt", ""))):
        findings.append("alpha_missing")
    try:
        actual_fps = _fraction(probe.get("r_frame_rate"))
    except ValueError:
        actual_fps = Fraction(0, 1)
    if actual_fps != expected.fps:
        findings.append("frame_rate_mismatch")
    try:
        actual_duration = _fraction(probe.get("duration"))
    except ValueError:
        actual_duration = Fraction(-1, 1)
    tolerance = Fraction(1, 1) / expected.fps
    if abs(actual_duration - expected.duration) > tolerance:
        findings.append("duration_mismatch")
    return findings


def probe_delivery(path: Path) -> dict[str, Any]:
    target = path.expanduser().resolve()
    if not target.is_file() or target.is_symlink():
        raise ValueError(f"missing regular delivery movie: {target}")
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,profile,width,height,pix_fmt,r_frame_rate,duration",
        "-of",
        "json",
        str(target),
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    payload = json.loads(completed.stdout)
    streams = payload.get("streams")
    if not isinstance(streams, list) or len(streams) != 1 or not isinstance(streams[0], dict):
        raise ValueError(f"ffprobe did not return exactly one video stream: {target}")
    return streams[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="验证透明 ProRes 4444 交付文件。")
    parser.add_argument("movie", type=Path)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--fps", required=True)
    parser.add_argument("--duration", required=True)
    args = parser.parse_args()
    try:
        expectation = DeliveryExpectation(args.width, args.height, _fraction(args.fps), _fraction(args.duration))
        probe = probe_delivery(args.movie)
        findings = validate_probe(probe, expectation)
    except (OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "invalid", "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    result = {"status": "valid" if not findings else "invalid", "probe": probe, "findings": findings}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not findings else 2


if __name__ == "__main__":
    raise SystemExit(main())
