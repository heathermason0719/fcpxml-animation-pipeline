#!/usr/bin/env python3
"""Explicitly migrate or reconcile one Vn's pinned HyperFrames runtime."""

from __future__ import annotations

try:
    from scripts.manifest_transaction import manifest_mutation
except ModuleNotFoundError:  # direct script execution
    from manifest_transaction import manifest_mutation

import argparse
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from scripts.hyperframes_adapter import cue_adapter, load_manifest, save_manifest
    from scripts.hyperframes_runtime import (
        MANAGED_SCRIPTS,
        read_runtime_pin,
        require_exact_version,
        run_with_isolated_npm_cache,
    )
    from scripts.validate_hyperframes_adapter import validate_project
    from scripts.workflow_status import evidence_fingerprint
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from hyperframes_adapter import cue_adapter, load_manifest, save_manifest  # type: ignore
    from hyperframes_runtime import (  # type: ignore
        MANAGED_SCRIPTS,
        read_runtime_pin,
        require_exact_version,
        run_with_isolated_npm_cache,
    )
    from validate_hyperframes_adapter import validate_project  # type: ignore
    from workflow_status import evidence_fingerprint  # type: ignore


CompatibilityChecker = Callable[[Path, str], list[dict[str, Any]]]


def _atomic_bytes(path: Path, content: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_bytes(path, (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def _default_compatibility_checker(root: Path, _version: str) -> list[dict[str, Any]]:
    run_with_isolated_npm_cache(
        ["npm", "run", "check"],
        cwd=root,
    )
    return [{"name": "hyperframes-check", "result": "passed", "command": "npm run check"}]


def _load_meta(root: Path) -> tuple[Path, dict[str, Any]]:
    path = root / "meta.json"
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"missing regular meta.json: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("meta.json must contain an object")
    return path, payload


def _metadata_state(meta: dict[str, Any]) -> tuple[str, list[dict[str, Any]], bool]:
    toolchain = meta.get("toolchain")
    if isinstance(toolchain, dict) and isinstance(toolchain.get("hyperframes"), dict):
        hyperframes = toolchain["hyperframes"]
        created = require_exact_version(hyperframes.get("createdWithVersion"))
        migrations = hyperframes.get("migrations")
        if not isinstance(migrations, list) or any(not isinstance(item, dict) for item in migrations):
            raise ValueError("meta.json toolchain.hyperframes.migrations must be an array of objects")
        return created, migrations, False
    created = require_exact_version(meta.get("hyperframesVersion"))
    return created, [], True


def _rewrite_package_pin(root: Path, from_version: str, to_version: str) -> None:
    path = root / "package.json"
    package = json.loads(path.read_text(encoding="utf-8"))
    scripts = package.get("scripts") if isinstance(package, dict) else None
    if not isinstance(scripts, dict):
        raise ValueError("package.json scripts must be an object")
    source = f"--package=hyperframes@{from_version}"
    target = f"--package=hyperframes@{to_version}"
    for name in MANAGED_SCRIPTS:
        command = scripts.get(name)
        if not isinstance(command, str) or command.count(source) != 1:
            raise ValueError(f"managed script {name} is not pinned to {from_version}")
        scripts[name] = command.replace(source, target)
    _atomic_json(path, package)


def _invalidate_review_evidence(
    manifest: dict[str, Any],
    migration_id: str,
    *,
    preserve_a11: bool,
) -> list[dict[str, Any]]:
    invalidated: list[dict[str, Any]] = []
    stage_evidence = manifest.get("workflow", {}).get("stageEvidence", {})
    if not isinstance(stage_evidence, dict):
        return invalidated
    for stage_id in ("A11", "A12", "A13", "A14"):
        if preserve_a11 and stage_id == "A11":
            continue
        evidence = stage_evidence.get(stage_id)
        if not isinstance(evidence, dict) or not evidence:
            continue
        record: dict[str, Any] = {
            "stageId": stage_id,
            "evidenceFingerprint": evidence_fingerprint(evidence),
        }
        if stage_id == "A11" and isinstance(evidence.get("cueApprovals"), dict):
            record["cueIds"] = sorted(evidence["cueApprovals"])
            for approval in evidence["cueApprovals"].values():
                if isinstance(approval, dict):
                    approval["status"] = "invalidated"
                    approval["invalidatedByRuntimeMigrationId"] = migration_id
        evidence["status"] = "invalidated"
        evidence["invalidatedByRuntimeMigrationId"] = migration_id
        invalidated.append(record)
    return invalidated


def _rebind_a11(
    manifest: dict[str, Any],
    runtime_version: str,
) -> list[dict[str, Any]]:
    workflow = manifest.get("workflow")
    evidence = workflow.get("stageEvidence", {}).get("A11") if isinstance(workflow, dict) else None
    if not isinstance(evidence, dict) or evidence.get("status") != "approved":
        raise ValueError("A11 rebind requires current approved A11 evidence")
    approvals = evidence.get("cueApprovals")
    if not isinstance(approvals, dict):
        raise ValueError("A11 rebind requires cue approvals")
    cue_ids: list[str] = []
    for cue in manifest.get("cues", []):
        if cue.get("productionMode") != "animation":
            continue
        cue_id = cue.get("id")
        lock = cue_adapter(cue).get("layoutLock")
        approval = approvals.get(cue_id)
        if not isinstance(lock, dict) or not isinstance(approval, dict):
            raise ValueError(f"A11 rebind lacks lock or approval for {cue_id}")
        for item, label in ((lock, "layout lock"), (approval, "cue approval")):
            bound = item.get("runtimeVersion")
            if bound not in {None, runtime_version}:
                raise ValueError(f"{label} for {cue_id} is bound to {bound}, not {runtime_version}")
            item["runtimeVersion"] = runtime_version
        cue_ids.append(cue_id)
    return [
        {
            "stageId": "A11",
            "runtimeVersion": runtime_version,
            "cueIds": sorted(cue_ids),
            "evidenceFingerprint": evidence_fingerprint(evidence),
        }
    ]


def _a11_is_bound(manifest: dict[str, Any], runtime_version: str) -> bool:
    workflow = manifest.get("workflow")
    evidence = workflow.get("stageEvidence", {}).get("A11") if isinstance(workflow, dict) else None
    if not isinstance(evidence, dict) or evidence.get("status") != "approved":
        return False
    approvals = evidence.get("cueApprovals")
    if not isinstance(approvals, dict):
        return False
    for cue in manifest.get("cues", []):
        if cue.get("productionMode") != "animation":
            continue
        cue_id = cue.get("id")
        lock = cue_adapter(cue).get("layoutLock")
        approval = approvals.get(cue_id)
        if not isinstance(lock, dict) or not isinstance(approval, dict):
            return False
        if lock.get("runtimeVersion") != runtime_version:
            return False
        if approval.get("runtimeVersion") != runtime_version:
            return False
    return True


def _adapter_check(root: Path, *, allow_runtime_lock_mismatch: bool) -> dict[str, Any]:
    result = validate_project(root)
    findings = result.get("findings", [])
    unexpected = [
        finding
        for finding in findings
        if not (allow_runtime_lock_mismatch and finding.get("code") == "layout_lock_mismatch")
    ]
    if unexpected:
        raise ValueError(f"AfterForge adapter validation failed: {unexpected}")
    record: dict[str, Any] = {
        "name": "afterforge-adapter-validation",
        "result": "passed",
        "command": "python3 scripts/validate_hyperframes_adapter.py <Vn>",
    }
    if findings:
        record["expectedInvalidations"] = findings
    return record


@manifest_mutation
def migrate_hyperframes_runtime(
    version_root: Path,
    target_version: str,
    *,
    rebind_current_a11: bool = False,
    compatibility_checker: CompatibilityChecker = _default_compatibility_checker,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    root = version_root.expanduser().resolve()
    target = require_exact_version(target_version)
    package_path = root / "package.json"
    meta_path, meta = _load_meta(root)
    manifest_path = root / "animation-manifest.json"
    original_bytes = {
        package_path: package_path.read_bytes(),
        meta_path: meta_path.read_bytes(),
        manifest_path: manifest_path.read_bytes(),
    }
    current = read_runtime_pin(root)
    created, migrations, legacy_metadata = _metadata_state(meta)
    manifest = load_manifest(root)
    if current == target and not legacy_metadata:
        if not rebind_current_a11 or _a11_is_bound(manifest, target):
            return {"status": "already-current", "runtimeVersion": current, "versionRoot": str(root)}
    if current != target and rebind_current_a11:
        raise ValueError("A11 evidence may be rebound only when the package already uses the target runtime")

    migration_id = f"HF-M{len(migrations) + 1:04d}"
    try:
        if current != target:
            _rewrite_package_pin(root, current, target)
        pinned = read_runtime_pin(root)
        checks: list[dict[str, Any]] = [
            {
                "name": "package-script-pin-consistency",
                "result": "passed",
                "runtimeVersion": pinned,
            }
        ]
        external_checks = compatibility_checker(root, target)
        if not isinstance(external_checks, list) or any(
            not isinstance(item, dict)
            or not isinstance(item.get("name"), str)
            or item.get("result") != "passed"
            for item in external_checks
        ):
            raise ValueError("compatibility checker must return named passed checks")
        checks.extend(external_checks)

        rebound = _rebind_a11(manifest, target) if rebind_current_a11 else []
        invalidated = _invalidate_review_evidence(
            manifest,
            migration_id,
            preserve_a11=rebind_current_a11,
        )
        save_manifest(root, manifest)
        checks.append(_adapter_check(root, allow_runtime_lock_mismatch=current != target))

        event_type = "reconciliation" if current == target else "runtime-upgrade"
        from_version = created if event_type == "reconciliation" else current
        review_evidence = {
            "preserved": [],
            "rebound": rebound,
            "invalidated": invalidated,
        }
        event = {
            "id": migration_id,
            "eventType": event_type,
            "fromVersion": from_version,
            "toVersion": target,
            "recordedAt": recorded_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "compatibilityChecks": checks,
            "reviewEvidence": review_evidence,
        }
        meta.pop("hyperframesVersion", None)
        toolchain = meta.setdefault("toolchain", {})
        if not isinstance(toolchain, dict):
            raise ValueError("meta.json toolchain must be an object")
        toolchain["hyperframes"] = {
            "createdWithVersion": created,
            "migrations": [*migrations, event],
        }
        _atomic_json(meta_path, meta)
    except BaseException:
        for path, content in original_bytes.items():
            _atomic_bytes(path, content)
        raise

    return {
        "status": "reconciled" if current == target else "migrated",
        "versionRoot": str(root),
        "migrationId": migration_id,
        "runtimeVersion": target,
        "compatibilityChecks": checks,
        "reviewEvidence": review_evidence,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="显式迁移或核对一个 Vn 的 HyperFrames runtime pin。")
    parser.add_argument("version_root", type=Path)
    parser.add_argument("target_version", help="迁移目标，必须是精确 semantic version。")
    parser.add_argument(
        "--rebind-current-a11",
        action="store_true",
        help="仅用于有证据证明现有 A11 产物已由当前目标 runtime 生成的核对迁移。",
    )
    args = parser.parse_args()
    try:
        result = migrate_hyperframes_runtime(
            args.version_root,
            args.target_version,
            rebind_current_a11=args.rebind_current_a11,
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
