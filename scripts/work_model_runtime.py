"""Initialize an exact locally available runtime; never install or query latest."""
import json
from pathlib import Path
from scripts.hyperframes_runtime import require_exact_version,read_runtime_pin
from scripts.scaffold_hyperframes import _package_json,_hyperframes_json


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


def runtime_files(root, manifest, version, supplied=None):
    version=require_exact_version(version)
    if (root/'package.json').exists() and read_runtime_pin(root)!=version:
        raise ValueError('runtime change requires an explicitly created new version')
    if supplied is None and (root/'assets/vendor/gsap.min.js').is_file():
        supplied=root/'assets/vendor/gsap.min.js'
    vendor=local_vendor(version,supplied)
    package=_package_json('afterforge',manifest['identity']['versionId'],version).replace('npm exec --yes','npm exec --offline --yes')
    return {'package.json':package.encode(),'hyperframes.json':_hyperframes_json().encode(),
            'assets/vendor/gsap.min.js':vendor.read_bytes()}
