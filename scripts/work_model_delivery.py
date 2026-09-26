"""Protocol-3 publication: visible complete media, lightweight immutable evidence."""
from __future__ import annotations
import copy
import json
import os
import shutil
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET
from scripts.delivery_contract import PROTOCOL_VERSION, delivery_names
from scripts.delivery_media import collect_inherited, inherited_identity, inherit_into_xml, assert_unique_media
from scripts.work_model_store import layout, safe, sha, load, digest, project_lock, fresh_hashes
from scripts.manifest_transaction import manifest_transaction
from scripts.inject_fcpxml import build_delivery_fcpxml, _serialize
from scripts.validate_fcpxml_package import validate_delivery_package
from scripts.work_model_delivery_v2 import ( _asset_path, _source_path, _identity, _inventory as _legacy_inventory,
    _write_json, _copy, _known_dtd, MANIFEST_NAME)


def _inventory(root, *, exclude=None):
    # Finder may add this after delivery; it is not an output or a media locator.
    ignored = set(exclude or ()) | {str(p.relative_to(root)) for p in Path(root).rglob('.DS_Store') if p.is_file() and not p.is_symlink()}
    return _legacy_inventory(root, exclude=ignored)


def _require_dtd(source):
    dtd = _known_dtd(source, None)
    if dtd is None: raise ValueError('FCPXML DTD is required for formal delivery')
    return dtd


def _publication_authority(root, input_key, release_id):
    from scripts.work_model_jobs import _approved, _spec
    fresh_hashes()
    current = load(root, writable=True)
    review = _approved(root, current)
    if digest(_spec(root, current, 'deliver', {})) != input_key:
        raise ValueError('delivery input fingerprint differs from current authorized work')
    journals = [json.loads(p.read_text()) for p in (root/'jobs').glob('*.json')]
    if not any(j.get('action') == 'deliver' and j.get('status') == 'running'
               and j.get('releaseId') == release_id and j.get('inputKey') == input_key
               and j.get('reviewSetId') == review['id'] for j in journals):
        raise ValueError('formal publication requires the current authorized delivery job')
    return review['id']


def _link(source, target):
    try: os.link(source, target)
    except OSError as error: raise ValueError('formal media hard link failed; copying is not allowed') from error
    if sha(source) != sha(target): raise ValueError('linked formal media hash mismatch')


def _file_name(name, checksum, used):
    if not isinstance(name, str) or Path(name).name != name or not name.lower().endswith('.mov'): raise ValueError('invalid formal MOV filename')
    if name.casefold() in used and used[name.casefold()] != checksum:
        name = Path(name).stem + '-' + checksum + '.mov'
    used[name.casefold()] = checksum
    return name


def prepare_release(root, manifest, *, afterforge_root, release_id, input_key, dependency_paths, dtd=None, input_root=None):
    root = Path(root).resolve(); afterforge = Path(afterforge_root).resolve()
    if layout(root)[0] != afterforge: raise ValueError('afterforge_root differs from registered layout')
    if manifest.get('schemaVersion') != '3.0': raise ValueError('new delivery requires schema 3.0')
    review_id = _publication_authority(root, input_key, release_id)
    inputs = root if input_root is None else Path(input_root).resolve()
    source = _source_path(inputs, manifest)
    _require_dtd(source)  # The public writer never supports skip-DTD.
    frozen = copy.deepcopy(manifest)
    from scripts.validate_fcpxml_package import _animated_cues
    animated = _animated_cues(frozen)
    if not animated: raise ValueError('formal delivery requires animation')
    frozen.setdefault('provenance', {}).setdefault('sourceReferenceBase', str(source.parent))
    bindings = collect_inherited(afterforge, source, frozen)
    package_relative, xml_name = delivery_names(frozen['identity'], release_id)
    snapshot_relative = 'releases/' + release_id
    if safe(afterforge, package_relative, exists=False).exists() or safe(root, snapshot_relative, exists=False).exists():
        raise ValueError('release target already exists; verify before retry')
    partial = root / 'releases/.partial'; partial.mkdir(parents=True, exist_ok=True)
    package = Path(tempfile.mkdtemp(prefix=release_id+'-delivery-', dir=partial))
    evidence = Path(tempfile.mkdtemp(prefix=release_id+'-evidence-', dir=partial))
    try:
        media_by_hash = {}; used = {}; source_files = {}
        def add(path, name, checksum, role, cue=None, binding=None):
            if sha(path) != checksum: raise ValueError('formal source media changed')
            if checksum not in media_by_hash:
                name = _file_name(name, checksum, used)
                media_by_hash[checksum] = {'fileName': name, 'sha256': checksum, 'size': path.stat().st_size,
                    'path': package_relative+'/'+name, 'root': 'afterforge', 'roles': [], 'cueIds': [], 'sourceResourceIds': []}
                source_files[checksum] = path
                _link(path, package/name)
            item = media_by_hash[checksum]
            if role not in item['roles']: item['roles'].append(role)
            if cue:
                item['cueIds'].append(cue['id']); item.setdefault('cueId', cue['id'])
                item.setdefault('inputKeys', []).extend([cue['deliveryAsset']['inputKey']] if cue['deliveryAsset'].get('inputKey') else [])
                cue['deliveryAsset']['fileName'] = item['fileName']
            if binding: item['sourceResourceIds'].append(binding['resourceId'])
        for cue in animated:
            asset = cue['deliveryAsset']; add(_asset_path(inputs, asset, cue['id']), asset['fileName'], asset['sha256'], 'rendered', cue=cue)
        for b in bindings:
            if b['afterforge']: add(Path(b['path']), b['fileName'], b['sha256'], 'inherited', binding=b)
        media = sorted(media_by_hash.values(), key=lambda m: m['fileName'])
        record = {'id': release_id, 'inputKey': input_key, 'protocolVersion': PROTOCOL_VERSION,
            'packagePath': package_relative, 'xmlFileName': xml_name, 'snapshotPath': snapshot_relative,
            'evidencePath': snapshot_relative, 'manifestPath': MANIFEST_NAME, 'sourcePath': 'source/source.fcpxml',
            'identity': _identity(frozen, release_id), 'reviewSetId': review_id, 'media': media, 'sourceMedia': inherited_identity(bindings)}
        migration = frozen.get('provenance', {}).get('deliveryMigration')
        if migration and migration.get('replacementDeliveryId') == release_id:
            record['migrationProvenance'] = copy.deepcopy(migration)
        frozen['delivery'] = copy.deepcopy(record)
        document = build_delivery_fcpxml(source, frozen)
        tree = ET.fromstring(document.xml_bytes)
        inherit_into_xml(tree, bindings, media)
        (package/xml_name).write_bytes(_serialize(tree))
        record['infoFcpxmlSha256'] = sha(package/xml_name)
        frozen['delivery'] = copy.deepcopy(record)
        validate_delivery_package(package, source, frozen, dtd_path=_require_dtd(source))
        _copy(source, evidence/'source/source.fcpxml')
        frozen['project']['source']['fcpxml'] = 'source/source.fcpxml'
        _write_json(evidence/MANIFEST_NAME, frozen)
        inventory = {'package': _inventory(package), 'snapshot': _inventory(evidence),
            'dependencies': [{'path': p, 'sha256': sha(safe(inputs,p))} for p in sorted(set(dependency_paths))]}
        _write_json(evidence/'inventory.json', inventory)
        record['inventory'] = inventory
        return {'stagingPackage': str(package), 'stagingSnapshot': str(evidence), 'packagePath': package_relative,
            'snapshotPath': snapshot_relative, 'manifest': frozen, 'record': record, 'inventory': inventory,
            'infoFcpxmlSha256': record['infoFcpxmlSha256']}
    except BaseException:
        shutil.rmtree(package, ignore_errors=True); shutil.rmtree(evidence, ignore_errors=True); raise


def _verify(root, afterforge, record, package, evidence):
    if record.get('protocolVersion') != PROTOCOL_VERSION: raise ValueError('new publication requires current delivery protocol')
    for path in (package, evidence):
        if path.is_symlink() or not path.is_dir(): raise ValueError('delivery/evidence is missing or unsafe')
    frozen = json.loads(safe(evidence, record['manifestPath']).read_text())
    expected, xml_name = delivery_names(frozen['identity'], record['id'])
    if record.get('packagePath') != expected or record.get('xmlFileName') != xml_name:
        raise ValueError('formal delivery must use the shallow contract path')
    if record.get('snapshotPath') != 'releases/'+record['id'] or record.get('evidencePath') != record['snapshotPath']:
        raise ValueError('invalid delivery evidence path')
    if record.get('identity') != _identity(frozen, record['id']): raise ValueError('delivery identity mismatch')
    if frozen.get('delivery') != {k:v for k,v in record.items() if k != 'inventory'}:
        raise ValueError('frozen delivery differs from release record')
    if record.get('manifestPath') != MANIFEST_NAME or record.get('sourcePath') != 'source/source.fcpxml':
        raise ValueError('invalid evidence locator')
    inventory = record['inventory']
    if json.loads(safe(evidence, 'inventory.json').read_text()) != inventory: raise ValueError('evidence inventory mismatch')
    if _inventory(package) != inventory['package']: raise ValueError('package inventory mismatch')
    if _inventory(evidence, exclude={'inventory.json'}) != inventory['snapshot']: raise ValueError('snapshot inventory mismatch')
    if {x['path'] for x in inventory['snapshot']} != {MANIFEST_NAME, 'source/source.fcpxml'}:
        raise ValueError('delivery evidence must contain only metadata and source XML')
    source = safe(evidence, record['sourcePath'])
    if sha(package/xml_name) != record['infoFcpxmlSha256']: raise ValueError('delivery XML hash mismatch')
    validate_delivery_package(package, source, frozen, dtd_path=_require_dtd(source))
    assert_unique_media(afterforge, record['media'])
    return True


def verify_release(root, afterforge_root, record):
    root=Path(root).resolve(); afterforge=Path(afterforge_root).resolve()
    if layout(root)[0] != afterforge: raise ValueError('registered layout mismatch')
    if record.get('protocolVersion') == '2':
        from scripts.work_model_delivery_v2 import verify_release as verify_v2
        return verify_v2(root, afterforge, record)
    return _verify(root, afterforge, record, safe(afterforge,record['packagePath']), safe(root,record['snapshotPath']))


def publish_release(root, prepared):
    root = Path(root).resolve()
    afterforge, _ = layout(root)
    with project_lock(afterforge), manifest_transaction(root):
        return _publish_release(root, prepared)


def _publish_release(root, prepared):
    root=Path(root).resolve(); afterforge,_=layout(root)
    record=prepared.get('record')
    if not isinstance(record,dict): raise ValueError('prepared release lacks record')
    if record.get('protocolVersion') != PROTOCOL_VERSION: raise ValueError('legacy publication is read-only')
    if _publication_authority(root, record['inputKey'], record['id']) != record['reviewSetId']:
        raise ValueError('delivery approval changed before publication')
    package=Path(prepared['stagingPackage']); evidence=Path(prepared['stagingSnapshot'])
    partial=root/'releases/.partial'
    for p in (package,evidence):
        if not p.is_absolute() or not p.resolve().is_relative_to(partial.resolve()) or p.is_symlink(): raise ValueError('unsafe staged release')
    target=safe(afterforge,record['packagePath'],exists=False); target_evidence=safe(root,record['snapshotPath'],exists=False)
    if target.exists() or target_evidence.exists():
        if target.exists() and target_evidence.exists():
            verify_release(root,afterforge,record)
            shutil.rmtree(package,ignore_errors=True);shutil.rmtree(evidence,ignore_errors=True)
            return record
        raise ValueError('orphaned release target prevents publication')
    # Reconstruct inherited provenance from the original source before accepting
    # even a hand-built prepared record. No request controls the media scope.
    frozen=json.loads((evidence/MANIFEST_NAME).read_text())
    bindings=collect_inherited(afterforge,evidence/record['sourcePath'],frozen)
    if inherited_identity(bindings) != record['sourceMedia']: raise ValueError('inherited sources changed before publication')
    _verify(root,afterforge,record,package,evidence)
    target.parent.mkdir(parents=True,exist_ok=True);target_evidence.parent.mkdir(parents=True,exist_ok=True)
    moved=[]
    try:
        os.rename(evidence,target_evidence);moved.append((target_evidence,evidence))
        os.rename(package,target);moved.append((target,package))
        verify_release(root,afterforge,record)
    except BaseException:
        for dest,original in reversed(moved):
            if dest.exists(): os.rename(dest,original)
        raise
    return record
