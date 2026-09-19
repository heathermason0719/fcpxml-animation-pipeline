#!/usr/bin/env python3
"""Small, stage-free media primitives for the v3 work model.

This module deliberately owns no manifest mutations, cache policy, or review
authorization.  Callers supply the already-resolved cue and publish results
only after their own transaction checks.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path
from typing import Any

try:
    from scripts.hyperframes_runtime import read_runtime_pin
    from scripts.work_model_runtime import local_cached_cli
    from scripts.validate_delivery import probe_delivery
except ModuleNotFoundError:  # pragma: no cover - direct script use
    from hyperframes_runtime import read_runtime_pin  # type: ignore
    from work_model_runtime import local_cached_cli  # type: ignore
    from validate_delivery import probe_delivery  # type: ignore


def _time(value: Any) -> Fraction:
    if isinstance(value, Fraction):
        return value
    if not isinstance(value, str):
        raise ValueError(f"invalid rational time: {value!r}")
    raw = value[:-1] if value.endswith("s") else value
    try:
        return Fraction(raw)
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError(f"invalid rational time: {value!r}") from error


def _text(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def _fftime(value: Fraction) -> str:
    """Render a rational time as an FFmpeg filter-compatible decimal."""
    with localcontext() as context:
        context.prec = 30
        rendered = format(Decimal(value.numerator) / Decimal(value.denominator), ".24f").rstrip("0").rstrip(".")
    return rendered or "0"


def _inside(root: Path, path: Path) -> Path:
    resolved = path.expanduser().resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(f"path must stay inside version root: {path}") from error
    return resolved


def _adapter(cue: dict[str, Any]) -> dict[str, Any]:
    adapter = cue.get("renderAdapters", {}).get("hyperframes")
    if not isinstance(adapter, dict):
        raise ValueError(f"cue {cue.get('id', '<unknown>')} lacks renderAdapters.hyperframes")
    required = ("compositionId", "compositionSrc", "motionSrc", "layoutDependencies")
    if any(not adapter.get(name) for name in required):
        raise ValueError(f"cue {cue.get('id', '<unknown>')} has incomplete HyperFrames adapter")
    return adapter


def _quality_dimensions(quality: str) -> tuple[int, int]:
    if quality == "preview":
        return (854, 480)
    if quality == "delivery":
        return (1920, 1080)
    raise ValueError("quality must be preview or delivery")


def _fps(manifest: dict[str, Any]) -> Fraction:
    try:
        frame_duration = _time(manifest["project"]["source"]["frameDuration"])
    except (KeyError, TypeError) as error:
        raise ValueError("project.source.frameDuration is required") from error
    if frame_duration <= 0:
        raise ValueError("project.source.frameDuration must be positive")
    return 1 / frame_duration


def build_render_command(root: Path, cue: dict[str, Any], *, quality: str, target: Path, composition: str | None = None) -> list[str]:
    """Build the exact-pinned HyperFrames render invocation for one cue."""
    root = root.expanduser().resolve()
    read_runtime_pin(root)  # validates every managed script, including render.
    adapter = _adapter(cue)
    _quality_dimensions(quality)
    # Rendering is rooted at the version directory so cue assets retain their
    # manifest-relative resolution.  The generated host is optional here to
    # keep this pure command builder useful to callers and tests.
    source = composition or str(adapter["compositionId"])
    command = [
        "npm", "run", "render", "--", "--composition", source,
        "--format", "mov", "--quality", "high", "--no-best-effort",
        "--output", str(_inside(root, target)),
    ]
    return command


def _run_logged(command: list[str], *, cwd: Path, log_path: Path) -> None:
    """Forward one renderer's output to disk without retaining it in memory."""
    if command[:3] == ["npm", "run", "render"]:
        runtime = read_runtime_pin(cwd)
        cached = local_cached_cli(runtime)
        if cached is not None:
            command = [*cached, "render", *command[4:]]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        environment = dict(os.environ, npm_config_offline="true", NPM_CONFIG_OFFLINE="true")
        start = handle.tell()
        process = subprocess.Popen(command, cwd=cwd, stdout=handle, stderr=subprocess.STDOUT, text=True, env=environment)
        returncode = process.wait()
    if returncode:
        raise subprocess.CalledProcessError(returncode, command)
    from scripts.work_model_capabilities import validate_render_resources
    with log_path.open(encoding='utf-8') as recorded:
        recorded.seek(start)
        validate_render_resources(recorded.read())


def _relative(root: Path, path: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _render_host_html(cue: dict[str, Any], *, width: int, height: int, fps: Fraction, native_width: int, native_height: int) -> str:
    adapter = _adapter(cue)
    duration = _fftime(_time(cue["resolvedTimeline"]["duration"]))
    scale_x = Decimal(width) / Decimal(native_width)
    scale_y = Decimal(height) / Decimal(native_height)
    composition_id = str(adapter["compositionId"])
    return (
        "<!doctype html><html><head><meta charset=\"UTF-8\">"
        f'<meta name="viewport" content="width={width}, height={height}">'
        '<script src="assets/vendor/gsap.min.js"></script><style>'
        f'*{{box-sizing:border-box}}html,body{{margin:0;width:{width}px;height:{height}px;overflow:hidden;background:transparent}}'
        f'#root{{position:relative;width:{width}px;height:{height}px;overflow:hidden;background:transparent}}'
        f'.cue-slot{{position:absolute;left:0;top:0;width:{native_width}px;height:{native_height}px;transform-origin:0 0;transform:scale({scale_x},{scale_y})}}'
        '</style></head><body>'
        f'<div id="root" data-composition-id="render-{composition_id}" data-width="{width}" data-height="{height}" data-duration="{duration}" data-fps="{_text(fps)}">'
        f'<div id="render-host-{composition_id}" class="clip cue-slot" data-composition-id="{composition_id}" data-composition-src="{adapter["compositionSrc"]}" '
        f'data-start="0" data-duration="{duration}" data-track-index="0" data-width="{native_width}" data-height="{native_height}"></div></div>'
        f'<script>window.__timelines=window.__timelines||{{}};window.__timelines["render-{composition_id}"]=gsap.timeline({{paused:true}});</script>'
        '</body></html>\n'
    )


def render_cue(root: Path, manifest: dict[str, Any], cue: dict[str, Any], *, quality: str, target: Path, log_path: Path) -> dict[str, Any]:
    """Render a transparent cue movie without imposing workflow-stage gates."""
    root = root.expanduser().resolve()
    target = _inside(root, target)
    log_path = _inside(root, log_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    adapter = _adapter(cue)
    for field in ("compositionSrc", "motionSrc"):
        candidate = _inside(root, root / str(adapter[field]))
        if not candidate.is_file() or candidate.is_symlink():
            raise ValueError(f"missing regular cue adapter file: {adapter[field]}")
    width, height = _quality_dimensions(quality)
    fps = _fps(manifest)
    native = manifest.get("project", {}).get("delivery", {})
    native_width = int(native.get("width", 1920))
    native_height = int(native.get("height", 1080))
    if native_width <= 0 or native_height <= 0:
        raise ValueError("project.delivery dimensions must be positive")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".afterforge-render-host-", suffix=".html", dir=root)
    host = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            from scripts.work_model_capabilities import guarded_host
            handle.write(guarded_host(_render_host_html(cue, width=width, height=height, fps=fps, native_width=native_width, native_height=native_height)))
        command = build_render_command(root, cue, quality=quality, target=target, composition=_relative(root, host))
        command += ["--fps", _text(fps)]
        _run_logged(command, cwd=root, log_path=log_path)
    finally:
        try:
            host.unlink()
        except FileNotFoundError:
            pass
    probe = probe_delivery(target)
    return {"cueId": cue.get("id"), "quality": quality, "path": _relative(root, target), "probe": probe}


def _has_audio(path: Path) -> bool:
    completed = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    streams = json.loads(completed.stdout).get("streams", [])
    return any(isinstance(item, dict) and item.get("codec_type") == "audio" for item in streams)


def build_composite_command(root: Path, manifest: dict[str, Any], overlays: list[dict[str, Any]], *, start: Fraction, duration: Fraction, target: Path, has_audio: bool) -> list[str]:
    """Build an FFmpeg command that trims global overlays into one preview range."""
    root = root.expanduser().resolve()
    if duration <= 0:
        raise ValueError("composite duration must be positive")
    media_src = manifest.get("project", {}).get("renderAdapters", {}).get("hyperframes", {}).get("previewMediaSrc")
    if not isinstance(media_src, str):
        raise ValueError("project.renderAdapters.hyperframes.previewMediaSrc is required")
    media = _inside(root, root / media_src)
    if not media.is_file() or media.is_symlink():
        raise ValueError(f"missing regular preview media: {media_src}")
    preview = manifest.get("project", {}).get("preview", {})
    width, height = int(preview.get("width", 854)), int(preview.get("height", 480))
    fps = _fps(manifest)
    command = ["ffmpeg", "-y", "-v", "error", "-i", str(media)]
    selected: list[tuple[dict[str, Any], Path, Fraction, Fraction]] = []
    end = start + duration
    for overlay in sorted(overlays, key=lambda item: (int(item["layer"]), str(item["cueId"]))):
        cue_start, cue_duration = _time(overlay["start"]), _time(overlay["duration"])
        active_start, active_end = max(start, cue_start), min(end, cue_start + cue_duration)
        if active_end <= active_start:
            continue
        raw = Path(str(overlay["path"])).expanduser()
        path = raw.resolve() if raw.is_absolute() else _inside(root, root / raw)
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"missing regular overlay movie: {overlay['path']}")
        selected.append((overlay, path, active_start, active_end))
        command += ["-i", str(path)]
    frame_count = duration * fps
    if frame_count.denominator != 1:
        raise ValueError("composite range must align to an exact source frame count")
    filters = [f"[0:v]trim=start={_fftime(start)}:duration={_fftime(duration)},setpts=PTS-STARTPTS,scale={width}:{height}[base]"]
    current = "base"
    for index, (overlay, _, active_start, active_end) in enumerate(selected, start=1):
        cue_start = _time(overlay["start"])
        local_start = active_start - cue_start
        local_duration = active_end - active_start
        offset = active_start - start
        label = f"ov{index}"
        out = f"layer{index}"
        filters.append(f"[{index}:v]trim=start={_fftime(local_start)}:duration={_fftime(local_duration)},setpts=PTS-STARTPTS+{_fftime(offset)}/TB[{label}]")
        filters.append(f"[{current}][{label}]overlay=0:0:eof_action=pass[{out}]")
        current = out
    if has_audio:
        filters.append(f"[0:a]atrim=start={_fftime(start)}:duration={_fftime(duration)},asetpts=PTS-STARTPTS[audio]")
    command += ["-filter_complex", ";".join(filters), "-map", f"[{current}]"]
    if has_audio:
        command += ["-map", "[audio]", "-c:a", "aac"]
    command += ["-r", _text(fps), "-frames:v", str(frame_count.numerator), "-c:v", "libx264", "-crf", "0", "-pix_fmt", "yuv420p", str(_inside(root, target))]
    return command


def composite_preview(root: Path, manifest: dict[str, Any], overlays: list[dict[str, Any]], *, start: Fraction, duration: Fraction, target: Path, log_path: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    target, log_path = _inside(root, target), _inside(root, log_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    media_src = manifest["project"]["renderAdapters"]["hyperframes"]["previewMediaSrc"]
    media = _inside(root, root / media_src)
    command = build_composite_command(root, manifest, overlays, start=start, duration=duration, target=target, has_audio=_has_audio(media))
    _run_logged(command, cwd=root, log_path=log_path)
    probe = probe_delivery(target)
    return {"path": _relative(root, target), "width": probe["width"], "height": probe["height"], "probe": probe}


def _rgba_at(path: Path, moment: Fraction, width: int, height: int, log_path: Path | None) -> bytes:
    command = ["ffmpeg", "-v", "error", "-ss", _fftime(moment), "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgba", "-"]
    completed = subprocess.run(command, capture_output=True)
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("ab") as handle:
            handle.write(completed.stderr)
    if completed.returncode or len(completed.stdout) != width * height * 4:
        raise ValueError(f"could not decode alpha sample at {_text(moment)}s")
    return completed.stdout


def validate_alpha(path: Path, cue: dict[str, Any], *, log_path: Path | None = None) -> dict[str, Any]:
    """Verify decoded alpha pixels, rather than trusting a nonempty MOV file."""
    path = path.expanduser().resolve()
    probe = probe_delivery(path)
    width, height = int(probe["width"]), int(probe["height"])
    expectation = cue.get("alphaExpectation") or {"mode": "transparent", "samples": []}
    mode = expectation.get("mode")
    if mode not in ("transparent", "opaque"):
        raise ValueError("alphaExpectation.mode must be transparent or opaque")
    samples = expectation.get("samples") or []
    duration = Fraction(str(probe.get("duration", "0")))
    if not samples:
        samples = [{"time": _text(duration * Fraction(part, 4)) + "s"} for part in (0, 1, 2, 3)]
    background_seen = content_seen = False
    opaque_only = True
    results: list[dict[str, Any]] = []
    for sample in samples:
        moment = _time(sample["time"])
        pixels = _rgba_at(path, moment, width, height, log_path)
        alpha = pixels[3::4]
        has_background = any(value <= 8 for value in alpha)
        has_content = any(value > 8 for value in alpha)
        background_seen |= has_background
        content_seen |= has_content
        opaque_only &= all(value >= 247 for value in alpha)
        for x, y in sample.get("transparentPoints", []):
            if not (0 <= x < width and 0 <= y < height) or alpha[y * width + x] > 8:
                raise ValueError(f"transparent alpha expectation failed at ({x}, {y})")
        for x, y in sample.get("opaquePoints", []):
            if not (0 <= x < width and 0 <= y < height) or alpha[y * width + x] < 247:
                raise ValueError(f"opaque alpha expectation failed at ({x}, {y})")
        results.append({"time": sample["time"], "hasTransparent": has_background, "hasVisible": has_content})
    if mode == "transparent" and (not background_seen or not content_seen):
        raise ValueError("transparent alpha output must contain both background and nontransparent content")
    if mode == "opaque" and not opaque_only:
        raise ValueError("opaque alpha output must contain only fully opaque pixels")
    return {"status": "valid", "mode": mode, "probe": probe, "samples": results}
