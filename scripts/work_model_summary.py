"""Small read-only views of the existing status; no new execution authority."""
import copy

from scripts.work_model_feedback_targets import OPEN_FEEDBACK, feedback_applies


def _fields(value, names):
    return {key:copy.deepcopy(value[key]) for key in names if key in value}


def project_view(manifest, state, *, view='full', cue_id=None, feedback_id=None):
    if view == 'full' and cue_id is None and feedback_id is None:
        return state
    if view not in {'summary','cue','feedback'}:
        raise ValueError('status view must be full, summary, cue or feedback')
    if (view == 'cue') != (cue_id is not None) or (view == 'feedback') != (feedback_id is not None):
        raise ValueError('detail view requires exactly its cue_id or feedback_id')
    cues = state['cues']
    def applies(feedback, cue):
        return feedback_applies(manifest, feedback, {'kind':'review', 'cueIds':[cue['id']],
            'objectIds':[cue['objectId']] if cue.get('objectId') else []})
    opened = [f for f in state['feedback'] if f.get('status') in OPEN_FEEDBACK]
    index = []
    for item in opened:
        row = _fields(item, ('id','status','target','applicability'))
        row['body'] = item['body'][:240]
        if len(item['body']) > 240:
            row['bodyTruncated'] = True
        row['appliesToCueIds'] = [c['id'] for c in cues if applies(item,c)]
        index.append(row)
    base = {'view':view, **_fields(state, ('identity','editRevision','legacy')), 'feedbackIndex':index,
        'details':{'full':'status <version-root>', 'cue':'status <version-root> --cue-id <id>',
                   'feedback':'status <version-root> --feedback-id <id>'}}
    if view == 'feedback':
        item = next((f for f in state['feedback'] if f['id'] == feedback_id), None)
        if item is None:
            raise ValueError('unknown feedback_id')
        return {**base, 'feedback':copy.deepcopy(item)}
    if view == 'cue':
        cue = next((c for c in cues if c['id'] == cue_id), None)
        if cue is None:
            raise ValueError('unknown cue_id')
        return {**base, 'cue':copy.deepcopy(cue),
            'feedback':[copy.deepcopy(f) for f in opened if applies(f,cue)],
            'conceptDesign':next((copy.deepcopy(c) for c in state.get('conceptDesign', {}).get('cues', []) if c['cueId'] == cue_id), None),
            'storyboard':next((copy.deepcopy(c) for c in state.get('storyboard', {}).get('cues', []) if c['id'] == cue_id), None)}
    production = {c['cueId']:c for c in state.get('production', [])}
    cue_index = []
    for cue in cues:
        cue_index.append({**_fields(cue, ('id','objectId','title','productionMode','resolvedTimeline','status')),
            **_fields(production.get(cue['id'], {}), ('firstConfirmed','implementationAvailable','problem'))})
    movies = [a for a in state['artifacts'] if a['kind'] in {'full-preview','local-preview','cue-preview'}]
    latest = max(movies, key=lambda a:a.get('createdAt',''), default=None)
    tasks = sorted(state.get('tasks', []), key=lambda t:t.get('createdAt',''))
    return {**base, 'currentGoal':_fields(state.get('brief', {}), ('summary','changeSummary')),
        'workingIntent':copy.deepcopy(state.get('workingIntent', {'items':[]})), 'cues':cue_index,
        'productionRequest':copy.deepcopy(state.get('storyboard', {}).get('productionRequest')),
        'conceptHandoff':copy.deepcopy(state.get('conceptDesign', {}).get('storyboardHandoff')),
        'latestPreview':_fields(latest, ('id','kind','path','sha256','range','complete','current','coverage')) if latest else None,
        'reviewSet':_fields(state['reviewSet'], ('id','artifactIds')) if state.get('reviewSet') else None,
        'activeTasks':[copy.deepcopy(t) for t in tasks if t.get('status') not in {'complete','completed','failed'}],
        'latestTask':copy.deepcopy(tasks[-1]) if tasks else None,
        'counts':{'cues':len(cues),'openFeedback':len(opened),'feedback':len(state['feedback']),
                  'artifacts':len(state['artifacts']),'tasks':len(tasks),'concepts':len(state.get('concepts', []))}}
