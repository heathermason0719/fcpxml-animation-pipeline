#!/usr/bin/env python3
"""Generate the composited preview host from manifest v2."""

from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path
from typing import Any

try:
    from scripts.hyperframes_adapter import (
        GENERATED_INDEX_MARKER,
        cue_adapter,
        decimal_number,
        decimal_seconds,
        load_manifest,
        project_dimensions,
        projection_scale,
        project_duration,
        safe_project_path,
    )
except ModuleNotFoundError:
    from hyperframes_adapter import (  # type: ignore
        GENERATED_INDEX_MARKER,
        cue_adapter,
        decimal_number,
        decimal_seconds,
        load_manifest,
        project_dimensions,
        projection_scale,
        project_duration,
        safe_project_path,
    )


def assemble_hyperframes(version_root: Path) -> dict[str, Any]:
    root = version_root.expanduser().resolve()
    manifest = load_manifest(root)
    project = manifest["project"]
    width, height = project_dimensions(manifest, "preview")
    delivery_width, delivery_height = project_dimensions(manifest, "delivery")
    scale_x, scale_y = (decimal_number(value) for value in projection_scale(manifest))
    duration = project_duration(manifest)
    project_adapter = project.get("renderAdapters", {}).get("hyperframes", {})
    media_src = project_adapter.get("previewMediaSrc", "assets/media/rough-cut.m4v")
    safe_project_path(root, media_src)
    slots: list[str] = []
    animated: list[str] = []
    skipped: list[str] = []
    for track, cue in enumerate(manifest["cues"], start=2):
        if cue.get("productionMode") == "source-only":
            skipped.append(cue["id"])
            continue
        if cue.get("productionMode") != "animation":
            raise ValueError(f"unsupported productionMode for {cue.get('id')}")
        adapter = cue_adapter(cue)
        safe_project_path(root, adapter["compositionSrc"])
        animated.append(cue["id"])
        slots.append(
            f'''      <div id="host-{escape(adapter['compositionId'], quote=True)}" class="clip overlay-slot" data-composition-id="{escape(adapter['compositionId'], quote=True)}" data-composition-src="{escape(adapter['compositionSrc'], quote=True)}" data-start="{decimal_seconds(cue['resolvedTimeline']['start'])}" data-duration="{decimal_seconds(cue['resolvedTimeline']['duration'])}" data-track-index="{track}" data-width="{delivery_width}" data-height="{delivery_height}"></div>'''
        )
    slot_text = "\n".join(slots)
    html = f'''<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width={width}, height={height}">
    <!-- {GENERATED_INDEX_MARKER} -->
    <script src="assets/vendor/gsap.min.js"></script>
    <style>
      * {{ box-sizing: border-box; }}
      html, body {{ margin: 0; width: {width}px; height: {height}px; overflow: hidden; background: transparent; }}
      #root {{ position: relative; width: {width}px; height: {height}px; overflow: hidden; background: #000; }}
      #rough-cut-video {{ position: absolute; inset: 0; width: {width}px; height: {height}px; }}
      #rough-cut-video {{ object-fit: cover; }}
      .overlay-slot {{ position: absolute; left: 0; top: 0; width: {delivery_width}px; height: {delivery_height}px; transform-origin: 0 0; transform: scale({scale_x}, {scale_y}); pointer-events: none; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-width="{width}" data-height="{height}" data-duration="{duration}">
      <video id="rough-cut-video" class="clip" src="{escape(media_src, quote=True)}" data-start="0" data-duration="{duration}" data-track-index="0" muted playsinline></video>
      <audio id="rough-cut-audio" src="{escape(media_src, quote=True)}" data-start="0" data-duration="{duration}" data-track-index="10" data-volume="1"></audio>
{slot_text}
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      window.__timelines.main = gsap.timeline({{ paused: true }});
    </script>
  </body>
</html>
'''
    (root / "index.html").write_text(html, encoding="utf-8")
    return {"status": "assembled", "index": "index.html", "animatedCueIds": animated, "skippedCueIds": skipped}


def main() -> int:
    parser = argparse.ArgumentParser(description="从 manifest v2 生成 HyperFrames 合成审阅入口。")
    parser.add_argument("version_root", type=Path)
    args = parser.parse_args()
    try:
        result = assemble_hyperframes(args.version_root)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
