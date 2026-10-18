"""Prepare a local UI-only copy of an explicit read-only production version.

No rendering, task execution or adoption is performed here. Browser decisions
belong only to the resulting copy. Never use its manifest as production input.
"""
from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.work_model_store import layout, load, save, sha


def prepare(source: Path, destination: Path):
    source = source.expanduser().resolve()
    destination = destination.expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError('output root must not exist')
    if source == destination or source in destination.parents:
        raise ValueError('fixture must be outside the production version')
    manifest = load(source)
    if manifest['schemaVersion'] != '3.0':
        raise ValueError('UI fixture requires an explicit schema-3 source version')
    _, index = layout(source)
    source_sha = sha(source / 'animation-manifest.json')
    identity = manifest['identity']
    relative = Path('工程/episodes') / identity['episodeId'] / identity['versionId']
    afterforge = destination / 'AfterForge'
    version = afterforge / relative
    version.mkdir(parents=True)
    # Independent bytes keep browser exercises unable to alter the frozen source.
    for name in ('assets', 'compositions', 'previews'):
        if (source / name).is_dir():
            for path in (source / name).rglob('*'):
                if path.is_symlink():
                    raise ValueError('fixture source must not contain symlinks')
            shutil.copytree(source / name, version / name, copy_function=shutil.copy2)
    for name in ('frame.md', 'package.json', 'hyperframes.json', 'meta.json'):
        if (source / name).is_file():
            shutil.copy2(source / name, version / name)
    isolated = copy.deepcopy(manifest)
    isolated['deliveries'] = []
    isolated['decisions'] = [d for d in isolated['decisions'] if d['kind'] not in
                             {'approve', 'authorize', 'approve-and-deliver', 'accept-import', 'roundtrip'}]
    isolated['requests'] = {}
    save(version, isolated)
    isolated_index = {'schemaVersion': index['schemaVersion'], 'projectId': index['projectId'],
                      'title': index.get('title', '') + ' · 隔离 UI 验收', 'revision': 0,
                      'episodes': [{'id': identity['episodeId'], 'title': identity['episodeTitle'],
                                    'versions': [{'id': identity['versionId'],
                                                  'title': identity['versionTitle'] + ' · 隔离副本',
                                                  'root': relative.as_posix(), 'legacy': False}]}],
                      'requests': {}, 'protocolBaselines': {}}
    (afterforge / '工程/project.json').write_text(json.dumps(isolated_index, ensure_ascii=False, indent=2))
    if sha(source / 'animation-manifest.json') != source_sha:
        raise ValueError('read-only source changed while preparing fixture')
    evidence = {'sourceVersion': str(source), 'sourceManifestSha256': source_sha,
                'afterforge': str(afterforge), 'version': str(version),
                'fixtureOnly': True, 'rendered': False}
    (destination / 'prepare-evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-version', required=True, type=Path)
    parser.add_argument('--root', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source_version, args.root), ensure_ascii=False, indent=2))
