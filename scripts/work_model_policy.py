"""Creative-object and production authority, independent of media identity.

These checks execute a stated commission. They never interpret chat text,
infer object continuity from filenames, or roll active work back to a stage.
"""
from __future__ import annotations

import copy
import uuid

from scripts.work_model_store import digest, now, user_source
from scripts.hyperframes_adapter import parse_time
from scripts.fcpxml_timing import format_time


def identifier(prefix):
    return prefix + '-' + uuid.uuid4().hex[:16]


def upgrade(manifest):
    """Prepare a complete, unqualified object model inside a writer transaction.

    Enrollment assigns identity, never approval or an inferred relationship to
    another object. Readers deliberately leave old/partially enrolled data alone.
    """
    before = copy.deepcopy(manifest)
    manifest['workModelVersion'] = '2.1.0'
    for field in ('creativeObjects', 'storyboards', 'reviewRounds', 'explorations', 'productionRuns'):
        manifest.setdefault(field, [])
    objects = {o['id']: o for o in manifest['creativeObjects']}
    if len(objects) != len(manifest['creativeObjects']):
        raise ValueError('duplicate creative object identity')
    assigned = set()
    for cue in manifest['cues']:
        if cue['productionMode'] != 'animation':
            continue
        oid = cue.get('objectId')
        if not oid:
            oid = identifier('object')
            manifest['creativeObjects'].append({'id': oid, 'createdAt': now()})
            objects[oid] = manifest['creativeObjects'][-1]
            cue['objectId'] = oid
        if oid not in objects or oid in assigned:
            raise ValueError('creative object identity is missing or assigned twice; clarify the relationship')
        assigned.add(oid)
    return manifest != before


def bind_objects(before, manifest, relations=None):
    relations = relations or {}
    old = {c['id']: c for c in before['cues']}
    objects = {o['id']: o for o in manifest['creativeObjects']}
    seen = set()
    for cue in manifest['cues']:
        if cue['productionMode'] != 'animation':
            cue.pop('objectId', None)
            continue
        previous = old.get(cue['id'], {})
        relation = relations.get(cue['id'])
        supplied = cue.get('objectId')
        if relation:
            basis = relation.get('basis', {})
            if not basis.get('text') or not basis.get('reference'):
                raise ValueError('object relationship requires a stated basis; ask only about material ambiguity')
            kind = relation.get('kind')
            if kind == 'continue':
                oid = relation.get('objectId')
                if oid not in objects:
                    raise ValueError('unknown continuing creative object')
            elif kind == 'new':
                oid = identifier('object')
                objects[oid] = {'id': oid, 'createdAt': now(), 'basis': copy.deepcopy(basis)}
                manifest['creativeObjects'].append(objects[oid])
            else:
                raise ValueError('object relationship must explicitly be new or continue')
        elif previous.get('objectId'):
            oid = previous['objectId']
            if supplied not in (None, oid):
                raise ValueError('creative object replacement requires an explicit object relationship')
        elif supplied:
            raise ValueError('a new technical cue cannot claim an object without its relationship basis')
        elif not before.get('creativeObjects') or cue['id'] in old:
            # Enrol unqualified old data or the initial set. No prior eligibility
            # exists to inherit; a controlled relationship is needed thereafter.
            oid = identifier('object')
            objects[oid] = {'id': oid, 'createdAt': now()}
            manifest['creativeObjects'].append(objects[oid])
        else:
            raise ValueError('new technical cue requires objectRelations: declare new or continuing object')
        if oid in seen:
            raise ValueError('one creative object cannot be assigned to multiple independent cues')
        seen.add(oid)
        cue['objectId'] = oid


def object_ids(manifest, cue_ids):
    cues = {c['id']: c for c in manifest['cues'] if c['productionMode'] == 'animation'}
    if not isinstance(cue_ids, list) or len(set(cue_ids)) != len(cue_ids):
        raise ValueError('cueIds must be an explicit unique list')
    if not set(cue_ids).issubset(cues):
        raise ValueError('unknown animation cue in production scope')
    result = []
    for cid in cue_ids:
        if not cues[cid].get('objectId'):
            raise ValueError('creative object not registered; use controlled edit before first design')
        result.append(cues[cid]['objectId'])
    return result


def first_confirmed(manifest, object_id):
    return bool(qualification_evidence(manifest, object_id))


def qualification_evidence(manifest, object_id):
    if not object_id:
        return []
    explicit = [d['id'] for d in manifest['decisions']
                if d['kind'] == 'confirm-design' and object_id in d.get('objectIds', [])]
    obj = next((o for o in manifest.get('creativeObjects', []) if o['id'] == object_id), {})
    continuity = obj.get('continuity', {})
    if continuity.get('qualificationEvidenceIds'):
        explicit.append(continuity['id'])
    return explicit


def copy_object_relations(manifest, origin, request, source_hash):
    """Apply a structured commission; prose, paths and same IDs decide nothing."""
    source = user_source(request.get('commission'))
    cues = [c for c in manifest['cues'] if c['productionMode'] == 'animation']
    mode, relations = request.get('copyMode'), request.get('objectContinuity')
    if mode == 'restart' and relations is None:
        relations = {c['id']: {'kind': 'new'} for c in cues}
    elif mode is not None:
        raise ValueError('copyMode must be restart alone; use objectContinuity for explicit object relationships')
    if not isinstance(relations, dict) or set(relations) != {c['id'] for c in cues}:
        raise ValueError('copyFrom requires explicit objectContinuity or copyMode=restart; clarify cross-version relationships')
    known = {o['id'] for o in origin.get('creativeObjects', [])}
    used = set()
    for cue in cues:
        relation = relations[cue['id']]
        if not isinstance(relation, dict) or relation.get('kind') not in {'new', 'continue'}:
            raise ValueError('objectContinuity must state new or continue for each copied cue')
        expected = {'kind'} if relation['kind'] == 'new' else {'kind', 'sourceObjectId'}
        if set(relation) != expected:
            raise ValueError('objectContinuity contains unsupported or missing relationship fields')
        obj = {'id': identifier('object'), 'createdAt': now(), 'basis': copy.deepcopy(source)}
        if relation['kind'] == 'continue':
            oid = relation['sourceObjectId']
            if oid not in known or oid in used:
                raise ValueError('unknown or duplicate continuing source object')
            used.add(oid)
            obj['continuity'] = {'id': identifier('continuity'), 'sourceVersionId': origin['identity']['versionId'],
                'sourceObjectId': oid, 'sourceManifestSha256': source_hash,
                'qualificationEvidenceIds': qualification_evidence(origin, oid), 'source': copy.deepcopy(source),
                'createdAt': now()}
        manifest['creativeObjects'].append(obj)
        cue['objectId'] = obj['id']


def storyboard_current(root, manifest, record):
    from scripts.work_model_storyboard import frame_current, storyboard_spec
    cue = next((c for c in manifest['cues'] if c['id'] == record['cueId']), None)
    if not cue or cue.get('objectId') != record.get('objectId'):
        return False
    artifacts = {a['id']: a for a in manifest['artifacts']}
    frames = [artifacts.get(key) for key in record['artifactIds']]
    if not frames or any(not f or f.get('purpose') != 'storyboard' for f in frames):
        return False
    if sum(f.get('role') == 'hero' for f in frames) != 1:
        return False
    try:
        required = storyboard_spec(root, manifest, {'cueIds': [cue['id']]})['frames']
        if {(f['frameId'], f['inputKey']) for f in required} != {(f['frameId'], f['inputKey']) for f in frames}:
            return False
    except (ValueError, KeyError, OSError):
        return False
    return all(frame_current(root, manifest, f) for f in frames)


def normalized_range(value):
    if not isinstance(value, dict) or set(value) != {'start', 'duration'}:
        raise ValueError('production range requires start and duration')
    start, duration = parse_time(value['start']), parse_time(value['duration'])
    if start < 0 or duration <= 0:
        raise ValueError('production range must be positive')
    return {'start': format_time(start), 'duration': format_time(duration)}


def creative_decision(root, manifest, request):
    kind = request['kind']
    record = {'id': identifier('decision'), 'kind': kind, 'source': user_source(request.get('source')),
              'createdAt': now()}
    if kind == 'confirm-design':
        ids = request.get('storyboardIds')
        if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)):
            raise ValueError('first design confirmation requires explicit storyboardIds')
        records = {s['id']: s for s in manifest.get('storyboards', [])}
        selected = [records.get(key) for key in ids]
        if any(not s for s in selected):
            raise ValueError('first design confirmation requires current verified Storyboard frames')
        from scripts.work_model_confirmation import apply_feedback_resolutions, confirmation_problems
        resolutions = apply_feedback_resolutions(manifest, request, selected)
        problems = confirmation_problems(root, manifest, selected)
        if problems:
            raise ValueError('first design confirmation requires current verified Storyboard: ' + str(problems))
        record.update(storyboardIds=ids, objectIds=[s['objectId'] for s in selected])
        if resolutions:
            record['feedbackResolutions'] = resolutions
    elif kind in {'explore-motion', 'authorize-demo'}:
        task = request.get('taskId')
        if not isinstance(task, str) or not task.strip():
            raise ValueError('production authorization requires a taskId')
        if completed_runs(manifest, task):
            raise ValueError('completed production task requires a new explicit commission')
        if any(d.get('taskId') == task for d in manifest['decisions']):
            raise ValueError('taskId already has a production authorization')
        ids = request.get('cueIds')
        if ids is None or (kind == 'explore-motion' and not ids):
            raise ValueError('explicit bounded cueIds are required')
        record.update(taskId=task, cueIds=ids, objectIds=object_ids(manifest, ids))
        if kind == 'authorize-demo':
            presentation = request.get('presentationCueIds')
            excluded = request.get('excludedCueIds', [])
            if presentation is None:
                raise ValueError('Demo authorization requires explicit presentationCueIds')
            record.update(presentationCueIds=presentation, presentationObjectIds=object_ids(manifest, presentation),
                          excludedCueIds=excluded, excludedObjectIds=object_ids(manifest, excluded))
            if set(presentation) & set(excluded):
                raise ValueError('presented and excluded cues must be disjoint')
        if 'range' in request:
            record['range'] = normalized_range(request['range'])
        if kind == 'explore-motion':
            all_ids = {c['id'] for c in manifest['cues'] if c['productionMode'] == 'animation'}
            if len(all_ids) > 1 and set(ids) == all_ids:
                bounded = record.get('range')
                source = manifest['project'].get('source')
                if not bounded or not source or (parse_time(bounded['start']) == 0 and
                        parse_time(bounded['duration']) >= parse_time(source['duration'])):
                    raise ValueError('bounded exploration cannot authorize whole-version Motion production')
    else:
        raise ValueError('unsupported creative decision')
    manifest['decisions'].append(record)
    return record


def production_basis(manifest, request, rendered_ids, *, full=False, job_id=None, time_range=None):
    """Validate before execution AND before any completed/cache result return."""
    work = request.get('workCueIds', request.get('cueIds', []))
    work_objects = object_ids(manifest, work)
    rendered_objects = object_ids(manifest, rendered_ids)
    task = request.get('taskId')
    basis = next((d for d in reversed(manifest['decisions'])
                  if task and d.get('taskId') == task and d['kind'] in {'explore-motion', 'authorize-demo'}), None)
    if full and (not basis or basis['kind'] != 'authorize-demo'):
        raise ValueError('整版 Demo requires explicit production authorization / 制作依据')
    if basis:
        if not set(work_objects).issubset(basis['objectIds']):
            raise ValueError('work exceeds the explicitly authorized creative objects')
        completed = completed_runs(manifest, task)
        if any(r['jobId'] != job_id for r in completed):
            raise ValueError('completed production authorization cannot start another task')
        if basis.get('range'):
            actual = normalized_range(time_range if time_range is not None else request.get('range'))
            allowed_start = parse_time(basis['range']['start'])
            allowed_end = allowed_start + parse_time(basis['range']['duration'])
            actual_start = parse_time(actual['start'])
            if actual_start < allowed_start or actual_start + parse_time(actual['duration']) > allowed_end:
                raise ValueError('preview/work range exceeds the explicitly authorized range')
    if full:
        excluded = object_ids(manifest, request.get('excludedCueIds', []))
        if set(excluded) != set(basis.get('excludedObjectIds', [])):
            raise ValueError('Demo exclusions differ from user authorization')
        all_objects = set(object_ids(manifest, [c['id'] for c in manifest['cues'] if c['productionMode'] == 'animation']))
        if all_objects != set(basis['presentationObjectIds']) | set(excluded):
            raise ValueError('Demo scope changed; new objects need an explicit user commission')
        if not set(rendered_objects).issubset(basis['presentationObjectIds']):
            raise ValueError('presented objects exceed Demo authorization')
        missing = set(basis['presentationObjectIds']) - set(rendered_objects)
        if missing and not request.get('allowDraft', False):
            raise ValueError('full Demo target incomplete / 首次资格或实现缺失: ' + ', '.join(sorted(missing)))
    for oid in set(work_objects + rendered_objects):
        if first_confirmed(manifest, oid):
            continue
        if not full and basis and basis['kind'] == 'explore-motion' and oid in basis['objectIds']:
            continue
        raise ValueError('首次设计 / first design confirmation or explicit bounded Motion exploration required')
    return {'policyVersion': '2.1.0', 'taskId': task, 'scope': 'full' if full else 'local',
            'decisionIds': [basis['id']] if basis else [], 'objectIds': rendered_objects,
            'workObjectIds': work_objects}


def completed_runs(manifest, task):
    corrected = {r['jobId'] for r in manifest.get('productionCorrections', []) if r['taskId'] == task}
    return [r for r in manifest.get('productionRuns', []) if r['taskId'] == task and r['jobId'] not in corrected]


def commission_fulfilled(manifest, spec):
    """A finished render, a finished commission and a formal review differ."""
    basis = spec.get('productionBasis', {})
    decision = next((d for d in manifest['decisions'] if d.get('taskId') == basis.get('taskId')), None)
    if not decision:
        return False
    actual = set(basis.get('objectIds', []))
    if decision['kind'] == 'authorize-demo':
        return (spec['scope'] == 'full' and not spec['timeline']['missingCueIds']
                and actual == set(decision['presentationObjectIds'])
                and set(object_ids(manifest, spec['timeline'].get('excludedCueIds', []))) == set(decision['excludedObjectIds']))
    if decision['kind'] == 'explore-motion':
        # Context can include active objects, but all commissioned exploratory
        # objects must have been presented before this finite task is complete.
        return (set(decision['objectIds']).issubset(actual)
                and not set(decision['cueIds']).intersection(spec['timeline']['missingCueIds'])
                and (not decision.get('range') or normalized_range(spec['timeline']['range']) == decision['range']))
    return False


def correct_incomplete_runs(root, manifest):
    """Append a narrowly evidenced correction; never rewrite old runs/artifacts."""
    import json
    from scripts.work_model_store import safe
    corrected = {r['jobId'] for r in manifest.get('productionCorrections', [])}
    for run in manifest.get('productionRuns', []):
        if run['jobId'] in corrected:
            continue
        decision = next((d for d in manifest['decisions'] if d.get('taskId') == run['taskId'] and d['kind'] == 'authorize-demo'), None)
        if not decision:
            continue
        path = safe(root, 'jobs/' + run['jobId'] + '.json', exists=False)
        if not path.is_file():
            continue
        job = json.loads(path.read_text())
        if job.get('request', {}).get('taskId') != run['taskId']:
            continue
        outputs = [a for a in manifest['artifacts'] if a.get('eventId') == run['jobId'] and a.get('kind') == 'full-preview'
                   and a['id'] in job.get('result', {}).get('artifactIds', [])]
        if len(outputs) != 1:
            continue
        artifact = outputs[0]
        # Explicitly excluded layers are a fulfilled restricted request. Only
        # the old writer's recorded missing *requested* layers prove the defect.
        absent = set(artifact.get('missingCueIds', [])) & set(decision.get('presentationCueIds', []))
        if absent and not artifact.get('complete'):
            manifest.setdefault('productionCorrections', []).append({'taskId': run['taskId'], 'jobId': run['jobId'],
                'artifactId': artifact['id'], 'reason': 'requested-presentation-missing', 'missingCueIds': sorted(absent), 'createdAt': now()})


def artifact_eligible(manifest, artifact):
    basis = artifact.get('productionBasis')
    if not basis or basis.get('policyVersion') != '2.1.0':
        return False
    try:
        if not set(object_ids(manifest, artifact.get('cueIds', []))).issubset(basis.get('objectIds', [])):
            return False
    except ValueError:
        return False
    decisions = {d['id']: d for d in manifest['decisions']}
    selected = [decisions.get(i) for i in basis.get('decisionIds', [])]
    if any(d is None for d in selected):
        return False
    if basis['scope'] == 'full' and not any(d['kind'] == 'authorize-demo' for d in selected):
        return False
    for oid in basis.get('objectIds', []):
        if first_confirmed(manifest, oid):
            continue
        if basis['scope'] == 'local' and any(d['kind'] == 'explore-motion' and oid in d['objectIds'] for d in selected):
            continue
        return False
    return True


def blocking_feedback(manifest, target):
    from scripts.work_model_feedback_targets import blocking_feedback as applicable_blockers
    return applicable_blockers(manifest, target)


def check_motion_edit(root, before, manifest, request, files, *, runtime_transition=None):
    """Gate executable/time-driven publication across the canonical closure.

    Static markup is a restricted declarative language. We do not attempt to
    decide whether arbitrary JavaScript is a harmless layout script.
    """
    changed = {name for name, data, old in files if data != old}
    proposed = {name: data for name, data, old in files}
    infrastructure_only = runtime_transition is not None and not runtime_transition['motionAffecting']
    if infrastructure_only:
        from scripts.work_model_runtime import RUNTIME_FILES
        changed.difference_update(RUNTIME_FILES)
    from scripts.work_model_sources import inspect_sources, _content
    from scripts.work_model_inputs import dependencies
    from pathlib import Path
    old_objects = {c.get('objectId'): c for c in before['cues'] if c.get('objectId')}
    old_ids = {c['id']: c for c in before['cues']}
    affected, owned = [], set()
    for cue in manifest['cues']:
        if cue['productionMode'] != 'animation':
            continue
        adapter = cue.get('renderAdapters', {}).get('hyperframes', {})
        # Reassigning identity does not itself publish different source bytes.
        # It still loses qualification, and preview applies that separate fact.
        old_cue = old_objects.get(cue.get('objectId'), old_ids.get(cue['id'], {}))
        old = old_cue.get('renderAdapters', {}).get('hyperframes', {})
        if not adapter.get('compositionSrc'):
            continue
        current = inspect_sources(root, cue, proposed, allow_missing=True)
        previous = inspect_sources(root, old_cue, allow_missing=True) if old.get('compositionSrc') else {'files': [], 'motionFiles': [], 'motionBindings': []}
        owned.update(current['files'])
        motion = set(current['motionFiles']) | set(previous['motionFiles'])
        attached = set(current['motionFiles']) - set(previous['motionFiles'])
        attached = {p for p in attached if p in proposed or (Path(root) / p).is_file()}
        if infrastructure_only:
            attached.discard('assets/vendor/gsap.min.js')
        bindings_changed = current['motionBindings'] != previous['motionBindings']
        # The runtime vendor is an implicit input of every Motion render host.
        vendor_changed = ('assets/vendor/gsap.min.js' in changed or
                          (runtime_transition is not None and runtime_transition['motionAffecting']))
        if motion.intersection(changed) or attached or bindings_changed or vendor_changed:
            affected.append(cue['id'])
    # Executable files must belong to a Cue so that scope/authority can be
    # checked. Inert assets can be prepared before they are associated.
    for path in changed - owned:
        if request.get('operation') == 'runtime' and path == 'assets/vendor/gsap.min.js':
            continue  # bootstrap has no creative objects; later changes gate all
        if Path(path).suffix.lower() in {'.js', '.mjs', '.html', '.htm', '.svg', '.css'}:
            dynamic, refs = _content(path, proposed[path].decode('utf-8'))
            if dynamic or any(executes is True for _, executes in refs):
                raise ValueError('Motion source publication requires a canonical Cue owner')
    work = request.get('work', {})
    declared = work.get('cueIds', request.get('cueIds'))
    if declared is not None:
        allowed = set(declared)
        old_by_id = {c['id']: c for c in before['cues']}
        new_by_id = {c['id']: c for c in manifest['cues']}
        altered = {cid for cid in old_by_id.keys() | new_by_id.keys() if old_by_id.get(cid) != new_by_id.get(cid)}
        if not altered.issubset(allowed) or not set(affected).issubset(allowed):
            raise ValueError('edit exceeds the explicitly declared creative cue scope')
        for cue in before['cues']:
            if cue['id'] in allowed or cue['productionMode'] != 'animation':
                continue
            if changed.intersection({'frame.md', 'package.json', 'hyperframes.json', 'assets/vendor/gsap.min.js'}):
                raise ValueError('shared dependency would change an unselected creative cue')
            try:
                inputs = dependencies(root, cue, require_motion=False)
            except (OSError, ValueError):
                adapter = cue.get('renderAdapters', {}).get('hyperframes', {})
                inputs = [adapter.get('compositionSrc'), *adapter.get('layoutDependencies', [])]
            if changed.intersection(inputs):
                raise ValueError('shared dependency would change an unselected creative cue')
    if work.get('mode') == 'motion':
        affected = list(dict.fromkeys(affected + work.get('cueIds', [])))
    if affected:
        supplied = {**work, 'cueIds': affected, 'taskId': work.get('taskId', request.get('taskId'))}
        presented = affected
        if work.get('scope') == 'full':
            basis = next((d for d in manifest['decisions'] if d.get('taskId') == supplied.get('taskId') and d['kind'] == 'authorize-demo'), {})
            presented = [c['id'] for c in manifest['cues'] if c.get('objectId') in basis.get('presentationObjectIds', [])]
            supplied.setdefault('excludedCueIds', [c['id'] for c in manifest['cues'] if c.get('objectId') in basis.get('excludedObjectIds', [])])
        production_basis(manifest, supplied, presented, full=work.get('scope') == 'full')
