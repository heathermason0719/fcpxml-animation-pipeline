"""Resolve feedback applicability from stable product and review evidence.

Feedback is written against a concrete target, while confirmations, reviews and
delivery operate on different collections of objects.  This module translates
both sides to the same frozen product identities without inferring adoption
from a matching exploration id alone.
"""
from __future__ import annotations

from scripts.hyperframes_adapter import parse_time


OPEN_FEEDBACK = {"pending", "needs-clarification"}
NONBLOCKING_APPLICABILITY = {"deferred", "not-applicable"}


def _unique(values):
    return sorted({value for value in values if isinstance(value, str) and value})


def _cues(manifest):
    return {cue.get("id"): cue for cue in manifest.get("cues", []) if isinstance(cue, dict)}


def _objects_for_cues(manifest, cue_ids):
    cues = _cues(manifest)
    return _unique(cues[cue_id].get("objectId") for cue_id in cue_ids if cue_id in cues)


def _board(manifest, board_id):
    return next((item for item in manifest.get("storyboards", [])
                 if isinstance(item, dict) and item.get("id") == board_id), None)


def _artifact(manifest, artifact_id):
    return next((item for item in manifest.get("artifacts", [])
                 if isinstance(item, dict) and item.get("id") == artifact_id), None)


def _board_for_artifact(manifest, artifact_id):
    return next((item for item in manifest.get("storyboards", []) if isinstance(item, dict)
                 and artifact_id in item.get("artifactIds", [])), None)


def _target(*, kind, cue_ids=(), object_ids=(), storyboard_ids=(), artifact_ids=(), segment_ids=(), time=None,
            review_id=None):
    value = {
        "kind": kind,
        "cueIds": _unique(cue_ids),
        "objectIds": _unique(object_ids),
        "storyboardIds": _unique(storyboard_ids),
        "artifactIds": _unique(artifact_ids),
        "segmentIds": _unique(segment_ids),
    }
    if time is not None:
        value["time"] = time
    if review_id:
        value["reviewId"] = review_id
    return value


def design_target(manifest, boards):
    """Return the stable product scope selected by a design confirmation."""
    items = []
    for candidate in boards or []:
        item = _board(manifest, candidate) if isinstance(candidate, str) else candidate
        if not isinstance(item, dict):
            continue
        items.append(item)
    cue_ids = [item.get("cueId") for item in items]
    return _target(kind="design", cue_ids=cue_ids,
                   object_ids=[item.get("objectId") for item in items] + _objects_for_cues(manifest, cue_ids),
                   storyboard_ids=[item.get("id") for item in items],
                   artifact_ids=[artifact for item in items for artifact in item.get("artifactIds", [])])


def review_target(manifest, review):
    """Return every canonical object actually covered by a complete review.

    The production basis is authoritative for a full review's presented scope.
    Its use keeps an unmodified but presented Cue covered even if a particular
    review artifact happens not to enumerate the Cue directly.
    """
    if not isinstance(review, dict):
        return _target(kind="review")
    artifacts = [_artifact(manifest, key) for key in review.get("artifactIds", [])]
    artifacts = [item for item in artifacts if item]
    basis = review.get("productionBasis", {})
    cue_ids = [cue_id for item in artifacts for cue_id in item.get("cueIds", [])]
    cue_ids += basis.get("presentationCueIds", [])
    object_ids = [object_id for item in artifacts for object_id in item.get("objectIds", [])]
    object_ids += basis.get("presentationObjectIds", [])
    object_ids += _objects_for_cues(manifest, cue_ids)
    return _target(kind="review", cue_ids=cue_ids, object_ids=object_ids,
                   artifact_ids=[item.get("id") for item in artifacts], review_id=review.get("id"))


def _feedback_exploration(manifest, feedback):
    target = feedback.get("target", {})
    if not isinstance(target, dict):
        return None
    artifact = _artifact(manifest, target.get("artifactId"))
    exploration_id = target.get("explorationId") or (artifact or {}).get("explorationId")
    variant_id = target.get("variantId") or (artifact or {}).get("variantId")
    if not exploration_id or not variant_id:
        return None
    return {
        "explorationId": exploration_id,
        "variantId": variant_id,
        "variantRevision": target.get("variantRevision"),
        "variantContentIdentity": target.get("variantContentIdentity"),
    }


def _adoptions(manifest, anchor):
    for exploration in manifest.get("explorations", []):
        if not isinstance(exploration, dict) or exploration.get("id") != anchor["explorationId"]:
            continue
        for adoption in exploration.get("adoptions", []):
            if not isinstance(adoption, dict) or adoption.get("variantId") != anchor["variantId"]:
                continue
            # Legacy records with no frozen candidate evidence cannot make an
            # optional exploration opinion block canonical work.
            if not adoption.get("variantContentIdentity"):
                continue
            if anchor.get("variantContentIdentity") != adoption.get("variantContentIdentity"):
                continue
            if anchor.get("variantRevision") is not None and anchor.get("variantRevision") != adoption.get("variantRevision"):
                continue
            yield adoption


def _canonical_scope(manifest, feedback):
    target = feedback.get("target", {})
    if not isinstance(target, dict):
        return _target(kind="feedback")
    cue_ids = list(target.get("cueIds", []))
    object_ids = list(target.get("objectIds", []))
    board = _board(manifest, target.get("storyboardId"))
    if board:
        object_ids.append(board.get("objectId"))
    artifact = _artifact(manifest, target.get("artifactId"))
    if artifact and artifact.get("purpose") != "exploration":
        object_ids += artifact.get("objectIds", [])
        # A frame artifact may outlive its canonical Cue binding.  Its
        # historical Storyboard owns the product identity, so never translate
        # that artifact through a later Cue with the same technical id.
        historical = _board_for_artifact(manifest, artifact.get("id"))
        if historical:
            object_ids.append(historical.get("objectId"))
        else:
            cue_ids += artifact.get("cueIds", [])
    # `objectIds` is frozen by the feedback writer.  Once present it owns the
    # product association: mapping an old technical Cue id again could attach
    # this opinion to a later replacement that reused the same id.
    if not object_ids:
        object_ids += _objects_for_cues(manifest, cue_ids)
    interval = None
    if target.get("timeStart") is not None or target.get("timeEnd") is not None:
        try:
            interval = (parse_time(target["timeStart"]) if target.get("timeStart") is not None else None,
                        parse_time(target["timeEnd"]) if target.get("timeEnd") is not None else None)
        except (TypeError, ValueError):
            interval = None
    return _target(kind="feedback", cue_ids=cue_ids, object_ids=object_ids,
                   storyboard_ids=[target.get("storyboardId")], artifact_ids=[target.get("artifactId")],
                   segment_ids=target.get("segmentIds", []), time=interval)


def _interval_overlaps(manifest, cue_id, interval):
    cue = _cues(manifest).get(cue_id)
    timeline = (cue or {}).get("resolvedTimeline", {})
    try:
        start = parse_time(timeline["start"])
        end = start + parse_time(timeline["duration"])
    except (KeyError, TypeError, ValueError):
        return False
    return (interval[0] is None or interval[0] < end) and (interval[1] is None or start < interval[1])


def _scope_matches(manifest, scope, target):
    """Product identity survives changes to its historical location anchors.

    Cue/segment/time fields locate a comment; changing a Cue's placement must
    not silently resolve an opinion already attached to a stable object.
    Narrower location matching is used only when there is no object owner.
    """
    if scope['objectIds']:
        return bool(set(scope['objectIds']).intersection(target.get('objectIds', [])))
    if scope['cueIds']:
        return bool(set(scope['cueIds']).intersection(target.get('cueIds', [])))
    if scope['segmentIds']:
        segments = {segment for cue in _cues(manifest).values() if cue.get('id') in target.get('cueIds', [])
                    for segment in cue.get('segmentIds', [])}
        return bool(set(scope['segmentIds']).intersection(segments))
    if scope.get('time') is not None:
        return any(_interval_overlaps(manifest, cue_id, scope['time']) for cue_id in target.get('cueIds', []))
    return True


def _has_unresolved_narrow_anchor(source):
    return any(source.get(key) is not None for key in ("storyboardId", "artifactId", "cueIds", "segmentIds", "timeStart", "timeEnd"))


def feedback_applies(manifest, feedback, target):
    """Whether a pending feedback fact applies to a resolved canonical target."""
    if not isinstance(feedback, dict) or not isinstance(target, dict):
        return False
    source = feedback.get("target", {})
    if not isinstance(source, dict) or source.get("versionId") != manifest.get("identity", {}).get("versionId"):
        return False
    if feedback.get("applicability", {}).get("kind", "current") in NONBLOCKING_APPLICABILITY:
        return False
    exploration = _feedback_exploration(manifest, feedback)
    if exploration:
        adopted = [adoption for adoption in _adoptions(manifest, exploration)
                   if set(adoption.get("objectIds", [])).intersection(target.get("objectIds", []))]
        if not adopted:
            return False
        explicit = _canonical_scope(manifest, feedback)
        return _scope_matches(manifest, explicit, target)
    scope = _canonical_scope(manifest, feedback)
    if scope["objectIds"] or scope["cueIds"] or scope["segmentIds"] or scope.get("time") is not None:
        return _scope_matches(manifest, scope, target)
    if _has_unresolved_narrow_anchor(source):
        return False
    # A version-scoped opinion deliberately has no narrower product anchor.
    return True


def blocking_feedback(manifest, target):
    """Return unresolved feedback that applies to the selected target."""
    return sorted((item for item in manifest.get("feedback", [])
                   if isinstance(item, dict) and item.get("status") in OPEN_FEEDBACK
                   and feedback_applies(manifest, item, target)), key=lambda item: item.get("id", ""))
