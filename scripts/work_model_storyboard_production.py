"""Optional Storyboard-to-production handoff, within the existing decision writer."""
from scripts.work_model_confirmation import confirmation_problems
from scripts.work_model_concepts import require_concepts
from scripts.work_model_feedback_targets import design_target, feedback_applies
from scripts.work_model_policy import completed_runs


def validate(root, manifest, request):
    ids = request['storyboardIds']
    known = {s['id']: s for s in manifest.get('storyboards', [])}
    if not isinstance(ids, list) or not ids or any(not isinstance(i, str) for i in ids) or len(ids) != len(set(ids)) or any(i not in known for i in ids):
        raise ValueError('Storyboard production requires unique known storyboardIds')
    boards = [known[i] for i in ids]
    selected = [s['cueId'] for s in boards]
    all_ids = {c['id'] for c in manifest['cues'] if c['productionMode'] == 'animation'}
    if (len(set(selected)) != len(selected) or set(selected) != set(request['cueIds']) or
            set(selected) != set(request['presentationCueIds']) or
            set(selected) | set(request.get('excludedCueIds', [])) != all_ids):
        raise ValueError('Storyboard production must explicitly partition selected and excluded cues')
    problems = confirmation_problems(root, manifest, boards)
    if problems:
        raise ValueError('Storyboard production requires current reviewed frames: ' + str(problems))
    require_concepts(root, manifest, selected)
    return ids


def cue_status(root, manifest, cue, board, problems):
    problems = list(problems)
    try:
        require_concepts(root, manifest, [cue['id']])
    except ValueError as error:
        problems.append({'code': 'concept-unavailable', 'message': str(error)})
    target = design_target(manifest, [board]) if board else {'cueIds':[cue['id']], 'objectIds':[cue.get('objectId')]}
    deferred = any(f.get('status') in {'pending', 'needs-clarification'} and
        f.get('applicability', {}).get('kind') == 'deferred' and
        feedback_applies(manifest, {**f, 'applicability':{'kind':'current'}}, target)
        for f in manifest.get('feedback', []))
    return {'productionProblems':problems, 'productionDeferred':deferred}


def latest_request(manifest):
    record = next((d for d in reversed(manifest['decisions']) if d['kind'] == 'authorize-demo'), None)
    if not record:
        return None
    return {**record, 'status':'completed' if completed_runs(manifest, record['taskId']) else 'pending'}
