"""Controlled mutations for Vn review comments, approvals, and authorization."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

try:
    from scripts.hyperframes_adapter import cue_adapter, find_cue, load_manifest, parse_time, safe_project_path, save_manifest
    from scripts.layout_lock import verify_layouts
    from scripts.workflow_status import current_input_fingerprint, resolve_stage_status
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from hyperframes_adapter import cue_adapter, find_cue, load_manifest, parse_time, safe_project_path, save_manifest  # type: ignore
    from layout_lock import verify_layouts  # type: ignore
    from workflow_status import current_input_fingerprint, resolve_stage_status  # type: ignore


def _stage_evidence(manifest: dict[str, Any], stage_id: str) -> dict[str, Any]:
    workflow = manifest.setdefault("workflow", {})
    evidence = workflow.setdefault("stageEvidence", {})
    stage = evidence.setdefault(stage_id, {})
    if not isinstance(stage, dict):
        raise ValueError(f"stage evidence is not an object: {stage_id}")
    return stage


def _next_comment_id(stage_id: str, comments: list[dict[str, Any]]) -> tuple[str, int]:
    revision = max((int(comment.get("revision", 0)) for comment in comments), default=0) + 1
    return f"{stage_id}-C{revision:04d}", revision


def _invalidate(stage: dict[str, Any], comment_id: str) -> None:
    if stage:
        stage["status"] = "invalidated"
        stage["invalidatedByCommentId"] = comment_id


def _normalize_impact_scopes(
    stage_id: str,
    impact_scopes: list[str] | None,
    issue_type: str | None,
) -> list[str]:
    if impact_scopes is None:
        impact_scopes = [issue_type] if issue_type is not None else (["static"] if stage_id == "A11" else [])
    if (
        not isinstance(impact_scopes, list)
        or not impact_scopes
        or any(scope not in {"static", "motion"} for scope in impact_scopes)
        or len(set(impact_scopes)) != len(impact_scopes)
    ):
        raise ValueError("impactScopes must contain static, motion, or both exactly once")
    normalized = [scope for scope in ("static", "motion") if scope in impact_scopes]
    if stage_id == "A11" and normalized != ["static"]:
        raise ValueError("A11 comments have static impactScopes")
    return normalized


def add_review_comment(
    version_root: Path,
    *,
    stage_id: str,
    body: str,
    actor: str,
    impact_scopes: list[str] | None = None,
    issue_type: str | None = None,
    cue_id: str | None = None,
    frame_id: str | None = None,
    time_start: str | None = None,
    time_end: str | None = None,
) -> dict[str, Any]:
    if actor != "user":
        raise ValueError("only the user may submit review comments")
    if stage_id not in {"A11", "A13"}:
        raise ValueError("review comments are supported only at A11 or A13")
    scopes = _normalize_impact_scopes(stage_id, impact_scopes, issue_type)
    if not isinstance(body, str) or not body.strip():
        raise ValueError("comment body cannot be empty")
    if stage_id == "A11" and not cue_id:
        raise ValueError("A11 comments require cueId")
    if stage_id == "A13" and time_start is None:
        raise ValueError("A13 comments require timeStart from the player context")
    for value in (time_start, time_end):
        if value is not None:
            parse_time(value)
    if time_start is not None and time_end is not None and parse_time(time_end) < parse_time(time_start):
        raise ValueError("comment timeEnd cannot precede timeStart")

    root = version_root.expanduser().resolve()
    manifest = load_manifest(root)
    if cue_id is not None:
        find_cue(manifest, cue_id)
    stage = _stage_evidence(manifest, stage_id)
    comments = stage.setdefault("comments", [])
    if not isinstance(comments, list):
        raise ValueError(f"{stage_id} comments must be an array")
    comment_id, revision = _next_comment_id(stage_id, comments)
    comment: dict[str, Any] = {
        "id": comment_id,
        "stageId": stage_id,
        "revision": revision,
        "author": "user",
        "impactScopes": scopes,
        "body": body.strip(),
        "status": "open",
    }
    if cue_id is not None:
        comment["cueId"] = cue_id
    if frame_id is not None:
        comment["frameId"] = frame_id
    if time_start is not None:
        comment["timeStart"] = time_start
    if time_end is not None:
        comment["timeEnd"] = time_end
    comments.append(comment)
    stage["commentRevision"] = revision
    manifest.setdefault("workflow", {})["activeReviewContext"] = stage_id

    if "static" in scopes:
        if not cue_id:
            raise ValueError("static comments require cueId")
        cue = find_cue(manifest, cue_id)
        a11 = _stage_evidence(manifest, "A11")
        _invalidate(a11, comment_id)
        approval = a11.get("cueApprovals", {}).get(cue_id)
        if isinstance(approval, dict):
            approval["status"] = "invalidated"
            approval["invalidatedByCommentId"] = comment_id
        _invalidate(_stage_evidence(manifest, "A13"), comment_id)
        _invalidate(_stage_evidence(manifest, "A14"), comment_id)
    else:
        _invalidate(_stage_evidence(manifest, "A13"), comment_id)
        _invalidate(_stage_evidence(manifest, "A14"), comment_id)
    save_manifest(root, manifest)
    return comment


def address_review_comment(
    version_root: Path,
    stage_id: str,
    comment_id: str,
    *,
    actor: str,
) -> dict[str, Any]:
    if actor != "agent":
        raise ValueError("only the Agent may mark a review comment addressed")
    root = version_root.expanduser().resolve()
    manifest = load_manifest(root)
    stage = _stage_evidence(manifest, stage_id)
    matches = [comment for comment in stage.get("comments", []) if comment.get("id") == comment_id]
    if len(matches) != 1:
        raise ValueError(f"unknown review comment: {comment_id}")
    comment = matches[0]
    if comment.get("status") != "open":
        raise ValueError(f"review comment is not open: {comment_id}")
    comment["status"] = "addressed"
    comment["addressedBy"] = "agent"
    save_manifest(root, manifest)
    return comment


def approve_storyboard(
    version_root: Path,
    *,
    actor: str,
    cue_ids: list[str] | None = None,
) -> dict[str, Any]:
    if actor != "user":
        raise ValueError("only the user may approve Storyboard")
    root = version_root.expanduser().resolve()
    manifest = load_manifest(root)
    workflow = manifest.get("workflow")
    if not isinstance(workflow, dict) or not isinstance(workflow.get("stageContractVersion"), str):
        raise ValueError("workflow stage contract is not initialized")
    animated = [cue for cue in manifest["cues"] if cue.get("productionMode") == "animation"]
    animated_ids = [cue["id"] for cue in animated]
    selected = animated_ids if cue_ids is None else cue_ids
    if not selected or any(cue_id not in animated_ids for cue_id in selected):
        raise ValueError("Storyboard approval contains unknown or source-only cue ids")
    if len(selected) != len(set(selected)):
        raise ValueError("Storyboard approval contains duplicate cue ids")
    missing_descriptions = [
        cue["id"]
        for cue in animated
        if cue["id"] in selected
        and (
            not isinstance(cue.get("finalAnimationDescription"), str)
            or not cue["finalAnimationDescription"].strip()
        )
    ]
    if missing_descriptions:
        raise ValueError(
            "Storyboard approval requires finalAnimationDescription: "
            + ", ".join(missing_descriptions)
        )
    verification = verify_layouts(root)
    checked = set(verification.get("checkedCueIds", []))
    invalid = set(verification.get("invalidCueIds", []))
    unavailable = [cue_id for cue_id in selected if cue_id not in checked or cue_id in invalid]
    if unavailable:
        raise ValueError(f"Storyboard approval requires a valid layout lock: {', '.join(unavailable)}")
    stage = _stage_evidence(manifest, "A11")
    comments = stage.setdefault("comments", [])
    for comment in comments:
        if comment.get("cueId") in selected and comment.get("status") == "open":
            raise ValueError(f"Storyboard cue has an open comment: {comment.get('cueId')}")
    approvals = stage.setdefault("cueApprovals", {})
    for cue in animated:
        if cue["id"] not in selected:
            continue
        lock = cue_adapter(cue)["layoutLock"]
        cue_comments = [comment for comment in comments if comment.get("cueId") == cue["id"]]
        comment_revision = max((int(comment.get("revision", 0)) for comment in cue_comments), default=0)
        approvals[cue["id"]] = {
            "status": "approved",
            "runtimeVersion": lock["runtimeVersion"],
            "layoutRevision": lock["revision"],
            "layoutAggregateSha256": lock["aggregateSha256"],
            "approvedPosterSha256": lock["approvedPosterSha256"],
            "reviewFrameSetSha256": lock.get("reviewFrameSetSha256"),
            "commentRevision": comment_revision,
        }
        for comment in cue_comments:
            if comment.get("status") == "addressed":
                comment["status"] = "accepted"
                comment["acceptedBy"] = "user"
    def approval_is_current(cue: dict[str, Any]) -> bool:
        lock = cue_adapter(cue).get("layoutLock")
        approval = approvals.get(cue["id"])
        return (
            isinstance(lock, dict)
            and isinstance(approval, dict)
            and approval.get("status") == "approved"
            and approval.get("runtimeVersion") == lock.get("runtimeVersion")
            and approval.get("layoutRevision") == lock.get("revision")
            and approval.get("layoutAggregateSha256") == lock.get("aggregateSha256")
            and approval.get("approvedPosterSha256") == lock.get("approvedPosterSha256")
            and approval.get("reviewFrameSetSha256") == lock.get("reviewFrameSetSha256")
        )

    stage.update(
        {
            "stageId": "A11",
            "contractVersion": workflow["stageContractVersion"],
            "semanticVersion": 1,
            "status": "approved" if all(approval_is_current(cue) for cue in animated) else "partially-approved",
        }
    )
    a12 = workflow.setdefault("stageEvidence", {}).get("A12")
    preserve_a12 = False
    if isinstance(a12, dict) and a12.get("status") == "ready":
        try:
            preview = safe_project_path(root, a12["preview"])
            preserve_a12 = (
                a12.get("sha256") == hashlib.sha256(preview.read_bytes()).hexdigest()
                and a12.get("inputFingerprint") == current_input_fingerprint(root, manifest)
            )
        except (KeyError, OSError, ValueError):
            preserve_a12 = False
    for downstream_id in (("A13", "A14") if preserve_a12 else ("A12", "A13", "A14")):
        _invalidate(_stage_evidence(manifest, downstream_id), "A11-approval-changed")
    workflow["activeReviewContext"] = "A11"
    save_manifest(root, manifest)
    return {"status": stage["status"], "approvedCueIds": selected}


def register_demo(
    version_root: Path,
    preview_relative: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = version_root.expanduser().resolve()
    manifest = load_manifest(root)
    workflow = manifest.get("workflow")
    if not isinstance(workflow, dict) or not isinstance(workflow.get("stageContractVersion"), str):
        raise ValueError("workflow stage contract is not initialized")
    preview = safe_project_path(root, preview_relative)
    evidence = {
        "stageId": "A12",
        "contractVersion": workflow["stageContractVersion"],
        "semanticVersion": 1,
        "status": "ready",
        "preview": preview_relative,
        "sha256": hashlib.sha256(preview.read_bytes()).hexdigest(),
        "inputFingerprint": current_input_fingerprint(root, manifest),
    }
    if metadata:
        evidence["media"] = metadata
    workflow.setdefault("stageEvidence", {})["A12"] = evidence
    for stage_id in ("A13", "A14"):
        _invalidate(_stage_evidence(manifest, stage_id), "A12-demo-changed")
    workflow["activeReviewContext"] = "A13"
    save_manifest(root, manifest)
    return evidence


def approve_demo(version_root: Path, *, actor: str) -> dict[str, Any]:
    if actor != "user":
        raise ValueError("only the user may approve the Demo")
    root = version_root.expanduser().resolve()
    status = resolve_stage_status(root)
    if status.get("blockingStage") != "A13":
        raise ValueError("Demo approval is not currently eligible")
    manifest = load_manifest(root)
    workflow = manifest["workflow"]
    demo = workflow["stageEvidence"]["A12"]
    stage = _stage_evidence(manifest, "A13")
    comments = stage.setdefault("comments", [])
    if any(comment.get("status") == "open" for comment in comments):
        raise ValueError("Demo has open comments")
    for comment in comments:
        if comment.get("status") == "addressed":
            comment["status"] = "accepted"
            comment["acceptedBy"] = "user"
    comment_revision = max((int(comment.get("revision", 0)) for comment in comments), default=0)
    stage.update(
        {
            "stageId": "A13",
            "contractVersion": workflow["stageContractVersion"],
            "semanticVersion": 1,
            "status": "approved",
            "demoSha256": demo["sha256"],
            "inputFingerprint": demo["inputFingerprint"],
            "commentRevision": comment_revision,
        }
    )
    _invalidate(_stage_evidence(manifest, "A14"), "A13-approval-changed")
    workflow["activeReviewContext"] = "A13"
    save_manifest(root, manifest)
    return stage


def authorize_native_render(version_root: Path, *, actor: str) -> dict[str, Any]:
    if actor != "user":
        raise ValueError("only the user may authorize native rendering")
    root = version_root.expanduser().resolve()
    status = resolve_stage_status(root)
    if status.get("blockingStage") != "A14":
        raise ValueError("native rendering authorization is not currently eligible")
    manifest = load_manifest(root)
    workflow = manifest["workflow"]
    demo = workflow["stageEvidence"]["A12"]
    evidence = {
        "stageId": "A14",
        "contractVersion": workflow["stageContractVersion"],
        "semanticVersion": 1,
        "status": "authorized",
        "demoSha256": demo["sha256"],
        "inputFingerprint": demo["inputFingerprint"],
    }
    workflow["stageEvidence"]["A14"] = evidence
    save_manifest(root, manifest)
    return evidence


def record_fcp_acceptance(version_root: Path, *, actor: str) -> dict[str, Any]:
    if actor != "user":
        raise ValueError("only the user may record Final Cut Pro acceptance")
    root = version_root.expanduser().resolve()
    status = resolve_stage_status(root)
    if status.get("blockingStage") != "D5":
        raise ValueError("Final Cut Pro acceptance is not currently eligible")
    manifest = load_manifest(root)
    workflow = manifest["workflow"]
    d4 = workflow["stageEvidence"]["D4"]
    evidence = {
        "stageId": "D5",
        "contractVersion": workflow["stageContractVersion"],
        "semanticVersion": 1,
        "status": "accepted",
        "packageName": d4["packageName"],
        "deliveryFingerprint": d4["deliveryFingerprint"],
        "infoFcpxmlSha256": d4["infoFcpxmlSha256"],
    }
    workflow["stageEvidence"]["D5"] = evidence
    save_manifest(root, manifest)
    return evidence
