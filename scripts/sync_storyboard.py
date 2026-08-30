#!/usr/bin/env python3
"""Generate STORYBOARD.md and review projections from manifest v2."""

from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path
from typing import Any

try:
    from scripts.hyperframes_adapter import (
        GENERATED_REVIEW_MARKER,
        cue_adapter,
        decimal_seconds,
        decimal_number,
        ensure_parent,
        load_manifest,
        project_dimensions,
        projection_scale,
        project_duration,
        safe_project_path,
    )
except ModuleNotFoundError:
    from hyperframes_adapter import (  # type: ignore
        GENERATED_REVIEW_MARKER,
        cue_adapter,
        decimal_seconds,
        decimal_number,
        ensure_parent,
        load_manifest,
        project_dimensions,
        projection_scale,
        project_duration,
        safe_project_path,
    )


def _review_html(
    cue: dict[str, Any],
    preview_width: int,
    preview_height: int,
    delivery_width: int,
    delivery_height: int,
    scale_x: str,
    scale_y: str,
) -> str:
    adapter = cue_adapter(cue)
    cue_id = str(cue["id"])
    review_id = f"review-{cue_id.replace('_', '-')}"
    duration = decimal_seconds(cue["resolvedTimeline"]["duration"])
    still = escape(adapter["stillSrc"], quote=True)
    mount = ""
    if cue["productionMode"] == "animation":
        composition_id = escape(adapter["compositionId"], quote=True)
        composition_src = escape(adapter["compositionSrc"], quote=True)
        mount = f'''\n    <div id="review-overlay-{escape(cue_id.replace('_', '-'), quote=True)}" class="clip overlay" data-composition-id="{composition_id}" data-composition-src="{composition_src}" data-start="0" data-duration="{duration}" data-track-index="1" data-width="{delivery_width}" data-height="{delivery_height}"></div>'''
    return f'''<!doctype html>
<html lang="zh-CN">
  <body>
    <template>
      <!-- {GENERATED_REVIEW_MARKER} -->
      <style>
        #root {{ position: absolute; inset: 0; width: {preview_width}px; height: {preview_height}px; overflow: hidden; background: #000; }}
        .source {{ position: absolute; inset: 0; width: 100%; height: 100%; }}
        .source {{ object-fit: cover; }}
        .overlay {{ position: absolute; left: 0; top: 0; width: {delivery_width}px; height: {delivery_height}px; transform-origin: 0 0; transform: scale({scale_x}, {scale_y}); }}
      </style>
      <div id="root" data-composition-id="{review_id}" data-width="{preview_width}" data-height="{preview_height}" data-duration="{duration}">
        <img class="source" src="{still}" alt="">{mount}
      </div>
      <script>
        window.__timelines = window.__timelines || {{}};
        window.__timelines["{review_id}"] = gsap.timeline({{ paused: true }});
      </script>
    </template>
  </body>
</html>
'''


def _storyboard_status(cue: dict[str, Any]) -> str:
    state = cue.get("workflowState")
    if state in {"motion-built", "motion-approved", "rendered"}:
        return "animated"
    if state in {"layout-built", "layout-approved"}:
        return "built"
    return "outline"


def _yaml_string(value: Any) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _storyboard(manifest: dict[str, Any]) -> str:
    project = manifest["project"]
    preview = project["preview"]
    lines = [
        "---",
        f"format: {preview['width']}x{preview['height']}",
        f"duration: {project_duration(manifest)}s",
        f"message: {_yaml_string(project.get('message', project.get('name', '')))}",
        f"arc: {_yaml_string(project.get('arc', ''))}",
        f"audience: {_yaml_string(project.get('audience', ''))}",
        "mode: collaborative",
        "---",
        "",
        f"<!-- {GENERATED_REVIEW_MARKER} -->",
        "",
    ]
    for index, cue in enumerate(manifest["cues"], start=1):
        adapter = cue_adapter(cue)
        title = cue.get("screenText", [None])[0] if cue.get("screenText") else cue.get("type", cue["id"])
        route = cue.get("designRoute", {})
        functions = route.get("functions", {})
        relation = route.get("sourceRelationship", {})
        languages = route.get("referenceLanguages", {})
        screen_text = "｜".join(cue.get("screenText", [])) or "无"
        shot = cue.get("originalShotNumber") or "未提供原镜号"
        lines.extend(
            [
                f"## Frame {index} — {title}",
                "",
                f"- cue_id: {cue['id']}",
                f"- source_shot: {shot}",
                f"- status: {_storyboard_status(cue)}",
                f"- src: {adapter['reviewSrc']}",
                f"- duration: {decimal_seconds(cue['resolvedTimeline']['duration'])}s",
                f"- poster: {adapter.get('heroTime', 0.1)}s",
                f"- scene: {cue.get('composition', '')}",
                f"- voiceover: {_yaml_string(cue.get('narrationAnchor', ''))}",
                f"- function: {functions.get('primary', '')}",
                f"- source_relation: {relation.get('primary', '')}",
                f"- reference_language: {languages.get('primary') or '无'}",
                f"- screen_text: {screen_text}",
                f"- motion: {cue.get('motionIntent', '')}",
                "",
                route.get("rationale", ""),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _write_generated_review(path: Path, content: str) -> None:
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if GENERATED_REVIEW_MARKER not in existing:
            raise ValueError(f"refusing to overwrite non-generated review file: {path}")
    ensure_parent(path)
    path.write_text(content, encoding="utf-8")


def sync_storyboard(version_root: Path) -> dict[str, Any]:
    root = version_root.expanduser().resolve()
    manifest = load_manifest(root)
    preview_width, preview_height = project_dimensions(manifest, "preview")
    delivery_width, delivery_height = project_dimensions(manifest, "delivery")
    scale_x, scale_y = projection_scale(manifest)
    generated: list[str] = []
    for cue in manifest["cues"]:
        adapter = cue_adapter(cue)
        safe_project_path(root, adapter["stillSrc"])
        if cue.get("productionMode") == "animation":
            safe_project_path(root, adapter["compositionSrc"])
        review_path = safe_project_path(root, adapter["reviewSrc"], must_exist=False)
        _write_generated_review(
            review_path,
            _review_html(
                cue,
                preview_width,
                preview_height,
                delivery_width,
                delivery_height,
                decimal_number(scale_x),
                decimal_number(scale_y),
            ),
        )
        generated.append(adapter["reviewSrc"])
    (root / "STORYBOARD.md").write_text(_storyboard(manifest), encoding="utf-8")
    return {"status": "synced", "storyboard": "STORYBOARD.md", "reviewFiles": generated}


def main() -> int:
    parser = argparse.ArgumentParser(description="从 manifest v2 生成 Storyboard 与 review projection。")
    parser.add_argument("version_root", type=Path)
    args = parser.parse_args()
    try:
        result = sync_storyboard(args.version_root)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
