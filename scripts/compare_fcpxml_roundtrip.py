#!/usr/bin/env python3
"""Compare a delivered FCPXML with a Final Cut Pro re-export semantically."""

from __future__ import annotations

try:
    from scripts.rework_state import revision_evidence
except ModuleNotFoundError:
    from rework_state import revision_evidence

try:
    from scripts.manifest_transaction import manifest_commit, optimistic_operation
except ModuleNotFoundError:  # direct script execution
    from manifest_transaction import manifest_commit, optimistic_operation

import argparse
import hashlib
import json
from fractions import Fraction
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree as ET

try:
    from scripts.fcpxml_text_style import PROFILE, TextStyleNormalization
except ModuleNotFoundError:
    from fcpxml_text_style import PROFILE, TextStyleNormalization

try:
    from scripts.hyperframes_adapter import load_manifest, parse_time, save_manifest
    from scripts.validate_fcpxml_package import (
        _global_afterforge_intervals,
        _remove_afterforge_anchors,
    )
    from scripts.workflow_status import resolve_stage_status
except ModuleNotFoundError:
    from hyperframes_adapter import load_manifest, parse_time, save_manifest  # type: ignore
    from validate_fcpxml_package import (  # type: ignore
        _global_afterforge_intervals,
        _remove_afterforge_anchors,
    )
    from workflow_status import resolve_stage_status  # type: ignore


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


def _resource_identity(resource: ET.Element) -> tuple[Any, ...]:
    uid = resource.get("uid")
    if uid:
        return resource.tag, "uid", uid
    if resource.tag == "asset":
        media = resource.findall("media-rep")
        basename = _media_basename(media[0].get("src")) if len(media) == 1 else None
        return resource.tag, "media", basename, resource.get("name")
    attributes = tuple(
        sorted(
            (key, _canonical_time(value))
            for key, value in resource.attrib.items()
            if key != "id"
        )
    )
    return resource.tag, attributes


def _resource_map(root: ET.Element) -> dict[str, tuple[Any, ...]]:
    resources = root.find("resources")
    if resources is None:
        raise ValueError("round-trip FCPXML lacks resources")
    return {
        resource_id: _resource_identity(resource)
        for resource in resources
        if (resource_id := resource.get("id"))
    }


def _canonical_time(value: str) -> str:
    if not value.endswith("s"):
        return value
    try:
        fraction = parse_time(value)
    except ValueError:
        return value
    if fraction.denominator == 1:
        return f"{fraction.numerator}s"
    return f"{fraction.numerator}/{fraction.denominator}s"


def _source_story_equal(
    delivered: ET.Element,
    reexported: ET.Element,
    delivered_resources: dict[str, tuple[Any, ...]],
    reexported_resources: dict[str, tuple[Any, ...]],
    *,
    normalization=None,
    basic_title=False,
    path="sequence",
) -> bool:
    if delivered.tag != reexported.tag:
        return False
    if delivered.tag == "title":
        basic_title = bool(normalization and normalization.is_basic_title(
            delivered, reexported, delivered_resources, reexported_resources))
    children = (normalization.children(delivered, reexported, path)
                if basic_title and delivered.tag == "title" else list(delivered))
    if len(children) != len(reexported):
        return False
    delivered_text = delivered.text if delivered.text and delivered.text.strip() else None
    reexported_text = reexported.text if reexported.text and reexported.text.strip() else None
    if delivered_text != reexported_text or set(delivered.attrib) != set(reexported.attrib):
        return False

    for key in delivered.attrib:
        left = delivered.attrib[key]
        right = reexported.attrib[key]
        if key in {"ref", "format"} and left in delivered_resources and right in reexported_resources:
            if delivered_resources[left] != reexported_resources[right]:
                return False
            continue
        if left.endswith("s") and right.endswith("s"):
            try:
                difference = abs(parse_time(left) - parse_time(right))
            except ValueError:
                difference = None
            if difference is not None:
                tolerance = Fraction(1, 1_000_000) if delivered.tag == "timept" and key in {"time", "value"} else Fraction(0)
                if difference > tolerance:
                    return False
                continue
        if left != right and not (basic_title and delivered.tag == "text-style" and not len(delivered)
                                  and normalization.color_equal(key, left, right, path)):
            return False

    return all(
        _source_story_equal(left, right, delivered_resources, reexported_resources,
                           normalization=normalization, basic_title=basic_title,
                           path=f"{path}/{index}/{left.tag}")
        for index, (left, right) in enumerate(zip(children, reexported))
    )


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
    delivered_spine = delivered_sequence.find("spine")
    spine = reexported_sequence.find("spine")
    resources = reexported_root.find("resources")
    if delivered_spine is None or spine is None or resources is None:
        raise ValueError("round-trip FCPXML lacks resources or spine")

    all_afterforge_names = {
        item.get("name")
        for item in spine.iter("asset-clip")
        if item.get("name", "").startswith("AF__")
    }
    delivered_names = {item.get('name') for item in delivered_spine.iter('asset-clip') if item.get('name', '').startswith('AF__')}
    if all_afterforge_names != delivered_names:
        raise ValueError(
            f"round-trip animation cue set changed: expected {sorted(expected_names)}, "
            f"found {sorted(all_afterforge_names)}"
        )
    intervals = _global_afterforge_intervals(spine, expected_names)
    if set(intervals) != expected_names:
        raise ValueError("round-trip animation placement set changed")
    delivered_intervals = _global_afterforge_intervals(delivered_spine, expected_names)
    if set(delivered_intervals) != expected_names:
        raise ValueError("delivered animation placement set changed")

    for cue in animated:
        cue_id = cue["id"]
        asset = cue["deliveryAsset"]
        resource = _resource_for_file(resources, asset["fileName"])
        _assert_pure_video(resource, cue_id)
        if resource.get("duration") is not None:
            registered_duration = parse_time(asset["duration"])
            physical_duration = parse_time(resource.get("duration"))
            frame_duration = parse_time(manifest["project"]["source"]["frameDuration"])
            if not registered_duration <= physical_duration <= registered_duration + frame_duration:
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
        delivered_interval = delivered_intervals[anchor_name]
        if interval.start != delivered_interval.start:
            raise ValueError(f"round-trip animation connected clip position changed: {cue_id}")
        if interval.duration != delivered_interval.duration:
            raise ValueError(f"round-trip animation connected clip duration changed: {cue_id}")
        if interval.duration != parse_time(asset["duration"]):
            raise ValueError(f"round-trip animation connected clip duration changed: {cue_id}")
        semantic_start = parse_time(cue["resolvedTimeline"]["start"])
        semantic_duration = parse_time(cue["resolvedTimeline"]["duration"])
        if not semantic_start <= interval.start < semantic_start + semantic_duration:
            raise ValueError(f"round-trip animation moved outside its semantic range: {cue_id}")

    delivered_map, reexported_map = _resource_map(delivered_root), _resource_map(reexported_root)
    normalization = TextStyleNormalization(delivered_root, reexported_root)
    formal_hashes = []
    if manifest.get('delivery', {}).get('protocolVersion') == '3':
        from scripts.delivery_media import reachable_assets, media_path
        from scripts.work_model_store import sha
        delivered_assets, exported_assets = reachable_assets(delivered_root), reachable_assets(reexported_root)
        by_name = {m['fileName']: m for m in manifest['delivery']['media']}
        observed = set()
        delivered_by_hash = {}
        for original in delivered_assets.values():
            rep = next((r for r in original.findall('media-rep') if r.get('kind') == 'original-media'), None)
            name = _media_basename(rep.get('src')) if rep is not None else None
            if name in by_name: delivered_by_hash.setdefault(by_name[name]['sha256'], []).append(original)
        def same_media_timing(original, exported):
            before_fmt = delivered_root.find(f"resources/format[@id='{original.get('format')}']")
            after_fmt = reexported_root.find(f"resources/format[@id='{exported.get('format')}']")
            if before_fmt is None or after_fmt is None: return False
            if any(before_fmt.get(k) != after_fmt.get(k) for k in ('width','height')): return False
            frame = parse_time(before_fmt.get('frameDuration'))
            if parse_time(after_fmt.get('frameDuration')) != frame: return False
            if parse_time(original.get('start','0s')) != parse_time(exported.get('start','0s')): return False
            before_duration = parse_time(original.get('duration'))
            after_duration = parse_time(exported.get('duration'))
            return before_duration <= after_duration <= before_duration + frame
        for key, asset in exported_assets.items():
            rep = next((r for r in asset.findall('media-rep') if r.get('kind') == 'original-media'), None)
            if rep is None: raise ValueError('round-trip asset lacks original media')
            path = media_path(rep.get('src',''), Path(reexported_xml).parent)
            checksum = sha(path) if path and path.is_file() and path.suffix.lower() == '.mov' else None
            matched = next((m for m in by_name.values() if m['sha256'] == checksum), None)
            if _media_basename(rep.get('src')) in by_name and matched is None:
                raise ValueError('round-trip formal media missing or changed: '+rep.get('src'))
            if matched:
                _assert_pure_video(asset, matched['fileName'])
                if not any(same_media_timing(original, asset) for original in delivered_by_hash[checksum]):
                    raise ValueError('round-trip formal media timing/format changed: '+matched['fileName'])
                observed.add(checksum)
                reexported_map[key] = ('asset', 'AfterForge-sha256', checksum)
        if observed != {m['sha256'] for m in by_name.values()}:
            raise ValueError('round-trip does not cover every formal animation MOV')
        for key, asset in delivered_assets.items():
            rep = next((r for r in asset.findall('media-rep') if r.get('kind') == 'original-media'), None)
            name = _media_basename(rep.get('src')) if rep is not None else None
            if name in by_name: delivered_map[key] = ('asset', 'AfterForge-sha256', by_name[name]['sha256'])
        # Compound/multicam references cannot hide a changed nested animation.
        exported_resources = reexported_root.find('resources')
        for resource in delivered_root.find('resources'):
            if resource.tag != 'media': continue
            matches = [r for r in exported_resources if reexported_map.get(r.get('id')) == delivered_map.get(resource.get('id'))]
            if len(matches) != 1: raise ValueError('round-trip nested resource missing')
            left, right = ET.fromstring(ET.tostring(resource)), ET.fromstring(ET.tostring(matches[0]))
            left.attrib.pop('id', None); right.attrib.pop('id', None)
            if not _source_story_equal(left,right,delivered_map,reexported_map,
                                      normalization=normalization, path=f"resource/{resource.get('id')}"):
                raise ValueError('round-trip nested storyline changed')
        formal_hashes = sorted(observed)
    delivered_clean = _remove_afterforge_anchors(delivered_sequence, cue_ids)
    reexported_clean = _remove_afterforge_anchors(reexported_sequence, cue_ids)
    if not _source_story_equal(
        delivered_clean,
        reexported_clean,
        delivered_map,
        reexported_map,
        normalization=normalization,
    ):
        raise ValueError("round-trip source storyline changed")

    return {
        "status": "valid",
        "deliveredXml": str(Path(delivered_xml).expanduser().resolve()),
        "reexportedXml": str(Path(reexported_xml).expanduser().resolve()),
        "animatedCueIds": [cue["id"] for cue in animated],
        "formalMediaSha256": formal_hashes,
        "normalizationProfile": PROFILE if normalization.records else None,
        "normalizations": normalization.records,
        "sourceOnlyCueIds": sorted(
            cue["id"] for cue in manifest.get("cues", []) if cue.get("productionMode") == "source-only"
        ),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).expanduser().resolve().read_bytes()).hexdigest()


@optimistic_operation
def register_roundtrip(version_root: Path, reexported_xml: Path) -> dict[str, Any]:
    root = Path(version_root).expanduser().resolve()
    stage_status = resolve_stage_status(root)
    if stage_status.get("nextEligibleStage") != "D6":
        raise ValueError(
            "round-trip registration requires current D5 Final Cut Pro acceptance; "
            f"blocked at {stage_status.get('blockingStage')}"
        )
    manifest = load_manifest(root)
    workflow = manifest["workflow"]
    d4 = workflow["stageEvidence"]["D4"]
    delivered = root.parent / d4["packageName"] / "Info.fcpxml"
    reexported = Path(reexported_xml).expanduser().resolve()
    compared_hashes = (_sha256(delivered), _sha256(reexported))
    result = compare_roundtrip(delivered, reexported, manifest)
    evidence = {
        "stageId": "D6",
        **revision_evidence(manifest),
        "contractVersion": workflow["stageContractVersion"],
        "semanticVersion": 1,
        "status": "valid",
        "deliveryFingerprint": d4["deliveryFingerprint"],
        "deliveredSha256": compared_hashes[0],
        "reexportedPath": str(reexported),
        "reexportedSha256": compared_hashes[1],
        "animatedCueIds": result["animatedCueIds"],
    }
    with manifest_commit(root):
        if resolve_stage_status(root).get("nextEligibleStage") != "D6":
            raise ValueError("round-trip registration requires current D5 inputs after comparison")
        if (_sha256(delivered), _sha256(reexported)) != compared_hashes:
            raise ValueError("round-trip XML inputs changed during comparison")
        workflow["stageEvidence"]["D6"] = evidence
        save_manifest(root, manifest)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="比较 FCP 导入后再导出的 FCPXML 语义。")
    parser.add_argument("delivered_xml", type=Path)
    parser.add_argument("reexported_xml", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--register-vn",
        type=Path,
        help="验证后把 D6 evidence 写入这个明确指定的 Vn。",
    )
    args = parser.parse_args()
    try:
        if args.register_vn is not None:
            registered_manifest = load_manifest(args.register_vn)
            d4 = registered_manifest.get("workflow", {}).get("stageEvidence", {}).get("D4", {})
            expected_delivered = args.register_vn.expanduser().resolve().parent / d4.get("packageName", "") / "Info.fcpxml"
            if args.delivered_xml.expanduser().resolve() != expected_delivered:
                raise ValueError("delivered_xml does not match the Vn D4 package")
            result = register_roundtrip(args.register_vn, args.reexported_xml)
        else:
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            result = compare_roundtrip(args.delivered_xml, args.reexported_xml, manifest)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
