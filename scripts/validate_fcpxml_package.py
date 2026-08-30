#!/usr/bin/env python3
"""Validate a flat AfterForge FCPXMLD delivery package."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

try:
    from scripts.fcpxml_timing import TimelineInterval, collect_positive_anchors
    from scripts.hyperframes_adapter import parse_time
except ModuleNotFoundError:
    from fcpxml_timing import TimelineInterval, collect_positive_anchors  # type: ignore
    from hyperframes_adapter import parse_time  # type: ignore


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _animated_cues(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for cue in manifest.get("cues", []):
        mode = cue.get("productionMode")
        if mode == "animation":
            if not isinstance(cue.get("deliveryAsset"), dict):
                raise ValueError(f"animated cue lacks deliveryAsset: {cue.get('id')}")
            result.append(cue)
        elif mode == "source-only":
            if "deliveryAsset" in cue:
                raise ValueError(f"source-only cue has deliveryAsset: {cue.get('id')}")
        else:
            raise ValueError(f"unsupported productionMode: {mode!r}")
    return sorted(result, key=lambda item: item["id"])


def _single_project(root: ET.Element, label: str) -> ET.Element:
    projects = root.findall(".//project")
    if len(projects) != 1:
        raise ValueError(f"{label} must contain exactly one Project, found {len(projects)}")
    return projects[0]


def _remove_afterforge_anchors(sequence: ET.Element, cue_ids: set[str]) -> ET.Element:
    cleaned = copy.deepcopy(sequence)
    expected_names = {f"AF__{cue_id}" for cue_id in cue_ids}
    for parent in cleaned.iter():
        for child in list(parent):
            if child.tag == "asset-clip" and child.get("name") in expected_names:
                parent.remove(child)
    return cleaned


def _semantic_tree(element: ET.Element) -> tuple[Any, ...]:
    text = element.text if element.text and element.text.strip() else None
    return (
        element.tag,
        tuple(sorted(element.attrib.items())),
        text,
        tuple(_semantic_tree(child) for child in element),
    )


def _assert_source_sequence_unchanged(
    source_root: ET.Element,
    delivered_root: ET.Element,
    cue_ids: set[str],
) -> None:
    source_sequence = _single_project(source_root, "source FCPXML").find("sequence")
    delivered_sequence = _single_project(delivered_root, "delivered FCPXML").find("sequence")
    if source_sequence is None or delivered_sequence is None:
        raise ValueError("source or delivered Project has no sequence")
    if source_sequence.get("duration") != delivered_sequence.get("duration"):
        raise ValueError("delivered sequence duration changed")
    cleaned = _remove_afterforge_anchors(delivered_sequence, cue_ids)
    if _semantic_tree(source_sequence) != _semantic_tree(cleaned):
        raise ValueError("source sequence changed outside AfterForge connected clips")


def _global_afterforge_intervals(
    spine: ET.Element,
    expected_names: set[str],
) -> dict[str, TimelineInterval]:
    found: dict[str, TimelineInterval] = {}
    for host in spine:
        if host.tag == "transition" or int(host.get("lane", "0")) != 0:
            continue
        if host.get("offset") is None or host.get("duration") is None:
            continue
        host_offset = parse_time(host.get("offset"))
        host_start = parse_time(host.get("start", "0s"))
        for child in host:
            name = child.get("name")
            if child.tag != "asset-clip" or name not in expected_names:
                continue
            if name in found:
                raise ValueError(f"duplicate AfterForge connected clip: {name}")
            lane = int(child.get("lane", "0"))
            if lane <= 0:
                raise ValueError(f"AfterForge connected clip must use a positive lane: {name}")
            start = host_offset + parse_time(child.get("offset", "0s")) - host_start
            found[name] = TimelineInterval(name, start, parse_time(child.get("duration")), lane)
    return found


def _assert_no_lane_overlap(spine: ET.Element) -> None:
    occupied = collect_positive_anchors(spine)
    for index, left in enumerate(occupied):
        for right in occupied[index + 1 :]:
            if left.lane != right.lane:
                continue
            if left.start < right.end and right.start < left.end:
                raise ValueError(
                    f"lane overlap on lane {left.lane}: {left.key} and {right.key}"
                )


def _assert_reference_graph(root: ET.Element) -> None:
    ids: list[str] = [value for element in root.iter() if (value := element.get("id"))]
    if len(ids) != len(set(ids)):
        raise ValueError("FCPXML contains duplicate id values")
    known = set(ids)
    unresolved = sorted(
        {
            ref
            for element in root.iter()
            if (ref := element.get("ref")) and ref not in known
        }
    )
    if unresolved:
        raise ValueError(f"FCPXML contains unresolved ref values: {unresolved}")


def validate_delivery_package(
    package_root: Path,
    source_xml: Path,
    manifest: dict[str, Any],
    *,
    dtd_path: Path | None = None,
) -> dict[str, Any]:
    package = Path(package_root).expanduser().resolve()
    source = Path(source_xml).expanduser().resolve()
    if not package.is_dir() or package.is_symlink() or package.suffix != ".fcpxmld":
        raise ValueError(f"delivery package must be a regular .fcpxmld directory: {package}")
    if not source.is_file() or source.is_symlink():
        raise ValueError(f"source FCPXML is missing or unsafe: {source}")

    animated = _animated_cues(manifest)
    expected_files = {"Info.fcpxml", *(cue["deliveryAsset"]["fileName"] for cue in animated)}
    actual_items = list(package.iterdir())
    if {item.name for item in actual_items} != expected_files:
        raise ValueError(
            f"delivery package contents differ: expected {sorted(expected_files)}, "
            f"found {sorted(item.name for item in actual_items)}"
        )
    if any(not item.is_file() or item.is_symlink() for item in actual_items):
        raise ValueError("delivery package must contain only regular root-level files")

    source_hash = manifest.get("sourceHashes", {}).get("fcpxml")
    if not isinstance(source_hash, str) or sha256_file(source) != source_hash:
        raise ValueError("source FCPXML hash does not match manifest")
    for cue in animated:
        asset = cue["deliveryAsset"]
        movie = package / asset["fileName"]
        if sha256_file(movie) != asset["sha256"]:
            raise ValueError(f"delivery movie hash mismatch: {asset['fileName']}")

    info = package / "Info.fcpxml"
    try:
        source_root = ET.parse(source).getroot()
        delivered_root = ET.parse(info).getroot()
    except ET.ParseError as error:
        raise ValueError(f"malformed FCPXML: {error}") from error
    _assert_reference_graph(delivered_root)

    expected_event_name = f"AfterForge__{manifest['sourceVersion']}"
    library = delivered_root.find("library")
    if library is None or library.get("location") is not None:
        raise ValueError("delivered FCPXML must have a location-free library")
    events = library.findall("event")
    if len(events) != 1 or events[0].attrib != {"name": expected_event_name}:
        raise ValueError("delivered FCPXML Event identity is invalid")
    project = _single_project(delivered_root, "delivered FCPXML")
    source_project_name = _single_project(source_root, "source FCPXML").get("name") or "Project"
    if project.attrib != {"name": f"{expected_event_name}__{source_project_name}"}:
        raise ValueError("delivered FCPXML Project identity is invalid")

    resources = delivered_root.find("resources")
    sequence = project.find("sequence")
    spine = None if sequence is None else sequence.find("spine")
    if resources is None or spine is None:
        raise ValueError("delivered FCPXML lacks resources or spine")
    expected_names = {f"AF__{cue['id']}" for cue in animated}
    intervals = _global_afterforge_intervals(spine, expected_names)
    if set(intervals) != expected_names:
        raise ValueError(
            f"AfterForge connected clips differ: expected {sorted(expected_names)}, "
            f"found {sorted(intervals)}"
        )

    resource_ids: set[str] = set()
    for cue in animated:
        cue_id = cue["id"]
        asset = cue["deliveryAsset"]
        resource_matches = [item for item in resources.findall("asset") if item.get("name") == asset["fileName"]]
        if len(resource_matches) != 1:
            raise ValueError(f"expected exactly one AfterForge asset resource: {cue_id}")
        resource = resource_matches[0]
        resource_ids.add(resource.get("id"))
        media_reps = resource.findall("media-rep")
        if (
            resource.get("hasVideo") != "1"
            or resource.get("hasAudio") is not None
            or resource.get("duration") != asset["duration"]
            or len(media_reps) != 1
            or media_reps[0].get("kind") != "original-media"
            or media_reps[0].get("src") != f"./{asset['fileName']}"
        ):
            raise ValueError(f"AfterForge asset resource is not pure relative video: {cue_id}")
        if any(item.tag.startswith("audio") for item in resource.iter()):
            raise ValueError(f"AfterForge asset resource contains audio: {cue_id}")

        anchor_name = f"AF__{cue_id}"
        anchor_matches = [item for item in spine.iter("asset-clip") if item.get("name") == anchor_name]
        if len(anchor_matches) != 1:
            raise ValueError(f"expected exactly one AfterForge connected clip: {cue_id}")
        anchor = anchor_matches[0]
        if anchor.get("ref") != resource.get("id") or anchor.get("srcEnable") != "video":
            raise ValueError(f"AfterForge connected clip reference is invalid: {cue_id}")
        interval = intervals[anchor_name]
        if interval.start != parse_time(cue["resolvedTimeline"]["start"]):
            raise ValueError(f"AfterForge connected clip position changed: {cue_id}")
        if interval.duration != parse_time(asset["duration"]):
            raise ValueError(f"AfterForge connected clip duration changed: {cue_id}")

    if len(resource_ids) != len(animated):
        raise ValueError("AfterForge asset resources are not independent")
    _assert_no_lane_overlap(spine)
    _assert_source_sequence_unchanged(source_root, delivered_root, {cue["id"] for cue in animated})

    if dtd_path is not None:
        dtd = Path(dtd_path).expanduser().resolve()
        if not dtd.is_file() or dtd.is_symlink():
            raise ValueError(f"DTD is missing or unsafe: {dtd}")
        completed = subprocess.run(
            ["xmllint", "--noout", "--dtdvalid", dtd.as_uri(), str(info)],
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise ValueError(f"FCPXML DTD validation failed: {detail}")

    return {
        "status": "valid",
        "packagePath": str(package),
        "animatedCueIds": [cue["id"] for cue in animated],
        "sourceOnlyCueIds": sorted(
            cue["id"] for cue in manifest["cues"] if cue.get("productionMode") == "source-only"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="验证 AfterForge 扁平 FCPXMLD 交付包。")
    parser.add_argument("package_root", type=Path)
    parser.add_argument("source_xml", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--dtd", type=Path)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        result = validate_delivery_package(
            args.package_root,
            args.source_xml,
            manifest,
            dtd_path=args.dtd,
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
