"""Read-only verifier for existing protocol-2 releases."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

try:
    from scripts.inject_fcpxml import build_delivery_fcpxml
    from scripts.validate_fcpxml_package import sha256_file, validate_delivery_package
    from scripts.work_model_store import layout
except ModuleNotFoundError:
    from inject_fcpxml import build_delivery_fcpxml  # type: ignore
    from validate_fcpxml_package import sha256_file, validate_delivery_package  # type: ignore
    from work_model_store import layout  # type: ignore


PROTOCOL_VERSION = "2"
MANIFEST_NAME = "animation-manifest.json"


def _relative(root: Path, path: Path, label: str) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError as error:
        raise ValueError(f"{label} escapes workspace") from error


def _regular(path: Path, label: str) -> Path:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} must be a regular file: {path}")
    return path


def _safe_relative(root: Path, value: str, label: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError(f"{label} must be a non-empty relative path")
    path = (root / value).resolve(strict=False)
    _relative(root, path, label)
    return path


def _safe_name(value: str, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} is required")
    value = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "-", value.strip())
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"-+", "-", value).strip(".-")
    if not value:
        raise ValueError(f"{label} has no usable filename characters")
    return value[:120]


def _release_display(release_id: str) -> str:
    match = re.fullmatch(r"d(\d{4,})", release_id)
    if not match:
        raise ValueError("release_id must use dNNNN numbering")
    return f"交付{match.group(1)}"


def _identity(manifest: dict[str, Any], release_id: str) -> str:
    identity = manifest.get("identity")
    if not isinstance(identity, dict):
        raise ValueError("schema-3 identity is missing")
    values = []
    for key in ("projectId", "episodeId", "versionId"):
        value = identity.get(key)
        if not isinstance(value, str) or not value or any(char in value for char in "/\\"):
            raise ValueError(f"identity.{key} is invalid")
        values.append(value)
    return "AfterForge__{}__{}__{}__{}".format(*values, release_id)


def _source_path(root: Path, manifest: dict[str, Any]) -> Path:
    source = manifest.get("project", {}).get("source", {}).get("fcpxml")
    path = _safe_relative(root, source, "project.source.fcpxml")
    _regular(path, "source FCPXML")
    expected = manifest.get("sourceHashes", {}).get("fcpxml")
    if not isinstance(expected, str) or sha256_file(path) != expected:
        raise ValueError("source FCPXML hash does not match manifest")
    return path


def _asset_path(root: Path, asset: dict[str, Any], cue_id: str) -> Path:
    relative = asset.get("relativePath")
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"deliveryAsset.relativePath is required: {cue_id}")
    path = _safe_relative(root, relative, f"deliveryAsset.relativePath for {cue_id}")
    _regular(path, f"delivery asset for {cue_id}")
    expected = asset.get("sha256")
    if not isinstance(expected, str) or sha256_file(path) != expected:
        raise ValueError(f"delivery asset hash does not match manifest: {cue_id}")
    return path


def _animated(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    cues = manifest.get("cues")
    if not isinstance(cues, list):
        raise ValueError("manifest cues must be a list")
    result = []
    names: set[str] = set()
    for cue in cues:
        if not isinstance(cue, dict) or not isinstance(cue.get("id"), str):
            raise ValueError("each cue must have an id")
        if cue.get("productionMode") == "source-only":
            if "deliveryAsset" in cue:
                raise ValueError(f"source-only cue has deliveryAsset: {cue['id']}")
            continue
        asset = cue.get("deliveryAsset")
        name = asset.get("fileName") if isinstance(asset, dict) else None
        if cue.get("productionMode") != "animation" or not isinstance(name, str) or Path(name).name != name:
            raise ValueError(f"animated cue is not registered: {cue['id']}")
        if name in names:
            raise ValueError(f"duplicate deliveryAsset filename: {name}")
        names.add(name)
        result.append(cue)
    if not result:
        raise ValueError("manifest contains no animated cues")
    return sorted(result, key=lambda cue: cue["id"])


def _copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    if sha256_file(source) != sha256_file(target):
        raise ValueError(f"copy hash mismatch: {source.name}")


def _inventory(root: Path, *, exclude: set[str] | None = None) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    excluded = exclude or set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"immutable release contains a symlink: {path}")
        if path.is_file():
            relative = str(path.relative_to(root))
            if relative not in excluded:
                files.append({"path": relative, "sha256": sha256_file(path)})
        elif not path.is_dir():
            raise ValueError(f"immutable release contains an unsupported member: {path}")
    return sorted(files, key=lambda item: item["path"])


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _known_dtd(source: Path, supplied: Path | None) -> Path | None:
    if supplied is not None:
        return Path(supplied).expanduser().resolve()
    try:
        version = ET.parse(source).getroot().get("version")
    except (ET.ParseError, OSError) as error:
        raise ValueError(f"cannot determine FCPXML version: {source}") from error
    if not isinstance(version, str) or not re.fullmatch(r"\d+(?:\.\d+)?", version):
        raise ValueError(f"unsupported FCPXML version: {version!r}")
    candidate = Path("/Applications/Final Cut Pro.app/Contents/Frameworks/Interchange.framework/Versions/A/Resources") / f"FCPXMLv{version.replace('.', '_')}.dtd"
    return candidate if candidate.is_file() and not candidate.is_symlink() else None


def verify_release(root: Path, afterforge_root: Path, record: dict[str, Any]) -> bool:
    version_root = Path(root).expanduser().resolve()
    afterforge = Path(afterforge_root).expanduser().resolve()
    declared_afterforge, _ = layout(version_root)
    if afterforge != declared_afterforge:
        raise ValueError("afterforge_root does not match the registered project layout")
    if record.get("protocolVersion") != PROTOCOL_VERSION:
        raise ValueError("unsupported delivery protocol")
    package = _safe_relative(afterforge, record.get("packagePath"), "packagePath")
    snapshot = _safe_relative(version_root, record.get("snapshotPath"), "snapshotPath")
    if not package.is_dir() or package.is_symlink() or not snapshot.is_dir() or snapshot.is_symlink():
        raise ValueError("release package or snapshot is missing or unsafe")
    inventory = record.get("inventory")
    if not isinstance(inventory, dict):
        raise ValueError("release inventory is missing")
    inventory_file = snapshot / "inventory.json"
    _regular(inventory_file, "snapshot inventory")
    if json.loads(inventory_file.read_text(encoding="utf-8")) != inventory:
        raise ValueError("snapshot inventory differs from release record")
    if _inventory(package) != inventory.get("package"):
        raise ValueError("package inventory differs from release record")
    if _inventory(snapshot, exclude={"inventory.json"}) != inventory.get("snapshot"):
        raise ValueError("snapshot inventory differs from release record")
    manifest_path = _safe_relative(snapshot, record.get("manifestPath"), "manifestPath")
    source_path = _safe_relative(snapshot, record.get("sourcePath"), "sourcePath")
    _regular(manifest_path, "frozen manifest")
    _regular(source_path, "frozen source")
    frozen = json.loads(manifest_path.read_text(encoding="utf-8"))
    delivery = frozen.get("delivery")
    if not isinstance(delivery, dict) or any(delivery.get(key) != record.get(key) for key in (
        "id", "inputKey", "protocolVersion", "packagePath", "snapshotPath", "infoFcpxmlSha256", "identity"
    )):
        raise ValueError("frozen delivery identity differs from release record")
    if sha256_file(package / "Info.fcpxml") != record.get("infoFcpxmlSha256"):
        raise ValueError("Info.fcpxml hash differs from release record")
    if delivery.get("media") != record.get("media") or not isinstance(record.get("media"), list):
        raise ValueError("frozen delivery media differs from release record")
    assets = {
        cue.get("id"): cue.get("deliveryAsset")
        for cue in frozen.get("cues", []) if cue.get("productionMode") == "animation"
    }
    if {item.get("cueId") for item in record["media"] if isinstance(item, dict)} != set(assets):
        raise ValueError("release media cue set differs from frozen manifest")
    for media in record["media"]:
        if not isinstance(media, dict) or not isinstance(media.get("cueId"), str):
            raise ValueError("release media is invalid")
        asset = assets[media["cueId"]]
        if not isinstance(asset, dict) or media.get("path") != str(Path(record["snapshotPath"]) / asset.get("relativePath", "")):
            raise ValueError("release media path differs from frozen delivery asset")
        media_path = _regular(_safe_relative(version_root, media.get("path"), "release media path"), "release media")
        if sha256_file(media_path) != asset.get("sha256"):
            raise ValueError("release media hash differs from frozen delivery asset")
    validate_delivery_package(package, source_path, frozen)
    return True
