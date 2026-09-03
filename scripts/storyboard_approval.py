"""Pure per-cue Storyboard approval/readiness assessment shared by every consumer."""

from __future__ import annotations

from typing import Any

try:
    from scripts.hyperframes_adapter import cue_adapter
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from hyperframes_adapter import cue_adapter  # type: ignore


def evaluate_storyboard_cue(
    cue: dict[str, Any],
    *,
    approval: Any,
    comments: list[dict[str, Any]],
    layout_valid: bool,
) -> dict[str, Any]:
    """Assess current evidence without mutating it or reading the filesystem.

    ``layout_valid`` comes from live layout verification, not lock presence.
    Stage-contract compatibility remains the caller's stage-level responsibility.
    A stale approval can be replaced when the cue's current readiness is valid.
    """
    lock = cue_adapter(cue).get("layoutLock")
    cue_comments = [comment for comment in comments if comment.get("cueId") == cue["id"]]
    description = cue.get("finalAnimationDescription")
    blockers: list[str] = []
    reasons: list[str] = []
    complete_lock = (
        isinstance(lock, dict)
        and all(isinstance(lock.get(key), str) and bool(lock[key].strip())
                for key in ("runtimeVersion", "aggregateSha256", "approvedPosterSha256"))
        and type(lock.get("revision")) is int
        and lock["revision"] > 0
        and ("reviewFrames" not in lock or bool(lock.get("reviewFrameSetSha256")))
    )
    if not layout_valid or not complete_lock:
        blockers.append("布局锁无效")
        reasons.append("layout-lock-invalid")
    if not isinstance(description, str) or not description.strip():
        blockers.append("缺少最终动画说明")
        reasons.append("final-animation-description-missing")
    if any(comment.get("status") == "open" for comment in cue_comments):
        blockers.append("存在未处理 comment")
        reasons.append("open-comments")

    if reasons:
        evidence_status = reasons[0]
    elif not approval:
        evidence_status = "missing"
    elif not isinstance(approval, dict):
        evidence_status = "cue-approval-invalid"
    else:
        latest_comment_revision = max((comment.get("revision", 0) for comment in cue_comments), default=0)
        approved_comment_revision = approval.get("commentRevision", -1)
        bindings = (
            ("runtimeVersion", "runtimeVersion"),
            ("layoutRevision", "revision"),
            ("layoutAggregateSha256", "aggregateSha256"),
            ("approvedPosterSha256", "approvedPosterSha256"),
            ("reviewFrameSetSha256", "reviewFrameSetSha256"),
        )
        current = (
            approval.get("status") == "approved"
            and all(approval.get(approved) == lock.get(locked) for approved, locked in bindings)
            and type(approved_comment_revision) is int
            and approved_comment_revision == latest_comment_revision
        )
        evidence_status = "current" if current else "cue-approval-stale"
    return {
        "approvalStatus": "current" if evidence_status == "current" else ("stale" if approval else "pending"),
        "canApprove": not blockers,
        "approvalBlockers": blockers,
        "evidenceStatus": evidence_status,
    }
