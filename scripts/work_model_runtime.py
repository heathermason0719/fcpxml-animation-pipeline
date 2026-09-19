"""Initialize and identify an exact local runtime; never install or query latest."""
import hashlib
import json
from pathlib import Path
from scripts.hyperframes_runtime import MANAGED_SCRIPTS, PACKAGE_PIN, require_exact_version,read_runtime_pin
from scripts.scaffold_hyperframes import _package_json,_hyperframes_json


RUNTIME_FILES = ('package.json', 'hyperframes.json', 'assets/vendor/gsap.min.js')
# These are the locally verified vendor distributions used by the maintained
# real-render fixtures.  A new bootstrap may only introduce one of these
# byte-identities (or an exact vendor present alongside the cached runtime).
# The runtime pin is independent from GSAP's own version.
TRUSTED_VENDOR_SHA256 = {
    'c174bfce53a729418d57a8ad8625e7247c793a22fef8e2851e3cfa3de9cd8280': 'gsap@3.14.2',
    'c3a03a345e45bc954cd48c43f11572891f5dca7a5d99348d5bc14753a728618c': 'gsap@3.15.0',
}


class RuntimeFiles(dict):
    """Internal runtime transaction bytes with non-client-controlled provenance."""

    def __init__(self, *args, vendor_provenance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.vendor_provenance = vendor_provenance


def _sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _trusted_vendor_provenance(value):
    fingerprint = _sha256_bytes(value)
    label = TRUSTED_VENDOR_SHA256.get(fingerprint)
    if label is None:
        raise ValueError('runtime bootstrap requires a verified local GSAP vendor source')
    return {'kind': 'pinned-local-vendor', 'library': label, 'sha256': fingerprint}


def local_vendor(version, supplied=None):
    cache=Path.home()/'.npm/_npx'
    found=False
    for package in cache.glob('*/node_modules/hyperframes/package.json'):
        if package.is_symlink(): continue
        if json.loads(package.read_text()).get('version') != version: continue
        found=True
        if supplied is not None:
            if supplied.is_file() and not supplied.is_symlink(): return supplied
            raise ValueError('supplied GSAP source must be a regular local file')
        modules=package.parent.parent
        candidates=[modules/'gsap/dist/gsap.min.js',package.parent/'node_modules/gsap/dist/gsap.min.js']
        for path in candidates:
            if path.is_file() and not path.is_symlink(): return path
    if found:
        raise ValueError('GSAP is not included in this cached runtime; provide a local vendorSource in .staging')
    raise ValueError('exact HyperFrames runtime is not locally cached; installation needs separate authorization')


def local_cached_cli(version, *, cache_root=None):
    """Return the exact already-expanded HyperFrames CLI, without npm I/O."""
    version = require_exact_version(version)
    roots = [Path(cache_root)] if cache_root is not None else [Path.home() / '.npm' / '_npx']
    candidates = []
    for root in roots:
        if root.is_dir() and not root.is_symlink():
            candidates.extend(root.glob('*/node_modules/hyperframes/package.json'))
    for package in sorted(candidates, key=lambda value: value.stat().st_mtime_ns, reverse=True):
        if package.is_symlink() or not package.is_file():
            continue
        try:
            valid = json.loads(package.read_text()).get('version') == version
        except json.JSONDecodeError:
            valid = False
        entry = package.parent / 'bin' / 'hyperframes.mjs'
        if valid and entry.is_file() and not entry.is_symlink():
            return ['node', str(entry)]
    return None


def runtime_files(root, manifest, version, supplied=None):
    version=require_exact_version(version)
    if (root/'package.json').exists() and read_runtime_pin(root)!=version:
        raise ValueError('runtime change requires an explicitly created new version')
    explicit_vendor = supplied is not None
    if supplied is None and (root/'assets/vendor/gsap.min.js').is_file():
        supplied=root/'assets/vendor/gsap.min.js'
    vendor=local_vendor(version,supplied)
    vendor_bytes = vendor.read_bytes()
    # A user-provided fresh bootstrap source must match a maintained local
    # distribution fingerprint.  Legacy enrollment reads an existing vendor
    # instead; it records identity without reclassifying historical bytes as a
    # new trusted installation.
    if explicit_vendor and not (root / 'package.json').exists():
        _trusted_vendor_provenance(vendor_bytes)
    package=_package_json('afterforge',manifest['identity']['versionId'],version).replace('npm exec --yes','npm exec --offline --yes')
    return RuntimeFiles({
        'package.json': package.encode(),
        'hyperframes.json': _hyperframes_json().encode(),
        'assets/vendor/gsap.min.js': vendor_bytes,
    }, vendor_provenance={'kind': 'resolved-local-vendor',
                          'sha256': _sha256_bytes(vendor_bytes)})


def _runtime_pin_from_package(data):
    try:
        package = json.loads(data.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError('runtime package.json must be valid UTF-8 JSON') from error
    scripts = package.get('scripts') if isinstance(package, dict) else None
    if not isinstance(scripts, dict):
        raise ValueError('runtime package.json scripts must be an object')
    versions = []
    for name in MANAGED_SCRIPTS:
        command = scripts.get(name)
        if not isinstance(command, str):
            raise ValueError(f'runtime package.json is missing managed script: {name}')
        matches = PACKAGE_PIN.findall(command)
        if len(matches) != 1:
            raise ValueError(f'runtime managed script {name} must contain one exact HyperFrames pin')
        versions.append(require_exact_version(matches[0]))
    if len(set(versions)) != 1:
        raise ValueError('runtime managed HyperFrames scripts must use the same exact version')
    return versions[0]


def _proposed_runtime_files(root, files):
    """Return the complete proposed controlled runtime file set.

    ``files`` accepts the mapping produced by :func:`runtime_files` or the
    ``(name, bytes, old)`` tuples used by the application transaction.
    """
    root = Path(root)
    supplied = files if isinstance(files, dict) else {name: data for name, data, _ in files}
    result = {}
    for name in RUNTIME_FILES:
        if name in supplied:
            data = supplied[name]
            if not isinstance(data, bytes):
                raise ValueError(f'runtime file {name} must be bytes')
            result[name] = data
            continue
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f'runtime identity is missing controlled file: {name}')
        result[name] = path.read_bytes()
    return result


def _existing_runtime_files(root):
    root = Path(root)
    result = {}
    for name in RUNTIME_FILES:
        path = root / name
        if path.is_symlink() or not path.is_file():
            return None
        result[name] = path.read_bytes()
    return result


def _has_existing_runtime_material(root):
    root = Path(root)
    return any((root / name).exists() for name in RUNTIME_FILES)


def _has_runtime_history(root, manifest):
    """Detect persisted execution evidence when legacy controlled files vanished."""
    if any(manifest.get(name) for name in ('artifacts', 'reviewSets', 'deliveries', 'productionRuns')):
        return True
    jobs = Path(root) / 'jobs'
    return jobs.is_dir() and any(jobs.glob('*.json'))


def runtime_transition(root, manifest, files, version=None):
    """Classify a controlled runtime transaction and produce its identity fact.

    A runtime identity records the exact three fixed infrastructure files.  It
    cannot be reset by deleting one of them: when an identity already exists,
    only its exact fingerprint is a repair.  The result is deliberately
    derived from transaction bytes and the previous manifest, never a request
    flag supplied by a client.
    """
    proposed = _proposed_runtime_files(root, files)
    pin = _runtime_pin_from_package(proposed['package.json'])
    if version is not None and require_exact_version(version) != pin:
        raise ValueError('runtime package pin does not match requested exact version')
    fingerprints = {name: _sha256_bytes(proposed[name]) for name in RUNTIME_FILES}
    previous = manifest.get('runtimeIdentity')
    if previous is not None and not isinstance(previous, dict):
        raise ValueError('runtimeIdentity must be an object')
    previous_files = previous.get('files') if previous else None
    previous_pin = previous.get('version') if previous else None
    if previous:
        if not isinstance(previous_files, dict) or not isinstance(previous_pin, str):
            raise ValueError('runtimeIdentity is incomplete')
        if previous_pin != pin:
            raise ValueError('runtime change requires an explicitly created new version')
        if previous_files == fingerprints:
            identity = dict(previous)
            # Repair deliberately keeps the initial provenance, rather than
            # letting a later request overwrite history with a new source.
            return {'kind': 'repair', 'identity': identity, 'motionAffecting': False}
        provenance = previous.get('vendorProvenance')
        if fingerprints['assets/vendor/gsap.min.js'] != previous_files.get('assets/vendor/gsap.min.js'):
            provenance = _trusted_vendor_provenance(proposed['assets/vendor/gsap.min.js'])
        identity = {'version': pin, 'files': fingerprints, 'vendorProvenance': provenance}
        return {'kind': 'change', 'identity': identity, 'motionAffecting': True}

    existing = _existing_runtime_files(root)
    if existing is not None:
        # A legacy version already has executable infrastructure.  Enrollment
        # records its reproducible byte identity; it does not introduce a new
        # executable vendor into a fresh production version.
        existing_pin = _runtime_pin_from_package(existing['package.json'])
        if existing_pin != pin:
            raise ValueError('runtime change requires an explicitly created new version')
        existing_fingerprints = {name: _sha256_bytes(existing[name]) for name in RUNTIME_FILES}
        if existing_fingerprints != fingerprints:
            # This is not enrollment: the transaction changes known executable
            # infrastructure, so normal Motion production authority must gate
            # it even when a pre-identity legacy manifest is being upgraded.
            identity = {'version': pin, 'files': fingerprints,
                        'vendorProvenance': {'kind': 'legacy-config-change',
                                             'sha256': fingerprints['assets/vendor/gsap.min.js']}}
            return {'kind': 'change', 'identity': identity, 'motionAffecting': True}
        identity = {'version': pin, 'files': fingerprints,
                    'vendorProvenance': {'kind': 'legacy-enrollment',
                                         'sha256': fingerprints['assets/vendor/gsap.min.js']}}
        return {'kind': 'enroll', 'identity': identity, 'motionAffecting': False}

    if _has_existing_runtime_material(root):
        # Without all three files there is no reproducible legacy identity to
        # enroll.  Treating this as a fresh bootstrap would permit deletion of
        # a known runtime file to erase the production boundary.
        raise ValueError('incomplete existing runtime cannot be reset as a bootstrap')

    if _has_runtime_history(root, manifest):
        raise ValueError('runtime history cannot be reset as a bootstrap')

    provenance = getattr(files, 'vendor_provenance', None)
    if not isinstance(provenance, dict) or provenance.get('sha256') != fingerprints['assets/vendor/gsap.min.js']:
        raise ValueError('runtime bootstrap requires a verified local GSAP vendor source before first Motion publication')
    identity = {'version': pin, 'files': fingerprints, 'vendorProvenance': dict(provenance)}
    return {'kind': 'bootstrap', 'identity': identity, 'motionAffecting': False}
