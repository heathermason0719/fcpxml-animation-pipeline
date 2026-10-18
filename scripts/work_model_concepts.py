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
    if any(field in request for field in ('copiedFromConceptId', 'selectionSource')):
        raise ValueError('concept copy provenance is assigned only by the version writer')
    action = request.get('action')
    if action == 'select':
        # A user selection changes the recommended direction, never its approval.
        # Prepare and verify all bytes before touching the round; update() owns
        # publication, schema validation and rollback under the version lock.
        source = user_source(request.get('source'))
        record = _concept(manifest, request.get('conceptId'))
        cue = next((c for c in manifest['cues'] if record and c.get('objectId') == record['objectId']
                    and c['productionMode'] == 'animation'), None)
        if not record or not cue:
            raise ValueError('select requires a concept belonging to a current animation object')
        if not image_current(root, record):
            raise ValueError('concept image unavailable; restore the recorded image bytes')
        state = _object(manifest, record['objectId'])['concept']
        adopted = confirmed(manifest, record['objectId'])
        from scripts.work_model_feedback_targets import same_concept_image
        if adopted and same_concept_image(manifest, adopted['id'], record['id']):
            if not image_current(root, adopted):
                raise ValueError('confirmed concept image unavailable; restore the recorded image bytes')
            return adopted, []
        data = safe(root, record['path']).read_bytes()
        if hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError('concept image changed while selecting; restore recorded bytes')
        if adopted:
            state['round'] += 1
            state.setdefault('revisions', []).append({'round': state['round'], 'source': source, 'createdAt': now()})
        if record['round'] == state['round']:
            state['recommendedId'] = record['id']
            return record, []
        # A repeated historical selection reuses an owned current-round copy.
        # This keeps one candidate identity and its opinions through retries or
        # selecting the original thumbnail again; equal bytes alone do not link
        # independently registered directions.
        for candidate in reversed(manifest['concepts']):
            if (candidate['round'] == state['round']
                    and same_concept_image(manifest, candidate['id'], record['id'])
                    and image_current(root, candidate)):
                state['recommendedId'] = candidate['id']
                return candidate, []
        copied = copy.deepcopy(record)
        copied.update(id=identifier('concept'), cueId=cue['id'], round=state['round'], createdAt=now(),
                      copiedFromConceptId=record['id'], selectionSource=source)
        copied['path'] = 'assets/concepts/' + copied['id'] + Path(record['path']).suffix.lower()
        manifest['concepts'].append(copied)
        state['recommendedId'] = copied['id']
        return copied, [(safe(root, copied['path'], exists=False), data, None)]
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
        raise ValueError('concept action must be register, propose, select, or reopen')
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


def _handoff_partition(manifest, selected, excluded):
    for values in (selected, excluded):
        if (not isinstance(values, list) or not all(isinstance(cid, str) and cid for cid in values)
                or len(set(values)) != len(values)):
            raise ValueError('concept handoff requires explicit unique cueIds and excludedCueIds')
    all_ids = {c['id'] for c in manifest['cues'] if c['productionMode'] == 'animation'}
    if not selected or set(selected) & set(excluded) or set(selected) | set(excluded) != all_ids:
        raise ValueError('concept handoff must exactly partition selected and excluded animation cues')
    return object_ids(manifest, selected), object_ids(manifest, excluded)


def handoff(root, manifest, request):
    """Confirm selected current images and save the stated Storyboard scope.

    This is a short version transaction, not a Motion/Demo commission or a
    new production gate. Validate the entire selection before confirming any
    image; the caller publishes both facts with one schema-checked save.
    """
    if not enabled(manifest):
        raise ValueError('concept handoff requires a fresh work model 2.2 version')
    source = user_source(request.get('source'))
    cue_ids, excluded_ids = request.get('cueIds'), request.get('excludedCueIds')
    objects, excluded_objects = _handoff_partition(manifest, cue_ids, excluded_ids)
    concept_ids = request.get('conceptIds')
    if (not isinstance(concept_ids, list) or len(concept_ids) != len(cue_ids)
            or not all(isinstance(cid, str) and cid for cid in concept_ids)
            or len(set(concept_ids)) != len(concept_ids)):
        raise ValueError('concept handoff requires one explicit current recommended concept per selected cue')
    records = [_concept(manifest, cid) for cid in concept_ids]
    if any(not record or record['objectId'] != oid for record, oid in zip(records, objects)):
        raise ValueError('concept handoff requires the current recommended concept for each selected object')
    problems = confirmation_problems(root, manifest, records)
    if problems:
        raise ValueError('concept handoff requires current reviewable images: ' + str(problems))
    pending = [record['id'] for record in records if not confirmed(manifest, record['objectId'])]
    if pending:
        confirm(root, manifest, {'conceptIds': pending, 'source': source})
    record = {'id': identifier('storyboard-handoff'), 'requestId': request['requestId'],
              'source': source, 'createdAt': now(),
              'selected': [{'cueId': cid, 'objectId': oid, 'conceptId': concept_id}
                           for cid, oid, concept_id in zip(cue_ids, objects, concept_ids)],
              'excluded': [{'cueId': cid, 'objectId': oid,
                            'conceptId': _object(manifest, oid).get('concept', {}).get('recommendedId')}
                           for cid, oid in zip(excluded_ids, excluded_objects)]}
    manifest.setdefault('storyboardHandoffs', []).append(record)
    return record


def handoff_status(root, manifest):
    """Latest handoff and advisory validity, never consumed as eligibility."""
    latest = next(iter(reversed(manifest.get('storyboardHandoffs', []))), None)
    if not latest:
        return None
    problems = []
    cues = {c['id']: c for c in manifest['cues'] if c['productionMode'] == 'animation'}
    items = latest['selected'] + latest['excluded']
    if (len({item['cueId'] for item in items}) != len(items) or {item['cueId'] for item in items} != set(cues)
            or any(cues.get(item['cueId'], {}).get('objectId') != item['objectId'] for item in items)):
        problems.append({'code': 'handoff-scope-changed', 'message': '动画范围或创意对象已变化，请核对原分镜交棒范围。'})
    records = []
    for item in latest['selected']:
        record = _concept(manifest, item['conceptId'])
        active = confirmed(manifest, item['objectId'])
        if not record or record['objectId'] != item['objectId'] or not active or active['id'] != item['conceptId']:
            problems.append({'code': 'handoff-concept-changed', 'cueId': item['cueId'],
                             'message': '本场当前概念依据已变化，请核对原分镜交棒。'})
        if record:
            records.append(record)
    if records:
        problems.extend(confirmation_problems(root, manifest, records))
    return {**copy.deepcopy(latest), 'current': not problems, 'problems': problems}


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
    return {'cues': cards, 'storyboardHandoff': handoff_status(root, manifest)}
