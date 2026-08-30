#!/usr/bin/env python3
"""Compare a delivered FCPXML with a Final Cut Pro re-export semantically."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree as ET

try:
    from scripts.hyperframes_adapter import parse_time
    from scripts.validate_fcpxml_package import (
        _global_afterforge_intervals,
        _remove_afterforge_anchors,
        _semantic_tree,
    )
except ModuleNotFoundError:
    from hyperframes_adapter import parse_time  # type: ignore
    from validate_fcpxml_package import (  # type: ignore
        _global_afterforge_intervals,
        _remove_afterforge_anchors,
        _semantic_tree,
    )


def _parse(path: Path, label: str) -> ET.Element:
    target = Path(path).expanduser().resolve()
    if not target.is_file() or target.is_symlink():
        raise ValueError(f"{label} is missing or unsafe: {target}")
    try:
        return ET.parse(target).getroot()
    except ET.ParseError as error:
        raise ValueError(f"{label} is malformed: {error}") from error


def _single_sequence(root: ET.Element, label: str) -> ET.Element:
    sequences = root.findall(".//project/sequence")
    if len(sequences) != 1:
        raise ValueError(f"{label} must contain exactly one Project sequence")
    return sequences[0]


def _media_basename(src: str | None) -> str | None:
    if not src:
        return None
    parsed = urlparse(src)
    path = parsed.path if parsed.scheme else src
    return Path(unquote(path)).name


def _resource_for_file(resources: ET.Element, file_name: str) -> ET.Element:
    matches: list[ET.Element] = []
    for resource in resources.findall("asset"):
        media = resource.findall("media-rep")
        if len(media) == 1 and _media_basename(media[0].get("src")) == file_name:
            matches.append(resource)
    if len(matches) != 1:
        raise ValueError(f"round-trip must contain exactly one media identity for {file_name}")
    return matches[0]


def _assert_pure_video(resource: ET.Element, cue_id: str) -> None:
    if resource.get("hasVideo") != "1":
        raise ValueError(f"round-trip animation lacks video: {cue_id}")
    if resource.get("hasAudio") not in {None, "0"}:
        raise ValueError(f"round-trip animation became audio-bearing: {cue_id}")
    if resource.get("audioSources") not in {None, "0"} or resource.get("audioChannels") is not None:
        raise ValueError(f"round-trip animation gained audio sources: {cue_id}")
    if any(item.tag.startswith("audio") for item in resource.iter()):
        raise ValueError(f"round-trip animation contains audio nodes: {cue_id}")


def compare_roundtrip(
    delivered_xml: Path,
    reexported_xml: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    delivered_root = _parse(delivered_xml, "delivered FCPXML")
    reexported_root = _parse(reexported_xml, "re-exported FCPXML")
    delivered_sequence = _single_sequence(delivered_root, "delivered FCPXML")
    reexported_sequence = _single_sequence(reexported_root, "re-exported FCPXML")
    if parse_time(delivered_sequence.get("duration")) != parse_time(reexported_sequence.get("duration")):
        raise ValueError("round-trip sequence duration changed")

    animated = sorted(
        [cue for cue in manifest.get("cues", []) if cue.get("productionMode") == "animation"],
        key=lambda cue: cue["id"],
    )
    if not animated or any(not isinstance(cue.get("deliveryAsset"), dict) for cue in animated):
        raise ValueError("manifest animated cues must all have deliveryAsset")
    cue_ids = {cue["id"] for cue in animated}
    expected_names = {f"AF__{cue_id}" for cue_id in cue_ids}
    spine = reexported_sequence.find("spine")
    resources = reexported_root.find("resources")
    if spine is None or resources is None:
        raise ValueError("re-exported FCPXML lacks resources or spine")

    all_afterforge_names = {
        item.get("name")
        for item in spine.iter("asset-clip")
        if item.get("name", "").startswith("AF__")
    }
    if all_afterforge_names != expected_names:
        raise ValueError(
            f"round-trip animation cue set changed: expected {sorted(expected_names)}, "
            f"found {sorted(all_afterforge_names)}"
        )
    intervals = _global_afterforge_intervals(spine, expected_names)
    if set(intervals) != expected_names:
        raise ValueError("round-trip animation placement set changed")

    for cue in animated:
        cue_id = cue["id"]
        asset = cue["deliveryAsset"]
        resource = _resource_for_file(resources, asset["fileName"])
        _assert_pure_video(resource, cue_id)
        if resource.get("duration") is not None and parse_time(resource.get("duration")) != parse_time(asset["duration"]):
            raise ValueError(f"round-trip animation resource duration changed: {cue_id}")

        anchor_name = f"AF__{cue_id}"
        anchors = [item for item in spine.iter("asset-clip") if item.get("name") == anchor_name]
        if len(anchors) != 1:
            raise ValueError(f"round-trip animation connected clip count changed: {cue_id}")
        anchor = anchors[0]
        if anchor.get("ref") != resource.get("id"):
            raise ValueError(f"round-trip animation media reference changed: {cue_id}")
        if anchor.get("srcEnable") not in {None, "all", "video"}:
            raise ValueError(f"round-trip animation source enable is invalid: {cue_id}")
        interval = intervals[anchor_name]
        if interval.duration != parse_time(asset["duration"]):
            raise ValueError(f"round-trip animation connected clip duration changed: {cue_id}")
        semantic_start = parse_time(cue["resolvedTimeline"]["start"])
        semantic_duration = parse_time(cue["resolvedTimeline"]["duration"])
        if not semantic_start <= interval.start < semantic_start + semantic_duration:
            raise ValueError(f"round-trip animation moved outside its semantic range: {cue_id}")

    delivered_clean = _remove_afterforge_anchors(delivered_sequence, cue_ids)
    reexported_clean = _remove_afterforge_anchors(reexported_sequence, cue_ids)
    if _semantic_tree(delivered_clean) != _semantic_tree(reexported_clean):
        raise ValueError("round-trip source storyline changed")

    return {
        "status": "valid",
        "deliveredXml": str(Path(delivered_xml).expanduser().resolve()),
        "reexportedXml": str(Path(reexported_xml).expanduser().resolve()),
        "animatedCueIds": [cue["id"] for cue in animated],
        "sourceOnlyCueIds": sorted(
            cue["id"] for cue in manifest.get("cues", []) if cue.get("productionMode") == "source-only"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="比较 FCP 导入后再导出的 FCPXML 语义。")
    parser.add_argument("delivered_xml", type=Path)
    parser.add_argument("reexported_xml", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        result = compare_roundtrip(args.delivered_xml, args.reexported_xml, manifest)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
