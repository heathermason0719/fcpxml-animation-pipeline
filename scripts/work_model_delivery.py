"""Prepare and atomically publish schema-3 immutable FCPXML delivery releases."""

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


def prepare_release(
    root: Path,
    manifest: dict[str, Any],
    *,
    afterforge_root: Path,
    release_id: str,
    input_key: str,
    dependency_paths: list[str],
    dtd: Path | None = None,
    input_root: Path | None = None,
) -> dict[str, Any]:
    """Build isolated staging directories. This function never changes live state."""
    version_root = Path(root).expanduser().resolve()
    inputs = version_root if input_root is None else Path(input_root).expanduser().resolve()
    afterforge = Path(afterforge_root).expanduser().resolve()
    declared_afterforge, _ = layout(version_root)
    if afterforge != declared_afterforge:
        raise ValueError("afterforge_root does not match the registered project layout")
    if not afterforge.is_dir() or afterforge.is_symlink():
        raise ValueError("AfterForge root must be a regular directory")
    if not inputs.is_dir() or inputs.is_symlink():
        raise ValueError("input_root must be a regular directory")
    if manifest.get("schemaVersion") != "3.0":
        raise ValueError("prepare_release requires manifest schemaVersion 3.0")
    if not isinstance(input_key, str) or not input_key:
        raise ValueError("input_key is required")
    release_display = _release_display(release_id)
    episode_title = manifest.get("identity", {}).get("episodeTitle")
    title = _safe_name(episode_title, "identity.episodeTitle")
    identity = _identity(manifest, release_id)
    source = _source_path(inputs, manifest)
    dtd = _known_dtd(source, dtd)
    animated = _animated(manifest)

    package_relative = Path("交付") / f"{title}--{manifest['identity']['episodeId']}" / release_display / f"{title}.fcpxmld"
    snapshot_relative = Path("releases") / release_id
    package_target = _safe_relative(afterforge, str(package_relative), "package path")
    snapshot_target = _safe_relative(version_root, str(snapshot_relative), "snapshot path")
    if package_target.exists() or snapshot_target.exists():
        raise ValueError("release target already exists; verify it before retrying")

    frozen = copy.deepcopy(manifest)
    frozen["delivery"] = {
        "id": release_id, "inputKey": input_key, "protocolVersion": PROTOCOL_VERSION,
        "packagePath": str(package_relative), "snapshotPath": str(snapshot_relative),
        "identity": identity,
    }
    document = build_delivery_fcpxml(source, frozen)
    partial = version_root / "releases" / ".partial"
    partial.mkdir(parents=True, exist_ok=True)
    package = Path(tempfile.mkdtemp(prefix=f".{release_id}-package-", suffix=".fcpxmld", dir=partial))
    snapshot = Path(tempfile.mkdtemp(prefix=f".{release_id}-snapshot-", dir=partial))
    try:
        (package / "Info.fcpxml").write_bytes(document.xml_bytes)
        for cue in animated:
            asset = cue["deliveryAsset"]
            source_asset = _asset_path(inputs, asset, cue["id"])
            _copy(source_asset, package / asset["fileName"])
            _copy(source_asset, snapshot / "delivery-assets" / asset["fileName"])
        validate_delivery_package(package, source, frozen, dtd_path=dtd)
        info_hash = sha256_file(package / "Info.fcpxml")
        media = [
            {"cueId": cue["id"], "path": str(snapshot_relative / "delivery-assets" / cue["deliveryAsset"]["fileName"])}
            for cue in animated
        ]
        frozen["delivery"]["infoFcpxmlSha256"] = info_hash
        frozen["delivery"]["manifestPath"] = MANIFEST_NAME
        frozen["delivery"]["sourcePath"] = "source/source.fcpxml"
        frozen["delivery"]["media"] = media
        frozen["project"]["source"]["fcpxml"] = "source/source.fcpxml"
        for cue in frozen["cues"]:
            if cue.get("productionMode") == "animation":
                cue["deliveryAsset"]["relativePath"] = f"delivery-assets/{cue['deliveryAsset']['fileName']}"
        _write_json(snapshot / MANIFEST_NAME, frozen)
        _copy(source, snapshot / "source" / "source.fcpxml")
        dependencies: list[dict[str, str]] = []
        for value in dependency_paths:
            dependency = _safe_relative(inputs, value, "dependency path")
            _regular(dependency, "dependency")
            target = snapshot / "files" / value
            _copy(dependency, target)
            dependencies.append({"sourcePath": _relative(inputs, dependency, "dependency"),
                                 "snapshotPath": str(target.relative_to(snapshot)), "sha256": sha256_file(target)})
        inventory = {
            "package": _inventory(package),
            "snapshot": _inventory(snapshot),
            "dependencies": dependencies,
        }
        _write_json(snapshot / "inventory.json", inventory)
        result = {
            "id": release_id, "inputKey": input_key, "protocolVersion": PROTOCOL_VERSION,
            "packagePath": str(package_relative), "snapshotPath": str(snapshot_relative),
            "infoFcpxmlSha256": info_hash, "manifestPath": MANIFEST_NAME,
            "sourcePath": "source/source.fcpxml", "identity": identity, "inventory": inventory,
            "media": media,
        }
        return {"stagingPackage": str(package), "packagePath": str(package_relative),
                "stagingSnapshot": str(snapshot), "snapshotPath": str(snapshot_relative),
                "manifest": frozen, "infoFcpxmlSha256": info_hash, "inventory": inventory,
                "record": result}
    except BaseException:
        shutil.rmtree(package, ignore_errors=True)
        shutil.rmtree(snapshot, ignore_errors=True)
        raise


def _record(prepared: dict[str, Any]) -> dict[str, Any]:
    record = prepared.get("record")
    if not isinstance(record, dict):
        raise ValueError("prepared release lacks record")
    return record


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


def publish_release(root: Path, prepared: dict[str, Any]) -> dict[str, Any]:
    """Publish a prepared release without overwrite; caller owns the manifest lock."""
    version_root = Path(root).expanduser().resolve()
    record = _record(prepared)
    afterforge, _ = layout(version_root)
    package = Path(prepared.get("stagingPackage", "")).resolve()
    snapshot = Path(prepared.get("stagingSnapshot", "")).resolve()
    partial = (version_root / "releases" / ".partial").resolve()
    for path, label in ((package, "staging package"), (snapshot, "staging snapshot")):
        _relative(partial, path, label)
        if not path.is_dir() or path.is_symlink():
            raise ValueError(f"{label} is missing or unsafe")
    package_target = _safe_relative(afterforge, record["packagePath"], "packagePath")
    snapshot_target = _safe_relative(version_root, record["snapshotPath"], "snapshotPath")
    if package_target.exists() or snapshot_target.exists():
        if package_target.exists() and snapshot_target.exists():
            verify_release(version_root, afterforge, record)
            shutil.rmtree(package, ignore_errors=True)
            shutil.rmtree(snapshot, ignore_errors=True)
            return record
        raise ValueError("orphaned release target prevents publication")
    # The staged directories have already been validated during preparation. Rename is atomic on this filesystem.
    package_target.parent.mkdir(parents=True, exist_ok=True)
    snapshot_target.parent.mkdir(parents=True, exist_ok=True)
    moved_snapshot = False
    moved_package = False
    try:
        os.rename(snapshot, snapshot_target)
        moved_snapshot = True
        os.rename(package, package_target)
        moved_package = True
        verify_release(version_root, afterforge, record)
        return record
    except BaseException:
        if moved_package:
            if package_target.exists() and not package_target.is_symlink():
                shutil.rmtree(package_target)
            if snapshot_target.exists() and not snapshot_target.is_symlink():
                shutil.rmtree(snapshot_target)
        elif moved_snapshot and snapshot_target.exists() and not package_target.exists():
            os.rename(snapshot_target, snapshot)
        parent = package_target.parent
        while parent != afterforge:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
        raise
