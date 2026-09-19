"""Review handoff batches and scoped feedback; no design approval side effects."""
from __future__ import annotations
import copy

from scripts.hyperframes_adapter import parse_time
from scripts.work_model_store import now, user_source
from scripts.work_model_policy import identifier


def add_feedback(manifest, request, *, root=None):
    body = request.get('body')
    if not isinstance(body, str) or not body.strip():
        raise ValueError('feedback body is required')
    target = copy.deepcopy(request.get('target', {}))
    if target.get('versionId') != manifest['identity']['versionId']:
        raise ValueError('feedback target version mismatch')
    artifacts = {item['id']: item for item in manifest['artifacts']}
    if target.get('artifactId') and target['artifactId'] not in artifacts:
        raise ValueError('unknown feedback artifact')
    for field, valid in (('cueIds', {c['id'] for c in manifest['cues']}),
                         ('segmentIds', {s['id'] for s in manifest['brief']['segments']})):
        if not set(target.get(field, [])).issubset(valid):
            raise ValueError('unknown feedback target')
    if target.get('storyboardId'):
        board = next((s for s in manifest.get('storyboards', []) if s['id'] == target['storyboardId']), None)
        if not board or target.get('artifactId') not in board['artifactIds']:
            raise ValueError('feedback frame does not belong to that Storyboard snapshot')
        artifact = next(a for a in manifest['artifacts'] if a['id'] == target['artifactId'])
        if target.get('frameId') != artifact['frameId'] or target.get('cueIds') != [board['cueId']]:
            raise ValueError('feedback frame anchor mismatch')
    artifact = artifacts.get(target.get('artifactId'))
    artifact_exploration = artifact and artifact.get('purpose') == 'exploration'
    if artifact_exploration:
        if target.get('explorationId') not in (None, artifact.get('explorationId')) or target.get('variantId') not in (None, artifact.get('variantId')):
            raise ValueError('feedback exploration anchor mismatch')
        target['explorationId'] = artifact['explorationId']
        target['variantId'] = artifact['variantId']
    if target.get('explorationId') or target.get('variantId'):
        exploration = next((e for e in manifest.get('explorations', []) if e['id'] == target.get('explorationId')), None)
        variant = next((v for v in (exploration or {}).get('variants', []) if v['id'] == target.get('variantId')), None)
        if not variant:
            raise ValueError('unknown exploration variant')
        if target.get('variantRevision') is not None or target.get('variantContentIdentity') is not None:
            raise ValueError('feedback exploration lineage is captured by the writer')
        if artifact_exploration:
            # An old exploration frame with no frozen lineage is historical
            # evidence of an unknown candidate.  It must not be rebound to a
            # later variant merely because the display id still matches.
            for key in ('variantRevision', 'variantContentIdentity'):
                if artifact.get(key) is not None:
                    target[key] = artifact[key]
        else:
            from scripts.work_model_exploration import variant_lineage
            lineage = variant_lineage(variant, root, manifest=manifest)
            target['variantRevision'] = lineage['revision']
            target['variantContentIdentity'] = lineage['contentIdentity']
    # Freeze product identity on write; renaming a technical cue must neither
    # detach its comments nor transfer them to a newly created object.
    if 'objectIds' in target:
        raise ValueError('feedback object identity is captured by the writer')
    if target.get('cueIds'):
        target['objectIds'] = [c['objectId'] for c in manifest['cues']
                               if c['id'] in target['cueIds'] and c.get('objectId')]
    start = parse_time(target['timeStart']) if target.get('timeStart') else None
    end = parse_time(target['timeEnd']) if target.get('timeEnd') else None
    if (start is not None and start < 0) or (end is not None and (start is None or end < start)):
        raise ValueError('invalid feedback time interval')
    if manifest['project'].get('source'):
        total = parse_time(manifest['project']['source']['duration'])
        if any(t is not None and t > total for t in (start, end)):
            raise ValueError('feedback interval outside episode')
    record = {'id': identifier('feedback'), 'body': body.strip(), 'target': target,
              'source': user_source(request.get('source')), 'status': 'pending', 'createdAt': now()}
    manifest['feedback'].append(record)
    return record


def submit_round(root, manifest, request):
    from scripts.work_model_storyboard import frame_current
    ids = request.get('storyboardIds', [])
    known = {s['id'] for s in manifest.get('storyboards', [])}
    if len(ids) != len(set(ids)) or not set(ids).issubset(known):
        raise ValueError('unknown or duplicate reviewed Storyboard snapshot')
    feedback_ids = list(request.get('feedbackIds', []))
    records = {f['id']: f for f in manifest['feedback']}
    if len(feedback_ids) != len(set(feedback_ids)) or not set(feedback_ids).issubset(records):
        raise ValueError('unknown or duplicate review feedback')
    submitted = {fid for r in manifest.get('reviewRounds', []) for fid in r['feedbackIds']}
    if submitted.intersection(feedback_ids):
        raise ValueError('feedback already belongs to a submitted round')
    for draft in request.get('drafts', []):
        aid = draft.get('target', {}).get('artifactId')
        artifact = next((a for a in manifest['artifacts'] if a['id'] == aid), None)
        if not artifact or artifact.get('purpose') != 'storyboard' or not frame_current(root, manifest, artifact):
            raise ValueError('stale frame draft; retain draft and explicitly rebind before handoff')
        feedback_ids.append(add_feedback(manifest, draft)['id'])
    record = {'id': identifier('round'), 'storyboardIds': list(ids), 'feedbackIds': feedback_ids,
              'source': user_source(request.get('source')), 'status': 'submitted', 'createdAt': now()}
    manifest['reviewRounds'].append(record)
    return record


def round_progress(manifest, request):
    record = next((r for r in manifest['reviewRounds'] if r['id'] == request.get('roundId')), None)
    if not record or request.get('status') not in {'processing', 'processed'}:
        raise ValueError('unknown round or unsupported processing status')
    if request['status'] == 'processed':
        unresolved = [f for f in manifest['feedback'] if f['id'] in record['feedbackIds']
                      and f['status'] in {'pending', 'needs-clarification'}
                      and f.get('applicability', {}).get('kind', 'current') == 'current']
        if unresolved:
            raise ValueError('submitted feedback is still unresolved')
        if not request.get('resolution'):
            raise ValueError('processed round requires an actual resolution')
    record.update(status=request['status'], resolution=request.get('resolution', ''), updatedAt=now())
    return record
