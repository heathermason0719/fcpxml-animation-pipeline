#!/usr/bin/env python3
"""Publish an immutable, flat, fingerprinted AfterForge FCPXMLD package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Sequence
from xml.etree import ElementTree as ET

try:
    from scripts.hyperframes_adapter import load_manifest, save_manifest
    from scripts.inject_fcpxml import build_delivery_fcpxml
    from scripts.layout_lock import verify_layouts
    from scripts.manifest_transaction import manifest_commit, optimistic_operation
    from scripts.validate_fcpxml_package import sha256_file, validate_delivery_package
    from scripts.workflow_inputs import require_current_input_evidence
    from scripts.workflow_status import resolve_stage_status
except ModuleNotFoundError:
    from hyperframes_adapter import load_manifest, save_manifest  # type: ignore
    from inject_fcpxml import build_delivery_fcpxml  # type: ignore
    from layout_lock import verify_layouts  # type: ignore
    from manifest_transaction import manifest_commit, optimistic_operation  # type: ignore
    from validate_fcpxml_package import sha256_file, validate_delivery_package  # type: ignore
    from workflow_inputs import require_current_input_evidence  # type: ignore
    from workflow_status import resolve_stage_status  # type: ignore


DELIVERY_PROTOCOL_VERSION = "1"


def _canonical_records(records: Sequence[dict[str, Any]], label: str) -> list[dict[str, Any]]:
    normalized = [dict(item) for item in records]
    if any(not isinstance(item.get("cueId"), str) for item in normalized):
        raise ValueError(f"every {label} record must have cueId")
    cue_ids = [item["cueId"] for item in normalized]
    if len(cue_ids) != len(set(cue_ids)):
        raise ValueError(f"duplicate cueId in {label} records")
    return sorted(normalized, key=lambda item: item["cueId"])


def delivery_fingerprint(
    source_sha256: str,
    delivery_assets: Sequence[dict[str, Any]],
    placements: Sequence[dict[str, Any]],
    protocol_version: str,
) -> str:
    if not isinstance(source_sha256, str) or len(source_sha256) != 64:
        raise ValueError("source SHA-256 must be a 64-character string")
    if not isinstance(protocol_version, str) or not protocol_version:
        raise ValueError("delivery protocol version must be non-empty")
    payload = {
        "deliveryProtocolVersion": protocol_version,
        "sourceFcpxmlSha256": source_sha256,
        "deliveryAssets": _canonical_records(delivery_assets, "delivery asset"),
        "placements": _canonical_records(placements, "placement"),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _resolve_source_xml(version_root: Path, manifest: dict[str, Any]) -> Path:
    relative = manifest.get("project", {}).get("source", {}).get("fcpxml")
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError("project.source.fcpxml must be a non-empty workspace-relative path")
    workspace = version_root.parent.parent.resolve()
    source = (version_root / relative).resolve(strict=False)
    try:
        workspace_relative = source.relative_to(workspace)
    except ValueError as error:
        raise ValueError("source FCPXML escapes the project workspace") from error
    if not workspace_relative.parts or workspace_relative.parts[0] != "user-inbox":
        raise ValueError("source FCPXML must resolve inside project user-inbox")
    if not source.is_file() or source.is_symlink():
        raise ValueError(f"source FCPXML is missing or unsafe: {source}")
    expected_hash = manifest.get("sourceHashes", {}).get("fcpxml")
    actual_hash = sha256_file(source)
    if not isinstance(expected_hash, str) or actual_hash != expected_hash:
        raise ValueError("source FCPXML hash does not match manifest")
    return source


def _animated_cues(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    animated: list[dict[str, Any]] = []
    file_names: set[str] = set()
    for cue in manifest["cues"]:
        mode = cue.get("productionMode")
        if mode == "source-only":
            if "deliveryAsset" in cue:
                raise ValueError(f"source-only cue cannot have deliveryAsset: {cue.get('id')}")
            continue
        if mode != "animation" or not isinstance(cue.get("deliveryAsset"), dict):
            raise ValueError(f"animated cue is not registered: {cue.get('id')}")
        file_name = cue["deliveryAsset"].get("fileName")
        if not isinstance(file_name, str) or Path(file_name).name != file_name:
            raise ValueError(f"unsafe deliveryAsset fileName: {cue.get('id')}")
        if file_name in file_names:
            raise ValueError(f"duplicate deliveryAsset fileName: {file_name}")
        file_names.add(file_name)
        animated.append(cue)
    if not animated:
        raise ValueError("manifest contains no animated cues")
    return sorted(animated, key=lambda item: item["id"])


def _verify_a11(version_root: Path, manifest: dict[str, Any], animated: list[dict[str, Any]]) -> None:
    expected = {cue["id"] for cue in animated}
    if any(not cue.get("renderAdapters", {}).get("hyperframes", {}).get("layoutLock") for cue in animated):
        raise ValueError("every animated cue must have an A11 layout lock")
    verification = verify_layouts(version_root)
    if verification.get("status") != "valid" or set(verification.get("checkedCueIds", [])) != expected:
        raise ValueError(f"A11 layout locks are invalid or incomplete: {verification}")


def _record_d4(
    root: Path,
    package: Path,
    fingerprint: str,
    publication_status: str,
) -> None:
    manifest = load_manifest(root)
    workflow = manifest["workflow"]
    workflow.setdefault("stageEvidence", {})["D4"] = {
        "stageId": "D4",
        "contractVersion": workflow["stageContractVersion"],
        "semanticVersion": 1,
        "status": "published",
        "publicationStatus": publication_status,
        "packageName": package.name,
        "deliveryFingerprint": fingerprint,
        "infoFcpxmlSha256": sha256_file(package / "Info.fcpxml"),
    }
    save_manifest(root, manifest)


def _resolve_canonical_movies(
    version_root: Path,
    animated: list[dict[str, Any]],
) -> dict[str, Path]:
    source_dir = version_root / "delivery/prores4444"
    if not source_dir.is_dir() or source_dir.is_symlink():
        raise ValueError(f"canonical delivery movie directory is missing or unsafe: {source_dir}")
    candidates = [
        path for path in source_dir.iterdir()
        if path.is_file() and not path.is_symlink()
    ]
    hashes: dict[str, list[Path]] = {}
    for candidate in candidates:
        hashes.setdefault(sha256_file(candidate), []).append(candidate)
    resolved: dict[str, Path] = {}
    for cue in animated:
        cue_id = cue["id"]
        expected_hash = cue["deliveryAsset"].get("sha256")
        matches = hashes.get(expected_hash, [])
        if len(matches) != 1:
            raise ValueError(
                f"expected exactly one canonical MOV matching registered hash for {cue_id}, "
                f"found {len(matches)}"
            )
        resolved[cue_id] = matches[0]
    return resolved


def _materialize_movie(source: Path, target: Path) -> str:
    try:
        os.link(source, target)
        return "hardlink"
    except OSError:
        shutil.copy2(source, target)
        return "copy"


def default_dtd_path(source_xml: Path) -> Path:
    try:
        version = ET.parse(source_xml).getroot().get("version")
    except (ET.ParseError, OSError) as error:
        raise ValueError(f"cannot determine FCPXML version: {source_xml}") from error
    if not version or not version.replace(".", "_").replace("_", "").isdigit():
        raise ValueError(f"unsupported FCPXML version: {version!r}")
    dtd = Path(
        "/Applications/Final Cut Pro.app/Contents/Frameworks/Interchange.framework/"
        f"Versions/A/Resources/FCPXMLv{version.replace('.', '_')}.dtd"
    )
    if not dtd.is_file():
        raise ValueError(f"Final Cut Pro DTD is unavailable for FCPXML {version}: {dtd}")
    return dtd


def _package_file_hashes(package: Path) -> dict[str, str]:
    """Ephemeral validation snapshot, not a second delivery authority."""
    if not package.is_dir() or package.is_symlink():
        raise ValueError("delivery package changed or is not a regular directory")
    files: dict[str, str] = {}
    for path in package.iterdir():
        if not path.is_file() or path.is_symlink():
            raise ValueError("delivery package contains a non-regular file")
        files[path.name] = sha256_file(path)
    return files


def _assert_validated_package_current(
    root: Path, source: Path, source_hash: str,
    package: Path, validated_files: dict[str, str],
) -> dict[str, Any]:
    """Recheck file-only changes as well as the caller's manifest CAS."""
    status = resolve_stage_status(root)
    if status.get("evidence", {}).get("D3") not in {"current", "compatible-historical"}:
        raise ValueError("delivery package requires current D3 inputs after validation")
    if sha256_file(source) != source_hash:
        raise ValueError("source FCPXML changed during package validation")
    if _package_file_hashes(package) != validated_files:
        raise ValueError("delivery package bytes changed during validation")
    return status


@optimistic_operation
def build_delivery_package(
    version_root: Path,
    *,
    dtd_path: Path | None = None,
) -> dict[str, Any]:
    root = Path(version_root).expanduser().resolve()
    stage_status = resolve_stage_status(root)
    if stage_status.get("evidence", {}).get("D3") not in {"current", "compatible-historical"}:
        raise ValueError(
            "delivery package build requires current D3 registration evidence; "
            f"blocked at {stage_status.get('blockingStage')}"
        )
    manifest = load_manifest(root)
    animated = _animated_cues(manifest)
    _verify_a11(root, manifest, animated)
    source_xml = _resolve_source_xml(root, manifest)
    source_hash = sha256_file(source_xml)
    canonical_movies = _resolve_canonical_movies(root, animated)

    document = build_delivery_fcpxml(source_xml, manifest)
    delivery_assets = [
        {"cueId": cue["id"], **cue["deliveryAsset"]}
        for cue in animated
    ]
    fingerprint = delivery_fingerprint(
        source_hash,
        delivery_assets,
        document.fingerprint_inputs["placements"],
        DELIVERY_PROTOCOL_VERSION,
    )
    package_name = f"AfterForge__{manifest['sourceVersion']}__d-{fingerprint}.fcpxmld"
    package_parent = root.parent
    target = package_parent / package_name
    if target.exists():
        try:
            validated_files = _package_file_hashes(target)
            validation = validate_delivery_package(
                target,
                source_xml,
                manifest,
                dtd_path=dtd_path,
            )
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
            raise ValueError(f"existing delivery package is invalid: {error}") from error
        result = {
            **validation,
            "status": "reused",
            "deliveryFingerprint": fingerprint,
            "deliveryProtocolVersion": DELIVERY_PROTOCOL_VERSION,
        }
        with manifest_commit(root):
            final_status = _assert_validated_package_current(root, source_xml, source_hash, target, validated_files)
            recorded_d4 = manifest.get("workflow", {}).get("stageEvidence", {}).get("D4")
            same_registered_package = (
                final_status.get("evidence", {}).get("D4") in {"current", "compatible-historical"}
                and isinstance(recorded_d4, dict)
                and recorded_d4.get("packageName") == target.name
                and recorded_d4.get("deliveryFingerprint") == fingerprint
                and recorded_d4.get("infoFcpxmlSha256") == validated_files["Info.fcpxml"]
            )
            if not same_registered_package:
                require_current_input_evidence(root, manifest)
                _record_d4(root, target, fingerprint, "reused")
        return result

    require_current_input_evidence(root, manifest)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{package_name}.tmp-",
            suffix=".fcpxmld",
            dir=package_parent,
        )
    )
    methods: dict[str, str] = {}
    try:
        (temporary / "Info.fcpxml").write_bytes(document.xml_bytes)
        for cue in animated:
            cue_id = cue["id"]
            target_movie = temporary / cue["deliveryAsset"]["fileName"]
            methods[cue_id] = _materialize_movie(canonical_movies[cue_id], target_movie)
            if sha256_file(target_movie) != cue["deliveryAsset"]["sha256"]:
                raise ValueError(f"materialized delivery movie hash mismatch: {cue_id}")
        validated_files = _package_file_hashes(temporary)
        validate_delivery_package(temporary, source_xml, manifest, dtd_path=dtd_path)
        with manifest_commit(root):
            _assert_validated_package_current(root, source_xml, source_hash, temporary, validated_files)
            require_current_input_evidence(root, manifest)
            if target.exists():
                raise ValueError(f"delivery package appeared during publication: {target}")
            os.rename(temporary, target)
            _record_d4(root, target, fingerprint, "published")
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    result = {
        "status": "published",
        "packagePath": str(target),
        "deliveryFingerprint": fingerprint,
        "deliveryProtocolVersion": DELIVERY_PROTOCOL_VERSION,
        "animatedCueIds": [cue["id"] for cue in animated],
        "sourceOnlyCueIds": sorted(
            cue["id"] for cue in manifest["cues"] if cue.get("productionMode") == "source-only"
        ),
        "materialization": methods,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="构建并验证扁平、不可覆盖的 AfterForge FCPXMLD。")
    parser.add_argument("version_root", type=Path)
    parser.add_argument("--dtd", type=Path)
    parser.add_argument("--skip-dtd", action="store_true", help="仅用于受控测试，不执行 DTD 校验。")
    args = parser.parse_args()
    try:
        manifest = load_manifest(args.version_root)
        source = _resolve_source_xml(args.version_root.expanduser().resolve(), manifest)
        dtd = None if args.skip_dtd else (args.dtd or default_dtd_path(source))
        result = build_delivery_package(args.version_root, dtd_path=dtd)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
