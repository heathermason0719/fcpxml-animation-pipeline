#!/usr/bin/env python3
"""Migrate a legacy HyperFrames Vn into the single-layout-source adapter."""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any

try:
    from scripts.assemble_hyperframes import assemble_hyperframes
    from scripts.hyperframes_adapter import SCHEMA_VERSION, save_manifest
    from scripts.sync_storyboard import sync_storyboard
except ModuleNotFoundError:
    from assemble_hyperframes import assemble_hyperframes  # type: ignore
    from hyperframes_adapter import SCHEMA_VERSION, save_manifest  # type: ignore
    from sync_storyboard import sync_storyboard  # type: ignore


INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc\s*=)[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE)
COMPOSITION_ID = re.compile(r'data-composition-id=["\']([^"\']+)["\']')
FRONTMATTER_VALUE = re.compile(r"^(message|arc|audience):\s*(.+?)\s*$")


def _read_legacy_manifest(root: Path) -> dict[str, Any]:
    path = root / "animation-manifest.json"
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"missing regular animation-manifest.json: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cues"), list):
        raise ValueError("legacy animation manifest must contain cues")
    if payload.get("schemaVersion") == SCHEMA_VERSION:
        raise ValueError("project already uses manifest schema 2.0")
    return payload


def _frontmatter(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end < 0:
        return {}
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        match = FRONTMATTER_VALUE.match(line)
        if not match:
            continue
        raw = match.group(2)
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw.strip('"\'')
        values[match.group(1)] = str(value)
    return values


def _split_animation(html: str, motion_relative: str) -> tuple[str, str, str]:
    matches = list(INLINE_SCRIPT.finditer(html))
    timeline_match = next((match for match in reversed(matches) if "gsap.timeline" in match.group(1)), None)
    if timeline_match is None:
        raise ValueError("legacy animation composition lacks an inline GSAP timeline")
    id_match = COMPOSITION_ID.search(html)
    if id_match is None:
        raise ValueError("legacy animation composition lacks data-composition-id")
    external = f'<script src="{motion_relative}"></script>'
    canonical = html[: timeline_match.start()] + external + html[timeline_match.end() :]
    body = timeline_match.group(1).strip()
    motion = "(() => {\n" + body + "\n})();\n"
    return canonical, motion, id_match.group(1)


def _layout_dependencies(root: Path, canonical_relative: str) -> list[str]:
    dependencies = [canonical_relative]
    stylesheet = root / "assets/storyboard.css"
    if stylesheet.is_file() and not stylesheet.is_symlink():
        dependencies.append("assets/storyboard.css")
    fonts = root / "assets/fonts"
    if fonts.is_dir() and not fonts.is_symlink():
        dependencies.extend(path.relative_to(root).as_posix() for path in sorted(fonts.rglob("*")) if path.is_file() and not path.is_symlink())
    return dependencies


def _hero_time(hero_times: dict[str, float], cue: dict[str, Any]) -> float:
    cue_id = str(cue.get("id", ""))
    if cue_id not in hero_times:
        raise ValueError(f"missing hero time for animated cue: {cue_id}")
    value = float(hero_times[cue_id])
    if value < 0:
        raise ValueError(f"hero time must be non-negative: {cue_id}")
    return value


def migrate_version(version_root: Path, hero_times: dict[str, float]) -> dict[str, Any]:
    root = version_root.expanduser().resolve()
    if not root.is_dir() or root.is_symlink():
        raise ValueError(f"version root must be a regular directory: {root}")
    legacy = _read_legacy_manifest(root)
    migrated = copy.deepcopy(legacy)
    frontmatter = _frontmatter(root / "STORYBOARD.md")
    migrated["schemaVersion"] = SCHEMA_VERSION
    migrated["reviews"] = {
        "a11": {"status": "pending-migration-parity"},
        "a12": copy.deepcopy(legacy.get("a12Review", {"status": "pending"})),
        "a13": copy.deepcopy(legacy.get("a13Revision", {"status": "pending"})),
    }
    for key in ("reviewStatus", "a12Review", "a13Revision"):
        migrated.pop(key, None)
    project = migrated.setdefault("project", {})
    project.update(frontmatter)
    project.setdefault("renderAdapters", {})["hyperframes"] = {
        "previewMediaSrc": "assets/media/rough-cut.m4v"
    }

    writes: dict[Path, str] = {}
    animated_ids: list[str] = []
    source_only_ids: list[str] = []
    for cue in migrated["cues"]:
        storyboard = cue.pop("storyboard", None)
        cue.pop("reviewStatus", None)
        if not isinstance(storyboard, dict):
            raise ValueError(f"legacy cue lacks storyboard data: {cue.get('id')}")
        frame_src = storyboard.get("src")
        still_src = storyboard.get("still")
        if not isinstance(frame_src, str) or not isinstance(still_src, str):
            raise ValueError(f"legacy cue has invalid storyboard paths: {cue.get('id')}")
        basename = Path(frame_src).name
        review_relative = f"compositions/review/{basename}"
        if cue.get("type") == "no-animation":
            cue["productionMode"] = "source-only"
            cue["workflowState"] = "layout-approved"
            cue["renderAdapters"] = {
                "hyperframes": {
                    "reviewSrc": review_relative,
                    "stillSrc": still_src,
                    "heroTime": float(storyboard.get("poster", 0.1)),
                }
            }
            source_only_ids.append(str(cue["id"]))
            continue

        legacy_animation = root / "compositions/animation" / basename
        if not legacy_animation.is_file() or legacy_animation.is_symlink():
            raise ValueError(f"missing legacy animation composition: {legacy_animation}")
        canonical_relative = f"compositions/cues/{basename}"
        motion_relative = f"compositions/motion/{Path(basename).stem}.js"
        canonical, motion, composition_id = _split_animation(
            legacy_animation.read_text(encoding="utf-8"), motion_relative
        )
        writes[root / canonical_relative] = canonical
        writes[root / motion_relative] = motion
        cue["productionMode"] = "animation"
        cue["workflowState"] = "motion-built"
        cue["renderAdapters"] = {
            "hyperframes": {
                "compositionId": composition_id,
                "compositionSrc": canonical_relative,
                "motionSrc": motion_relative,
                "reviewSrc": review_relative,
                "stillSrc": still_src,
                "heroTime": _hero_time(hero_times, cue),
                "layoutDependencies": _layout_dependencies(root, canonical_relative),
                "layoutLock": None,
            }
        }
        animated_ids.append(str(cue["id"]))

    existing = [path for path in writes if path.exists()]
    if existing:
        raise ValueError("migration targets already exist: " + ", ".join(str(path.relative_to(root)) for path in existing))

    original_manifest = (root / "animation-manifest.json").read_bytes()
    original_storyboard = (root / "STORYBOARD.md").read_bytes() if (root / "STORYBOARD.md").is_file() else None
    original_index = (root / "index.html").read_bytes() if (root / "index.html").is_file() else None
    created: list[Path] = []
    try:
        for path, content in writes.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            created.append(path)
        (root / "compositions/review").mkdir(parents=True, exist_ok=True)
        (root / "approvals/a11").mkdir(parents=True, exist_ok=True)
        save_manifest(root, migrated)
        sync_storyboard(root)
        assemble_hyperframes(root)
    except BaseException:
        (root / "animation-manifest.json").write_bytes(original_manifest)
        if original_storyboard is None:
            (root / "STORYBOARD.md").unlink(missing_ok=True)
        else:
            (root / "STORYBOARD.md").write_bytes(original_storyboard)
        if original_index is None:
            (root / "index.html").unlink(missing_ok=True)
        else:
            (root / "index.html").write_bytes(original_index)
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return {
        "status": "migrated",
        "versionRoot": str(root),
        "animatedCueIds": animated_ids,
        "sourceOnlyCueIds": source_only_ids,
        "legacyDirectoriesPreserved": ["compositions/frames", "compositions/animation"],
    }


def _hero_time_argument(value: str) -> tuple[str, float]:
    cue_id, separator, raw = value.partition("=")
    if not separator or not cue_id:
        raise argparse.ArgumentTypeError("hero time must use cue_id=seconds")
    try:
        seconds = float(raw)
    except ValueError as error:
        raise argparse.ArgumentTypeError("hero time seconds must be numeric") from error
    return cue_id, seconds


def main() -> int:
    parser = argparse.ArgumentParser(description="迁移 legacy HyperFrames Vn 到单一布局源结构。")
    parser.add_argument("version_root", type=Path)
    parser.add_argument("--hero-time", action="append", default=[], type=_hero_time_argument)
    args = parser.parse_args()
    try:
        result = migrate_version(args.version_root, dict(args.hero_time))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
