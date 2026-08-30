#!/usr/bin/env python3
"""Generate one native-size render host for every animated canonical cue."""

from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path
from typing import Any

try:
    from scripts.hyperframes_adapter import (
        GENERATED_DELIVERY_MARKER,
        cue_adapter,
        decimal_seconds,
        delivery_projection_src,
        ensure_parent,
        load_manifest,
        project_dimensions,
        safe_project_path,
    )
except ModuleNotFoundError:
    from hyperframes_adapter import (  # type: ignore
        GENERATED_DELIVERY_MARKER,
        cue_adapter,
        decimal_seconds,
        delivery_projection_src,
        ensure_parent,
        load_manifest,
        project_dimensions,
        safe_project_path,
    )


def _delivery_html(cue: dict[str, Any], width: int, height: int) -> str:
    adapter = cue_adapter(cue)
    duration = decimal_seconds(cue["resolvedTimeline"]["duration"])
    delivery_id = f"delivery-{adapter['compositionId']}"
    return f'''<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width={width}, height={height}">
    <!-- {GENERATED_DELIVERY_MARKER} -->
    <script src="assets/vendor/gsap.min.js"></script>
    <style>
      * {{ box-sizing: border-box; }}
      html, body {{ margin: 0; width: {width}px; height: {height}px; overflow: hidden; background: transparent; }}
      #root, .cue-slot {{ position: absolute; inset: 0; width: {width}px; height: {height}px; overflow: hidden; background: transparent; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="{escape(delivery_id, quote=True)}" data-width="{width}" data-height="{height}" data-duration="{duration}">
      <div id="delivery-host-{escape(adapter['compositionId'], quote=True)}" class="clip cue-slot" data-composition-id="{escape(adapter['compositionId'], quote=True)}" data-composition-src="{escape(adapter['compositionSrc'], quote=True)}" data-start="0" data-duration="{duration}" data-track-index="0" data-width="{width}" data-height="{height}"></div>
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      window.__timelines["{escape(delivery_id, quote=True)}"] = gsap.timeline({{ paused: true }});
    </script>
  </body>
</html>
'''


def _write_generated(path: Path, content: str) -> None:
    if path.exists() and GENERATED_DELIVERY_MARKER not in path.read_text(encoding="utf-8"):
        raise ValueError(f"refusing to overwrite non-generated delivery projection: {path}")
    ensure_parent(path)
    path.write_text(content, encoding="utf-8")


def sync_delivery(version_root: Path) -> dict[str, Any]:
    root = version_root.expanduser().resolve()
    manifest = load_manifest(root)
    width, height = project_dimensions(manifest, "delivery")
    generated: list[str] = []
    animated: list[str] = []
    skipped: list[str] = []
    for cue in manifest["cues"]:
        if cue.get("productionMode") == "source-only":
            skipped.append(cue["id"])
            continue
        if cue.get("productionMode") != "animation":
            raise ValueError(f"unsupported productionMode for {cue.get('id')}")
        adapter = cue_adapter(cue)
        safe_project_path(root, adapter["compositionSrc"])
        relative = delivery_projection_src(adapter)
        target = safe_project_path(root, relative, must_exist=False)
        _write_generated(target, _delivery_html(cue, width, height))
        generated.append(relative)
        animated.append(cue["id"])
    return {
        "status": "synced",
        "deliveryFiles": generated,
        "animatedCueIds": animated,
        "skippedCueIds": skipped,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="为 animated cues 生成原生交付尺寸 HyperFrames host。")
    parser.add_argument("version_root", type=Path)
    args = parser.parse_args()
    try:
        result = sync_delivery(args.version_root)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
