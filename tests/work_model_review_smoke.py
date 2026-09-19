#!/usr/bin/env python3
"""Opt-in real Review fixture derived from the read-only 2026-09-09 baseline."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import work_model as model
from scripts.work_model_store import load, sha


BASELINE = Path('/Users/xiaobaimac/Movies/trumen/AfterForge/2026-09-09_v1')
DEFAULT_ROOT = Path(tempfile.gettempdir()) / 'afterforge-review-smoke'


def hashes(root: Path) -> dict[str, str]:
    return {item.relative_to(root).as_posix(): sha(item) for item in sorted(root.rglob('*'))
            if item.is_file() and not item.is_symlink()}


def request(root: Path, name: str, **kwargs):
    return {'requestId': name, 'expectedRevision': load(root)['editRevision'], **kwargs}


def main() -> int:
    parser = argparse.ArgumentParser(description='Build an isolated real-PNG Review UI fixture.')
    parser.add_argument('--run', action='store_true', help='required acknowledgement before creating /private/tmp fixture')
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    if not args.run:
        parser.error('pass --run to create the fixture')
    if not BASELINE.is_dir():
        raise SystemExit(f'missing read-only baseline: {BASELINE}')
    root = args.root.resolve()
    if root.exists():
        raise SystemExit(f'refusing to overwrite retained fixture: {root}')
    before = hashes(BASELINE)
    opened = model.open_project(root / 'AfterForge', {
        'requestId': 'review-smoke-open', 'expectedRevision': 0, 'title': '楚门 Review UI',
        'episodeTitle': '2026-09-09 基线静帧审阅', 'copyFrom': str(BASELINE), 'copyMode': 'restart',
        'commission': {'channel': 'chat', 'text': '明确授权：从 2026-09-09 基线创建隔离 Review UI fixture', 'reference': 'review-smoke-harness'},
    })
    version = Path(opened['root'])
    manifest = load(version)
    animated = [cue for cue in manifest['cues'] if cue['productionMode'] == 'animation']
    if len(animated) != 4:
        raise RuntimeError(f'expected four inherited animation cues, found {len(animated)}')
    # Exact local moments derived from the baseline's approved A11 frames:
    # identity 7/12s, watching 3.5/9.5s, authorization 7⅔s, question ⅛/2⅛s.
    moments = {
        'c01_identity': [('hero', '问题与身份 · 7秒', '7s'), ('question', '身份撤去，问题原位保持 · 12秒', '12s')],
        'c03_watching': [('hero', '看电影 · 18秒', '7/2s'), ('him', '看他 · 24秒', '19/2s')],
        'c04_authorization': [('hero', '观看授权 · 39秒', '23/3s')],
        'c05_question': [('hero', '淡出画面中的构图终态 · 51秒', '1/8s'), ('black', '保持至黑场 · 53秒', '17/8s')],
    }
    for cue in animated:
        still_src = cue['renderAdapters']['hyperframes'].get('stillSrc')
        frames = [{'id': frame_id, 'role': 'hero' if frame_id == 'hero' else 'auxiliary', 'label': label,
                   'time': moment, 'mode': 'motion', 'background': 'none'}
                  for frame_id, label, moment in moments[cue['id']]]
        # The final c05 black hold is a true black-stage frame, rather than an
        # overlay on its preceding fade still.
        if still_src:
            for frame in frames:
                if not (cue['id'] == 'c05_question' and frame['id'] == 'black'):
                    frame['stillSrc'] = still_src
        cue['storyboard'] = {'frames': frames}
    model.update(version, request(version, 'review-smoke-register', operation='edit',
        patch={'cues': manifest['cues'], 'brief': manifest['brief']}))
    result = model.preview(version, request(version, 'review-smoke-png', scope='storyboard', cueIds=[cue['id'] for cue in animated]))
    if len(result['storyboardIds']) != 4 or len(result['artifactIds']) != 7:
        raise RuntimeError('expected four current Storyboards containing seven real PNG frames')
    current = load(version)
    artifacts = [item for item in current['artifacts'] if item['id'] in result['artifactIds']]
    if any(not (version / item['path']).is_file() for item in artifacts):
        raise RuntimeError('a registered Review PNG is missing')
    if any(item.get('mode') != 'motion' for item in artifacts):
        raise RuntimeError('formal Review frames must be real motion snapshots')
    by_cue = {}
    for item in artifacts:
        by_cue.setdefault(item['cueId'], []).append(item)
    for cue_id in ('c01_identity', 'c03_watching', 'c05_question'):
        if len({item['sha256'] for item in by_cue[cue_id]}) != 2:
            raise RuntimeError(f'baseline {cue_id} hero and auxiliary frames are pixel-identical')

    # Keep visual experiments separate from the four registered Storyboards.
    # They snapshot two real, contrasting baseline moments and never adopt a
    # candidate into the canonical cue set.
    canonical_before_exploration = copy.deepcopy(current['cues'])
    def candidate_cues(frame_cue_id: str, frame_id: str):
        candidates = copy.deepcopy(current['cues'])
        for cue in candidates:
            cue.pop('objectId', None)
            cue.pop('deliveryAsset', None)
            if cue['id'] == frame_cue_id:
                selected = next(frame for frame in cue['storyboard']['frames'] if frame['id'] == frame_id)
                selected['role'] = 'hero'  # A candidate still needs one review hero.
                cue['storyboard']['frames'] = [selected]
        return candidates
    model.update(version, request(version, 'review-smoke-exploration', operation='exploration', exploration={
        'id': 'review-smoke-variants',
        'question': '身份揭示和黑场收束各自作为候选审阅样张时，画面是否仍清晰可辨？',
        'description': '两个候选仅供 Review UI 比较，不修改正式 cue。',
        'variants': [
            {'id': 'identity-moment', 'label': '身份时刻', 'description': 'c01 在 7 秒的真实 motion 快照',
             'cues': candidate_cues('c01_identity', 'hero')},
            {'id': 'black-moment', 'label': '黑场时刻', 'description': 'c05 在 17/8 秒的真实 motion 快照',
             'cues': candidate_cues('c05_question', 'black')},
        ],
    }))
    explorations = [
        ('identity-moment', 'c01_identity'),
        ('black-moment', 'c05_question'),
    ]
    exploration_results = []
    for variant_id, cue_id in explorations:
        exploration_results.append(model.preview(version, request(version, f'review-smoke-{variant_id}',
            scope='exploration', explorationId='review-smoke-variants', variantId=variant_id, cueIds=[cue_id])))
    after_exploration = load(version)
    if after_exploration['cues'] != canonical_before_exploration:
        raise RuntimeError('exploration preview mutated the canonical cue set')
    variants = after_exploration['explorations'][-1]['variants']
    exploration_artifacts = [artifact for variant in variants for artifact in after_exploration['artifacts']
                             if artifact['id'] in variant.get('artifactIds', [])]
    if len(exploration_artifacts) != 2 or any(item['purpose'] != 'exploration' for item in exploration_artifacts):
        raise RuntimeError('expected two separately registered exploration PNG samples')
    if len({item['sha256'] for item in exploration_artifacts}) != 2:
        raise RuntimeError('exploration samples are pixel-identical')
    if hashes(BASELINE) != before:
        raise RuntimeError('read-only baseline changed while building fixture')
    evidence = {
        'command': f'{Path(sys.executable).name} -B tests/work_model_review_smoke.py --run --root {root}',
        'fixture': str(root), 'version': str(version), 'baseline': str(BASELINE),
        'baselineUnchanged': True, 'animatedCueIds': [cue['id'] for cue in animated],
        'storyboardIds': result['storyboardIds'], 'frameCount': len(artifacts),
        'frames': [{'cueId': item['cueId'], 'frameId': item['frameId'], 'role': item['role'],
                    'path': item['path'], 'sha256': item['sha256']} for item in artifacts],
        'exploration': {'id': 'review-smoke-variants', 'variantIds': [variant_id for variant_id, _ in explorations],
                        'artifactIds': [artifact_id for outcome in exploration_results for artifact_id in outcome['artifactIds']],
                        'frames': [{'cueId': item['cueId'], 'frameId': item['frameId'], 'path': item['path'],
                                    'sha256': item['sha256']} for item in exploration_artifacts]},
    }
    (root / 'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
