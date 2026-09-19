"""Canonical facts about the narration and visible-copy context of a Cue.

These facts make an absence explicit without inventing a second prose source:
the copy itself remains in the established Cue and brief fields.  The helper is
deliberately pure so callers can validate a proposed manifest before saving it.
"""
from __future__ import annotations

from scripts.work_model_inputs import cue_narration


_CHANNELS = ("narration", "screenText")
_STATES = {"present", "none", "unknown"}


def _nonblank(value):
    return isinstance(value, str) and bool(value.strip())


def _screen_text(cue):
    """Return only actual visible copy, never labels or arbitrary metadata."""
    value = cue.get("screenText") if isinstance(cue, dict) else None
    if isinstance(value, str):
        return value.strip() if _nonblank(value) else ""
    if isinstance(value, dict):
        values = [value.get(key) for key in ("text", "content")]
    elif isinstance(value, list):
        values = [
            item if isinstance(item, str) else item.get(key)
            for item in value
            for key in (("text", "content") if isinstance(item, dict) else (None,))
        ]
    else:
        values = []
    return "\n".join(item.strip() for item in values if _nonblank(item))


def _actual_text(manifest, cue, channel):
    cue = cue if isinstance(cue, dict) else {}
    if channel == "narration":
        return cue_narration(manifest, cue).strip()
    return _screen_text(cue)


def _declaration(cue, channel):
    context = cue.get("contentContext") if isinstance(cue, dict) else None
    value = context.get(channel) if isinstance(context, dict) else None
    return value if isinstance(value, dict) else None


def content_context(manifest, cue):
    """Return normalized channel facts without modifying a Cue.

    A declaration controls the state when structurally usable.  Without one,
    actual nonblank text is ``present`` and missing input is ``unknown``;
    missing data is never treated as a factual absence.
    """
    result = {}
    for channel in _CHANNELS:
        actual = _actual_text(manifest, cue, channel)
        declaration = _declaration(cue, channel)
        state = declaration.get("state") if declaration and declaration.get("state") in _STATES else None
        entry = {"state": state or ("present" if actual else "unknown")}
        if actual:
            entry["text"] = actual
        basis = declaration.get("basis") if declaration else None
        if (isinstance(basis, dict) and _nonblank(basis.get("text"))
                and _nonblank(basis.get("reference"))):
            entry["basis"] = {"text": basis["text"].strip(), "reference": basis["reference"].strip()}
        result[channel] = entry
    return result


def _problem(code, message, channel=None):
    result = {"code": code, "message": message}
    if channel:
        result["channel"] = channel
    return result


def validate_content_declarations(manifest, cue):
    """Return declaration shape and contradiction problems for one Cue.

    This does not reject an otherwise valid draft solely because a channel is
    ``unknown``.  Completion checks belong in :func:`content_problems`.
    """
    if not isinstance(cue, dict):
        return [_problem("invalid-content-context", "Cue content context requires a Cue object.")]
    context = cue.get("contentContext")
    if context is None:
        return []
    if not isinstance(context, dict) or set(context) != set(_CHANNELS):
        return [_problem("invalid-content-context", "contentContext requires exactly narration and screenText facts.")]

    problems = []
    for channel in _CHANNELS:
        declaration = context[channel]
        if not isinstance(declaration, dict) or "state" not in declaration or set(declaration) - {"state", "basis"}:
            problems.append(_problem("invalid-content-declaration", "Content channel requires state and optional basis only.", channel))
            continue
        state = declaration.get("state")
        if state not in _STATES:
            problems.append(_problem("invalid-content-state", "Content state must be present, none, or unknown.", channel))
            continue
        basis = declaration.get("basis")
        if basis is not None and (not isinstance(basis, dict) or set(basis) != {"text", "reference"}
                                  or not _nonblank(basis.get("text")) or not _nonblank(basis.get("reference"))):
            problems.append(_problem("invalid-content-basis", "Content basis requires nonblank text and reference.", channel))
        if state == "none" and basis is None:
            problems.append(_problem("none-content-requires-basis", "An explicit none content fact requires an evidenced basis.", channel))
        actual = _actual_text(manifest, cue, channel)
        if state == "none" and actual:
            problems.append(_problem("none-" + ("narration" if channel == "narration" else "screen-text") + "-conflicts-with-text",
                                     "An explicit none content fact conflicts with actual Cue text.", channel))
        if state == "present" and not actual:
            problems.append(_problem("present-" + ("narration" if channel == "narration" else "screen-text") + "-requires-text",
                                     "A present content fact requires actual Cue text.", channel))
    return problems


def content_problems(manifest, cue):
    """Return confirmation blockers after validating the Cue's content facts."""
    problems = validate_content_declarations(manifest, cue)
    for channel, entry in content_context(manifest, cue).items():
        if entry["state"] == "unknown":
            label = "narration" if channel == "narration" else "screen-text"
            problems.append(_problem("unknown-" + label + "-content",
                                     "Storyboard confirmation requires an explicit content fact for this channel.", channel))
    return problems
