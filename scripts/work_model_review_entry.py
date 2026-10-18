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

from scripts.work_model_store import atomic_json, layout, load

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


def result_target(root, result):
    """Describe this result, never substitute the latest production result."""
    manifest = load(root)
    artifact = next((a for a in manifest['artifacts'] if a['id'] in result.get('artifactIds', []) and a['kind'] == 'full-preview'), None)
    if not artifact:
        return None
    return {'versionId':manifest['identity']['versionId'], 'tab':'preview', 'artifactId':artifact['id'],
            'videoPath':str(Path(root) / artifact['path'])}


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


def handoff(root, result):
    target = result_target(root, result)
    if not target:
        return result
    afterforge, _ = layout(root)
    locator = afterforge / '工程/review-service.json'
    expected = {'root':str(afterforge), 'mode':'project', **code_identity()}
    entry = {**target, 'available':False}
    try:
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
        entry.update(available=True, url=base + '/?' + urlencode({k:target[k] for k in ('versionId','tab','artifactId')}))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        entry.update(error=str(error), reopen=f'{sys.executable} scripts/serve_workflow_review.py {str(afterforge)!r} --port 0')
    return {**result, 'reviewEntry':entry}
