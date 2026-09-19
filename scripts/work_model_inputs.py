"""Content identities deliberately exclude prose, approval state and job progress."""
from __future__ import annotations

import re
from fractions import Fraction
from pathlib import Path
from urllib.parse import unquote, urlsplit

from scripts.fcpxml_timing import format_time
from scripts.hyperframes_adapter import parse_time
from scripts.hyperframes_runtime import read_runtime_pin
from scripts.work_model_store import digest, safe, sha


def animation_cues(manifest):
    return [cue for cue in manifest["cues"] if cue["productionMode"] == "animation"]


def cue_narration(manifest, cue):
    """Resolve explicit canonical text associations, never infer them by time."""
    for key in ('narration', 'narrationAnchor'):
        value = cue.get(key)
        if isinstance(value, str) and value.strip():
            return value
    segments = {s['id']: s for s in manifest.get('brief', {}).get('segments', [])}
    values = []
    for sid in cue.get('segmentIds', []):
        segment = segments.get(sid, {})
        value = segment.get('narration') or segment.get('text')
        if isinstance(value, str) and value.strip():
            values.append(value)
    return '\n'.join(values)


def source_paths(root, manifest):
    source = manifest["project"].get("source")
    adapter = manifest["project"].get("renderAdapters", {}).get("hyperframes", {})
    if not source or not source.get("fcpxml") or not adapter.get("previewMediaSrc"):
        raise ValueError("缺少粗剪输入：FCPXML 与对应参考视频")
    xml = safe(root, source["fcpxml"])
    media = safe(root, adapter["previewMediaSrc"])
    if sha(xml) != manifest.get("sourceHashes", {}).get("fcpxml"):
        raise ValueError("source FCPXML differs from bound input")
    if sha(media) != manifest.get("sourceHashes", {}).get("referenceVideo"):
        raise ValueError("source reference video differs from bound input")
    frame = parse_time(source["frameDuration"])
    duration = parse_time(source["duration"])
    if frame <= 0 or duration <= 0 or (duration / frame).denominator != 1:
        raise ValueError("invalid source duration or time base")
    brief = manifest.get("brief", {})
    input_record = manifest.get("provenance", {}).get("input", {})
    narration = (brief.get("narration") or any(s.get("narration") or s.get("text") for s in brief.get("segments", []))
                 or any(c.get("narrationAnchor") for c in manifest["cues"])
                 or input_record.get("narrationSources")
                 or any(t.get("classification") == "narration_subtitle" for t in input_record.get("timelineText", [])))
    from scripts.work_model_content import content_context, validate_content_declarations
    animations = animation_cues(manifest)
    explicit_silence = bool(animations) and all(
        content_context(manifest, cue)['narration']['state'] == 'none'
        and not validate_content_declarations(manifest, cue) for cue in animations)
    if not narration and animations and not explicit_silence:
        raise ValueError("缺少旁白依据：请先整理已有字幕、转写或语义锚点")
    return xml, media


def dependencies(root, cue, *, require_motion=True):
    """One closure for publication checks, cache identity and render snapshots."""
    from scripts.work_model_sources import inspect_sources
    adapter = cue.get("renderAdapters", {}).get("hyperframes", {})
    for key in (("compositionSrc", "motionSrc") if require_motion else ("compositionSrc",)):
        if not isinstance(adapter.get(key), str):
            raise ValueError(f"missing {key}: {cue['id']}")
        safe(root, adapter[key])
    analysis = inspect_sources(root, cue)
    if require_motion and analysis['unseekableFiles']:
        raise ValueError('time-driven input requires an explicit fixed sample or seekable adapter: ' + ', '.join(analysis['unseekableFiles']))
    paths = analysis['files']
    return [p for p in paths if require_motion or p != adapter.get('motionSrc')]


def dependency_closure(root, paths, *, overrides=None, excluded=()):
    """Resolve declared inputs including staged bytes, without publishing them."""
    overrides = overrides or {}
    excluded = set(excluded)
    pending = list(paths)
    checked = set()
    patterns = [r'''(?:src|href|data-composition-src)\s*=\s*["']([^"']+)["']''',
                r'''url\(\s*["']?([^)'"\s]+)''',
                r'''(?:from\s+|import\s*\(|import\s*)["']([^"']+)["']''']
    while pending:
        relative = pending.pop()
        if relative in checked or relative in excluded:
            continue
        path = safe(root, relative, exists=relative not in overrides)
        checked.add(relative)
        if path.suffix.lower() not in {".html", ".css", ".js", ".mjs"}:
            continue
        text = overrides[relative].decode('utf-8') if relative in overrides else path.read_text()
        for pattern in patterns:
            for reference in re.findall(pattern, text):
                if reference.startswith(("#", "data:", "blob:")):
                    continue
                parsed = urlsplit(reference)
                if parsed.scheme or parsed.netloc:
                    raise ValueError(f"render dependency must be local: {reference}")
                candidate = unquote(parsed.path)
                if not candidate:
                    continue
                # HyperFrames resolves subcomposition assets from the project root.
                root_candidate = Path(root) / candidate
                local_candidate = path.parent / candidate
                selected = root_candidate if candidate in overrides or candidate in excluded or root_candidate.exists() else local_candidate
                try:
                    resolved = selected.resolve().relative_to(Path(root).resolve()).as_posix()
                except ValueError as error:
                    raise ValueError("render dependency escapes version") from error
                if resolved in excluded:
                    continue
                safe(root, resolved, exists=resolved not in overrides)
                if resolved not in checked:
                    pending.append(resolved)
    return sorted(checked)


def cue_inputs(root, manifest, cue, quality="preview"):
    root = Path(root)
    timeline = cue.get("resolvedTimeline", {})
    duration = parse_time(timeline.get("duration", "0s"))
    frame = parse_time(manifest["project"]["source"]["frameDuration"])
    if duration <= 0 or (duration / frame).denominator != 1:
        raise ValueError(f"cue duration must contain whole source frames: {cue['id']}")
    files = set(dependencies(root, cue))
    files.update({"package.json", "hyperframes.json"})
    if (root / "assets/vendor/gsap.min.js").is_file():
        files.add("assets/vendor/gsap.min.js")
    if (root / "frame.md").is_file():
        files.add("frame.md")
    return {
        "renderContract": 1,
        "runtime": read_runtime_pin(root), "quality": quality,
        "dimensions": manifest["project"]["preview" if quality == "preview" else "delivery"],
        "nativeDimensions": manifest["project"]["delivery"],
        "frameDuration": format_time(frame), "duration": format_time(duration),
        "screenText": cue.get("screenText", []),
        "compositionId": cue["renderAdapters"]["hyperframes"]["compositionId"],
        "compositionSrc": cue["renderAdapters"]["hyperframes"]["compositionSrc"],
        "alphaExpectation": cue.get("alphaExpectation", {"mode": "transparent"}),
        "files": {name: sha(safe(root, name)) for name in sorted(files)},
    }


def cue_key(root, manifest, cue, quality="preview"):
    return digest(cue_inputs(root, manifest, cue, quality))


def timeline_inputs(root, manifest, *, start=None, duration=None, allow_draft=False, excluded_cue_ids=(), required_cue_ids=None):
    xml, media = source_paths(root, manifest)
    source = manifest["project"]["source"]
    frame = parse_time(source["frameDuration"])
    total = parse_time(source["duration"])
    start = Fraction(0) if start is None else Fraction(start)
    duration = total if duration is None else Fraction(duration)
    if start < 0 or duration <= 0 or start + duration > total:
        raise ValueError("preview range is outside source timeline")
    if (start / frame).denominator != 1 or (duration / frame).denominator != 1:
        raise ValueError("preview range must align to source frames")
    records = []
    missing = []
    excluded = set(excluded_cue_ids)
    if not excluded.issubset({c['id'] for c in animation_cues(manifest)}):
        raise ValueError('unknown excluded cue')
    required = {c['id'] for c in animation_cues(manifest)} if required_cue_ids is None else set(required_cue_ids)
    ids = set()
    for number, cue in enumerate(manifest["cues"]):
        if cue["id"] in ids:
            raise ValueError("duplicate cue id")
        ids.add(cue["id"])
        if cue["productionMode"] != "animation" or cue["id"] in excluded:
            continue
        placement = cue.get("resolvedTimeline")
        if not placement:
            if allow_draft or cue["id"] not in required:
                missing.append(cue["id"])
                continue
            raise ValueError(f"cue has no resolved timeline: {cue['id']}")
        cue_start = parse_time(placement["start"])
        cue_duration = parse_time(placement["duration"])
        if cue_start < 0 or cue_duration <= 0 or cue_start + cue_duration > total or (cue_start / frame).denominator != 1:
            raise ValueError(f"cue outside source or not frame-aligned: {cue['id']}")
        if cue_start >= start + duration or cue_start + cue_duration <= start:
            continue
        try:
            if cue.get("status", "ready") != "ready":
                raise ValueError(f"unfinished cue: {cue['id']}")
            key = cue_key(root, manifest, cue)
        except (ValueError, OSError):
            if not allow_draft and cue['id'] in required:
                raise
            missing.append(cue["id"])
            continue
        records.append({"cueId": cue["id"], "renderKey": key, "start": format_time(cue_start),
                        "duration": format_time(cue_duration), "layer": cue.get("layer", number + 1)})
    result = {"version": 2, "sourceXml": sha(xml), "referenceVideo": sha(media),
            "dimensions": manifest["project"]["preview"], "frameDuration": format_time(frame),
            "range": {"start": format_time(start), "duration": format_time(duration)},
            "overlays": records, "missingCueIds": missing}
    if excluded:
        result['excludedCueIds'] = sorted(excluded)
    return result


def timeline_key(root, manifest, **kwargs):
    return digest(timeline_inputs(root, manifest, **kwargs))


def preview_range(manifest, request):
    source = manifest["project"].get("source")
    if not source:
        raise ValueError("缺少粗剪输入")
    frame = parse_time(source["frameDuration"])
    total = parse_time(source["duration"])
    if request.get("scope", "local") == "full":
        if 'range' in request and (parse_time(request['range']['start']) != 0 or parse_time(request['range']['duration']) != total):
            raise ValueError('full preview cannot silently ignore a limited range; use local scope')
        return Fraction(0), total
    if "range" in request:
        start = parse_time(request["range"]["start"])
        return start, parse_time(request["range"]["duration"])
    selected_cues = set(request.get("cueIds", []))
    selected_segments = set(request.get("segmentIds", []))
    ranges = []
    for cue in manifest["cues"]:
        if cue["id"] in selected_cues:
            selected_segments.update(cue.get("segmentIds", []))
            if cue.get("resolvedTimeline"):
                t = cue["resolvedTimeline"]
                ranges.append((parse_time(t["start"]), parse_time(t["start"]) + parse_time(t["duration"])))
    for segment in manifest["brief"]["segments"]:
        if segment["id"] in selected_segments and "timeStart" in segment and "timeEnd" in segment:
            ranges.append((parse_time(segment["timeStart"]), parse_time(segment["timeEnd"])))
    if not ranges:
        raise ValueError("local preview requires a segment, cue or explicit range")
    start = max(Fraction(0), min(a for a, _ in ranges) - 2)
    end = min(total, max(b for _, b in ranges) + 2)
    start = (start // frame) * frame
    end = min(total, -(-end // frame) * frame)
    return start, end - start
