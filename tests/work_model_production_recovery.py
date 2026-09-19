#!/usr/bin/env python3
"""Opt-in recovery proof against an untouched real production version.

This harness copies the designated version byte-for-byte into ``/private/tmp``
and only then exercises public work-model APIs.  It is deliberately excluded
from unittest discovery.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import work_model as model
from scripts.work_model_store import load, sha
from tests.work_model_fixtures import demo_request


SOURCE = Path('/Users/xiaobaimac/Movies/trumen/AfterForge/工程/episodes/episode-bd459610b45a/version-d7c63089d9f1')
DEFAULT_ROOT = Path(tempfile.gettempdir()) / 'afterforge-production-recovery'


def tree_hashes(root: Path) -> dict[str, str]:
    """Streaming SHA-256 inventory; regular files only, including historical jobs."""
    return {path.relative_to(root).as_posix(): sha(path) for path in sorted(root.rglob('*'))
            if path.is_file() and not path.is_symlink()}


def request(root: Path, name: str, **kwargs):
    return {'requestId': name, 'expectedRevision': load(root)['editRevision'], **kwargs}


def copy_fixture(destination: Path) -> Path:
    afterforge = destination / 'AfterForge'
    target = afterforge / '工程/episodes/episode-bd459610b45a/version-d7c63089d9f1'
    target.parent.mkdir(parents=True, exist_ok=True)
    # copy2 preserves historical bytes/timestamps while never linking to source.
    shutil.copytree(SOURCE, target, copy_function=shutil.copy2)
    source_project = SOURCE.parents[2] / 'project.json'
    project = afterforge / '工程/project.json'
    project.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_project, project)
    return target


def current_review(root: Path):
    return model.status(root).get('reviewSet')


def main() -> int:
    parser = argparse.ArgumentParser(description='Run isolated recovery from the real Truman production cache.')
    parser.add_argument('--run', action='store_true', help='required acknowledgement before copying the 2.7GB source to /private/tmp')
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    if not args.run:
        parser.error('pass --run to create the isolated recovery fixture')
    if not SOURCE.is_dir():
        raise SystemExit(f'missing designated source version: {SOURCE}')
    root_base = args.root.resolve()
    if root_base.exists():
        raise SystemExit(f'refusing to overwrite retained recovery fixture: {root_base}')

    source_before = tree_hashes(SOURCE)
    version = copy_fixture(root_base)
    copied_before = tree_hashes(version)
    if copied_before != source_before:
        raise RuntimeError('isolated copy differs from source before recovery begins')
    old = load(version)
    historical_status = model.status(version)
    old_artifacts = json.loads(json.dumps(old.get('artifacts', []), ensure_ascii=False))
    old_reviews = json.loads(json.dumps(old.get('reviewSets', []), ensure_ascii=False))
    old_ids = {'artifacts': [item['id'] for item in old_artifacts], 'reviews': [item['id'] for item in old_reviews]}

    old_resume_rejected = False
    jobs = sorted((version / 'jobs').glob('job-*.json'))
    if jobs:
        try:
            model.resume(version, request(version, 'reject-old-resume', jobId=json.loads(jobs[0].read_text())['id']))
        except ValueError:
            old_resume_rejected = True
    if not old_resume_rejected:
        raise RuntimeError('historical full-preview resume was not rejected')
    if current_review(version) is not None:
        raise RuntimeError('historical review unexpectedly qualifies as current')
    if historical_status.get('decisions') or historical_status.get('deliveries'):
        raise RuntimeError('designated incident fixture has unexpected user decisions or delivery')

    # Public no-op edit is the explicit enrolment boundary; it preserves source
    # and historical evidence while assigning current creative objects.
    model.update(version, request(version, 'enroll-current-objects', operation='edit', patch={}))
    # This legacy incident stored visible copy only in its canonical HTML.
    # Supply the actual inventory in this isolated fixture, never a fake none
    # declaration. This is a new current-input fact; historical cache keys may
    # legitimately differ after the metadata is completed.
    class VisibleCopy(HTMLParser):
        def __init__(self):
            super().__init__(); self.hidden = 0; self.values = []
        def handle_starttag(self, tag, attrs):
            if tag in {'head', 'style', 'script'}: self.hidden += 1
        def handle_endtag(self, tag):
            if tag in {'head', 'style', 'script'}: self.hidden -= 1
        def handle_data(self, value):
            if not self.hidden and value.strip(): self.values.append(value.strip())
    restored = load(version)
    copy_inventory = {}
    for cue in restored['cues']:
        if cue['productionMode'] != 'animation': continue
        source = cue['renderAdapters']['hyperframes']['compositionSrc']
        parser = VisibleCopy(); parser.feed((version / source).read_text())
        if not parser.values:
            raise RuntimeError('fixture requires an explicit inspected copy fact: ' + cue['id'])
        cue['screenText'] = [{'text': text} for text in parser.values]
        copy_inventory[cue['id']] = {'source': source, 'sha256': sha(version / source), 'text': parser.values}
    model.update(version, request(version, 'complete-real-copy-context', operation='edit', patch={'cues': restored['cues']}))
    cues = [cue['id'] for cue in load(version)['cues'] if cue['productionMode'] == 'animation']
    if len(cues) != 18:
        raise RuntimeError(f'expected 18 animated cues, found {len(cues)}')
    boards = model.preview(version, request(version, 'recover-storyboard', scope='storyboard', cueIds=cues))
    if len(boards['storyboardIds']) != 18:
        raise RuntimeError('did not render one current storyboard per animated cue')
    model.update(version, request(version, 'confirm-recovered-design', operation='decision', kind='confirm-design', storyboardIds=boards['storyboardIds'],
        source={'channel': 'chat', 'text': '模拟用户确认隔离恢复后的静态设计', 'reference': 'recovery-harness'}))

    # This public request registers one fresh task authorization and then
    # validates every cached MOV before reusing it in the full composite.
    full = model.preview(version, demo_request(version, 'recover-full-demo', cueIds=cues, workCueIds=cues, excludedCueIds=[]))
    review = full.get('reviewSet')
    if not review:
        raise RuntimeError('recovered full demo did not create a current review set')
    current = load(version)
    if current['artifacts'][:len(old_artifacts)] != old_artifacts or current['reviewSets'][:len(old_reviews)] != old_reviews:
        raise RuntimeError('historical artifact or review record changed during recovery')
    new_events = [item for item in current['artifacts'] if item.get('eventId') and item['id'] not in old_ids['artifacts']]
    if not new_events or review['id'] in old_ids['reviews']:
        raise RuntimeError('recovery did not create distinct current evidence')
    source_after = tree_hashes(SOURCE)
    if source_after != source_before:
        raise RuntimeError('source production tree changed during isolated recovery')
    (root_base / 'source-before.json').write_text(json.dumps(source_before, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (root_base / 'source-after.json').write_text(json.dumps(source_after, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (root_base / 'historical-status.json').write_text(json.dumps(historical_status, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (root_base / 'recovered-status.json').write_text(json.dumps(model.status(version), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    cache = []
    for job in sorted((version / 'jobs').glob('job-*.json')):
        data = json.loads(job.read_text())
        if data.get('request', {}).get('requestId') == 'recover-full-demo':
            cache = data.get('mediaReuse', {})
    evidence = {
        'command': f'{Path(sys.executable).name} -B tests/work_model_production_recovery.py --run --root {root_base}',
        'fixture': str(root_base), 'source': str(SOURCE), 'version': str(version),
        'completedCopyContext': copy_inventory, 'sourceFileCount': len(source_before), 'historicalIds': old_ids,
        'oldResumeRejected': old_resume_rejected, 'oldReviewCurrent': False,
        'newStoryboardIds': boards['storyboardIds'], 'newReviewId': review['id'],
        'newEventIds': [item['id'] for item in new_events], 'mediaReuse': cache,
        'sourceUnchanged': True,
        'sourceInventories': ['source-before.json', 'source-after.json'],
        'simulatedDecisionsOnly': True,
        'currentReviewApproved': False, 'deliveryAuthorized': False,
    }
    (root_base / 'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
