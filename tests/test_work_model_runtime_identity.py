"""Runtime identity distinguishes bootstrap, repair, enrollment, and change."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.scaffold_hyperframes import _hyperframes_json, _package_json
from scripts.work_model_runtime import (RuntimeFiles, TRUSTED_VENDOR_SHA256,
                                        runtime_files, runtime_transition)
from scripts import work_model as model
from scripts.work_model_store import load
from tests.work_model_fixtures import raster, user


class RuntimeIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.manifest = {'identity': {'versionId': 'version-test'}, 'cues': [], 'decisions': []}
        self.vendor = b'locally verified GSAP test distribution'
        self.vendor_hash = hashlib.sha256(self.vendor).hexdigest()

    def files(self, version='0.8.33', *, marked=True, vendor=None):
        vendor = self.vendor if vendor is None else vendor
        contents = {
            'package.json': _package_json('afterforge', 'version-test', version).replace('npm exec --yes', 'npm exec --offline --yes').encode(),
            'hyperframes.json': _hyperframes_json().encode(),
            'assets/vendor/gsap.min.js': vendor,
        }
        provenance = {'kind': 'pinned-local-vendor', 'library': 'test-gsap',
                      'sha256': hashlib.sha256(vendor).hexdigest()}
        return RuntimeFiles(contents, vendor_provenance=provenance) if marked else contents

    def install(self, files):
        for name, value in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value)

    def test_fresh_verified_bootstrap_is_not_motion_affecting_or_an_authority_fact(self):
        with patch.dict(TRUSTED_VENDOR_SHA256, {self.vendor_hash: 'test-gsap'}, clear=True):
            transition = runtime_transition(self.root, self.manifest, self.files(), '0.8.33')
        self.assertEqual(transition['kind'], 'bootstrap')
        self.assertFalse(transition['motionAffecting'])
        self.assertEqual(transition['identity']['version'], '0.8.33')
        self.assertEqual(set(transition['identity']['files']), {
            'package.json', 'hyperframes.json', 'assets/vendor/gsap.min.js'})
        self.assertEqual(self.manifest['decisions'], [])

    def test_fresh_unmarked_transaction_cannot_claim_bootstrap_trust(self):
        with self.assertRaisesRegex(ValueError, 'verified local GSAP'):
            runtime_transition(self.root, self.manifest, self.files(marked=False), '0.8.33')

    def test_fresh_explicit_vendor_source_is_verified_before_bootstrap(self):
        source = self.root / 'candidate-gsap.js'
        source.write_bytes(b'not GSAP')
        with patch('scripts.work_model_runtime.local_vendor', return_value=source):
            with self.assertRaisesRegex(ValueError, 'verified local GSAP'):
                runtime_files(self.root, self.manifest, '0.8.33', source)

    def test_known_identity_repairs_missing_files_without_requiring_motion_authority(self):
        files = self.files()
        self.install(files)
        initial = runtime_transition(self.root, self.manifest, files, '0.8.33')
        self.manifest['runtimeIdentity'] = initial['identity']
        (self.root / 'assets/vendor/gsap.min.js').unlink()
        repair = runtime_transition(self.root, self.manifest, files, '0.8.33')
        self.assertEqual(repair['kind'], 'repair')
        self.assertFalse(repair['motionAffecting'])
        self.assertEqual(repair['identity'], initial['identity'])

    def test_known_vendor_change_is_motion_affecting_and_pin_change_requires_new_version(self):
        files = self.files()
        self.install(files)
        self.manifest['runtimeIdentity'] = runtime_transition(self.root, self.manifest, files, '0.8.33')['identity']
        replacement = b'another locally verified GSAP distribution'
        replacement_hash = hashlib.sha256(replacement).hexdigest()
        with patch.dict(TRUSTED_VENDOR_SHA256, {self.vendor_hash: 'test-gsap', replacement_hash: 'test-gsap-next'}, clear=True):
            changed = runtime_transition(self.root, self.manifest, self.files(vendor=replacement), '0.8.33')
        self.assertEqual(changed['kind'], 'change')
        self.assertTrue(changed['motionAffecting'])
        with self.assertRaisesRegex(ValueError, 'new version'):
            runtime_transition(self.root, self.manifest, self.files('0.8.34'), '0.8.34')

    def test_legacy_runtime_enrolls_its_existing_fingerprint_without_bootstrap_vendor_proof(self):
        files = self.files(marked=False)
        self.install(files)
        enrolled = runtime_transition(self.root, self.manifest, files, '0.8.33')
        self.assertEqual(enrolled['kind'], 'enroll')
        self.assertFalse(enrolled['motionAffecting'])
        self.assertEqual(enrolled['identity']['vendorProvenance']['kind'], 'legacy-enrollment')

    def test_legacy_runtime_transaction_that_changes_vendor_is_not_enrollment(self):
        files = self.files(marked=False)
        self.install(files)
        changed = runtime_transition(self.root, self.manifest,
                                     self.files(marked=False, vendor=b'changed vendor'), '0.8.33')
        self.assertEqual(changed['kind'], 'change')
        self.assertTrue(changed['motionAffecting'])

    def test_partial_legacy_runtime_cannot_reset_its_history_as_fresh_bootstrap(self):
        path = self.root / 'assets/vendor/gsap.min.js'
        path.parent.mkdir(parents=True)
        path.write_bytes(b'old vendor')
        with self.assertRaisesRegex(ValueError, 'incomplete existing runtime'):
            runtime_transition(self.root, self.manifest, self.files(), '0.8.33')

    def test_deleted_legacy_runtime_with_render_history_cannot_become_a_bootstrap(self):
        self.manifest['artifacts'] = [{'id': 'artifact-existing-runtime'}]
        with self.assertRaisesRegex(ValueError, 'runtime history'):
            runtime_transition(self.root, self.manifest, self.files(), '0.8.33')


class RuntimeIdentityPublicApiTests(unittest.TestCase):
    """The application boundary must preserve classifier intent and rollback."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.vendor = b'locally verified GSAP test distribution'
        opened = model.open_project(self.root / 'AfterForge', {
            'requestId': 'open', 'expectedRevision': 0, 'episodeTitle': '静态启动',
        })
        self.root = Path(opened['root'])
        self.manifest = load(self.root)
        composition = self.root / '.staging' / 'layout.html'
        composition.parent.mkdir(parents=True, exist_ok=True)
        composition.write_text('<div data-composition-id="title">静态标题</div>')
        cue = {
            'id': 'title', 'productionMode': 'animation', 'screenText': ['静态标题'], 'narration': '标题出现',
            'finalAnimationDescription': '标题保持在画面中央',
            'renderAdapters': {'hyperframes': {
                'compositionId': 'title', 'compositionSrc': 'compositions/title.html',
                'layoutDependencies': [],
            }},
        }
        model.update(self.root, self.request('layout', operation='edit', patch={'cues': [cue]},
                                             files=[{'path': 'compositions/title.html', 'source': str(composition)}]))

    @property
    def root(self):
        return self._root

    @root.setter
    def root(self, value):
        self._root = Path(value)

    def files(self, version='0.8.33', *, marked=True, vendor=None):
        return RuntimeIdentityTests.files(self, version, marked=marked, vendor=vendor)

    def request(self, name, **values):
        return {'requestId': name, 'expectedRevision': load(self.root)['editRevision'], **values}

    def runtime_update(self, name, files, **extra):
        with patch.dict(TRUSTED_VENDOR_SHA256,
                        {hashlib.sha256(data).hexdigest(): 'test-gsap'
                         for path, data in files.items() if path == 'assets/vendor/gsap.min.js'}, clear=True):
            with patch('scripts.work_model_runtime.runtime_files', return_value=files):
                return model.update(self.root, self.request(name, operation='runtime', version='0.8.33', **extra))

    def staged_vendor(self, name, contents):
        path = self.root / '.staging' / name / 'gsap.min.js'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        return {'path': 'assets/vendor/gsap.min.js', 'source': str(path)}

    def confirm_static_design(self):
        with patch('scripts.work_model_jobs.render_storyboard', side_effect=raster):
            boards = model.preview(self.root, self.request('storyboard-for-confirm', scope='storyboard'))
        model.update(self.root, self.request('confirm', operation='decision', kind='confirm-design',
                                             storyboardIds=boards['storyboardIds'], source=user('确认静态标题设计')))

    def test_public_bootstrap_static_storyboard_and_exact_repair_need_no_decisions(self):
        files = self.files()
        self.runtime_update('bootstrap', files)
        first = load(self.root)
        self.assertEqual(first['decisions'], [])
        self.assertEqual(first['runtimeIdentity']['version'], '0.8.33')

        with patch('scripts.work_model_jobs.render_storyboard', side_effect=raster):
            boards = model.preview(self.root, self.request('storyboard', scope='storyboard'))
        self.assertTrue(boards['storyboardIds'])
        self.assertEqual(load(self.root)['decisions'], [])

        self.runtime_update('repeat', files)
        vendor = self.root / 'assets/vendor/gsap.min.js'
        vendor.unlink()
        self.runtime_update('repair', files)
        repaired = load(self.root)
        self.assertEqual(vendor.read_bytes(), files['assets/vendor/gsap.min.js'])
        self.assertEqual(repaired['runtimeIdentity'], first['runtimeIdentity'])
        self.assertEqual(repaired['decisions'], [])

    def test_public_cold_vendor_change_is_denied_and_rolls_back(self):
        files = self.files()
        self.runtime_update('bootstrap', files)
        before = load(self.root)
        vendor = self.root / 'assets/vendor/gsap.min.js'
        prior_bytes = vendor.read_bytes()
        changed = self.files(vendor=b'new verified vendor configuration')
        with self.assertRaisesRegex(ValueError, 'first|Motion|motion'):
            self.runtime_update('changed', changed)
        after = load(self.root)
        self.assertEqual(vendor.read_bytes(), prior_bytes)
        self.assertEqual(after['runtimeIdentity'], before['runtimeIdentity'])
        self.assertEqual(after['editRevision'], before['editRevision'])
        self.assertEqual(after['decisions'], [])

    def test_ordinary_edit_cannot_replace_controlled_vendor_when_cold(self):
        files = self.files()
        self.runtime_update('bootstrap', files)
        before = load(self.root)
        vendor = self.root / 'assets/vendor/gsap.min.js'
        previous = vendor.read_bytes()
        with self.assertRaisesRegex(ValueError, 'controlled runtime files require operation=runtime'):
            model.update(self.root, self.request('ordinary-cold', operation='edit', patch={},
                                                  files=[self.staged_vendor('ordinary-cold', b'ordinary replacement')]))
        after = load(self.root)
        self.assertEqual(vendor.read_bytes(), previous)
        self.assertEqual(after['runtimeIdentity'], before['runtimeIdentity'])
        self.assertEqual(after['editRevision'], before['editRevision'])

    def test_path_aliases_cannot_skip_controlled_vendor_reservation(self):
        self.runtime_update('bootstrap', self.files())
        before = load(self.root)
        for index, name in enumerate(['assets//vendor/gsap.min.js', 'assets/vendor/./gsap.min.js']):
            staged = self.staged_vendor('alias-' + str(index), b'cannot replace')
            staged['path'] = name
            with self.assertRaisesRegex(ValueError, 'controlled runtime'):
                model.update(self.root, self.request('alias-' + str(index), operation='edit', files=[staged]))
        self.assertEqual(load(self.root), before)

    def test_ordinary_edit_cannot_replace_controlled_vendor_after_confirmation(self):
        files = self.files()
        self.runtime_update('bootstrap', files)
        self.confirm_static_design()
        before = load(self.root)
        vendor = self.root / 'assets/vendor/gsap.min.js'
        previous = vendor.read_bytes()
        with self.assertRaisesRegex(ValueError, 'controlled runtime files require operation=runtime'):
            model.update(self.root, self.request('ordinary-active', operation='edit', patch={},
                                                  files=[self.staged_vendor('ordinary-active', b'ordinary replacement')],
                                                  work={'cueIds': ['title']}))
        after = load(self.root)
        self.assertEqual(vendor.read_bytes(), previous)
        self.assertEqual(after['runtimeIdentity'], before['runtimeIdentity'])
        self.assertEqual(after['editRevision'], before['editRevision'])

    def test_active_declared_scope_runtime_change_updates_identity(self):
        files = self.files()
        self.runtime_update('bootstrap', files)
        self.confirm_static_design()
        before = load(self.root)
        changed = self.files(vendor=b'active verified vendor configuration')
        self.runtime_update('active-runtime-change', changed, work={'cueIds': ['title']})
        after = load(self.root)
        self.assertEqual((self.root / 'assets/vendor/gsap.min.js').read_bytes(), changed['assets/vendor/gsap.min.js'])
        self.assertNotEqual(after['runtimeIdentity'], before['runtimeIdentity'])
        self.assertEqual(after['runtimeIdentity']['files']['assets/vendor/gsap.min.js'],
                         hashlib.sha256(changed['assets/vendor/gsap.min.js']).hexdigest())
        self.assertEqual([d['kind'] for d in after['decisions']], ['confirm-design'])


if __name__ == '__main__':
    unittest.main()
