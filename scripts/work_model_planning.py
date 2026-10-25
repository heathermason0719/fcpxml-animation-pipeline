"""Version-owned creative records, never production authority or media inputs.

Cues remain the editable plan. These immutable snapshots and call receipts let
an Agent recover the discussion and its bounded image exploration. The Agent
classifies style/problem semantics and records actual tool references; this
module does not intercept or execute image tools.
"""
from __future__ import annotations

import copy

from scripts.work_model_content import content_context
from scripts.work_model_store import digest, now, user_source
from scripts.work_model_policy import identifier


def _data(manifest):
    return manifest.get('creativePlanning', {'plans': [], 'rounds': [], 'attempts': []})


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + ' must be nonempty text')
    return value.strip()


def _cues(manifest):
    return {c['objectId']: c for c in manifest['cues']
            if c['productionMode'] == 'animation' and c.get('objectId')}


def _selected(manifest, cue_ids=None):
    cues = _cues(manifest)
    if cue_ids is None:
        return list(cues)
    by_id = {c['id']: oid for oid, c in cues.items()}
    if (not isinstance(cue_ids, list) or not cue_ids
            or not all(isinstance(cid, str) and cid in by_id for cid in cue_ids)
            or len(set(cue_ids)) != len(cue_ids)):
        raise ValueError('planning requires unique current animation cueIds')
    return [by_id[cid] for cid in cue_ids]


def _snapshot(manifest, oid):
    cue = _cues(manifest)[oid]
    content = {key: copy.deepcopy(cue.get(key, '')) for key in
               ('purpose', 'visualPlan', 'finalAnimationDescription')}
    content['contentContext'] = content_context(manifest, cue)
    return {'objectId': oid, 'cueId': cue['id'], 'title': cue.get('title', cue['id']),
            'content': content, 'contentKey': digest(content)}


def _plan_for(data, oid):
    return next((p for p in reversed(data['plans']) if any(o['objectId'] == oid for o in p['objects'])), None)


def _plan_current(manifest, plan, oid):
    cues = _cues(manifest)
    item = next((o for o in plan['objects'] if o['objectId'] == oid), None)
    scope_current = plan['scope'] != 'all' or {o['objectId'] for o in plan['objects']} == set(cues)
    return bool(item and oid in cues and scope_current
                and item['contentKey'] == _snapshot(manifest, oid)['contentKey'])


def _basis(manifest, oid):
    data = _data(manifest)
    cue = _cues(manifest)[oid]
    row = {'objectId': oid, 'cueId': cue['id'], 'title': cue.get('title', cue['id']), 'state': 'unrecorded'}
    plan = _plan_for(data, oid)
    if plan:
        current = _plan_current(manifest, plan, oid)
        row.update(planId=plan['id'], summary=plan['summary'], question=plan['question'],
                   state='needs-discussion' if not current else 'ready' if plan.get('closure') else 'waiting-response')
        if plan.get('closure'):
            row['source'] = copy.deepcopy(plan['closure']['source'])
    return row


def _ready(manifest, oid):
    basis = _basis(manifest, oid)
    if basis['state'] != 'ready':
        raise ValueError('image exploration needs a current discussion and explicit reply: ' + basis['state'])
    return basis


def _round_for(data, oid):
    return next((r for r in reversed(data['rounds']) if r['objectId'] == oid), None)


def _attempts(data, round_id):
    for attempt in data['attempts']:
        target = next((t for t in attempt['targets'] if t['roundId'] == round_id), None)
        if target:
            yield attempt, target


def _round_status(data, record):
    actual, pending, directions, streaks = 0, [], set(), {}
    ended = record.get('end', {}).get('reason')
    for attempt, target in _attempts(data, record['id']):
        outcome = attempt.get('outcome')
        if not outcome:
            pending.append(attempt['id'])
            continue
        if outcome['kind'] == 'not-called':
            continue
        actual += 1
        if outcome['kind'] != 'generated':
            continue
        directions.add(target['directionId'])
        evaluation = next(e for e in outcome['evaluations'] if e['objectId'] == record['objectId'])
        if target['kind'] == 'correction':
            pid = target['problemId']
            streaks[pid] = 0 if evaluation['problemResolved'] else streaks.get(pid, 0) + 1
        if evaluation['disposition'] in {'satisfied', 'stop'}:
            ended = evaluation['disposition'] + ': ' + evaluation['note']
    reason = (ended or ('call-limit-9' if actual >= 9 else 'direction-limit-3' if len(directions) >= 3
                       else 'correction-limit-3' if any(n >= 3 for n in streaks.values()) else None))
    return {'id': record['id'], 'objectId': record['objectId'], 'planId': record['planId'],
            'actualCalls': actual, 'pendingCalls': len(pending), 'pendingAttemptIds': pending,
            'remainingCalls': max(0, 9 - actual - len(pending)), 'directionCount': len(directions),
            'problemStreaks': streaks, 'state': 'awaiting-result' if pending else 'stopped' if reason else 'active',
            'reason': reason}


def _new_round(data, oid, plan_id, source=None):
    record = {'id': identifier('image-round'), 'objectId': oid, 'planId': plan_id, 'createdAt': now()}
    previous = _round_for(data, oid)
    if previous:
        record['previousRoundId'] = previous['id']
    if source:
        record['source'] = source
    data['rounds'].append(record)
    return record


def _pending(data, oid):
    return any(not a.get('outcome') and any(t['objectId'] == oid for t in a['targets']) for a in data['attempts'])


def _concept_basis(manifest, object_id):
    state = next((o.get('concept', {}) for o in manifest.get('creativeObjects', []) if o['id'] == object_id), {})
    return digest({key: state.get(key) for key in ('round', 'confirmedId', 'selectionId')})


def candidate_current(manifest, attempt_id, object_id, *, registering=True):
    """Late results may be archived; they must not auto-replace a recommendation."""
    data = _data(manifest)
    attempt = next((a for a in data['attempts'] if a['id'] == attempt_id), None)
    target = next((t for t in attempt['targets'] if t['objectId'] == object_id), None) if attempt else None
    if not target:
        raise ValueError('planningAttemptId must cover the candidate creative object')
    basis = _basis(manifest, object_id)
    active = _round_for(data, object_id)
    outcome = attempt.get('outcome')
    usable = not outcome if registering else not outcome or outcome['kind'] == 'generated'
    return bool(usable and basis['state'] == 'ready'
                and basis.get('planId') == target['planId'] and active and active['id'] == target['roundId']
                and target.get('conceptBasis') == _concept_basis(manifest, object_id)
                and _snapshot(manifest, object_id)['contentKey'] == target['contentKey'])


def _begin(manifest, data, request):
    requested = request.get('targets')
    if not isinstance(requested, list) or not requested or not all(isinstance(t, dict) for t in requested):
        raise ValueError('begin-image requires nonempty targets')
    objects = _selected(manifest, [t.get('cueId') for t in requested])
    targets = []
    for oid, incoming in zip(objects, requested):
        if set(incoming) - {'cueId', 'directionId', 'direction', 'kind', 'problemId', 'problem'}:
            raise ValueError('unexpected image target fields')
        basis = _ready(manifest, oid)
        record = _round_for(data, oid) or _new_round(data, oid, basis['planId'])
        state = _round_status(data, record)
        if _pending(data, oid):
            raise ValueError('pending image call is unresolved; reconcile it before another call or round')
        if state['state'] == 'stopped':
            raise ValueError('autonomous exploration stopped: ' + state['reason'])
        direction = _text(incoming.get('directionId'), 'directionId')
        description = _text(incoming.get('direction'), 'direction')
        kind = incoming.get('kind')
        if kind not in {'direction', 'correction'}:
            raise ValueError('image target kind must be direction or correction')
        previous = [t for a, t in _attempts(data, record['id'])
                    if a.get('outcome', {}).get('kind') != 'not-called']
        if any(t['directionId'] == direction and t['direction'] != description for t in previous):
            raise ValueError('reuse the stable direction description; a new style needs a new directionId')
        if manifest.get('workModelVersion') == '2.2.0':
            # Freeze the same initial round that concept/register will use.
            # This creates neither a recommendation nor a user confirmation.
            obj = next(o for o in manifest['creativeObjects'] if o['id'] == oid)
            obj.setdefault('concept', {'round': 1})
        target = {'objectId': oid, 'roundId': record['id'], 'planId': basis['planId'],
                  'conceptBasis': _concept_basis(manifest, oid),
                  'contentKey': _snapshot(manifest, oid)['contentKey'], 'directionId': direction,
                  'direction': description, 'kind': kind}
        if kind == 'correction':
            if not any(t['directionId'] == direction and a.get('outcome', {}).get('kind') == 'generated'
                       for a, t in _attempts(data, record['id'])):
                raise ValueError('a correction requires an existing generated direction')
            pid, problem = _text(incoming.get('problemId'), 'problemId'), _text(incoming.get('problem'), 'problem')
            if any(t.get('problemId') == pid and t.get('problem') != problem for t in previous):
                raise ValueError('reuse the stable problem description')
            target.update(problemId=pid, problem=problem)
        elif 'problemId' in incoming or 'problem' in incoming:
            raise ValueError('problem fields belong to a correction')
        targets.append(target)
    attempt = {'id': identifier('image-call'), 'createdAt': now(), 'targets': targets}
    data['attempts'].append(attempt)
    return attempt


def _finish(manifest, data, request):
    attempt = next((a for a in data['attempts'] if a['id'] == request.get('attemptId')), None)
    if not attempt:
        raise ValueError('unknown image attemptId')
    if attempt.get('outcome'):
        raise ValueError('image attempt already resolved; retry the original request for its receipt')
    kind = request.get('outcome')
    if kind not in {'generated', 'failed', 'not-called'}:
        raise ValueError('image outcome must be generated, failed or not-called')
    if kind == 'not-called' and any(c.get('planningAttemptId') == attempt['id'] for c in manifest.get('concepts', [])):
        raise ValueError('registered generated output proves the image call was made; reconcile its actual result')
    outcome = {'kind': kind, 'note': _text(request.get('note'), 'outcome note'), 'createdAt': now()}
    if kind != 'not-called':
        outcome['toolReference'] = _text(request.get('toolReference'), 'actual toolReference')
        if any(a.get('outcome', {}).get('toolReference') == outcome['toolReference'] for a in data['attempts']):
            raise ValueError('toolReference already belongs to another call; resolve the original attempt')
    elif request.get('toolReference'):
        raise ValueError('not-called cannot claim an actual toolReference')
    if kind == 'generated':
        evaluations = request.get('evaluations')
        if (not isinstance(evaluations, list) or not all(isinstance(e, dict) for e in evaluations)
                or len(evaluations) != len(attempt['targets'])
                or {e.get('objectId') for e in evaluations} != {t['objectId'] for t in attempt['targets']}):
            raise ValueError('generated result needs one evaluation per targeted object')
        concepts = {c['id']: c for c in manifest.get('concepts', [])}
        checked = []
        for evaluation in evaluations:
            if set(evaluation) - {'objectId', 'conceptIds', 'disposition', 'problemResolved', 'note'}:
                raise ValueError('unexpected evaluation fields')
            oid = evaluation['objectId']
            ids = evaluation.get('conceptIds')
            if (not isinstance(ids, list) or not ids or not all(isinstance(cid, str) for cid in ids)
                    or len(set(ids)) != len(ids) or any(cid not in concepts or concepts[cid]['objectId'] != oid
                    or concepts[cid].get('planningAttemptId') != attempt['id'] for cid in ids)):
                raise ValueError('generated concepts must be registered against this attempt and object')
            disposition = evaluation.get('disposition')
            if disposition not in {'continue', 'satisfied', 'stop'}:
                raise ValueError('evaluation disposition must be continue, satisfied or stop')
            row = {'objectId': oid, 'conceptIds': ids, 'disposition': disposition,
                   'note': _text(evaluation.get('note'), 'evaluation note')}
            target = next(t for t in attempt['targets'] if t['objectId'] == oid)
            if target['kind'] == 'correction':
                if type(evaluation.get('problemResolved')) is not bool:
                    raise ValueError('correction evaluation requires problemResolved')
                row['problemResolved'] = evaluation['problemResolved']
            elif 'problemResolved' in evaluation:
                raise ValueError('problemResolved belongs to a correction')
            checked.append(row)
        outcome['evaluations'] = checked
    elif request.get('evaluations'):
        raise ValueError('only generated images have visual evaluations')
    attempt['outcome'] = outcome
    return attempt


def update_planning(manifest, request):
    action = request.get('action')
    allowed = {'present', 'close', 'begin-image', 'finish-image', 'continue', 'stop'}
    if action not in allowed:
        raise ValueError('unsupported creative-planning action')
    data = manifest.setdefault('creativePlanning', {'plans': [], 'rounds': [], 'attempts': []})
    if action == 'present':
        objects = _selected(manifest, request.get('cueIds'))
        if not objects:
            raise ValueError('present requires an animation plan in canonical cues')
        plan = {'id': identifier('creative-plan'), 'createdAt': now(),
                'summary': _text(request.get('summary'), 'plan summary'),
                'question': _text(request.get('question'), 'closing question'),
                'scope': 'all' if set(objects) == set(_cues(manifest)) else 'selected',
                'objects': [_snapshot(manifest, oid) for oid in objects]}
        data['plans'].append(plan)
        return copy.deepcopy(plan)
    if action == 'close':
        plan = next((p for p in data['plans'] if p['id'] == request.get('planId')), None)
        if not plan:
            raise ValueError('unknown creative planId')
        if any(_plan_for(data, item['objectId'])['id'] != plan['id']
               or not _plan_current(manifest, plan, item['objectId']) for item in plan['objects']):
            raise ValueError('plan or scope changed; present the current discussion before reusing a reply')
        source = user_source(request.get('source'))
        if plan.get('closure') and plan['closure']['source'] != source:
            raise ValueError('plan already closed; preserve its original reply and present revised content')
        plan.setdefault('closure', {'source': source, 'createdAt': now()})
        return copy.deepcopy(plan)
    if action == 'begin-image':
        return copy.deepcopy(_begin(manifest, data, request))
    if action == 'finish-image':
        return copy.deepcopy(_finish(manifest, data, request))
    objects = _selected(manifest, request.get('cueIds'))
    if not objects:
        raise ValueError('continue/stop requires animation objects')
    source = user_source(request.get('source')) if action == 'continue' else None
    records = []
    for oid in objects:
        if _pending(data, oid):
            raise ValueError('pending image call is unresolved; reconcile it before another round')
        if action == 'continue':
            records.append(_new_round(data, oid, _ready(manifest, oid)['planId'], source))
        else:
            record = _round_for(data, oid)
            if not record:
                raise ValueError('no autonomous image round to stop')
            record.setdefault('end', {'reason': _text(request.get('reason'), 'stop reason'), 'createdAt': now()})
            records.append(record)
    return copy.deepcopy(records)


def status(manifest, *, object_id=None):
    data = _data(manifest)
    cues = _cues(manifest)
    scope = {object_id} if object_id else set(cues)
    objects = [_basis(manifest, oid) for oid in cues if oid in scope]
    rounds = [_round_status(data, record) for oid in cues if oid in scope
              for record in [_round_for(data, oid)] if record]
    plans = []
    for plan in data['plans']:
        if object_id and not any(o['objectId'] == object_id for o in plan['objects']):
            continue
        snapshot = copy.deepcopy(plan)
        snapshot['supersededObjectIds'] = [o['objectId'] for o in plan['objects']
            if o['objectId'] not in cues or _plan_for(data, o['objectId'])['id'] != plan['id']]
        snapshot['currentObjectIds'] = [o['objectId'] for o in plan['objects']
            if o['objectId'] not in snapshot['supersededObjectIds'] and _plan_current(manifest, plan, o['objectId'])]
        if object_id:
            snapshot['objects'] = [o for o in snapshot['objects'] if o['objectId'] == object_id]
        plans.append(snapshot)
    return {'objects': objects, 'rounds': rounds, 'historyCount': len(plans),
            'history': {'plans': plans,
                'rounds': [copy.deepcopy(r) for r in data['rounds'] if not object_id or r['objectId'] == object_id],
                'attempts': [copy.deepcopy(a) for a in data['attempts']
                             if not object_id or any(t['objectId'] == object_id for t in a['targets'])]}}
