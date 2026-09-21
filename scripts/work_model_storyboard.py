"""Static storyboard snapshots for the schema-3 work model.

This module intentionally has no job, manifest, or approval mutations.  It
turns one canonical cue composition into PNG review frames; callers own task
registration and any first-confirmation policy.
"""
from __future__ import annotations

import hashlib
import copy
import html
import os
import re
import shutil
import subprocess
import tempfile
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path
from typing import Any

try:
    from scripts.fcpxml_timing import format_time
    from scripts.hyperframes_adapter import parse_time
    from scripts.hyperframes_runtime import read_runtime_pin
    from scripts.work_model_runtime import local_cached_cli
    from scripts.work_model_store import digest, safe, sha
except ModuleNotFoundError:  # pragma: no cover - direct script use
    from fcpxml_timing import format_time  # type: ignore
    from hyperframes_adapter import parse_time  # type: ignore
    from hyperframes_runtime import read_runtime_pin  # type: ignore
    from work_model_runtime import local_cached_cli  # type: ignore
    from work_model_store import digest, safe, sha  # type: ignore


_LOCAL_REFERENCE = re.compile(
    r'''(?:src|href|data-composition-src)\s*=\s*["']([^"']+)["']|url\(\s*["']?([^)'"\s]+)|(?:from\s+|import\s*\(|import\s*)["']([^"']+)["']'''
)
_SCRIPT_WITH_SRC = re.compile(r"<script\b[^>]*\bsrc\s*=\s*([\"'])(?P<src>[^\"']+)\1[^>]*>\s*</script\s*>", re.I)
_MODULE_IMPORT = re.compile(r"(?:import\s+(?:[^;]*?\s+from\s+)?|import\s*\()([\"'])(?P<src>[^\"']+)\1[^;]*;?", re.I)


def _inside(root: Path, path: Path) -> Path:
    root = root.expanduser().resolve()
    path = path.expanduser().resolve(strict=False)
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"path must stay inside version root: {path}") from error
    return path


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.expanduser().resolve()).as_posix()


def _decimal(value: Fraction) -> str:
    with localcontext() as context:
        context.prec = 30
        result = format(Decimal(value.numerator) / Decimal(value.denominator), ".24f").rstrip("0").rstrip(".")
    return result or "0"


def _animation_cues(manifest: dict[str, Any], request: dict[str, Any]) -> list[dict[str, Any]]:
    requested = request.get("cueIds")
    if requested is not None and (not isinstance(requested, list) or not all(isinstance(item, str) for item in requested)):
        raise ValueError("cueIds must be an array of cue IDs")
    wanted = set(requested or ())
    if requested is not None and len(wanted) != len(requested):
        raise ValueError("cueIds must not repeat")
    cues = [cue for cue in manifest.get("cues", []) if cue.get("productionMode") == "animation"]
    known = {cue.get("id") for cue in cues}
    missing = wanted - known
    if missing:
        raise ValueError(f"unknown animation cue IDs: {', '.join(sorted(missing))}")
    return [cue for cue in cues if requested is None or cue.get("id") in wanted]


def _adapter(cue: dict[str, Any]) -> dict[str, Any]:
    adapter = cue.get("renderAdapters", {}).get("hyperframes")
    if not isinstance(adapter, dict) or not isinstance(adapter.get("compositionSrc"), str) or not adapter["compositionSrc"]:
        raise ValueError(f"cue {cue.get('id', '<unknown>')} lacks a HyperFrames compositionSrc")
    return adapter


def _frames(cue: dict[str, Any]) -> list[dict[str, Any]]:
    supplied = cue.get("storyboard", {}).get("frames")
    if supplied is None:
        supplied = [{"id": "hero", "role": "hero", "label": "Hero", "time": "0s", "mode": "layout", "background": "none"}]
    if not isinstance(supplied, list) or not supplied:
        raise ValueError(f"cue {cue.get('id')} storyboard.frames must be a nonempty array")
    result: list[dict[str, Any]] = []
    ids: set[str] = set()
    hero_count = 0
    for item in supplied:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            raise ValueError(f"cue {cue.get('id')} storyboard frame needs a stable id")
        if item["id"] in ids:
            raise ValueError(f"cue {cue.get('id')} storyboard frame IDs must be unique")
        ids.add(item["id"])
        role = item.get("role", "auxiliary")
        mode = item.get("mode", "layout")
        background = item.get("background", "none")
        if role not in {"hero", "auxiliary"} or mode not in {"layout", "motion"} or background not in {"none", "timeline"}:
            raise ValueError(f"cue {cue.get('id')} has an invalid storyboard frame descriptor")
        time = parse_time(item.get("time", "0s"))
        if time < 0:
            raise ValueError("storyboard frame time must be nonnegative")
        still = item.get("stillSrc")
        if still is not None and (not isinstance(still, str) or not still):
            raise ValueError("storyboard stillSrc must be a nonempty relative path")
        hero_count += role == "hero"
        frame = {"id": item["id"], "role": role, "label": item.get("label", item["id"]),
                 "time": format_time(time), "mode": mode, "background": background}
        if not isinstance(frame["label"], str):
            raise ValueError("storyboard frame label must be a string")
        if still is not None:
            frame["stillSrc"] = still
        state = item.get("state")
        if state is not None and (not isinstance(state, dict) or set(state) != {"id"} or not isinstance(state["id"], str) or not state["id"]):
            raise ValueError("storyboard frame state must be an object with a nonempty id")
        if state is not None:
            frame["state"] = state
        result.append(frame)
    if hero_count != 1:
        raise ValueError(f"cue {cue.get('id')} storyboard needs exactly one hero frame")
    return result


def _local_dependencies(root: Path, cue: dict[str, Any], *, include_motion: bool) -> list[str]:
    """Static snapshots use only the declarative, sanitized layout closure."""
    from scripts.work_model_sources import inspect_sources, static_markup
    import copy
    adapter = _adapter(cue)
    if include_motion:
        analysis = inspect_sources(root, cue)
        if analysis['unseekableFiles']:
            raise ValueError('time-driven input requires an explicit fixed sample or seekable adapter')
        return analysis['files']
    markup = safe(root, adapter['compositionSrc']).read_text(encoding='utf-8')
    stripped = static_markup(root, cue, markup)
    layout = copy.deepcopy(cue)
    static_adapter = layout['renderAdapters']['hyperframes']
    static_adapter.pop('motionSrc', None)
    static_adapter['layoutDependencies'] = [p for p in adapter.get('layoutDependencies', [])
        if p not in {adapter.get('motionSrc'), 'assets/vendor/gsap.min.js'}]
    return inspect_sources(root, layout, {adapter['compositionSrc']: stripped.encode('utf-8')})['files']


def _dimensions(manifest: dict[str, Any]) -> tuple[int, int]:
    dimensions = manifest.get("project", {}).get("preview", {})
    width, height = int(dimensions.get("width", 854)), int(dimensions.get("height", 480))
    if width <= 0 or height <= 0:
        raise ValueError("project.preview dimensions must be positive")
    return width, height


def _native_dimensions(manifest: dict[str, Any]) -> tuple[int, int]:
    dimensions = manifest.get("project", {}).get("delivery", {})
    width, height = int(dimensions.get("width", 1920)), int(dimensions.get("height", 1080))
    if width <= 0 or height <= 0:
        raise ValueError("project.delivery dimensions must be positive")
    return width, height


def animation_notes(cue):
    """Validate references against the complete declared frame set, without I/O."""
    frames = {f['id'] for f in _frames(cue)}
    notes = cue.get('storyboard', {}).get('animationNotes', [])
    if not isinstance(notes, list):
        raise ValueError('animationNotes must be an array')
    ids = set()
    for note in notes:
        if (not isinstance(note, dict) or set(note) != {'id', 'frameIds', 'text'}
                or not isinstance(note['id'], str) or not note['id'].strip()
                or not isinstance(note['text'], str) or not note['text'].strip()):
            raise ValueError('animation note requires stable id, frameIds and nonempty text')
        refs = note['frameIds']
        if (note['id'] in ids or not isinstance(refs, list) or not refs
                or not all(isinstance(i, str) for i in refs)
                or len(set(refs)) != len(refs) or not set(refs).issubset(frames)):
            raise ValueError('animation note IDs must be unique and reference existing frames')
        ids.add(note['id'])
    return copy.deepcopy(notes)


def review_snapshot(manifest, cue, frames):
    from scripts.work_model_inputs import cue_narration
    from scripts.work_model_content import content_context
    review = {'narration': cue_narration(manifest, cue) or '',
              'contentContext': content_context(manifest, cue),
              'finalAnimationDescription': cue.get('finalAnimationDescription') or cue.get('finalDescription') or '',
              'animationNotes': animation_notes(cue)}
    review['reviewInputKey'] = digest({'cueId': cue['id'], 'objectId': cue.get('objectId'), **review,
        'frames': [{'frameId': f['frameId'], 'inputKey': f['inputKey']} for f in frames]})
    return review


def _descriptor(root: Path, manifest: dict[str, Any], cue: dict[str, Any], frame: dict[str, Any],
                *, contract=5, legacy_review=None) -> dict[str, Any]:
    from scripts.work_model_inputs import cue_narration
    from scripts.work_model_content import content_context
    adapter = _adapter(cue)
    include_motion = frame["mode"] == "motion"
    files = set(_local_dependencies(root, cue, include_motion=include_motion))
    for required in ("package.json", "hyperframes.json"):
        safe(root, required)
        files.add(required)
    for optional in (("frame.md", "assets/vendor/gsap.min.js") if include_motion else ("frame.md",)):
        if (root / optional).is_file():
            safe(root, optional)
            files.add(optional)
    if frame.get("stillSrc"):
        safe(root, frame["stillSrc"])
        files.add(frame["stillSrc"])
    background_src = None
    if frame["background"] == "timeline":
        source = manifest.get("project", {}).get("renderAdapters", {}).get("hyperframes", {}).get("previewMediaSrc")
        if not isinstance(source, str) or not source:
            raise ValueError("timeline storyboard background requires previewMediaSrc")
        safe(root, source)
        files.add(source)
        background_src = source
    elif frame.get("stillSrc"):
        background_src = frame["stillSrc"]
    timeline = cue.get("resolvedTimeline", {})
    if frame["background"] == "timeline" and not isinstance(timeline.get("start"), str):
        raise ValueError("timeline storyboard background requires cue resolvedTimeline.start")
    start = parse_time(timeline["start"]) if frame["background"] == "timeline" else Fraction(0)
    if start < 0:
        raise ValueError("cue timeline start must be nonnegative")
    duration = timeline.get("duration")
    if duration is not None and not isinstance(duration, str):
        raise ValueError("cue resolvedTimeline.duration must be a rational time")
    if duration is not None and parse_time(frame["time"]) > parse_time(duration):
        raise ValueError("storyboard frame time exceeds cue duration")
    snapshot = {
        "cueId": cue["id"], "frameId": frame["id"], "role": frame["role"], "label": frame["label"],
        "time": frame["time"], "mode": frame["mode"], "background": frame["background"],
        "duration": duration, "state": frame.get("state"),
        "backgroundTime": format_time(start + parse_time(frame["time"])), "backgroundSrc": background_src,
        "narration": cue_narration(manifest, cue),
        "contentContext": content_context(manifest, cue),
        "finalDescription": cue.get("finalAnimationDescription") or cue.get("finalDescription"),
    }
    if background_src:
        snapshot['backgroundSample'] = {'source': background_src, 'sourceSha256': sha(safe(root, background_src)),
            'time': snapshot['backgroundTime'] if frame['background'] == 'timeline' else '0s'}
    if frame.get("stillSrc"):
        snapshot["stillSrc"] = frame["stillSrc"]
    if frame.get('sample'):
        snapshot['sample'] = True
    pixel_state = dict(snapshot)
    review_fields = ('narration', 'contentContext', 'finalDescription')
    if contract == 5:
        for field in review_fields:
            pixel_state.pop(field)
    elif legacy_review is not None:
        # Contract 4 mixed review prose into the pixel key. Only replace those
        # known prose fields; every actual image dependency is still recomputed.
        pixel_state.update({field: legacy_review[field] for field in review_fields})
    key_input = {
        "storyboardContract": contract, "runtime": read_runtime_pin(root), "dimensions": _dimensions(manifest),
        "frameDuration": (manifest.get("project", {}).get("source") or {}).get("frameDuration"),
        "compositionId": adapter.get("compositionId"), "compositionSrc": adapter["compositionSrc"],
        "state": pixel_state, "screenText": cue.get("screenText", []),
        "files": {path: sha(safe(root, path)) for path in sorted(files)},
    }
    # Product-object association belongs to publication identity, not pixels.
    # Keeping it outside inputKey preserves media reuse but makes an in-flight
    # job notice an object replacement before registering its captured frame.
    return {**snapshot, 'storyboardContract': contract, "objectId": cue.get("objectId"), "files": sorted(files), "inputKey": digest(key_input)}


def storyboard_spec(root: Path, manifest: dict[str, Any], request: dict[str, Any] | None = None) -> dict[str, Any]:
    """Describe selected animation-cue storyboard PNGs without rendering them."""
    root = Path(root).expanduser().resolve()
    request = request or {}
    if not isinstance(request, dict):
        raise ValueError("storyboard request must be an object")
    cues = _animation_cues(manifest, request)
    if request.get('scope') == 'still' and 'time' in request:
        if len(cues) != 1:
            raise ValueError('explicit still time requires exactly one cue')
        cue = cues[0]
        local = parse_time(request['time']) - parse_time(cue.get('resolvedTimeline', {}).get('start', '0s'))
        duration = parse_time(cue.get('resolvedTimeline', {}).get('duration', '0s'))
        if local < 0 or local >= duration:
            raise ValueError('still time must lie inside the selected cue')
        definition = dict(next(f for f in _frames(cue) if f['role'] == 'hero'))
        definition.update(id='sample', time=format_time(local), sample=True,
            mode='motion' if _adapter(cue).get('motionSrc') else 'layout')
        frames = [_descriptor(root, manifest, cue, definition)]
    else:
        frames = [_descriptor(root, manifest, cue, frame) for cue in cues for frame in _frames(cue)]
    reviews = {cue['id']: review_snapshot(manifest, cue, [f for f in frames if f['cueId'] == cue['id']]) for cue in cues}
    return {"frames": frames, 'reviews': reviews, "files": sorted({path for frame in frames for path in frame["files"]})}


def _frame_definition(cue, descriptor):
    if descriptor.get('sample'):
        return {'id': descriptor['frameId'], **{key: descriptor[key] for key in
            ('role', 'label', 'time', 'mode', 'background', 'state', 'stillSrc', 'sample') if key in descriptor}}
    return next(frame for frame in _frames(cue) if frame['id'] == descriptor.get('frameId'))


def _strip_motion(root: Path, composition_path: Path, composition: str, motion_src: str | None) -> str:
    from scripts.work_model_sources import static_markup
    adapter = {'compositionSrc': _relative(root, composition_path)}
    if motion_src:
        adapter['motionSrc'] = motion_src
    return static_markup(root, {'renderAdapters': {'hyperframes': adapter}}, composition)


def _apply_static_state(composition: str, state: dict[str, str] | None) -> str:
    if state is None:
        return composition
    attribute = html.escape(state["id"], quote=True)
    return re.sub(r"(<[A-Za-z][^>]*\bdata-composition-id\s*=\s*[\"'][^\"']+[\"'])", rf'\1 data-storyboard-state="{attribute}"', composition, count=1)


def _host_html(composition_id: str, source: str, width: int, height: int, native_width: int, native_height: int,
               duration: Fraction, state: dict[str, str] | None, background_src: str | None = None, *, static: bool = False) -> str:
    scale_x, scale_y = Decimal(width) / Decimal(native_width), Decimal(height) / Decimal(native_height)
    state_attr = "" if state is None else f' data-storyboard-state="{html.escape(state["id"], quote=True)}"'
    backdrop = '' if background_src is None else f'<img src="{html.escape(background_src, quote=True)}" style="position:absolute;inset:0;width:{width}px;height:{height}px" alt="">'
    if static:
        return (f'<!doctype html><html><head><meta charset="UTF-8">'
            f'<style>*{{box-sizing:border-box}}html,body,#storyboard-root{{margin:0;width:{width}px;height:{height}px;overflow:hidden;background:transparent}}'
            f'.cue-slot{{position:absolute;left:0;top:0;width:{native_width}px;height:{native_height}px;transform-origin:0 0;transform:scale({scale_x},{scale_y})}}</style>'
            f'</head><body><div id="storyboard-root" data-composition-id="storyboard-{html.escape(composition_id, quote=True)}" '
            f'data-no-timeline data-duration="{_decimal(duration)}" data-width="{width}" data-height="{height}">{backdrop}'
            f'<div class="clip cue-slot" data-composition-id="{html.escape(composition_id, quote=True)}" data-composition-src="{html.escape(source, quote=True)}" '
            f'data-no-timeline data-start="0" data-duration="{_decimal(duration)}" data-width="{native_width}" data-height="{native_height}"{state_attr}></div>'
            f'</div></body></html>')
    return (
        "<!doctype html><html><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=%d,height=%d\">"
        "<script src=\"assets/vendor/gsap.min.js\"></script><style>*{box-sizing:border-box}html,body,#storyboard-root{margin:0;width:%dpx;height:%dpx;overflow:hidden;background:transparent}.cue-slot{position:absolute;left:0;top:0;width:%dpx;height:%dpx;transform-origin:0 0;transform:scale(%s,%s)}</style>"
        "</head><body><div id=\"storyboard-root\" data-composition-id=\"storyboard-%s\" data-width=\"%d\" data-height=\"%d\" data-duration=\"%s\"%s>" + backdrop +
        "<div class=\"clip cue-slot\" data-composition-id=\"%s\" data-composition-src=\"%s\" data-start=\"0\" data-duration=\"%s\" data-width=\"%d\" data-height=\"%d\"%s></div></div>"
        "<script>window.__timelines=window.__timelines||{};window.__timelines[\"storyboard-%s\"]=gsap.timeline({paused:true});</script></body></html>\n"
    ) % (width, height, width, height, native_width, native_height, format(scale_x, "f"), format(scale_y, "f"), composition_id, width, height, _decimal(duration), state_attr, composition_id, source, _decimal(duration), native_width, native_height, state_attr, composition_id)


def _run_command(command: list[str], *, cwd: Path, log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        environment = dict(os.environ, npm_config_offline="true", NPM_CONFIG_OFFLINE="true")
        start = log.tell()
        process = subprocess.Popen(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, text=True, env=environment)
        if process.wait():
            raise subprocess.CalledProcessError(process.returncode, command)
    from scripts.work_model_capabilities import validate_render_resources
    with log_path.open(encoding='utf-8') as recorded:
        recorded.seek(start)
        validate_render_resources(recorded.read())


def _first_png(directory: Path) -> Path:
    images = sorted(path for path in directory.rglob("*.png") if path.is_file() and not path.is_symlink())
    if not images:
        raise ValueError("HyperFrames snapshot did not produce a PNG")
    return images[0]


def _snapshot_command(runtime: str, time: str, destination: Path) -> list[str]:
    # The CLI accepts decimal seconds, not FCPXML rational-time strings.
    # Convert only at this process boundary; canonical facts stay rational.
    time = _decimal(parse_time(time))
    cached = local_cached_cli(runtime)
    if cached is not None:
        return [*cached, "snapshot", ".", "--at", time, "--frames", "1", "--no-end", "--describe", "false", "--output", str(destination)]
    return ["npm", "exec", "--offline", f"--package=hyperframes@{runtime}", "--", "hyperframes", "snapshot", ".",
            "--at", time, "--frames", "1", "--no-end", "--describe", "false", "--output", str(destination)]


def _render_one(root: Path, manifest: dict[str, Any], cue: dict[str, Any], frame: dict[str, Any], target: Path, log_path: Path) -> None:
    adapter = _adapter(cue)
    width, height = _dimensions(manifest)
    native_width, native_height = _native_dimensions(manifest)
    runtime = read_runtime_pin(root)
    with tempfile.TemporaryDirectory(prefix=".afterforge-storyboard-", dir=root) as staging_name:
        staging = Path(staging_name)
        source = adapter["compositionSrc"]
        for relative in frame["files"]:
            origin = safe(root, relative)
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin, destination)
        if frame["mode"] == "layout":
            original = staging / source
            stripped = _strip_motion(root, safe(root, source), original.read_text(encoding="utf-8"), adapter.get("motionSrc"))
            stripped = re.sub(r'(<[A-Za-z][^>]*\bdata-composition-id\s*=\s*["\'][^"\']+["\'])', r'\1 data-no-timeline', stripped)
            original.write_text(_apply_static_state(stripped, frame.get("state")), encoding="utf-8")
        elif frame.get("state"):
            original = staging / source
            original.write_text(_apply_static_state(original.read_text(encoding="utf-8"), frame["state"]), encoding="utf-8")
        host = staging / "index.html"
        duration = parse_time(frame["duration"]) if frame.get("duration") else max(parse_time(frame["time"]) + 1, Fraction(1))
        background = frame.get('backgroundSrc')
        backdrop_src = None
        if background:
            backdrop_src = 'assets/storyboard-background.png'
            backdrop = staging / backdrop_src
            backdrop.parent.mkdir(parents=True, exist_ok=True)
            seek = ['-ss', _decimal(parse_time(frame['backgroundTime']))] if frame['background'] == 'timeline' else []
            _run_command(['ffmpeg', '-y', '-v', 'error', *seek, '-i', str(safe(root, background)),
                '-vf', f'scale={width}:{height}', '-frames:v', '1', str(backdrop)], cwd=root, log_path=log_path)
        from scripts.work_model_capabilities import guarded_host
        host.write_text(guarded_host(_host_html(str(adapter.get("compositionId", cue["id"])), source, width, height,
                                   native_width, native_height, duration, frame.get("state"), backdrop_src, static=frame["mode"] == "layout")), encoding="utf-8")
        rendered = staging / "rendered"
        _run_command(_snapshot_command(runtime, frame["time"], rendered), cwd=staging, log_path=log_path)
        image = _first_png(rendered)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(image, target)


def render_storyboard(root: Path, manifest: dict[str, Any], spec: dict[str, Any], output_dir: Path, log_path: Path) -> list[dict[str, Any]]:
    """Render an already-captured storyboard spec to one PNG per descriptor."""
    root = Path(root).expanduser().resolve()
    output_dir = _inside(root, Path(output_dir))
    log_path = _inside(root, Path(log_path))
    cues = {cue.get("id"): cue for cue in manifest.get("cues", [])}
    result = []
    for descriptor in spec.get("frames", []):
        cue = cues.get(descriptor.get("cueId"))
        if not isinstance(cue, dict):
            raise ValueError("storyboard descriptor references an unknown cue")
        current = _descriptor(root, manifest, cue, _frame_definition(cue, descriptor))
        if current["inputKey"] != descriptor.get("inputKey"):
            raise ValueError("storyboard inputs changed; capture a new spec before rendering")
        target = output_dir / f"{cue['id']}-{current['frameId']}-{current['inputKey'][:16]}.png"
        cached = reusable_frame(root, manifest, current)
        if cached:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(safe(root, cached['path']), target)
            if sha(target) != cached['sha256']:
                raise ValueError('cached PNG changed while copying verified bytes')
        else:
            _render_one(root, manifest, cue, current, target, log_path)
        result.append({**current, "path": _relative(root, target), "sha256": sha(target)})
    return result


def frame_current(root: Path, manifest: dict[str, Any], frame: dict[str, Any]) -> bool:
    """Return whether a rendered storyboard frame still has its exact inputs and bytes."""
    try:
        root = Path(root).expanduser().resolve()
        cue = next(cue for cue in manifest.get("cues", []) if cue.get("id") == frame.get("cueId"))
        contract = frame.get('storyboardContract', 4)
        if contract not in (4, 5):
            return False
        descriptor = _descriptor(root, manifest, cue, _frame_definition(cue, frame), contract=contract)
        return (descriptor['objectId'] == frame.get('objectId') and descriptor["inputKey"] == frame.get("inputKey")
                and sha(safe(root, frame.get("path"))) == frame.get("sha256"))
    except (KeyError, StopIteration, TypeError, ValueError, OSError):
        return False


def reusable_frame(root, manifest, descriptor):
    """Return evidence for identical PNG inputs/bytes, never just a cache name."""
    cue = next(c for c in manifest['cues'] if c['id'] == descriptor['cueId'])
    for old in reversed(manifest.get('artifacts', [])):
        if (old.get('cueId') != descriptor['cueId'] or old.get('frameId') != descriptor['frameId']
                or old.get('objectId') != descriptor.get('objectId')
                or old.get('purpose') not in {'storyboard', 'still', 'exploration'}):
            continue
        try:
            contract = old.get('storyboardContract', 4)
            if contract == 5:
                key = descriptor['inputKey']
            elif contract == 4:
                key = _descriptor(root, manifest, cue, _frame_definition(cue, descriptor),
                                  contract=4, legacy_review=old)['inputKey']
            else:
                continue
            if key == old.get('inputKey') and sha(safe(root, old['path'])) == old.get('sha256'):
                return old
        except (KeyError, OSError, ValueError, TypeError, StopIteration):
            continue
    return None
