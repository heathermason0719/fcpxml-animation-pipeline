"""Opt-in fixtures and append-only traces for an actual Agent scenario run.

The actor chooses requests after observe; this module never maps utterances to
operations. Rendering is stubbed for these semantic scenarios. Real PNG/MOV
rendering is covered by the separate opt-in production harnesses.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import sys
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import work_model as model
from scripts.work_model_inputs import cue_key, dependencies
from scripts.work_model_store import load, sha, digest
from tests import test_work_model_jobs as jobs
from tests.work_model_fixtures import raster, user

CASES = Path(__file__).with_name('fixtures') / 'work_model_agent_scenarios.json'


def cases():
    return json.loads(CASES.read_text(encoding='utf-8'))


def version(project):
    return project / model.project_status(project)['episodes'][0]['versions'][0]['root']


def request(root, name, **values):
    return {'requestId': name, 'expectedRevision': load(root)['editRevision'], **values}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


@contextmanager
def render_stubs(calls):
    def render(root, manifest, cue, *, quality, target, log_path):
        calls.append({'rendererStub': 'cue', 'cueId': cue['id'], 'quality': quality})
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(cue_key(root, manifest, cue, quality).encode())
    def composite(root, manifest, overlays, *, start, duration, target, log_path):
        calls.append({'rendererStub': 'composite', 'cueIds': [o['cueId'] for o in overlays]})
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(digest([overlays, str(start), str(duration)]).encode())
    def static(*args):
        calls.append({'rendererStub': 'static'})
        return raster(*args)
    with ExitStack() as stack:
        for name, implementation in [('render_storyboard', static), ('render_cue', render), ('composite_preview', composite)]:
            stack.enter_context(patch('scripts.work_model_jobs.' + name, side_effect=implementation))
        stack.enter_context(patch('scripts.work_model_jobs._validate_media', return_value={'probe': {}, 'alpha': {'status': 'valid'}}))
        yield


def staged(root, relative, contents):
    path = root / '.staging' / relative.replace('/', '_')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contents)
    return {'path': relative, 'source': str(path)}


def source_hashes(root):
    return {p.relative_to(root).as_posix(): sha(p) for folder in ('compositions', 'assets')
            for p in (root / folder).rglob('*') if p.is_file()}


def prepare(root):
    if root.exists():
        raise ValueError('--root must not exist')
    root.mkdir(parents=True)
    locations = {}
    for case in cases():
        seed = jobs.JobTests(methodName='runTest')
        seed.cold_start = True
        seed.setUp()
        project = root / 'cases' / case['id'] / 'AfterForge'
        try:
            shutil.copytree(seed.root.parents[3], project)
        finally:
            seed.doCleanups()
        v = version(project)
        original = load(v)
        cues, files = [], []
        for i, name in enumerate(('A', 'B', 'C')):
            cue = copy.deepcopy(original['cues'][0])
            cue.update(id=name, resolvedTimeline={'start': f'{i * 2}s', 'duration': '2s'},
                       narrationAnchor=f'场景旁白 {name}', screenText=[{'text': f'场景标题 {name}'}])
            cue.pop('objectId', None)
            adapter = cue['renderAdapters']['hyperframes']
            original_composition = adapter['compositionSrc']
            source = (v / original_composition).read_text()
            source = re.sub(r'<script\b[^>]*src=["\'][^"\']+["\'][^>]*>\s*</script>', '', source)
            adapter.pop('motionSrc', None)
            adapter['compositionSrc'] = f'compositions/cues/{name}.html'
            adapter['layoutDependencies'] = [adapter['compositionSrc'] if item == original_composition else item
                                              for item in adapter.get('layoutDependencies', [])
                                              if item != 'assets/vendor/gsap.min.js']
            files.append(staged(v, adapter['compositionSrc'], source.encode()))
            cues.append(cue)
        model.update(v, request(v, 'fixture-layout', operation='edit', patch={'cues': cues}, files=files,
            objectRelations={c['id']: {'kind': 'new', 'basis': {'text': '独立测试对象', 'reference': 'simulated:fixture'}} for c in cues}))
        calls = []
        if case['id'] not in {'cold-continue', 'pure-visual-content'}:
            with render_stubs(calls):
                model.preview(v, request(v, 'fixture-static', scope='storyboard'))
            m = load(v)
            active = ['C'] if case['id'] in {'round-handoff', 'confirm-selected'} else ['A', 'B', 'C']
            model.update(v, request(v, 'fixture-confirm', operation='decision', kind='confirm-design',
                storyboardIds=[s['id'] for s in m['storyboards'] if s['cueId'] in active], source=user('模拟前序用户明确确认', 'simulated:fixture')))
            if case['id'] not in {'round-handoff', 'confirm-selected'}:
                m = load(v)
                motion_files = []
                for cue in m['cues']:
                    name = cue['id']
                    path = f'compositions/motion/{name}.js'
                    cue['renderAdapters']['hyperframes']['motionSrc'] = path
                    motion_files.append(staged(v, path, f'// existing motion for {name}\n'.encode()))
                model.update(v, request(v, 'fixture-active', operation='edit', patch={'cues': m['cues']}, files=motion_files,
                    work={'mode': 'motion', 'cueIds': active}))
        if case['id'] == 'round-handoff':
            m = load(v)
            board = next(b for b in m['storyboards'] if b['cueId'] == 'A')
            frame = next(a for a in m['artifacts'] if a['id'] in board['artifactIds'])
            model.update(v, request(v, 'fixture-comment', operation='feedback', body='A 的标题字体再大一点',
                target={'versionId': m['identity']['versionId'], 'cueIds': ['A'], 'storyboardId': board['id'],
                        'artifactId': frame['id'], 'frameId': frame['frameId']}, source=user('A 的标题字体再大一点', 'simulated:fixture')))
        if case['id'] == 'pure-visual-content':
            m = load(v)
            a = next(c for c in m['cues'] if c['id'] == 'A')
            for key in ('narrationAnchor', 'narration', 'screenText', 'contentContext'):
                a.pop(key, None)
            a['segmentIds'] = []
            a['finalAnimationDescription'] = '人物脸部的定位框淡入并保持，没有文字和旁白。'
            model.update(v, request(v, 'fixture-visual-layout', operation='edit', patch={'cues': m['cues']},
                files=[staged(v, a['renderAdapters']['hyperframes']['compositionSrc'],
                    b'<div style="width:150px;height:200px;border:2px solid white"></div>')]))
        before = load(v)
        record = {'case': case, 'project': str(project), 'versionRoot': str(v), 'aliases': {'D': 'C'},
                  'beforeManifest': before, 'beforeSourceHashes': source_hashes(v),
                  'rendering': 'Semantic test doubles; no real media claim', 'setupRenderCalls': calls}
        write_json(root / 'cases' / case['id'] / 'fixture.json', record)
        locations[case['id']] = str(v)
    write_json(root / 'run.json', {'cases': locations, 'skillSha256': sha(REPO / 'SKILL.md')})
    return {'status': 'prepared', 'root': str(root), 'cases': locations}


def fixture(root, case_id):
    path = root / 'cases' / case_id / 'fixture.json'
    if case_id not in {c['id'] for c in cases()}:
        raise ValueError('unknown scenario')
    return json.loads(path.read_text())


def observe(root, case_id):
    value = fixture(root, case_id)
    case = {k: v for k, v in value['case'].items() if k != 'acceptance'}
    return {'case': case, 'aliases': value['aliases'], 'versionRoot': value['versionRoot'],
            'status': model.status(Path(value['versionRoot']))}


def act(root, case_id, action, request_file):
    value = fixture(root, case_id)
    v = Path(value['versionRoot'])
    payload = json.loads(request_file.read_text())
    if not payload.get('agentJudgment') or payload.get('utterance') != value['case']['utterance']:
        raise ValueError('record the Agent judgment and original utterance before acting')
    if action == 'clarify' and not payload.get('question'):
        raise ValueError('a clarification must record the focused question')
    if action not in {'update', 'preview', 'clarify'}:
        raise ValueError('unsupported scenario tool')
    path = root / 'cases' / case_id / 'trace.jsonl'
    entry = {'at': datetime.now(timezone.utc).isoformat(), 'phase': 'before', 'action': action,
             'payload': payload, 'renderCalls': []}
    with path.open('a') as log:
        log.write(json.dumps(entry, ensure_ascii=False) + '\n')
    try:
        with render_stubs(entry['renderCalls']):
            entry['result'] = ({'status': 'clarification-required'} if action == 'clarify'
                               else getattr(model, action)(v, payload['request']))
    except Exception as error:
        entry['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        entry.update(phase='after', state=model.status(v), sourceHashes=source_hashes(v))
        with path.open('a') as log:
            log.write(json.dumps(entry, ensure_ascii=False) + '\n')
    return {k: entry[k] for k in ('action', 'result', 'renderCalls') if k in entry}


def verify(root):
    checks = {}
    for case in cases():
        key = case['id']
        value = fixture(root, key)
        before = value['beforeManifest']
        path = root / 'cases' / key / 'trace.jsonl'
        events = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        done = [e for e in events if e['phase'] == 'after']
        if not done or any(e.get('error') for e in done):
            checks[key] = False
            continue
        v = Path(value['versionRoot'])
        state = load(v)
        new_decisions = state['decisions'][len(before['decisions']):]
        added_artifacts = state['artifacts'][len(before['artifacts']):]
        changed = {p for p, h in source_hashes(v).items() if value['beforeSourceHashes'].get(p) != h}
        if key == 'cold-continue':
            ok = len(state['storyboards']) == 3 and not state['decisions'] and all(a['purpose'] == 'storyboard' for a in added_artifacts)
            ok &= not any(c['rendererStub'] != 'static' for e in done for c in e['renderCalls'])
            ok &= not any(e['action'] == 'clarify' for e in done)
        elif key == 'pure-visual-content':
            cue = next(c for c in state['cues'] if c['id'] == 'A')
            context = cue.get('contentContext', {})
            ok = set(context) == {'narration', 'screenText'} and all(
                item.get('state') == 'none' and item.get('basis', {}).get('reference')
                for item in context.values())
            ok &= not cue.get('narrationAnchor') and not cue.get('narration') and not cue.get('screenText')
            ok &= not new_decisions and not any(e['action'] == 'clarify' for e in done)
            ok &= len(state['storyboards']) == 1 and state['storyboards'][0]['cueId'] == 'A'
            ok &= model.status(v)['storyboard']['cues'][0]['canConfirm']
        elif key == 'round-handoff':
            ok = len(state['reviewRounds']) == 1 and not new_decisions
            ok &= set(state['reviewRounds'][0]['feedbackIds']) == {f['id'] for f in before['feedback']}
            ok &= state['reviewRounds'][0]['status'] == 'processed'
            ok &= all(f['status'] == 'addressed' for f in state['feedback'])
            ok &= changed == {'compositions/cues/A.html'}
            ok &= state['decisions'] == before['decisions']
        elif key == 'confirm-selected':
            selected = {c['objectId'] for c in state['cues'] if c['id'] in {'A', 'B'}}
            ok = len(new_decisions) == 1 and new_decisions[0]['kind'] == 'confirm-design' and set(new_decisions[0]['objectIds']) == selected
        elif key == 'edit-a-only':
            ok = bool(changed) and changed == {'compositions/cues/A.html'} and not new_decisions
            ok &= state['cues'] == before['cues']
        elif key in {'demo-exclude-d', 'full-after-edit'}:
            last = next((a for a in reversed(added_artifacts) if a['kind'] == 'full-preview'), {})
            expected = ['C'] if key == 'demo-exclude-d' else []
            ok = bool(last) and last['coverage']['excludedCueIds'] == expected
            ok &= set(last['coverage']['presentedCueIds']) == ({'A', 'B', 'C'} - set(expected))
            ok &= last['complete'] == (not expected)
            ok &= any(d['kind'] == 'authorize-demo' for d in new_decisions)
            ok &= not any(d['kind'] in {'approve', 'authorize', 'approve-and-deliver'} for d in new_decisions)
        elif key == 'rename-continuation':
            original = next(c for c in before['cues'] if c['id'] == 'A')
            renamed = next((c for c in state['cues'] if c['id'] == 'A-renamed'), {})
            ok = renamed.get('objectId') == original['objectId'] and not new_decisions and not any(c['id'] == 'A' for c in state['cues'])
        else:
            ok = all(e['action'] == 'clarify' for e in done) and state == before and not changed
        checks[key] = bool(ok)
    result = {'status': 'verified' if all(checks.values()) else 'incomplete', 'checks': checks,
              'traceRoot': str(root), 'skillSha256': sha(REPO / 'SKILL.md'),
              'limitation': 'One actual Agent run of bounded scenarios; semantic media stubs; not an NLP router benchmark.'}
    write_json(root / 'evidence.json', result)
    if not all(checks.values()):
        raise AssertionError(result)
    return result


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'observe', 'act', 'verify'):
        command = commands.add_parser(name)
        command.add_argument('--root', required=True, type=Path)
        if name in {'observe', 'act'}:
            command.add_argument('--case', required=True)
        if name == 'act':
            command.add_argument('--action', required=True)
            command.add_argument('--request-file', required=True, type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.root)
    elif args.command == 'observe':
        result = observe(args.root, args.case)
    elif args.command == 'act':
        result = act(args.root, args.case, args.action, args.request_file)
    else:
        result = verify(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
