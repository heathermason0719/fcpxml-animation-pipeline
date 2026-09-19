"""Public-API setup for active-loop fixtures; only the raster renderer is fake."""
from pathlib import Path
from unittest.mock import patch
from scripts import work_model as model
from scripts.work_model_store import load, sha


def user(text='测试用户明确委托', reference='fixture:user-turn'):
    return {'channel': 'chat', 'text': text, 'reference': reference}


def request(root, name, **kwargs):
    return {'requestId': name, 'expectedRevision': load(root)['editRevision'], **kwargs}


def raster(root, manifest, spec, output_dir, log_path):
    records = []
    for index, frame in enumerate(spec['frames']):
        path = Path(output_dir) / (str(index) + '.png')
        path.parent.mkdir(parents=True, exist_ok=True)
        # Real input identity and registered output bytes still flow through
        # snapshotting, publication and first-confirmation verification.
        path.write_bytes(b'fixture PNG ' + frame['inputKey'].encode())
        records.append({**frame, 'path': path.relative_to(root).as_posix(), 'sha256': sha(path)})
    return records


def activate(root, name='initial'):
    model.update(root, request(root, name+'-objects', operation='edit', patch={}))
    # This copied single-source fixture intentionally holds on the original
    # image without adding visible copy.  Make that known absence explicit for
    # tests that need a confirmable synthetic Cue; never derive it from a real
    # project or apply it to other fixture Cues.
    manifest = load(root)
    for cue in manifest['cues']:
        if cue.get('id') == 'p1s01_c02_hold':
            cue['contentContext'] = {
                'narration': {'state': 'present'},
                'screenText': {'state': 'none', 'basis': {
                    'text': '合成 fixture 明确保留原画，不添加屏幕文字。',
                    'reference': 'fixture:single-source-hold',
                }},
            }
    model.update(root, request(root, name+'-content-context', operation='edit',
                               patch={'cues': manifest['cues']}))
    with patch('scripts.work_model_jobs.render_storyboard', side_effect=raster):
        result = model.preview(root, request(root, name+'-storyboard', scope='storyboard'))
    model.update(root, request(root, name+'-confirm', operation='decision', kind='confirm-design',
                 storyboardIds=result['storyboardIds'], source=user('确认这些静帧')))
    return result


def demo_request(root, name, **kwargs):
    task_id = 'task-' + name
    all_ids = [c['id'] for c in load(root)['cues'] if c['productionMode'] == 'animation']
    excluded = kwargs.get('excludedCueIds', [])
    return request(root, name, **{'scope': 'full', **kwargs, 'taskId': task_id,
        'decision': {'kind': 'authorize-demo', 'taskId': task_id,
            'cueIds': kwargs.get('workCueIds', kwargs.get('cueIds', [])),
            'presentationCueIds': [i for i in all_ids if i not in excluded], 'excludedCueIds': excluded,
            'source': user('按明确范围制作本轮整版 Demo', 'fixture:'+name)}})
