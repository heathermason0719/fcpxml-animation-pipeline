"""Optional visual alternatives: review material, never another source of truth."""
import copy
import hashlib
from pathlib import Path
from scripts.work_model_policy import identifier
from scripts.work_model_store import digest, now, safe, user_source


def variant_lineage(variant, root=None, overrides=None, *, manifest=None):
    """Return authored candidate lineage, including effective local source bytes.

    Pure fixture callers can omit ``root`` and receive metadata lineage.  A
    production caller supplies the version root plus staged overrides so the
    candidate's actual render closure, rather than its path strings, freezes
    the revision identity.
    """
    authored = {key: value for key, value in variant.items()
                if key not in {'artifactIds', 'revision', 'contentIdentity'}}
    identity = {'authored': authored}
    files = []
    if root is not None:
        from scripts.work_model_sources import inspect_sources, static_markup
        root = Path(root).resolve()
        overrides = overrides or {}
        paths = set()
        project = (manifest or {}).get('project', {})
        identity['renderContext'] = {key: project.get(key) for key in ('preview', 'delivery')}
        identity['renderContext']['frameDuration'] = (project.get('source') or {}).get('frameDuration')
        for cue in variant.get('cues', []):
            adapter = cue.get('renderAdapters', {}).get('hyperframes', {})
            source = adapter.get('compositionSrc')
            if not isinstance(source, str) or not source:
                continue
            frames = cue.get('storyboard', {}).get('frames') or []
            paths.update(frame['stillSrc'] for frame in frames if frame.get('stillSrc'))
            if any(frame.get('background') == 'timeline' for frame in frames):
                background = project.get('renderAdapters', {}).get('hyperframes', {}).get('previewMediaSrc')
                if background: paths.add(background)
            motion_sample = any(isinstance(frame, dict) and frame.get('mode', 'layout') == 'motion'
                                for frame in frames)
            if motion_sample:
                # A formally requested Motion sample is rendered from the
                # original executable closure and the pinned vendor host.
                paths.update(inspect_sources(root, cue, overrides, allow_missing=True)['files'])
                if 'assets/vendor/gsap.min.js' in overrides or (root / 'assets/vendor/gsap.min.js').is_file():
                    paths.add('assets/vendor/gsap.min.js')
            else:
                raw = overrides.get(source)
                if raw is None:
                    raw = safe(root, source).read_bytes()
                stripped = static_markup(root, cue, raw.decode('utf-8'), overrides=overrides)
                layout = copy.deepcopy(cue)
                layout_adapter = layout['renderAdapters']['hyperframes']
                layout_adapter.pop('motionSrc', None)
                layout_adapter['layoutDependencies'] = [path for path in adapter.get('layoutDependencies', [])
                                                        if path not in {adapter.get('motionSrc'), 'assets/vendor/gsap.min.js'}]
                effective = {**overrides, source: stripped.encode('utf-8')}
                paths.update(inspect_sources(root, layout, effective, allow_missing=True)['files'])
        # Storyboard and render hosts consume these version-owned inputs when
        # present; include their actual bytes without inventing absent files.
        for name in ('frame.md', 'package.json', 'hyperframes.json'):
            if name in overrides or (root / name).is_file():
                paths.add(name)
        closure = {}
        for name in sorted(paths):
            if name in overrides:
                data = overrides[name]
            else:
                path = safe(root, name, exists=False)
                if not path.is_file() or path.is_symlink():
                    continue
                data = path.read_bytes()
            closure[name] = hashlib.sha256(data).hexdigest()
        identity['closure'] = closure
        files = sorted(closure)
    revision = variant.get('revision')
    revision = revision if isinstance(revision, int) and revision >= 1 else 1
    content_identity = digest(identity)
    if variant.get('contentIdentity') and variant.get('contentIdentity') != content_identity:
        revision += 1
    return {'revision': revision, 'contentIdentity': content_identity, 'files': files}


def candidate_manifest(manifest, request):
    exploration = next((e for e in manifest.get('explorations', []) if e['id'] == request.get('explorationId')), None)
    variant = next((v for v in (exploration or {}).get('variants', []) if v['id'] == request.get('variantId')), None)
    if not variant:
        raise ValueError('unknown exploration variant')
    candidate = copy.deepcopy(manifest)
    candidate['cues'] = copy.deepcopy(variant['cues'])
    return candidate


def set_exploration(manifest, request, *, root=None, overrides=None):
    value = copy.deepcopy(request.get('exploration', {}))
    if set(value) - {'id', 'question', 'description', 'variants'}:
        raise ValueError('exploration edit cannot register artifacts or adoption facts')
    value.setdefault('id', identifier('exploration'))
    if not value.get('question') or not value.get('variants'):
        raise ValueError('exploration requires its visual question and candidate variants')
    variants = value['variants']
    if len({v['id'] for v in variants}) != len(variants):
        raise ValueError('duplicate visual variant')
    old = next((e for e in manifest['explorations'] if e['id'] == value['id']), None)
    old_variants = {item['id']: item for item in (old or {}).get('variants', [])}
    for variant in variants:
        if 'artifactIds' in variant:
            raise ValueError('exploration artifacts are registered only by generation')
        for cue in variant.get('cues', []):
            if 'objectId' in cue or 'deliveryAsset' in cue:
                raise ValueError('visual candidates are not canonical creative objects')
        previous = old_variants.get(variant['id'])
        lineage = variant_lineage(variant, root, overrides, manifest=manifest)
        identity = lineage['contentIdentity']
        previous_identity = previous.get('contentIdentity') if previous else None
        if previous and previous_identity == identity:
            variant['revision'] = previous.get('revision', 1)
            variant['contentIdentity'] = identity
            if previous.get('artifactIds'):
                variant['artifactIds'] = copy.deepcopy(previous['artifactIds'])
        else:
            variant['revision'] = (previous.get('revision', 0) if previous else 0) + 1
            variant['contentIdentity'] = identity
    value['createdAt'] = old['createdAt'] if old else now()
    value['adoptions'] = copy.deepcopy(old.get('adoptions', [])) if old else []
    manifest['explorations'] = [e for e in manifest['explorations'] if e['id'] != value['id']] + [value]
    return value


def adoption(manifest, request, *, root=None):
    candidate_manifest(manifest, request)  # validate chosen workspace/variant
    cue_ids = request.get('cueIds')
    if not isinstance(cue_ids, list) or not cue_ids:
        raise ValueError('visual adoption requires explicit application cueIds')
    if not set(cue_ids).issubset({c['id'] for c in manifest['cues']}):
        raise ValueError('unknown visual adoption cue')
    if not request.get('files') and not request.get('patch'):
        raise ValueError('adoption must include the canonical source update in the same transaction')
    exploration = next(e for e in manifest['explorations'] if e['id'] == request['explorationId'])
    variant = next(v for v in exploration['variants'] if v['id'] == request['variantId'])
    # A legacy exploration remains readable.  Adoption is a new writer fact,
    # so it may freeze the previously absent candidate lineage here without
    # backfilling anything during ordinary reads.
    lineage = variant_lineage(variant, root, manifest=manifest)
    if variant.get('contentIdentity') != lineage['contentIdentity']:
        variant['revision'] = (variant.get('revision', 0) if isinstance(variant.get('revision'), int) else 0) + 1
        variant['contentIdentity'] = lineage['contentIdentity']
    elif not isinstance(variant.get('revision'), int) or variant['revision'] < 1:
        variant['revision'] = lineage['revision']
    object_ids = [cue['objectId'] for cue in manifest['cues']
                  if cue['id'] in cue_ids and cue.get('objectId')]
    if len(object_ids) != len(cue_ids):
        raise ValueError('visual adoption requires registered canonical object identities')
    record = {'id': identifier('decision'), 'kind': 'adopt-direction',
        'source': user_source(request.get('source')), 'explorationId': request['explorationId'],
        'variantId': request['variantId'], 'variantRevision': variant['revision'],
        'variantContentIdentity': variant['contentIdentity'], 'cueIds': cue_ids,
        'objectIds': object_ids, 'createdAt': now()}
    manifest['decisions'].append(record)
    exploration['adoptions'].append(copy.deepcopy(record))
    return record
