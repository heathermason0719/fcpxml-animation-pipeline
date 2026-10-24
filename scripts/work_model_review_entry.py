"""Local CLI review handoff. Production APIs never start HTTP services."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen

from scripts.work_model_store import layout, load

REPOSITORY = Path(__file__).resolve().parents[1]


def code_identity():
    paths = sorted((REPOSITORY / 'scripts').glob('*.py')) + sorted((REPOSITORY / 'assets/review-v3').glob('*'))
    digest = hashlib.sha256()
    for path in paths:
        if path.is_file():
            digest.update(path.relative_to(REPOSITORY).as_posix().encode())
            digest.update(path.read_bytes())
    return {'repository':str(REPOSITORY), 'startupSourceSha256':digest.hexdigest()}


def service_identity(afterforge):
    return {'root':str(Path(afterforge).resolve()), 'mode':'project', 'pid':os.getpid(), **code_identity()}


def result_targets(root, result):
    """Describe every exact result; recommendations and newest artifacts are irrelevant."""
    manifest = load(root)
    version = {'versionId': manifest['identity']['versionId']}
    concepts = {c['id']: c for c in manifest.get('concepts', [])}
    boards = {b['id']: b for b in manifest.get('storyboards', [])}
    artifacts = {a['id']: a for a in manifest.get('artifacts', [])}
    records = result.get('record', [])
    records = records if isinstance(records, list) else [records]
    targets = []
    for record in records:
        concept = concepts.get(record.get('id')) if isinstance(record, dict) else None
        if not concept and isinstance(record, dict) and all(key in record for key in ('id', 'cueId', 'objectId', 'origin', 'path')):
            concept = record  # Preserve the successful receipt even when its target later goes missing.
        if concept:
            targets.append({**version, 'tab': 'overview', 'kind': 'concept',
                            'conceptId': concept['id'], 'cueId': concept['cueId']})
    for key in result.get('storyboardIds', []):
        board = boards.get(key)
        targets.append({**version, 'tab': 'storyboard', 'kind': 'storyboard', 'storyboardId': key,
                        **({'cueId': board['cueId']} if board else {})})
    for key in result.get('artifactIds', []):
        artifact = artifacts.get(key)
        if artifact is None:
            targets.append({**version, 'tab': 'preview', 'kind': 'missing-artifact', 'artifactId': key})
        elif artifact['kind'] in {'full-preview', 'local-preview', 'cue-preview'}:
            video = {**version, 'kind': artifact['kind'], 'artifactId': key,
                     'videoPath': str(Path(root) / artifact['path'])}
            scenes = artifact.get('reviewCues', []) if artifact['kind'] != 'full-preview' else []
            if scenes:
                targets.extend({**video, 'tab': 'storyboard', 'cueId': cue['id']} for cue in scenes)
            else:
                targets.append({**video, 'tab': 'preview'})
    return targets


def result_target(root, result):
    """Compatibility accessor for callers expecting one primary result."""
    return next(iter(result_targets(root, result)), None)


def _query(target):
    return {key: target[key] for key in ('versionId', 'tab', 'conceptId', 'storyboardId', 'cueId', 'artifactId', 'frameId') if key in target}


def _verified_service(locator, expected):
    try:
        record = json.loads(locator.read_text())
        if not isinstance(record, dict):
            return None
        parsed = urlparse(record['url'])
        if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.path not in {'','/'}:
            return None
        with urlopen(record['url'] + '/api/identity', timeout=1) as response:
            actual = json.load(response)
        if isinstance(actual, dict) and all(actual.get(k) == v for k,v in expected.items()):
            return record['url']
    except (OSError, ValueError, KeyError):
        pass
    return None


def handoff(root, result, *, start_service=True):
    targets = result_targets(root, result)
    if not targets:
        return result
    target = targets[0]
    afterforge, _ = layout(root)
    locator = afterforge / '工程/review-service.json'
    query = _query(target)
    if len(targets) > 1:
        query['targets'] = json.dumps([_query(t) for t in targets], ensure_ascii=False, separators=(',', ':'))
    entry = {**target, 'targets': targets, 'available': False, 'query': query,
             'reopen': f'{sys.executable} scripts/serve_workflow_review.py {str(afterforge)!r} --port 0'}
    if not start_service:
        return {**result, 'reviewEntry': {**entry, 'serviceSuppressed': True}}
    try:
        expected = {'root':str(afterforge), 'mode':'project', **code_identity()}
        from scripts.work_model_store import project_lock
        with project_lock(afterforge):
            base = _verified_service(locator, expected)
            if not base:
                log = afterforge / '工程/review-service.log'
                with log.open('ab') as output:
                    process = subprocess.Popen([sys.executable, '-B', str(REPOSITORY / 'scripts/serve_workflow_review.py'),
                        str(afterforge), '--port', '0'], cwd=REPOSITORY, stdin=subprocess.DEVNULL,
                        stdout=output, stderr=output, start_new_session=True)
                for _ in range(50):
                    base = _verified_service(locator, expected)
                    if base or process.poll() is not None:
                        break
                    time.sleep(.1)
            if not base:
                raise OSError('Review service did not become available; see ' + str(log))
        entry.update(available=True, url=base + '/?' + urlencode(query),
                     targets=[{**t, 'url': base + '/?' + urlencode(_query(t))} for t in targets])
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        entry.update(error=str(error))
    return {**result, 'reviewEntry':entry}
