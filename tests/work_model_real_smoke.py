#!/usr/bin/env python3
"""Opt-in, isolated real-render regression for the schema-3 work model.

Run manually with ``python tests/work_model_real_smoke.py --run``.  It creates
only synthetic material below the platform temporary directory and keeps the
resulting fixture for inspection; it is intentionally not discovered by
unittest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import work_model as model
from scripts.work_model_inputs import cue_key
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


def composition(cue_id: str, color: str, left: int) -> str:
    return f'''<!doctype html><html><head><style>
html,body{{margin:0;width:1920px;height:1080px;overflow:hidden;background:transparent}}
[data-composition-id="{cue_id}"]{{position:relative;width:1920px;height:1080px}}
#title{{position:absolute;left:{left}px;top:432px;width:620px;height:180px;border-radius:36px;background:{color}}}
</style></head><body><div data-composition-id="{cue_id}" data-width="1920" data-height="1080" data-duration="3" data-fps="24">
<div id="title" class="clip" data-start="0" data-duration="3" data-track-index="1"></div></div>
<script src="compositions/motion/{cue_id}.js"></script></body></html>\n'''


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the isolated schema-3 real rendering smoke fixture.")
    parser.add_argument("--run", action="store_true", help="required acknowledgement that real cached Chromium rendering will run")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--runtime", default="0.8.33", help="exact locally cached HyperFrames version; never installs")
    parser.add_argument("--gsap-source", type=Path,
                        help="optional regular local GSAP file to stage for an offline runtime that does not bundle GSAP")
    args = parser.parse_args()
    if not args.run:
        parser.error("pass --run to create and render the synthetic fixture")
    root_base = args.root.resolve()
    if root_base.exists():
        raise SystemExit(f"refusing to overwrite retained smoke fixture: {root_base}")
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
    model.update(version, runtime_request)
    cue_specs = [("opening", "#ff304f", 180, "2s", "2s", 2), ("middle", "#38d9a9", 520, "28s", "2s", 2), ("overlap", "#4c6fff", 880, "29s", "3s", 3), ("fade_end", "#ffd166", 420, "56s", "1s", 1)]
    cues = [{"id": name, "productionMode": "animation", "status": "ready", "resolvedTimeline": {"start": start, "duration": duration}, "layer": layer,
             "finalAnimationDescription": f"Synthetic {name} title", "renderAdapters": {"hyperframes": {"compositionId": name, "compositionSrc": f"compositions/cues/{name}.html", "motionSrc": f"compositions/motion/{name}.js", "layoutDependencies": ["assets/vendor/gsap.min.js"]}}, "alphaExpectation": {"mode": "transparent"}}
            for name, _, _, start, duration, layer in cue_specs]
    source_files: dict[str, str] = {}
    for name, color, left, _, duration, _ in cue_specs:
        source_files[f"compositions/cues/{name}.html"] = composition(name, color, left)
        source_files[f"compositions/motion/{name}.js"] = motion(name, int(duration[:-1]))
    files = stage(version, source_files, {})
    model.update(version, request(version, "seed", operation="edit", patch={"brief": {"summary": "synthetic minute", "segments": []}, "cues": cues}, files=files))
    model.preview(version, request(version, "full-initial", scope="full"))
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
    changed = {"compositions/cues/opening.html": composition("opening", "#ff304f", 320), "compositions/cues/middle.html": composition("middle", "#c77dff", 520)}
    model.update(version, request(version, "style-title", operation="edit", patch={"cues": load(version)["cues"], "brief": load(version)["brief"]}, files=stage(version, changed, {})))
    full = model.preview(version, request(version, "full-final", scope="full"))
    review = full["reviewSet"]["id"]
    delivered = model.deliver(version, request(version, "deliver", decision={"kind": "approve-and-deliver", "reviewSetId": review, "source": {"channel": "chat", "text": "approve synthetic fixture", "reference": "fixture"}}))
    release = delivered["delivery"]
    package_path = afterforge / release["packagePath"]
    if not (package_path / "Info.fcpxml").is_file() or sha(package_path / "Info.fcpxml") != release["infoFcpxmlSha256"]:
        raise RuntimeError("immutable package verification failed")
    if tree_hashes(inbox) != source_hashes:
        raise RuntimeError("work model modified synthetic user-inbox inputs")
    print(json.dumps({"status": "complete", "fixture": str(root_base), "version": str(version), "release": release, "package": str(package_path), "initialPreviewCache": before, "finalPreviewCache": cache_hashes(version, "preview")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
