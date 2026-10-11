"""Immutable concept images and explicit user confirmation of visual direction.

The application owns the version transaction. This module prepares image bytes
for that transaction; generation and external-image selection remain Agent work.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path

from scripts.work_model_store import now, safe, sha, user_source
from scripts.work_model_policy import identifier, object_ids
from scripts.work_model_content import content_context, content_problems


def enabled(manifest):
    return manifest.get('workModelVersion') == '2.2.0'


def _object(manifest, object_id):
    return next((o for o in manifest.get('creativeObjects', []) if o['id'] == object_id), None)


def _concept(manifest, concept_id):
    return next((c for c in manifest.get('concepts', []) if c['id'] == concept_id), None)


def confirmed(manifest, object_id):
    """Return the confirmed image for the object's active concept round."""
    state = (_object(manifest, object_id) or {}).get('concept', {})
    record = _concept(manifest, state.get('confirmedId'))
    if not record or record['objectId'] != object_id or record['round'] != state.get('round'):
        return None
    decision = next((d for d in manifest.get('decisions', []) if d['id'] == state.get('confirmationId')
                     and d['kind'] == 'confirm-concept' and record['id'] in d.get('conceptIds', [])
                     and object_id in d.get('objectIds', [])), None)
    return record if decision else None


def image_current(root, record):
    try:
        path = safe(root, record['path'])
        return path.is_file() and sha(path) == record['sha256']
    except (OSError, ValueError, KeyError):
        return False


def require_concepts(root, manifest, cue_ids):
    """Resolve production's concrete concept basis at the existing writer/job boundary."""
    if not enabled(manifest):
        return []
    ids = list(dict.fromkeys(cue_ids))
    objects = object_ids(manifest, ids)
    basis = []
    for cid, oid in zip(ids, objects):
        record = confirmed(manifest, oid)
        if not record:
            raise ValueError(f'concept confirmation / 概念图确认 required before production: {cid}')
        if not image_current(root, record):
            raise ValueError(f'confirmed concept image unavailable; restore the recorded image bytes: {cid}')
        state = _object(manifest, oid)['concept']
        basis.append({'conceptId': record['id'], 'objectId': oid, 'decisionId': state['confirmationId'],
                      'path': record['path'], 'sha256': record['sha256']})
    return basis


def _image(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        extension, codec = '.png', 'png'
    elif data.startswith(b'\xff\xd8\xff'):
        extension, codec = '.jpg', 'mjpeg'
    elif data.startswith(b'RIFF') and data[8:12] == b'WEBP':
        extension, codec = '.webp', 'webp'
    else:
        raise ValueError('concept image must be a real PNG, JPEG or single-frame WebP raster')
    probe = subprocess.run(['ffprobe', '-v', 'error', '-count_frames', '-show_entries',
                            'stream=codec_name,width,height,nb_read_frames', '-of', 'json', '-i', 'pipe:0'],
                           input=data, capture_output=True, check=False)
    try:
        streams = json.loads(probe.stdout)['streams']
        stream = streams[0]
        valid = (probe.returncode == 0 and not probe.stderr.strip() and len(streams) == 1
                 and stream['codec_name'] == codec and stream['nb_read_frames'] == '1'
                 and stream['width'] > 0 and stream['height'] > 0)
    except (KeyError, IndexError, ValueError, TypeError):
        valid = False
    if not valid:
        raise ValueError('concept image must decode as one complete raster frame')
    return extension, {'width': stream['width'], 'height': stream['height']}


def concept_target(records):
    return {'kind': 'concept', 'conceptIds': [c['id'] for c in records],
            'objectIds': [c['objectId'] for c in records], 'cueIds': [c['cueId'] for c in records]}


def confirmation_problems(root, manifest, records, *, prepared=None):
    from scripts.work_model_feedback_targets import blocking_feedback
    problems = []
    for record in records:
        state = (_object(manifest, record['objectId']) or {}).get('concept', {})
        cue = next((c for c in manifest['cues'] if c.get('objectId') == record['objectId']), None)
        if not cue or state.get('recommendedId') != record['id'] or state.get('round') != record['round']:
            problems.append({'code': 'concept-not-current', 'conceptId': record['id'],
                             'message': '概念稿已更新，请确认当前推荐稿。'})
        if not (prepared or {}).get(record['path']) and not image_current(root, record):
            problems.append({'code': 'concept-image-unavailable', 'conceptId': record['id'],
                             'message': '概念图片缺失或内容已变动，请恢复原图片。'})
        problems.extend(content_problems(manifest, cue))
    pending = blocking_feedback(manifest, concept_target(records))
    if pending:
        problems.append({'code': 'unresolved-feedback', 'feedbackIds': [f['id'] for f in pending],
                         'message': '所选概念稿仍有待处理意见。'})
    return problems


def confirm(root, manifest, request, *, prepared=None):
    if not enabled(manifest):
        raise ValueError('concept confirmation requires a fresh work model 2.2 version')
    ids = request.get('conceptIds')
    if not isinstance(ids, list) or not ids or not all(isinstance(i, str) for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('concept confirmation requires explicit unique conceptIds')
    records = [_concept(manifest, key) for key in ids]
    if any(record is None for record in records) or len({r['objectId'] for r in records}) != len(records):
        raise ValueError('concept confirmation requires one known image per creative object')
    source = user_source(request.get('source'))
    from scripts.work_model_confirmation import apply_feedback_resolutions
    resolutions = apply_feedback_resolutions(manifest, request, records, target=concept_target(records))
    problems = confirmation_problems(root, manifest, records, prepared=prepared)
    if problems:
        raise ValueError('concept confirmation requires current reviewable images: ' + str(problems))
    decision = {'id': identifier('decision'), 'kind': 'confirm-concept', 'source': source, 'createdAt': now(),
                'conceptIds': ids, 'objectIds': [r['objectId'] for r in records]}
    if resolutions:
        decision['feedbackResolutions'] = resolutions
    manifest['decisions'].append(decision)
    for record in records:
        _object(manifest, record['objectId'])['concept'].update(confirmedId=record['id'], confirmationId=decision['id'])
    return decision


def update_concept(root, manifest, request):
    if not enabled(manifest):
        raise ValueError('concept work requires a fresh work model 2.2 version')
    action = request.get('action')
    if action == 'reopen':
        source = user_source(request.get('source'))
        ids = request.get('cueIds')
        if not ids:
            raise ValueError('concept revision requires explicit cueIds')
        objects = object_ids(manifest, ids)
        if any(not confirmed(manifest, oid) for oid in objects):
            raise ValueError('only an already confirmed concept needs a user revision; unconfirmed concepts can be freely edited')
        for oid in objects:
            state = _object(manifest, oid)['concept']
            state['round'] += 1
            state.pop('recommendedId', None)
            state.setdefault('revisions', []).append({'round': state['round'], 'source': source, 'createdAt': now()})
        return {'cueIds': ids, 'objectIds': objects, 'source': source}, []
    if action == 'propose':
        record = _concept(manifest, request.get('conceptId'))
        if not record:
            raise ValueError('unknown conceptId')
        state = _object(manifest, record['objectId'])['concept']
        if confirmed(manifest, record['objectId']) and state.get('confirmedId') != record['id']:
            raise ValueError('confirmed concept changes require an explicit user concept revision')
        if record['round'] != state['round']:
            raise ValueError('recommend a concept from the current revision round')
        state['recommendedId'] = record['id']
        return record, []
    if action != 'register':
        raise ValueError('concept action must be register, propose, or reopen')
    cue_id = request.get('cueId')
    oid = object_ids(manifest, [cue_id])[0]
    state = _object(manifest, oid).setdefault('concept', {'round': 1})
    recommend, adopt = request.get('recommend', True), request.get('adopt', False)
    if type(recommend) is not bool or type(adopt) is not bool:
        raise ValueError('concept recommend/adopt must be booleans')
    if confirmed(manifest, oid) and (recommend or adopt):
        raise ValueError('confirmed concept changes require an explicit user concept revision')
    if adopt and not recommend:
        raise ValueError('adopting an imported concept also requires recommending that image')
    origin = request.get('origin')
    if (not isinstance(origin, dict) or origin.get('kind') not in {'codex-generated', 'user-imported'}
            or not isinstance(origin.get('reference'), str) or not origin['reference'].strip()
            or set(origin) - {'kind', 'reference', 'model'}):
        raise ValueError('concept origin requires actual kind and source reference; model is optional')
    for field in ('idea', 'motion'):
        if not isinstance(request.get(field), str) or not request[field].strip():
            raise ValueError('concept requires a short idea and motion description')
    source = Path(request.get('imageSource', '')).expanduser().absolute()
    if not source.is_relative_to(root / '.staging'):
        raise ValueError('concept imageSource must be prepared in version .staging')
    source = safe(root, source.relative_to(root).as_posix())
    if not source.is_file():
        raise ValueError('concept imageSource must be a regular image file')
    data = source.read_bytes()
    extension, dimensions = _image(data)
    concept_id = identifier('concept')
    relative = 'assets/concepts/' + concept_id + extension
    cue = next(c for c in manifest['cues'] if c['id'] == cue_id)
    record = {'id': concept_id, 'objectId': oid, 'cueId': cue_id, 'round': state['round'], 'createdAt': now(),
              'path': relative, 'sha256': hashlib.sha256(data).hexdigest(), 'dimensions': dimensions,
              'origin': copy.deepcopy(origin), 'idea': request['idea'].strip(), 'motion': request['motion'].strip(),
              'contentContext': content_context(manifest, cue)}
    manifest.setdefault('concepts', []).append(record)
    if recommend:
        state['recommendedId'] = concept_id
    if adopt:
        confirm(root, manifest, {**request, 'conceptIds': [concept_id]}, prepared={relative: data})
    return record, [(safe(root, relative, exists=False), data, None)]


def status(root, manifest):
    cards = []
    for cue in manifest['cues']:
        if cue['productionMode'] != 'animation':
            continue
        state = (_object(manifest, cue.get('objectId')) or {}).get('concept', {})
        recommendation = _concept(manifest, state.get('recommendedId'))
        adopted = confirmed(manifest, cue.get('objectId'))
        problems = confirmation_problems(root, manifest, [recommendation]) if recommendation else [
            {'code': 'missing-concept', 'message': '请先生成或导入概念图。'}]
        cards.append({'cueId': cue['id'], 'objectId': cue.get('objectId'), 'title': cue.get('title', cue['id']),
                      'segmentIds': cue.get('segmentIds', []), 'contentContext': content_context(manifest, cue),
                      'recommendedId': state.get('recommendedId'), 'confirmedId': state.get('confirmedId'),
                      'firstConfirmed': bool(adopted), 'revisionPending': bool(state.get('confirmedId') and not adopted),
                      'canConfirm': not problems and not adopted, 'confirmationProblems': problems,
                      'conceptIds': [c['id'] for c in manifest.get('concepts', []) if c['objectId'] == cue.get('objectId')]})
    return {'cues': cards}
