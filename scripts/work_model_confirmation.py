"""Confirmation-specific design evidence checks.

This module deliberately separates technical frame validity from the evidence a
person needs to confirm a design.  Callers own transaction boundaries: resolve
the user's explicit feedback choices on a working manifest, then ask for the
remaining blockers before recording a decision.
"""
from __future__ import annotations

from scripts.work_model_store import user_source


OPEN_FEEDBACK = {'pending', 'needs-clarification'}
NONBLOCKING_APPLICABILITY = {'deferred', 'not-applicable'}


def _selected(manifest, records):
    """Return selected storyboard records without silently changing scope."""
    known = {item.get('id'): item for item in manifest.get('storyboards', []) if isinstance(item, dict)}
    if not isinstance(records, list) or not records:
        raise ValueError('confirmation requires explicit Storyboard records')
    selected = []
    seen = set()
    for item in records:
        key = item if isinstance(item, str) else item.get('id') if isinstance(item, dict) else None
        if not isinstance(key, str) or key in seen or key not in known:
            raise ValueError('confirmation requires unique known Storyboard records')
        seen.add(key)
        selected.append(known[key])
    return selected


def _nonblank(value):
    return isinstance(value, str) and bool(value.strip())


def _feedback_applies(manifest, feedback, selected):
    from scripts.work_model_feedback_targets import design_target, feedback_applies
    return feedback_applies(manifest, feedback, design_target(manifest, selected))


def _feedback_blockers(manifest, selected):
    from scripts.work_model_feedback_targets import design_target, blocking_feedback
    return blocking_feedback(manifest, design_target(manifest, selected))


def confirmation_problems(root, manifest, records):
    """Return all confirmation blockers for explicitly selected storyboards."""
    from scripts.work_model_policy import storyboard_current
    from scripts.work_model_content import content_problems

    selected = _selected(manifest, records)
    cues = {item.get('id'): item for item in manifest.get('cues', []) if isinstance(item, dict)}
    problems = []
    for board in selected:
        cue = cues.get(board.get('cueId'))
        base = {'storyboardId': board['id'], 'cueId': board.get('cueId')}
        if not storyboard_current(root, manifest, board):
            problems.append({**base, 'code': 'storyboard-not-current',
                             'message': 'Storyboard frames are no longer current for this design object.'})
        if not _nonblank(board.get('finalAnimationDescription')):
            problems.append({**base, 'code': 'missing-final-animation-description',
                             'message': 'Storyboard confirmation requires a nonblank final animation description snapshot.'})
        problems.extend({**base, **problem} for problem in content_problems(manifest, cue))
    feedback = _feedback_blockers(manifest, selected)
    if feedback:
        problems.append({'code': 'unresolved-feedback',
                         'message': 'Selected design objects still have pending feedback or clarification.',
                         'feedbackIds': [item['id'] for item in feedback]})
    return problems


def apply_feedback_resolutions(manifest, request, records):
    """Apply only explicit user choices, after validating the whole batch.

    The function mutates ``manifest`` only after every item is known to belong
    to the confirmation objects.  A transaction caller can therefore abandon a
    rejected confirmation without a partial resolution record.
    """
    values = request.get('feedbackResolutions')
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError('feedbackResolutions must be a list')
    selected = _selected(manifest, records)
    source = user_source(request.get('source'))
    feedback = {item.get('id'): item for item in manifest.get('feedback', []) if isinstance(item, dict)}
    normalized = []
    seen = set()
    for item in values:
        if not isinstance(item, dict) or set(item) != {'feedbackId', 'action'}:
            raise ValueError('feedback resolution requires feedbackId and action')
        feedback_id, action = item.get('feedbackId'), item.get('action')
        if not isinstance(feedback_id, str) or feedback_id in seen:
            raise ValueError('feedback resolution ids must be unique')
        if action not in {'accept', 'defer', 'withdraw'}:
            raise ValueError('feedback resolution action must be accept, defer, or withdraw')
        record = feedback.get(feedback_id)
        if not record or not _feedback_applies(manifest, record, selected):
            raise ValueError('feedback resolution does not belong to this confirmation object')
        if item['action'] != 'accept' and record.get('status') not in OPEN_FEEDBACK:
            raise ValueError('only pending feedback or clarification can be deferred or withdrawn here')
        if item['action'] == 'accept' and record.get('status') not in OPEN_FEEDBACK | {'addressed'}:
            raise ValueError('only pending feedback or clarification can be resolved here')
        seen.add(feedback_id)
        normalized.append({'feedbackId': feedback_id, 'action': action})
    for item in normalized:
        record = feedback[item['feedbackId']]
        if item['action'] == 'accept':
            record.update(status='accepted', acceptedSource=source)
        else:
            record['applicability'] = {
                'kind': 'deferred' if item['action'] == 'defer' else 'not-applicable',
                'source': source,
            }
    return normalized
