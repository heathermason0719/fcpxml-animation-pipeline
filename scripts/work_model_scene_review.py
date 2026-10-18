"""Append-only acknowledgements of a scene's actual reviewed presentation.

These are UI progress, not creative qualification, production commissions or
media inputs. Only the shared version writer publishes them.
"""
from __future__ import annotations

import copy

from scripts.hyperframes_adapter import parse_time
from scripts.work_model_store import digest, now, safe, sha, user_source
from scripts.work_model_policy import identifier, storyboard_current, artifact_eligible


def _cue(manifest, cue_id):
    cue = next((c for c in manifest['cues'] if c['id'] == cue_id and c['productionMode'] == 'animation'), None)
    if not cue or not cue.get('objectId'):
        raise ValueError('scene review requires a registered current animation cue')
    return cue


def _animation_key(root, manifest, cue, artifact):
    from scripts.work_model_inputs import timeline_inputs
    from scripts.work_model_storyboard import review_snapshot
    # Freeze the presented interval, including overlapping layers and the real
    # source background. Unrelated scenes outside this interval do not reset
    # progress merely because a full video's global input key becomes stale.
    excluded = artifact.get('excludedCueIds', [])
    if artifact['kind'] == 'cue-preview':
        excluded = [c['id'] for c in manifest['cues'] if c['productionMode'] == 'animation' and c['id'] != cue['id']]
    timeline = timeline_inputs(root, manifest, start=parse_time(cue['resolvedTimeline']['start']),
        duration=parse_time(cue['resolvedTimeline']['duration']), excluded_cue_ids=excluded)
    return digest({'objectId': cue['objectId'], 'timeline': timeline,
                   'review': review_snapshot(manifest, cue, [])})


def _target(manifest, record):
    if record['kind'] == 'storyboard':
        from scripts.work_model_feedback_targets import design_target
        return design_target(manifest, [record['storyboardId']])
    return {'kind': 'scene', 'cueIds': [record['cueId']], 'objectIds': [record['objectId']],
            'artifactIds': [record['artifactId']]}


def _current(root, manifest, record):
    try:
        cue = _cue(manifest, record['cueId'])
        if cue['objectId'] != record['objectId']:
            return False
        if record['kind'] == 'storyboard':
            board = next((b for b in manifest.get('storyboards', []) if b['id'] == record['storyboardId']), None)
            return bool(board and board.get('reviewInputKey') == record['reviewInputKey']
                        and storyboard_current(root, manifest, board))
        artifact = next((a for a in manifest['artifacts'] if a['id'] == record['artifactId']), None)
        return bool(artifact and artifact['inputKey'] == record['inputKey']
                    and artifact['sha256'] == record['sha256'] and sha(safe(root, artifact['path'])) == record['sha256']
                    and _animation_key(root, manifest, cue, artifact) == record['sceneInputKey'])
    except (ValueError, KeyError, OSError, TypeError):
        return False


def project(root, manifest, record):
    from scripts.work_model_feedback_targets import blocking_feedback
    current = _current(root, manifest, record)
    problems = [] if current else [{'code': 'scene-review-not-current',
                                    'message': '本场呈现内容已变化或证据不可用，请查看当前内容。'}]
    feedback = blocking_feedback(manifest, _target(manifest, record))
    if feedback:
        problems.append({'code': 'unresolved-feedback', 'message': '本场仍有待处理意见。',
                         'feedbackIds': [f['id'] for f in feedback]})
    return {**copy.deepcopy(record), 'current': current, 'problems': problems}


def status(root, manifest):
    return [project(root, manifest, record) for record in manifest.get('sceneReviews', [])]


def acknowledge(root, manifest, request):
    source = user_source(request.get('source'))
    cue = _cue(manifest, request.get('cueId'))
    kind = request.get('kind')
    record = {'id': identifier('scene-review'), 'kind': kind, 'cueId': cue['id'], 'objectId': cue['objectId'],
              'source': source, 'createdAt': now()}
    if kind == 'storyboard':
        board = next((b for b in manifest.get('storyboards', []) if b['id'] == request.get('storyboardId')), None)
        if (request.get('artifactId') is not None or not board or board['cueId'] != cue['id']
                or board['objectId'] != cue['objectId'] or not board.get('reviewInputKey')
                or not storyboard_current(root, manifest, board)):
            raise ValueError('scene review requires the current Storyboard reviewInputKey and verified frames')
        record.update(storyboardId=board['id'], reviewInputKey=board['reviewInputKey'])
    elif kind == 'animation':
        from scripts.work_model import _artifact_current
        artifact = next((a for a in manifest['artifacts'] if a['id'] == request.get('artifactId')), None)
        if (request.get('storyboardId') is not None or not artifact
                or artifact['kind'] not in {'local-preview', 'full-preview', 'cue-preview'}
                or cue['id'] not in artifact['cueIds'] or not artifact_eligible(manifest, artifact)
                or not _artifact_current(root, manifest, artifact)):
            raise ValueError('scene review requires a current verified video artifact covering this cue')
        start, duration = (parse_time(artifact['range'][key]) for key in ('start', 'duration'))
        cue_start, cue_duration = (parse_time(cue['resolvedTimeline'][key]) for key in ('start', 'duration'))
        if start > cue_start or start + duration < cue_start + cue_duration:
            raise ValueError('scene review video must cover the entire cue duration')
        record.update(artifactId=artifact['id'], inputKey=artifact['inputKey'], sha256=artifact['sha256'],
                      sceneInputKey=_animation_key(root, manifest, cue, artifact))
    else:
        raise ValueError('scene review kind must be storyboard or animation')
    manifest.setdefault('sceneReviews', []).append(record)
    return record
