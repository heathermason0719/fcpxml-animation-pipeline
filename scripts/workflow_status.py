#!/usr/bin/env python3
"""Derive workflow stage status from Vn evidence without persisting currentStage."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

try:
    from scripts.hyperframes_adapter import cue_adapter, load_manifest, safe_project_path
    from scripts.layout_lock import verify_layouts
    from scripts.workflow_stages import assess_stage_evidence, load_stage_contract
    from scripts.workflow_inputs import evidence_fingerprint_version, input_fingerprint, require_current_input_evidence
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from hyperframes_adapter import cue_adapter, load_manifest, safe_project_path  # type: ignore
    from layout_lock import verify_layouts  # type: ignore
    from workflow_stages import assess_stage_evidence, load_stage_contract  # type: ignore
    from workflow_inputs import evidence_fingerprint_version, input_fingerprint, require_current_input_evidence  # type: ignore


PRE_REVIEW_STAGES = [f"A{number}" for number in range(1, 11)]


def evidence_fingerprint(evidence: dict[str, Any]) -> str:
    canonical = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def current_input_fingerprint(root: Path, manifest: dict[str, Any]) -> str:
    return input_fingerprint(root, manifest)


def _a12_evidence_status(root: Path, manifest: dict[str, Any], evidence: Any) -> str:
    if not isinstance(evidence, dict):
        return "missing"
    assessment = assess_stage_evidence(load_stage_contract(), "A12", evidence)
    if not assessment["usable"]:
        return assessment["status"]
    if evidence.get("status") != "ready":
        return "pending"
    try:
        version = evidence_fingerprint_version(evidence)
    except ValueError:
        return "unsupported-input-fingerprint-version"
    try:
        preview = safe_project_path(root, evidence["preview"])
        preview_sha256 = hashlib.sha256(preview.read_bytes()).hexdigest()
        fingerprint = input_fingerprint(root, manifest, version)
    except (KeyError, OSError, ValueError):
        return "artifact-invalid"
    if evidence.get("sha256") != preview_sha256:
        return "demo-hash-mismatch"
    if evidence.get("inputFingerprint") != fingerprint:
        return "input-fingerprint-mismatch"
    return "compatible-historical" if version == 1 else assessment["status"]


def _linked_input_version_status(upstream: dict[str, Any], evidence: dict[str, Any]) -> str | None:
    try:
        if evidence_fingerprint_version(upstream) != evidence_fingerprint_version(evidence):
            return "input-fingerprint-version-mismatch"
    except ValueError:
        return "unsupported-input-fingerprint-version"
    return None


def _pending_input_stage_status(
    root: Path, manifest: dict[str, Any], stage: str,
    completed: list[str], evidence: dict[str, str],
    *, input_stages: tuple[str, ...] = ("A12", "A13", "A14"),
    active_context: str | None = None,
) -> dict[str, Any]:
    try:
        require_current_input_evidence(root, manifest, stages=input_stages)
    except ValueError:
        # Historical completion remains readable, but weak evidence cannot grant a new write.
        return {
            "activeContext": None,
            "blockingStage": "A12",
            "nextEligibleStage": "A12",
            "completedStages": [item for item in completed if item != "D1"],
            "evidence": {**evidence, stage if stage in {"A13", "A14"} else "D1": "input-fingerprint-upgrade-required"},
        }
    return {
        "activeContext": active_context,
        "blockingStage": stage,
        "nextEligibleStage": stage,
        "completedStages": completed,
        "evidence": evidence,
    }


def _a13_evidence_status(contract: dict[str, Any], a12: dict[str, Any], evidence: Any) -> str:
    if not isinstance(evidence, dict):
        return "missing"
    assessment = assess_stage_evidence(contract, "A13", evidence)
    if not assessment["usable"]:
        return assessment["status"]
    if evidence.get("status") != "approved":
        return "pending"
    version_status = _linked_input_version_status(a12, evidence)
    if version_status:
        return version_status
    comments = evidence.get("comments", [])
    if not isinstance(comments, list) or any(comment.get("status") == "open" for comment in comments):
        return "open-comments"
    latest_revision = max((int(comment.get("revision", 0)) for comment in comments), default=0)
    if int(evidence.get("commentRevision", -1)) < latest_revision:
        return "approval-stale"
    if evidence.get("demoSha256") != a12.get("sha256"):
        return "demo-hash-mismatch"
    if evidence.get("inputFingerprint") != a12.get("inputFingerprint"):
        return "input-fingerprint-mismatch"
    return "compatible-historical" if evidence_fingerprint_version(evidence) == 1 else assessment["status"]


def _a14_evidence_status(contract: dict[str, Any], a12: dict[str, Any], evidence: Any) -> str:
    if not isinstance(evidence, dict):
        return "missing"
    assessment = assess_stage_evidence(contract, "A14", evidence)
    if not assessment["usable"]:
        return assessment["status"]
    if evidence.get("status") != "authorized":
        return "pending"
    version_status = _linked_input_version_status(a12, evidence)
    if version_status:
        return version_status
    if evidence.get("demoSha256") != a12.get("sha256"):
        return "demo-hash-mismatch"
    if evidence.get("inputFingerprint") != a12.get("inputFingerprint"):
        return "input-fingerprint-mismatch"
    return "compatible-historical" if evidence_fingerprint_version(evidence) == 1 else assessment["status"]


def _d2_evidence_status(
    root: Path,
    manifest: dict[str, Any],
    contract: dict[str, Any],
    a14: dict[str, Any],
) -> str:
    ledger_path = root / "delivery/render-ledger.json"
    if not ledger_path.is_file() or ledger_path.is_symlink():
        return "missing"
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "artifact-invalid"
    if not isinstance(ledger, dict):
        return "artifact-invalid"
    assessment = assess_stage_evidence(contract, "D2", ledger)
    if not assessment["usable"]:
        return assessment["status"]
    if ledger.get("status") != "rendered":
        return "pending"
    version_status = _linked_input_version_status(a14, ledger)
    if version_status:
        return version_status
    try:
        if ledger.get("authorizationFingerprint") != evidence_fingerprint(a14):
            return "authorization-fingerprint-mismatch"
        if ledger.get("inputFingerprint") != input_fingerprint(root, manifest, evidence_fingerprint_version(ledger)):
            return "input-fingerprint-mismatch"
    except (OSError, ValueError, KeyError):
        return "input-invalid"
    animated_ids = {
        cue["id"] for cue in manifest["cues"] if cue.get("productionMode") == "animation"
    }
    items = ledger.get("items")
    if not isinstance(items, list) or {item.get("cueId") for item in items if isinstance(item, dict)} != animated_ids:
        return "items-incomplete"
    for item in items:
        try:
            output = safe_project_path(root, item["output"])
            actual_hash = hashlib.sha256(output.read_bytes()).hexdigest()
        except (KeyError, OSError, ValueError):
            return "artifact-invalid"
        if item.get("sha256") != actual_hash:
            return "artifact-hash-mismatch"
    return "compatible-historical" if evidence_fingerprint_version(ledger) == 1 else assessment["status"]


def _d3_evidence_status(
    root: Path,
    manifest: dict[str, Any],
    contract: dict[str, Any],
    evidence: Any,
) -> str:
    if not isinstance(evidence, dict):
        return "missing"
    assessment = assess_stage_evidence(contract, "D3", evidence)
    if not assessment["usable"]:
        return assessment["status"]
    if evidence.get("status") != "registered":
        return "pending"
    ledger_path = root / "delivery/render-ledger.json"
    try:
        ledger_hash = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
    except OSError:
        return "render-ledger-missing"
    if evidence.get("renderLedgerSha256") != ledger_hash:
        return "render-ledger-mismatch"
    assets: dict[str, Any] = {}
    for cue in manifest["cues"]:
        if cue.get("productionMode") != "animation":
            continue
        asset = cue.get("deliveryAsset")
        if not isinstance(asset, dict):
            return "assets-incomplete"
        assets[cue["id"]] = asset
    if evidence.get("assetFingerprint") != evidence_fingerprint(
        {cue_id: assets[cue_id] for cue_id in sorted(assets)}
    ):
        return "asset-fingerprint-mismatch"
    return assessment["status"]


def _d4_evidence_status(
    root: Path,
    manifest: dict[str, Any],
    contract: dict[str, Any],
    evidence: Any,
) -> str:
    if not isinstance(evidence, dict):
        return "missing"
    assessment = assess_stage_evidence(contract, "D4", evidence)
    if not assessment["usable"]:
        return assessment["status"]
    if evidence.get("status") != "published":
        return "pending"
    package_name = evidence.get("packageName")
    fingerprint = evidence.get("deliveryFingerprint")
    if (
        not isinstance(package_name, str)
        or Path(package_name).name != package_name
        or not isinstance(fingerprint, str)
        or package_name != f"AfterForge__{manifest['sourceVersion']}__d-{fingerprint}.fcpxmld"
    ):
        return "package-identity-invalid"
    package = root.parent / package_name
    info = package / "Info.fcpxml"
    try:
        if hashlib.sha256(info.read_bytes()).hexdigest() != evidence.get("infoFcpxmlSha256"):
            return "package-hash-mismatch"
        for cue in manifest["cues"]:
            if cue.get("productionMode") != "animation":
                continue
            asset = cue.get("deliveryAsset", {})
            movie = package / asset["fileName"]
            if hashlib.sha256(movie.read_bytes()).hexdigest() != asset.get("sha256"):
                return "package-asset-mismatch"
    except (KeyError, OSError):
        return "package-invalid"
    return assessment["status"]


def _d5_evidence_status(
    contract: dict[str, Any],
    d4: dict[str, Any],
    evidence: Any,
) -> str:
    if not isinstance(evidence, dict):
        return "missing"
    assessment = assess_stage_evidence(contract, "D5", evidence)
    if not assessment["usable"]:
        return assessment["status"]
    if evidence.get("status") != "accepted":
        return "pending"
    for key in ("packageName", "deliveryFingerprint", "infoFcpxmlSha256"):
        if evidence.get(key) != d4.get(key):
            return "package-evidence-mismatch"
    return assessment["status"]


def _d6_evidence_status(
    root: Path,
    contract: dict[str, Any],
    d4: dict[str, Any],
    evidence: Any,
) -> str:
    if not isinstance(evidence, dict):
        return "missing"
    assessment = assess_stage_evidence(contract, "D6", evidence)
    if not assessment["usable"]:
        return assessment["status"]
    if evidence.get("status") != "valid":
        return "pending"
    if evidence.get("deliveryFingerprint") != d4.get("deliveryFingerprint"):
        return "delivery-fingerprint-mismatch"
    delivered = root.parent / d4["packageName"] / "Info.fcpxml"
    reexported_path = evidence.get("reexportedPath")
    if not isinstance(reexported_path, str):
        return "roundtrip-artifact-invalid"
    reexported = Path(reexported_path).expanduser().resolve()
    try:
        delivered_hash = hashlib.sha256(delivered.read_bytes()).hexdigest()
        reexported_hash = hashlib.sha256(reexported.read_bytes()).hexdigest()
    except OSError:
        return "roundtrip-artifact-invalid"
    if delivered_hash != evidence.get("deliveredSha256") or reexported_hash != evidence.get("reexportedSha256"):
        return "roundtrip-hash-mismatch"
    return assessment["status"]


def _a11_evidence_status(root: Path, manifest: dict[str, Any], evidence: Any) -> str:
    try:
        from scripts.storyboard_approval import evaluate_storyboard_cue
    except ModuleNotFoundError:
        from storyboard_approval import evaluate_storyboard_cue
    if not isinstance(evidence, dict):
        return "missing"
    contract = load_stage_contract()
    assessment = assess_stage_evidence(contract, "A11", evidence)
    if not assessment["usable"]:
        return assessment["status"]
    if evidence.get("status") != "approved":
        return "pending"
    comments = evidence.get("comments", [])
    if not isinstance(comments, list) or any(comment.get("status") == "open" for comment in comments):
        return "open-comments"
    verification = verify_layouts(root)
    animated = [cue for cue in manifest["cues"] if cue.get("productionMode") == "animation"]
    if any(
        not isinstance(cue.get("finalAnimationDescription"), str)
        or not cue["finalAnimationDescription"].strip()
        for cue in animated
    ):
        return "final-animation-description-missing"
    expected_ids = {cue["id"] for cue in animated}
    if verification.get("status") != "valid" or set(verification.get("checkedCueIds", [])) != expected_ids:
        return "layout-lock-invalid"
    approvals = evidence.get("cueApprovals")
    if not isinstance(approvals, dict) or set(approvals) != expected_ids:
        return "cue-approvals-incomplete"
    for cue in animated:
        result = evaluate_storyboard_cue(cue, approval=approvals.get(cue["id"]), comments=comments, layout_valid=True)
        if result["evidenceStatus"] != "current":
            return result["evidenceStatus"]
    return assessment["status"]


def resolve_stage_status(version_root: Path) -> dict[str, Any]:
    root = version_root.expanduser().resolve()
    manifest = load_manifest(root)
    stage_evidence = manifest.get("workflow", {}).get("stageEvidence", {})
    active_review_context = manifest.get("workflow", {}).get("activeReviewContext")
    a11 = stage_evidence.get("A11") if isinstance(stage_evidence, dict) else None
    a11_status = _a11_evidence_status(root, manifest, a11)
    if a11_status not in {"current", "compatible-historical"}:
        return {
            "activeContext": active_review_context if active_review_context in {"A11", "A13"} else "A11",
            "blockingStage": "A11",
            "nextEligibleStage": "A11",
            "completedStages": PRE_REVIEW_STAGES.copy(),
            "evidence": {"A11": a11_status},
        }
    a12 = stage_evidence.get("A12") if isinstance(stage_evidence, dict) else None
    a12_status = _a12_evidence_status(root, manifest, a12)
    if a12_status not in {"current", "compatible-historical"}:
        return {
            "activeContext": None,
            "blockingStage": "A12",
            "nextEligibleStage": "A12",
            "completedStages": [*PRE_REVIEW_STAGES, "A11"],
            "evidence": {"A11": a11_status, "A12": a12_status},
        }
    contract = load_stage_contract()
    a13 = stage_evidence.get("A13") if isinstance(stage_evidence, dict) else None
    a13_status = _a13_evidence_status(contract, a12, a13)
    if a13_status not in {"current", "compatible-historical"}:
        return _pending_input_stage_status(
            root, manifest, "A13", [*PRE_REVIEW_STAGES, "A11", "A12"],
            {"A11": a11_status, "A12": a12_status, "A13": a13_status},
            input_stages=("A12",), active_context="A13",
        )
    a14 = stage_evidence.get("A14") if isinstance(stage_evidence, dict) else None
    a14_status = _a14_evidence_status(contract, a12, a14)
    if a14_status not in {"current", "compatible-historical"}:
        return _pending_input_stage_status(
            root, manifest, "A14", [*PRE_REVIEW_STAGES, "A11", "A12", "A13"],
            {
                "A11": a11_status,
                "A12": a12_status,
                "A13": a13_status,
                "A14": a14_status,
            }, input_stages=("A12", "A13"), active_context="A13",
        )
    completed = [*PRE_REVIEW_STAGES, "A11", "A12", "A13", "A14", "D1"]
    evidence_status = {
        "A11": a11_status,
        "A12": a12_status,
        "A13": a13_status,
        "A14": a14_status,
        "D1": "current",
    }
    d2_status = _d2_evidence_status(root, manifest, contract, a14)
    evidence_status["D2"] = d2_status
    if d2_status not in {"current", "compatible-historical"}:
        return _pending_input_stage_status(root, manifest, "D2", completed, evidence_status)
    completed.append("D2")
    d3 = stage_evidence.get("D3") if isinstance(stage_evidence, dict) else None
    d3_status = _d3_evidence_status(root, manifest, contract, d3)
    evidence_status["D3"] = d3_status
    if d3_status not in {"current", "compatible-historical"}:
        return _pending_input_stage_status(root, manifest, "D3", completed, evidence_status)
    completed.append("D3")
    d4 = stage_evidence.get("D4") if isinstance(stage_evidence, dict) else None
    d4_status = _d4_evidence_status(root, manifest, contract, d4)
    evidence_status["D4"] = d4_status
    if d4_status not in {"current", "compatible-historical"}:
        return _pending_input_stage_status(root, manifest, "D4", completed, evidence_status)
    completed.append("D4")
    d5 = stage_evidence.get("D5") if isinstance(stage_evidence, dict) else None
    d5_status = _d5_evidence_status(contract, d4, d5)
    evidence_status["D5"] = d5_status
    if d5_status not in {"current", "compatible-historical"}:
        return {
            "activeContext": None,
            "blockingStage": "D5",
            "nextEligibleStage": "D5",
            "completedStages": completed,
            "evidence": evidence_status,
        }
    completed.append("D5")
    if workflow := manifest.get("workflow"):
        roundtrip_required = workflow.get("roundTripRequired", True)
    else:
        roundtrip_required = True
    if not roundtrip_required:
        return {
            "activeContext": None,
            "blockingStage": None,
            "nextEligibleStage": None,
            "completedStages": completed,
            "evidence": {**evidence_status, "D6": "not-applicable"},
        }
    d6 = stage_evidence.get("D6") if isinstance(stage_evidence, dict) else None
    d6_status = _d6_evidence_status(root, contract, d4, d6)
    evidence_status["D6"] = d6_status
    if d6_status not in {"current", "compatible-historical"}:
        return {
            "activeContext": None,
            "blockingStage": "D6",
            "nextEligibleStage": "D6",
            "completedStages": completed,
            "evidence": evidence_status,
        }
    return {
        "activeContext": None,
        "blockingStage": None,
        "nextEligibleStage": None,
        "completedStages": [*completed, "D6"],
        "evidence": evidence_status,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="根据 Vn evidence 推导 AfterForge workflow stage。")
    parser.add_argument("version_root", type=Path)
    args = parser.parse_args()
    try:
        result = resolve_stage_status(args.version_root)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
