#!/usr/bin/env python3
"""Wrap legacy preview-size cues in a delivery-native canonical root."""

from __future__ import annotations

try:
    from scripts.manifest_transaction import manifest_mutation
except ModuleNotFoundError:  # direct script execution
    from manifest_transaction import manifest_mutation

import argparse
import json
import os
import re
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

try:
    from scripts.hyperframes_adapter import (
        composition_dimensions,
        cue_adapter,
        decimal_number,
        load_manifest,
        project_dimensions,
        safe_project_path,
        save_manifest,
    )
except ModuleNotFoundError:
    from hyperframes_adapter import (  # type: ignore
        composition_dimensions,
        cue_adapter,
        decimal_number,
        load_manifest,
        project_dimensions,
        safe_project_path,
        save_manifest,
    )


ROOT_OPEN = re.compile(r'<div\b(?=[^>]*\bid=["\']root["\'])(?=[^>]*\bdata-composition-id=)[^>]*>', re.DOTALL)
WIDTH_ATTRIBUTE = re.compile(r'\bdata-width=["\'][^"\']+["\']')
HEIGHT_ATTRIBUTE = re.compile(r'\bdata-height=["\'][^"\']+["\']')
LEGACY_STAGE_ATTRIBUTE = "data-afterforge-legacy-stage"


def _atomic_text(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _wrap_legacy_cue(
    html: str,
    motion_src: str,
    preview: tuple[int, int],
    delivery: tuple[int, int],
) -> str:
    if LEGACY_STAGE_ATTRIBUTE in html:
        if composition_dimensions(html) != delivery:
            raise ValueError("legacy-stage cue does not use delivery root dimensions")
        return html
    actual = composition_dimensions(html)
    if actual == delivery:
        return html
    if actual != preview:
        raise ValueError(
            f"canonical dimensions {actual[0]}x{actual[1]} are neither preview nor delivery dimensions"
        )
    match = ROOT_OPEN.search(html)
    if match is None:
        raise ValueError("cannot locate canonical root opening tag")
    root_open = match.group(0)
    root_open = WIDTH_ATTRIBUTE.sub(f'data-width="{delivery[0]}"', root_open, count=1)
    root_open = HEIGHT_ATTRIBUTE.sub(f'data-height="{delivery[1]}"', root_open, count=1)
    script_token = f'<script src="{motion_src}"></script>'
    script_index = html.find(script_token, match.end())
    if script_index < 0:
        raise ValueError(f"cannot locate linked motion script: {motion_src}")
    root_close = html.rfind("</div>", match.end(), script_index)
    if root_close < 0:
        raise ValueError("cannot locate canonical root closing tag")
    scale_x = decimal_number(Decimal(delivery[0]) / Decimal(preview[0]))
    scale_y = decimal_number(Decimal(delivery[1]) / Decimal(preview[1]))
    override = f'''\n  <style data-afterforge-delivery-layout="legacy-stage">
    #root {{ width: {delivery[0]}px !important; height: {delivery[1]}px !important; }}
    .afterforge-legacy-stage {{ position: absolute; left: 0; top: 0; width: {preview[0]}px; height: {preview[1]}px; transform-origin: 0 0; transform: scale({scale_x}, {scale_y}); }}
  </style>'''
    stage_open = f'\n    <div class="afterforge-legacy-stage" {LEGACY_STAGE_ATTRIBUTE}="{preview[0]}x{preview[1]}">'
    stage_close = "\n    </div>"
    before_root = html[: match.start()] + override + "\n  " + root_open
    content_start = match.end()
    adjusted_root_close = root_close + len(before_root) - match.end()
    with_open = before_root + stage_open + html[content_start:]
    adjusted_root_close += len(stage_open)
    return with_open[:adjusted_root_close] + stage_close + with_open[adjusted_root_close:]


@manifest_mutation
def migrate_delivery_layout(version_root: Path) -> dict[str, Any]:
    root = version_root.expanduser().resolve()
    manifest = load_manifest(root)
    preview = project_dimensions(manifest, "preview")
    delivery = project_dimensions(manifest, "delivery")
    transformed: dict[Path, str] = {}
    migrated_cues: list[dict[str, Any]] = []
    for cue in manifest["cues"]:
        if cue.get("productionMode") != "animation":
            continue
        adapter = cue_adapter(cue)
        path = safe_project_path(root, adapter["compositionSrc"])
        original = path.read_text(encoding="utf-8")
        updated = _wrap_legacy_cue(original, adapter["motionSrc"], preview, delivery)
        if updated != original:
            transformed[path] = updated
            migrated_cues.append(cue)
    if not transformed:
        return {"status": "unchanged", "migratedCueIds": []}
    for cue in migrated_cues:
        cue["workflowState"] = "layout-built"
        adapter = cue_adapter(cue)
        previous_lock = adapter.get("layoutLock") or {}
        previous_revision = int(previous_lock.get("revision", adapter.get("layoutRevision", 0)))
        adapter["layoutRevision"] = previous_revision
        adapter["layoutLock"] = None
    review = manifest.setdefault("reviews", {}).setdefault("a11", {})
    review["status"] = "pending-migration-equivalence"
    review.pop("approvedCueIds", None)
    originals = {path: path.read_text(encoding="utf-8") for path in transformed}
    try:
        for path, content in transformed.items():
            _atomic_text(path, content)
        save_manifest(root, manifest)
    except BaseException:
        for path, content in originals.items():
            _atomic_text(path, content)
        raise
    return {"status": "migrated", "migratedCueIds": [cue["id"] for cue in migrated_cues]}


def main() -> int:
    parser = argparse.ArgumentParser(description="把旧 480p cue 迁移到原生交付尺寸 canonical root。")
    parser.add_argument("version_root", type=Path)
    args = parser.parse_args()
    try:
        result = migrate_delivery_layout(args.version_root)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
