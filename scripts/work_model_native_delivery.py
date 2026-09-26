"""Native render reuse: pending hard links, published metadata-only indexes."""
from __future__ import annotations
import json
import os
from pathlib import Path
from scripts.work_model_store import atomic_json, layout, safe, sha
from scripts.work_model_inputs import cue_key
from scripts.manifest_transaction import manifest_transaction
from scripts.delivery_media import formal_instances
from scripts.delivery_contract import PROTOCOL_VERSION


def _published(afterforge, index, key):
    for ep in index['episodes']:
        for version in ep['versions']:
            root = safe(afterforge, version['root'])
            manifest = json.loads((root / 'animation-manifest.json').read_text())
            for release in manifest.get('deliveries', []):
                if release.get('protocolVersion') != PROTOCOL_VERSION: continue
                for media in release['media']:
                    if key in media.get('inputKeys', []):
                        return safe(afterforge, media['path']), media['sha256']
    return None


def native_media(root, snapshot, manifest, cue, job):
    from scripts.work_model_jobs import _validate_media, render_cue, _job_path
    afterforge, index = layout(root)
    key = cue_key(snapshot, manifest, cue, 'delivery')
    relative = f'cache/cues/delivery/{key}/media.mov'
    pending = safe(root, relative, exists=False)
    record_path = pending.with_suffix('.json')
    candidate = None
    if record_path.is_file():
        record = json.loads(record_path.read_text())
        if record.get('inputKey') == key:
            base = afterforge if record.get('root') == 'afterforge' else root
            path = safe(base, record['path'], exists=False)
            if path.is_file():
                if sha(path) != record['sha256']:
                    raise ValueError('native delivery cache is corrupt; publication refused')
                candidate = path, record['sha256']
    candidate = candidate or _published(afterforge, index, key)
    target = safe(snapshot, relative, exists=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    cache_hit = candidate is not None
    if candidate:
        path, checksum = candidate
        if sha(path) != checksum: raise ValueError('published native media hash changed')
        os.link(path, target)  # No copy fallback, including across devices.
    else:
        render_cue(snapshot, manifest, cue, quality='delivery', target=target, log_path=snapshot/'render.log')
        checksum = sha(target)
        # A new render can produce byte-identical media from a different input.
        # Reuse the existing physical entity before it enters the pending cache.
        matches = formal_instances(afterforge, {checksum: {'size': target.stat().st_size}})[checksum]
        existing = next((p for p in matches if p != target), None)
        if existing:
            target.unlink()
            os.link(existing, target)
    valid = _validate_media(target, manifest, cue, 'delivery', snapshot/'render.log')
    with manifest_transaction(root):
        if not cache_hit:
            pending.parent.mkdir(parents=True, exist_ok=True)
            if pending.exists():
                if sha(pending) != checksum: raise ValueError('pending native cache differs')
                if pending.stat().st_ino != target.stat().st_ino: raise ValueError('duplicate pending native media')
            else:
                os.link(target, pending)
            atomic_json(record_path, {'inputKey':key, 'sha256':checksum, 'path':relative, **valid})
    job.setdefault('mediaReuse', {})[cue['id']] = 'cache-hit' if cache_hit else 'rebuilt'
    job['completedCueIds'] = list(dict.fromkeys(job.get('completedCueIds', []) + [cue['id']]))
    atomic_json(_job_path(root, job['id']), job)
    return {'path':relative, 'sha256':checksum, 'inputKey':key, **valid}


def finish_native_cache(root, release):
    """Only call after the verified release has a durable manifest record."""
    afterforge, _ = layout(root)
    with manifest_transaction(root):
        for media in release['media']:
            formal = safe(afterforge, media['path'])
            if sha(formal) != media['sha256']: raise ValueError('formal media changed before indexing')
            for key in media.get('inputKeys', []):
                movie = safe(root, f'cache/cues/delivery/{key}/media.mov', exists=False)
                if movie.exists() and sha(movie) != media['sha256']:
                    raise ValueError('pending media differs; refusing cache removal')
                atomic_json(movie.with_suffix('.json'), {'inputKey':key, 'sha256':media['sha256'],
                    'path':media['path'], 'root':'afterforge', 'deliveryId':release['id']})
                movie.unlink(missing_ok=True)
