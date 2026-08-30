#!/usr/bin/env python3
"""Build a deterministic FCPXML document with registered animation clips."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

try:
    from scripts.fcpxml_timing import (
        TimelineInterval,
        allocate_lanes,
        anchor_offset,
        collect_positive_anchors,
        find_primary_host,
        format_time,
    )
    from scripts.hyperframes_adapter import parse_time
except ModuleNotFoundError:
    from fcpxml_timing import (  # type: ignore
        TimelineInterval,
        allocate_lanes,
        anchor_offset,
        collect_positive_anchors,
        find_primary_host,
        format_time,
    )
    from hyperframes_adapter import parse_time  # type: ignore


@dataclass(frozen=True)
class DeliveryDocument:
    xml_bytes: bytes
    delivery_format_id: str
    resource_ids: dict[str, str]
    placements: list[dict[str, Any]]
    fingerprint_inputs: dict[str, Any]


class _ResourceIdAllocator:
    def __init__(self, resources: ET.Element) -> None:
        self._used = {item.get("id") for item in resources if item.get("id")}
        numeric = [int(match.group(1)) for value in self._used if (match := re.fullmatch(r"r(\d+)", value))]
        self._next = max(numeric, default=0) + 1

    def next(self) -> str:
        while f"r{self._next}" in self._used:
            self._next += 1
        value = f"r{self._next}"
        self._used.add(value)
        self._next += 1
        return value


def _single_source_project(root: ET.Element) -> ET.Element:
    projects = root.findall(".//project")
    if len(projects) != 1:
        raise ValueError(f"source FCPXML must contain exactly one Project, found {len(projects)}")
    return projects[0]


def _source_library(root: ET.Element) -> ET.Element | None:
    return root.find("library")


def _delivery_spec(manifest: dict[str, Any]) -> tuple[int, int, Fraction]:
    project = manifest.get("project")
    if not isinstance(project, dict):
        raise ValueError("manifest project is missing")
    delivery = project.get("delivery")
    source = project.get("source")
    if not isinstance(delivery, dict) or not isinstance(source, dict):
        raise ValueError("manifest source/delivery specifications are missing")
    width = int(delivery["width"])
    height = int(delivery["height"])
    frame_duration = parse_time(source["frameDuration"])
    if width <= 0 or height <= 0 or frame_duration <= 0:
        raise ValueError("manifest delivery dimensions and frame duration must be positive")
    return width, height, frame_duration


def _find_or_add_delivery_format(
    resources: ET.Element,
    allocator: _ResourceIdAllocator,
    *,
    width: int,
    height: int,
    frame_duration: Fraction,
) -> str:
    for item in resources.findall("format"):
        if (
            item.get("width") == str(width)
            and item.get("height") == str(height)
            and item.get("frameDuration") is not None
            and parse_time(item.get("frameDuration")) == frame_duration
        ):
            return item.get("id")

    resource_id = allocator.next()
    fps = frame_duration.denominator // frame_duration.numerator if frame_duration.numerator else 0
    attributes = {
        "id": resource_id,
        "name": f"FFVideoFormat{height}p{fps}",
        "frameDuration": format_time(frame_duration),
        "width": str(width),
        "height": str(height),
    }
    resources.append(ET.Element("format", attributes))
    return resource_id


def _animated_cues(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    cues = manifest.get("cues")
    if not isinstance(cues, list):
        raise ValueError("manifest cues must be a list")
    animated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for cue in cues:
        if not isinstance(cue, dict) or not isinstance(cue.get("id"), str):
            raise ValueError("each manifest cue must have an id")
        cue_id = cue["id"]
        if cue_id in seen:
            raise ValueError(f"duplicate cue id: {cue_id}")
        seen.add(cue_id)
        mode = cue.get("productionMode")
        if mode == "source-only":
            if "deliveryAsset" in cue:
                raise ValueError(f"source-only cue cannot have deliveryAsset: {cue_id}")
            continue
        if mode != "animation" or not isinstance(cue.get("deliveryAsset"), dict):
            raise ValueError(f"animated cue is not registered for delivery: {cue_id}")
        animated.append(cue)
    return sorted(animated, key=lambda item: item["id"])


def _insert_anchor(host: ET.Element, anchor: ET.Element) -> None:
    post_anchor_tags = {
        "marker",
        "chapter-marker",
        "rating",
        "keyword",
        "analysis-marker",
        "hidden-clip-marker",
        "audio-channel-source",
        "audio-role-source",
        "sync-source",
        "filter-video",
        "filter-video-mask",
        "filter-audio",
        "metadata",
        "reserved",
    }
    children = list(host)
    for index, child in enumerate(children):
        if child.tag in post_anchor_tags:
            host.insert(index, anchor)
            return
    host.append(anchor)


def _serialize(root: ET.Element) -> bytes:
    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="utf-8", short_empty_elements=True)
    return b'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n' + body + b"\n"


def build_delivery_fcpxml(source_xml: Path, manifest: dict[str, Any]) -> DeliveryDocument:
    source_xml = Path(source_xml)
    try:
        source_root = ET.parse(source_xml).getroot()
    except (ET.ParseError, OSError) as error:
        raise ValueError(f"cannot parse source FCPXML: {source_xml}") from error
    if source_root.tag != "fcpxml":
        raise ValueError("source XML root must be fcpxml")

    source_resources = source_root.find("resources")
    if source_resources is None:
        raise ValueError("source FCPXML has no resources")
    source_project = _single_source_project(source_root)
    source_sequence = source_project.find("sequence")
    if source_sequence is None or source_sequence.find("spine") is None:
        raise ValueError("source Project has no sequence/spine")

    output_root = ET.Element("fcpxml", dict(source_root.attrib))
    resources = copy.deepcopy(source_resources)
    output_root.append(resources)
    source_library = _source_library(source_root)
    library_attributes = {} if source_library is None else {
        key: value for key, value in source_library.attrib.items() if key != "location"
    }
    library = ET.SubElement(output_root, "library", library_attributes)
    source_version = manifest.get("sourceVersion")
    if not isinstance(source_version, str) or not source_version:
        raise ValueError("manifest sourceVersion is missing")
    event = ET.SubElement(library, "event", {"name": f"AfterForge__{source_version}"})
    source_project_name = source_project.get("name") or "Project"
    project = ET.SubElement(
        event,
        "project",
        {"name": f"AfterForge__{source_version}__{source_project_name}"},
    )
    sequence = copy.deepcopy(source_sequence)
    project.append(sequence)
    spine = sequence.find("spine")

    width, height, frame_duration = _delivery_spec(manifest)
    allocator = _ResourceIdAllocator(resources)
    delivery_format_id = _find_or_add_delivery_format(
        resources,
        allocator,
        width=width,
        height=height,
        frame_duration=frame_duration,
    )

    cues = _animated_cues(manifest)
    requests: list[TimelineInterval] = []
    cue_by_id: dict[str, dict[str, Any]] = {}
    for cue in cues:
        cue_id = cue["id"]
        timeline = cue.get("resolvedTimeline")
        asset = cue["deliveryAsset"]
        if not isinstance(timeline, dict):
            raise ValueError(f"cue has no resolvedTimeline: {cue_id}")
        start = parse_time(timeline["start"])
        duration = parse_time(asset["duration"])
        requests.append(TimelineInterval(cue_id, start, duration))
        cue_by_id[cue_id] = cue
    lanes = allocate_lanes(requests, collect_positive_anchors(spine))

    resource_ids: dict[str, str] = {}
    placements: list[dict[str, Any]] = []
    for request in sorted(requests, key=lambda item: (item.start, item.key)):
        cue = cue_by_id[request.key]
        asset = cue["deliveryAsset"]
        file_name = asset.get("fileName")
        if not isinstance(file_name, str) or not file_name or Path(file_name).name != file_name:
            raise ValueError(f"invalid deliveryAsset fileName: {request.key}")
        if int(asset.get("width", 0)) != width or int(asset.get("height", 0)) != height:
            raise ValueError(f"deliveryAsset dimensions do not match project delivery spec: {request.key}")
        if Fraction(str(asset.get("frameRate"))) != Fraction(1, 1) / frame_duration:
            raise ValueError(f"deliveryAsset frame rate does not match source: {request.key}")

        resource_id = allocator.next()
        resource_ids[request.key] = resource_id
        resource = ET.SubElement(
            resources,
            "asset",
            {
                "id": resource_id,
                "name": file_name,
                "start": "0s",
                "duration": format_time(request.duration),
                "hasVideo": "1",
                "format": delivery_format_id,
                "videoSources": "1",
            },
        )
        ET.SubElement(resource, "media-rep", {"kind": "original-media", "src": f"./{file_name}"})

        host = find_primary_host(spine, request.start)
        local_offset = anchor_offset(host, request.start)
        lane = lanes[request.key]
        anchor = ET.Element(
            "asset-clip",
            {
                "name": f"AF__{request.key}",
                "ref": resource_id,
                "lane": str(lane),
                "offset": format_time(local_offset),
                "start": "0s",
                "duration": format_time(request.duration),
                "format": delivery_format_id,
                "srcEnable": "video",
                "videoRole": "video",
            },
        )
        _insert_anchor(host.element, anchor)
        placements.append(
            {
                "cueId": request.key,
                "sequenceStart": format_time(request.start),
                "duration": format_time(request.duration),
                "lane": lane,
                "hostName": host.element.get("name") or host.element.tag,
                "hostOffset": format_time(host.sequence_start),
                "hostStart": format_time(host.local_start),
                "anchorOffset": format_time(local_offset),
                "resourceId": resource_id,
                "fileName": file_name,
            }
        )

    fingerprint_inputs = {
        "sourceVersion": source_version,
        "sourceProjectName": source_project_name,
        "placements": [
            {
                "cueId": item["cueId"],
                "sequenceStart": item["sequenceStart"],
                "duration": item["duration"],
                "lane": item["lane"],
                "fileName": item["fileName"],
            }
            for item in placements
        ],
    }
    return DeliveryDocument(
        xml_bytes=_serialize(output_root),
        delivery_format_id=delivery_format_id,
        resource_ids=resource_ids,
        placements=placements,
        fingerprint_inputs=fingerprint_inputs,
    )
