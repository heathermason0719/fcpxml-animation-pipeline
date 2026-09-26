"""Verified animation provenance and the complete FCPXML media closure."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET
from scripts.work_model_store import sha, digest, safe

MEDIA_MARKER = 'org.afterforge.media.sha256'


def reachable_assets(document):
    resources = document.find('resources')
    if resources is None: raise ValueError('source XML has no resources')
    # FCP also uses ref for local text-style definitions inside a Project.
    # Traverse those definitions without mistaking them for media resources.
    indexed = {item.get('id'): item for item in document.iter() if item.get('id')}
    projects = document.findall('.//project')
    if len(projects) != 1: raise ValueError('source XML requires one selected Project')
    pending = [n.get('ref') for n in projects[0].iter() if n.get('ref')]
    seen = set()
    while pending:
        key = pending.pop()
        if key in seen: continue
        if key not in indexed: raise ValueError('unresolved source resource: ' + key)
        seen.add(key)
        pending.extend(n.get('ref') for n in indexed[key].iter() if n.get('ref'))
    return {k: indexed[k] for k in sorted(seen) if indexed[k].tag == 'asset'}


def registered_origins(afterforge):
    """Manifests establish provenance; names alone never establish ownership."""
    result = {}
    for path in sorted(Path(afterforge).rglob('animation-manifest.json')):
        if any(p in {'.partial', '.scratch', '.staging'} for p in path.parts) or path.is_symlink(): continue
        try: manifest = json.loads(path.read_text())
        except (OSError, ValueError): continue
        entries = [(c.get('id'), c.get('deliveryAsset')) for c in manifest.get('cues', [])]
        for release in manifest.get('deliveries', []):
            entries.extend((a.get('cueId'), a) for a in release.get('media', []))
        for cue_id, asset in entries:
            if not isinstance(asset, dict) or not isinstance(asset.get('sha256'), str): continue
            value = {'manifest': path.relative_to(afterforge).as_posix(), 'cueId': cue_id,
                     **{k: asset[k] for k in ('sha256', 'fileName', 'width', 'height', 'frameRate', 'duration', 'codec', 'hasAlpha') if k in asset}}
            candidate = (Path(afterforge)/asset['path'] if asset.get('root') == 'afterforge' and asset.get('path')
                         else path.parent/asset.get('relativePath', '__absent__'))
            if candidate.resolve().is_relative_to(Path(afterforge).resolve()) and candidate.is_file() and not candidate.is_symlink():
                value['size'] = candidate.stat().st_size
            elif 'size' in asset:
                value['size'] = asset['size']
            result.setdefault(asset['sha256'], value)
    missing = {h:v for h,v in result.items() if 'size' not in v}
    names = {v.get('fileName') for v in missing.values()}
    if names:
        for directory, dirs, files in os.walk(afterforge, followlinks=False):
            dirs[:] = [d for d in dirs if d not in {'.scratch', '.partial', '.staging'}]
            for name in names.intersection(files):
                candidate = Path(directory)/name
                if candidate.is_symlink() or not candidate.is_file(): continue
                checksum = sha(candidate)
                if checksum in missing:
                    result[checksum]['size'] = candidate.stat().st_size
    return result


def media_path(src, base):
    url = urlsplit(src)
    if url.scheme not in ('', 'file') or url.netloc not in ('', 'localhost'): return None
    p = Path(unquote(url.path))
    return (p if p.is_absolute() else Path(base) / p).resolve()


def collect_inherited(afterforge, source, manifest):
    document = ET.parse(source).getroot()
    catalog = registered_origins(Path(afterforge))
    names = {v.get('fileName') for v in catalog.values()}
    sizes = {v['size'] for v in catalog.values() if 'size' in v}
    incomplete_sizes = any('size' not in v for v in catalog.values())
    base = manifest.get('provenance', {}).get('sourceReferenceBase') or str(Path(source).parent)
    bindings = []
    for key, asset in reachable_assets(document).items():
        originals = [r for r in asset.findall('media-rep') if r.get('kind') == 'original-media']
        if len(originals) != 1: raise ValueError('source asset must have one original-media: ' + key)
        rep = originals[0]; src = rep.get('src', '')
        path = media_path(src, base)
        marker = asset.find(f"metadata/md[@key='{MEDIA_MARKER}']")
        flagged = (asset.get('name', '').startswith('AF__') or Path(unquote(urlsplit(src).path)).name.startswith('AF__')
                   or asset.get('name') in names or (path is not None and path.name in names) or marker is not None)
        checksum = None
        if path and path.is_file() and (flagged or (path.suffix.lower() == '.mov'
                and (incomplete_sizes or path.stat().st_size in sizes))):
            checksum = sha(path)
        if flagged and checksum not in catalog:
            raise ValueError('unverified inherited AfterForge media: ' + src)
        if marker is not None and marker.get('value') != checksum:
            raise ValueError('inherited animation marker/hash mismatch: ' + key)
        binding = {'resourceId': key, 'sourceSrc': src, 'sha256': checksum, 'afterforge': checksum in catalog if checksum else False}
        if binding['afterforge']:
            binding.update(path=str(path), fileName=path.name, origin=catalog[checksum])
        bindings.append(binding)
    return bindings


def inherited_identity(bindings):
    return [{k: v for k, v in b.items() if k != 'path'} for b in bindings]


def inherit_into_xml(document, bindings, media):
    by_hash = {m['sha256']: m for m in media}
    resources = document.find('resources')
    reachable = reachable_assets(document)
    for asset in list(resources):
        if asset.tag == 'asset' and asset.get('id') not in reachable:
            resources.remove(asset)
    for binding in bindings:
        if not binding['afterforge']: continue
        asset = resources.find(f"asset[@id='{binding['resourceId']}']")
        name = by_hash[binding['sha256']]['fileName']
        for rep in list(asset.findall('media-rep')): asset.remove(rep)
        asset.insert(0, ET.Element('media-rep', {'kind': 'original-media', 'src': './' + name}))
        metadata = asset.find('metadata')
        if metadata is None: metadata = ET.SubElement(asset, 'metadata')
        marker = metadata.find(f"md[@key='{MEDIA_MARKER}']")
        if marker is None: marker = ET.SubElement(metadata, 'md', {'key': MEDIA_MARKER})
        marker.set('value', binding['sha256'])


def validate_inherited(source, output, bindings, media):
    """Compare actual source graph with frozen provenance and normalized output."""
    assets = reachable_assets(source)
    if {b['resourceId'] for b in bindings} != set(assets) or len(bindings) != len(assets):
        raise ValueError('source media closure differs from provenance')
    by_hash = {m['sha256']: m for m in media}
    resources = output.find('resources')
    inherited_hashes = set()
    for b in bindings:
        original = assets[b['resourceId']]
        rep = next((r for r in original.findall('media-rep') if r.get('kind') == 'original-media'), None)
        if rep is None or rep.get('src') != b['sourceSrc']: raise ValueError('source media binding differs')
        signaled = original.get('name', '').startswith('AF__') or Path(unquote(urlsplit(b['sourceSrc']).path)).name.startswith('AF__') or original.find(f"metadata/md[@key='{MEDIA_MARKER}']") is not None
        if signaled and not b['afterforge']: raise ValueError('AfterForge source media omitted')
        actual = resources.find(f"asset[@id='{b['resourceId']}']")
        if actual is None: raise ValueError('source media resource omitted')
        if not b['afterforge']: continue
        checksum = b['sha256']; inherited_hashes.add(checksum)
        if checksum not in by_hash or b.get('origin', {}).get('sha256') != checksum:
            raise ValueError('inherited movie missing or provenance invalid')
        marker = actual.find(f"metadata/md[@key='{MEDIA_MARKER}']")
        if marker is None or marker.get('value') != checksum:
            raise ValueError('inherited movie marker differs from provenance')
        actual = copy.deepcopy(actual)
        name = by_hash[checksum]['fileName']
        reps = actual.findall('media-rep')
        if len(reps) != 1 or reps[0].attrib != {'kind': 'original-media', 'src': './' + name} or list(reps[0]):
            raise ValueError('inherited movie must use relative original media without bookmark')
        # The builder may only relocate this resource and add the media marker.
        expected = copy.deepcopy(original)
        for r in list(expected.findall('media-rep')): expected.remove(r)
        expected.insert(0, ET.Element('media-rep', {'kind': 'original-media', 'src': './' + name}))
        for element in (expected, actual):
            md = element.find('metadata')
            if md is not None:
                for child in list(md):
                    if child.get('key') == MEDIA_MARKER: md.remove(child)
                if not len(md): element.remove(md)
        from scripts.validate_fcpxml_package import _semantic_tree
        if _semantic_tree(expected) != _semantic_tree(actual): raise ValueError('inherited resource semantics changed')
    return inherited_hashes


def formal_instances(afterforge, hashes, *, exclude=()):
    excluded = [Path(p).resolve() for p in exclude]
    sizes = {m['size'] for m in hashes.values()}
    found = {h: [] for h in hashes}
    for directory, dirs, files in os.walk(afterforge, followlinks=False):
        dirs[:] = [d for d in dirs if not any((Path(directory)/d).resolve().is_relative_to(x) for x in excluded)]
        for name in files:
            path = Path(directory)/name
            if path.is_symlink() or not path.is_file() or path.stat().st_size not in sizes: continue
            checksum = sha(path)
            if checksum in found: found[checksum].append(path)
    return found


def assert_unique_media(afterforge, media):
    known = {h: item for h,item in registered_origins(afterforge).items() if 'size' in item}
    known.update({m['sha256']: m for m in media})
    found = formal_instances(afterforge, known)
    for checksum, paths in found.items():
        if len({(p.stat().st_dev, p.stat().st_ino) for p in paths}) > 1:
            raise ValueError('duplicate physical formal media: ' + checksum + ' ' + ', '.join(str(p) for p in paths))
    return found
