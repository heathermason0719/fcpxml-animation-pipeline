#!/usr/bin/env python3
"""Opt-in, isolated real-render regression for the schema-3 work model.

Run manually with ``python tests/work_model_real_smoke.py --run``.  It creates
only synthetic material below the platform temporary directory and keeps the
resulting fixture for inspection; it is intentionally not discovered by
unittest.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import work_model as model
from scripts import work_model_jobs as jobs
from scripts.work_model_inputs import cue_key
from tests.work_model_fixtures import demo_request
from scripts.work_model_store import load


ROOT = Path(tempfile.gettempdir()) / "work-model-real-smoke"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hashes(directory: Path) -> dict[str, str]:
    return {
        path.relative_to(directory).as_posix(): sha(path)
        for path in sorted(directory.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def write_fixture_inputs(inbox: Path) -> None:
    inbox.mkdir(parents=True)
    run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=24:d=58",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:d=60",
        "-filter_complex", "[0:v]tpad=stop_mode=clone:stop_duration=2,trim=duration=60,fade=t=out:st=58:d=2[v]",
        "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
        str(inbox / "rough-preview.mp4"),
    ])
    (inbox / "source.fcpxml").write_text(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?><!DOCTYPE fcpxml>"
        "<fcpxml version=\"1.10\"><resources><format id=\"r1\" name=\"FFVideoFormat1080p24\" "
        "frameDuration=\"1/24s\" width=\"1920\" height=\"1080\"/></resources><library><event name=\"Synthetic\">"
        "<project name=\"Minute smoke\"><sequence duration=\"60s\" format=\"r1\"><spine>"
        "<gap name=\"base\" offset=\"0s\" start=\"0s\" duration=\"60s\"/></spine></sequence></project>"
        "</event></library></fcpxml>\n",
        encoding="utf-8",
    )
    (inbox / "narration.srt").write_text(
        "1\n00:00:00,000 --> 00:00:05,000\nSynthetic minute smoke narration.\n",
        encoding="utf-8",
    )


def composition(cue_id: str, color: str, left: int, *, include_motion: bool = False) -> str:
    motion_tag = f'<script src="compositions/motion/{cue_id}.js"></script>' if include_motion else ''
    return f'''<!doctype html><html><head><style>
html,body{{margin:0;width:1920px;height:1080px;overflow:hidden;background:transparent}}
@font-face{{font-family:SmokeChinese;src:url("assets/fonts/title.woff2") format("woff2")}}
[data-composition-id="{cue_id}"]{{position:relative;width:1920px;height:1080px}}
#title{{position:absolute;left:{left}px;top:432px;width:760px;height:180px;border-radius:36px;background:{color};color:white;font:700 82px SmokeChinese,sans-serif;line-height:180px;text-align:center}}
</style></head><body><div data-composition-id="{cue_id}" data-width="1920" data-height="1080" data-duration="3" data-fps="24">
<div id="title" class="clip" data-start="0" data-duration="3" data-track-index="1">中文标题 · {cue_id}</div></div>
{motion_tag}</body></html>\n'''


def motion(cue_id: str, seconds: int) -> str:
    return f'''window.__timelines=window.__timelines||{{}};
const tl=gsap.timeline({{paused:true}});tl.fromTo("#title",{{x:-120}},{{x:120,duration:{seconds}}},0);window.__timelines["{cue_id}"]=tl;\n'''


def stage(root: Path, contents: dict[str, str], binary: dict[str, Path]) -> list[dict[str, str]]:
    directory = root / ".staging" / "minute-smoke"
    directory.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, str]] = []
    for relative, text in contents.items():
        source = directory / relative.replace("/", "_")
        source.write_text(text, encoding="utf-8")
        files.append({"path": relative, "source": str(source)})
    for relative, origin in binary.items():
        source = directory / relative.replace("/", "_")
        shutil.copy2(origin, source)
        files.append({"path": relative, "source": str(source)})
    return files


def request(root: Path, request_id: str, **extra: object) -> dict[str, object]:
    return {"requestId": request_id, "expectedRevision": model.status(root)["editRevision"], **extra}


def cache_hashes(root: Path, quality: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for record in (root / "cache" / "cues" / quality).glob("*/media.json"):
        payload = json.loads(record.read_text(encoding="utf-8"))
        result[payload["inputKey"]] = payload["sha256"]
    return result


def cached_hash(root: Path, quality: str, key: str) -> str:
    return json.loads((root / "cache" / "cues" / quality / key / "media.json").read_text(encoding="utf-8"))["sha256"]


def dimensions(path: Path) -> tuple[int, int]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "json", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    stream = json.loads(result.stdout)["streams"][0]
    return int(stream["width"]), int(stream["height"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the isolated schema-3 real rendering smoke fixture.")
    parser.add_argument("--run", action="store_true", help="required acknowledgement that real cached Chromium rendering will run")
    parser.add_argument("--cold-only", action="store_true", help="retain the true cold-start snapshot after feedback handoff, before confirmation or Motion")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--runtime", default="0.8.33", help="exact locally cached HyperFrames version; never installs")
    parser.add_argument("--gsap-source", type=Path,
                        help="optional regular local GSAP file to stage for an offline runtime that does not bundle GSAP")
    parser.add_argument("--font-source", type=Path,
                        help="required regular local Chinese-capable WOFF2 font staged into the isolated fixture")
    args = parser.parse_args()
    if not args.run:
        parser.error("pass --run to create and render the synthetic fixture")
    root_base = args.root.resolve()
    if root_base.exists():
        raise SystemExit(f"refusing to overwrite retained smoke fixture: {root_base}")
    if args.font_source is None:
        parser.error("--font-source is required so the Chinese storyboard check never relies on a personal default font path")
    font = args.font_source.expanduser().resolve()
    if not font.is_file() or font.is_symlink():
        parser.error("--font-source must name a regular local font file")
    afterforge = root_base / "AfterForge"
    inbox = root_base / "user-inbox" / "2026-09-09_V1"
    write_fixture_inputs(inbox)
    source_hashes = tree_hashes(inbox)
    opened = model.open_project(afterforge, {"requestId": "open", "expectedRevision": 0, "title": "Synthetic", "episodeTitle": "Minute", "inputDirectory": str(inbox)})
    version = Path(opened["root"])
    runtime_request = request(version, "runtime", operation="runtime", version=args.runtime)
    if args.gsap_source is not None:
        source = args.gsap_source.expanduser()
        if not source.is_file() or source.is_symlink():
            parser.error("--gsap-source must name a regular local file")
        vendor = source.resolve()
        runtime_request["vendorSource"] = stage(version, {}, {"runtime/gsap.min.js": vendor})[0]["source"]
    cue_specs = [("opening", "#ff304f", 180, "2s", "2s", 2), ("middle", "#38d9a9", 520, "28s", "2s", 2), ("overlap", "#4c6fff", 880, "29s", "3s", 3), ("fade_end", "#ffd166", 420, "56s", "1s", 1)]
    cues = [{"id": name, "productionMode": "animation", "status": "ready", "resolvedTimeline": {"start": start, "duration": duration}, "layer": layer,
             "narrationAnchor": f"旁白对应中文标题 {name}", "screenText": [{"text": f"中文标题 · {name}"}],
             "finalAnimationDescription": f"Synthetic {name} title", "renderAdapters": {"hyperframes": {"compositionId": name, "compositionSrc": f"compositions/cues/{name}.html", "layoutDependencies": ["assets/fonts/title.woff2"]}}, "alphaExpectation": {"mode": "transparent"}}
            for name, _, _, start, duration, layer in cue_specs]
    next(cue for cue in cues if cue["id"] == "opening")["storyboard"] = {"frames": [
        {"id": "hero", "role": "hero", "label": "中文主审帧", "time": "0s", "mode": "layout", "background": "none", "state": {"id": "opening-hero"}},
        {"id": "context", "role": "auxiliary", "label": "原片语境帧", "time": "1/2s", "mode": "layout", "background": "timeline", "state": {"id": "opening-context"}},
    ]}
    source_files: dict[str, str] = {}
    for name, color, left, _, duration, _ in cue_specs:
        source_files[f"compositions/cues/{name}.html"] = composition(name, color, left)
    files = stage(version, source_files, {"assets/fonts/title.woff2": font})
    model.update(version, request(version, "seed", operation="edit", patch={"brief": {"summary": "synthetic minute", "segments": []}, "cues": cues}, files=files))
    # Exercise the formerly deadlocked order: create static Cue sources first.
    runtime_request['expectedRevision'] = load(version)['editRevision']
    model.update(version, runtime_request)
    if load(version)['decisions']:
        raise RuntimeError('runtime bootstrap created creative authority')
    # Existing technical files cannot authorize an initial full Motion demo.
    try:
        model.preview(version, request(version, "full-before-confirm", scope="full", cueIds=[c['id'] for c in cues], workCueIds=[c['id'] for c in cues], taskId="demo-before-confirm"))
    except ValueError:
        pass
    else:
        raise RuntimeError("cold-start full demo unexpectedly ran")
    # Observe the real renderer boundary; these spies delegate to the actual
    # functions if invoked, and never substitute synthetic render results.
    with patch.object(jobs, 'render_cue', wraps=jobs.render_cue) as cue_renderer, patch.object(jobs, 'composite_preview', wraps=jobs.composite_preview) as composite_renderer:
        board = model.preview(version, request(version, "cold-layout", scope="storyboard", cueIds=[c['id'] for c in cues]))
        static_calls = {'cueVideoRenderCalls': cue_renderer.call_count, 'compositeVideoCalls': composite_renderer.call_count}
    if any(static_calls.values()):
        raise RuntimeError('static Storyboard called a video renderer')
    state = load(version)
    # Feedback is independent from first design confirmation.
    opening_board = next(item for item in state['storyboards'] if item['cueId'] == 'opening')
    opening_frames = [item for item in state['artifacts'] if item['id'] in opening_board['artifactIds']]
    if {item['frameId'] for item in opening_frames} != {'hero', 'context'}:
        raise RuntimeError("opening storyboard did not retain distinct hero and context frames")
    by_frame = {item['frameId']: item for item in opening_frames}
    for frame in opening_frames:
        image = version / frame['path']
        if dimensions(image) != (854, 480) or image.stat().st_size < 4096:
            raise RuntimeError("Chinese storyboard snapshot is not a readable 854x480 PNG")
    if by_frame['hero'].get('background') != 'none' or by_frame['context'].get('background') != 'timeline' or by_frame['context'].get('backgroundTime') != '5/2s':
        raise RuntimeError("storyboard hero/context background or exact host time is wrong")
    opening_frame = by_frame['hero']
    feedback = model.update(version, request(version, "static-feedback", operation="feedback", body="Keep the cold-start layout readable",
        target={"versionId": load(version)['identity']['versionId'], "storyboardId": opening_board['id'], "artifactId": opening_frame['id'], "frameId": opening_frame['frameId'], "cueIds": ['opening']},
        source={"channel":"chat", "text":"static note", "reference":"fixture"}))["record"]
    model.update(version, request(version, "review-handoff", operation="review-submit", storyboardIds=board['storyboardIds'], feedbackIds=[feedback['id']], drafts=[],
        source={"channel":"chat", "text":"submit static review", "reference":"fixture"}))
    if load(version)['decisions']:
        raise RuntimeError("review handoff unexpectedly confirmed a design")
    cold_state = load(version)
    if any(c['renderAdapters']['hyperframes'].get('motionSrc') for c in cold_state['cues']) or list((version / 'compositions/motion').glob('*')):
        raise RuntimeError('cold-start fixture unexpectedly contains Motion implementation')
    (root_base / 'cold-start-manifest.json').write_text(json.dumps(cold_state, ensure_ascii=False, indent=2) + '\n')
    cold_evidence = {'version': str(version), 'noMotionImplementation': True, **static_calls,
        'firstConfirmationsAfterHandoff': 0, 'storyboardIds': board['storyboardIds'],
        'roundId': cold_state['reviewRounds'][-1]['id'], 'sourceUnchanged': tree_hashes(inbox) == source_hashes}
    (root_base / 'cold-start-evidence.json').write_text(json.dumps(cold_evidence, ensure_ascii=False, indent=2) + '\n')
    if args.cold_only:
        print(json.dumps(cold_evidence, ensure_ascii=False, indent=2))
        return 0
    try:
        model.update(version, request(version, "confirm-static-rejected", operation="decision", kind="confirm-design", storyboardIds=board['storyboardIds'],
            source={"channel":"chat", "text":"confirm static direction", "reference":"fixture"}))
    except ValueError:
        pass
    else:
        raise RuntimeError("pending handoff feedback unexpectedly allowed design confirmation")
    model.update(version, request(version, "confirm-static", operation="decision", kind="confirm-design", storyboardIds=board['storyboardIds'],
        feedbackResolutions=[{"feedbackId": feedback['id'], "action": "withdraw"}],
        source={"channel":"chat", "text":"这条意见不适用于本轮，撤回后确认静帧方向", "reference":"fixture"}))
    # Publish active motion only through a controlled update after confirmation.
    active = load(version)['cues']
    active_files = {}
    for name, color, left, _, duration, _ in cue_specs:
        active_files[f"compositions/cues/{name}.html"] = composition(name, color, left, include_motion=True)
        active_files[f"compositions/motion/{name}.js"] = motion(name, int(duration[:-1]))
        next(item for item in active if item['id'] == name)['renderAdapters']['hyperframes']['motionSrc'] = f"compositions/motion/{name}.js"
    model.update(version, request(version, "publish-active-motion", operation="edit", patch={"cues": active, "brief": load(version)['brief']},
        files=stage(version, active_files, {}), work={"mode":"motion", "cueIds":[c['id'] for c in active], "taskId":"active-motion"}))
    model.preview(version, demo_request(version, "full-initial", cueIds=[c['id'] for c in active], workCueIds=[c['id'] for c in active], excludedCueIds=[]))
    before = cache_hashes(version, "preview")
    initial = load(version)
    opening_before = cue_key(version, initial, next(item for item in initial["cues"] if item["id"] == "opening"), "preview")
    opening_movie_before = cached_hash(version, "preview", opening_before)
    moved = initial["cues"]
    next(item for item in moved if item["id"] == "opening")["resolvedTimeline"]["start"] = "3s"
    model.update(version, request(version, "move-title", operation="edit", patch={"cues": moved, "brief": load(version)["brief"]}))
    model.preview(version, request(version, "local-after-move", scope="local", cueIds=["opening"]))
    after_move = load(version)
    opening_after = cue_key(version, after_move, next(item for item in after_move["cues"] if item["id"] == "opening"), "preview")
    if opening_after != opening_before or cached_hash(version, "preview", opening_after) != opening_movie_before:
        raise RuntimeError("placement-only change rebuilt opening cue preview media")
    retimed = after_move["cues"]
    next(item for item in retimed if item["id"] == "middle")["resolvedTimeline"]["start"] = "27s"
    next(item for item in retimed if item["id"] == "overlap")["resolvedTimeline"]["start"] = "30s"
    model.update(version, request(version, "retime-middle-and-overlap", operation="edit", patch={"cues": retimed, "brief": after_move["brief"]}))
    model.preview(version, request(version, "local-after-retime", scope="local", cueIds=["middle", "overlap"]))

    # Only opening changes.  The full demo still presents the other valid cues,
    # and a deleted middle cache proves recovery never rewrites project inputs.
    before_opening_source = tree_hashes(inbox)
    middle_before = next(cue for cue in load(version)["cues"] if cue["id"] == "middle")
    middle_key = cue_key(version, load(version), middle_before, "preview")
    (version / "cache" / "cues" / "preview" / middle_key / "media.mov").unlink()
    changed = {"compositions/cues/opening.html": composition("opening", "#ff304f", 320, include_motion=True)}
    model.update(version, request(version, "style-opening-only", operation="edit", patch={"cues": load(version)["cues"], "brief": load(version)["brief"]},
        files=stage(version, changed, {}), work={"mode": "motion", "cueIds": ["opening"], "taskId": "opening-only-change"}))
    scoped = model.preview(version, demo_request(version, "full-opening-only", cueIds=["opening"], workCueIds=["opening"], excludedCueIds=[]))
    scoped_artifact = next(item for item in load(version)["artifacts"] if item["id"] == scoped["artifactIds"][0])
    scope = scoped_artifact["coverage"]
    if scope["workCueIds"] != ["opening"] or set(scope["presentedCueIds"]) != {"opening", "middle", "overlap", "fade_end"}:
        raise RuntimeError("opening-only full preview did not retain the other valid cues")
    if scope["mediaReuse"].get("middle") != "rebuilt" or tree_hashes(inbox) != before_opening_source:
        raise RuntimeError("missing middle cache did not rebuild safely from unchanged inputs")

    excluded = model.preview(version, demo_request(version, "full-exclude-d", cueIds=["opening"], workCueIds=["opening"], excludedCueIds=["fade_end"]))
    excluded_artifact = next(item for item in load(version)["artifacts"] if item["id"] == excluded["artifactIds"][0])
    if excluded["reviewSet"] is not None or excluded_artifact["complete"] or excluded_artifact["excludedCueIds"] != ["fade_end"]:
        raise RuntimeError("explicitly excluded D unexpectedly formed a complete review")

    # A genuinely new static cue stays unconfirmed and cannot force active local work to include it.
    current = copy.deepcopy(load(version)["cues"])
    new_cue = copy.deepcopy(next(cue for cue in current if cue["id"] == "opening"))
    new_cue["id"] = "new_static"
    new_cue["resolvedTimeline"] = {"start": "8s", "duration": "1s"}
    new_cue["renderAdapters"]["hyperframes"].pop("motionSrc", None)
    new_cue["renderAdapters"]["hyperframes"]["compositionId"] = "new_static"
    new_cue["renderAdapters"]["hyperframes"]["compositionSrc"] = "compositions/cues/new_static.html"
    new_cue.pop("objectId", None)
    current.append(new_cue)
    model.update(version, request(version, "add-unconfirmed-static", operation="edit", patch={"cues": current, "brief": load(version)["brief"]},
        objectRelations={"new_static": {"kind": "new", "basis": {"text": "临时静态替代方案不自动进入活动制作", "reference": "smoke:new-static"}}},
        files=stage(version, {"compositions/cues/new_static.html": composition("new_static", "#999999", 640)}, {})))
    local = model.preview(version, request(version, "active-local-with-new-static", scope="local", cueIds=["opening"]))
    new_static_object = next(cue for cue in load(version)["cues"] if cue["id"] == "new_static")["objectId"]
    if local["status"] != "complete" or any(new_static_object in item.get("objectIds", []) for item in load(version)["decisions"] if item["kind"] == "confirm-design"):
        raise RuntimeError("new static cue was automatically confirmed or blocked active local work")

    # Remove only the synthetic static cue, then rename opening while explicitly retaining its object identity.
    renamed = copy.deepcopy(load(version)["cues"])
    original_opening = next(cue for cue in renamed if cue["id"] == "opening")
    opening_object = original_opening["objectId"]
    original_opening["id"] = "opening_renamed"
    next(cue for cue in renamed if cue["id"] == "new_static")
    renamed = [cue for cue in renamed if cue["id"] != "new_static"]
    model.update(version, request(version, "rename-opening", operation="edit", patch={"cues": renamed, "brief": load(version)["brief"]},
        objectRelations={"opening_renamed": {"kind": "continue", "objectId": opening_object,
            "basis": {"text": "同一标题对象改名与技术重组", "reference": "smoke:rename"}}}))
    if model.status(version)["reviewSet"] is not None:
        raise RuntimeError("review remained current after canonical rename")
    if not any(decision["kind"] == "confirm-design" and opening_object in decision["objectIds"] for decision in load(version)["decisions"]):
        raise RuntimeError("same-object rename lost first design eligibility")
    model.preview(version, request(version, "local-after-rename", scope="local", cueIds=["opening_renamed"]))

    final_ids = [cue['id'] for cue in load(version)['cues'] if cue['productionMode'] == 'animation']
    full = model.preview(version, demo_request(version, "full-final", cueIds=["opening_renamed"], workCueIds=["opening_renamed"], excludedCueIds=[]))
    review = full["reviewSet"]["id"]
    delivered = model.deliver(version, request(version, "deliver", decision={"kind": "approve-and-deliver", "reviewSetId": review, "feedbackIds": [], "source": {"channel": "chat", "text": "approve synthetic fixture", "reference": "fixture"}}))
    release = delivered["delivery"]
    package_path = afterforge / release["packagePath"]
    if not (package_path / "Info.fcpxml").is_file() or sha(package_path / "Info.fcpxml") != release["infoFcpxmlSha256"]:
        raise RuntimeError("immutable package verification failed")
    if tree_hashes(inbox) != source_hashes:
        raise RuntimeError("work model modified synthetic user-inbox inputs")
    evidence = {
        'coldStart': cold_evidence,
        "snapshape": {"openingFrames": {key: {"path": value["path"], "dimensions": dimensions(version / value["path"]),
            "background": value.get("background"), "backgroundTime": value.get("backgroundTime"), "state": value.get("state")}
            for key, value in by_frame.items()}},
        "fonts": {"source": str(font), "sha256": sha(font), "staged": "assets/fonts/title.woff2"},
        "sourceSHA": source_hashes,
        "cueScope": {"openingOnly": scope, "excludedD": excluded_artifact["coverage"], "finalCueIds": final_ids},
        "cacheReuse": {"initial": before, "final": cache_hashes(version, "preview"), "middleRecovery": scope["mediaReuse"].get("middle")},
        "firsteligibility": {"openingObjectId": opening_object, "newStaticObjectId": new_static_object,
            "confirmedOpening": True, "reviewInvalidatedByRename": True},
    }
    (root_base / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "complete", "fixture": str(root_base), "version": str(version), "release": release, "package": str(package_path), "evidence": str(root_base / "evidence.json"), "initialPreviewCache": before, "finalPreviewCache": cache_hashes(version, "preview")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
