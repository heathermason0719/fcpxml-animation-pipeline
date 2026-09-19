"""Public API coverage for static source capability closure and identities."""
import base64
import copy
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import work_model as model
from scripts.work_model_inputs import cue_key
from scripts.work_model_store import load
from scripts.work_model_storyboard import frame_current
from tests import test_work_model_jobs as jobs
from tests.test_work_model_static_capabilities import ANIMATED, STILL
from tests.work_model_fixtures import raster


class StaticPublicationPublicApiTests(unittest.TestCase):
    cold_start = True
    setUp = jobs.JobTests.setUp
    req = jobs.JobTests.req

    def stage(self, name, relative, contents):
        path = self.root / '.staging' / name / Path(relative).name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(contents, bytes):
            path.write_bytes(contents)
        else:
            path.write_text(contents)
        return {'path': relative, 'source': str(path)}

    def composition_path(self):
        return load(self.root)['cues'][0]['renderAdapters']['hyperframes']['compositionSrc']

    def attempt_static_edit(self, name, markup, extra=(), patch=None, composition=None):
        files = [self.stage(name, composition or self.composition_path(), markup), *extra]
        return model.update(self.root, self.req(name, operation='edit', patch=patch or {}, files=files))

    def test_cold_static_capability_rejections_leave_controlled_state_unchanged(self):
        composition = self.composition_path()
        original = (self.root / composition).read_bytes()
        cases = {
            'marquee': ('<marquee>moving</marquee>', ()),
            'animated-local': ('<img src="assets/static/animated.gif">',
                               (self.stage('animated-local', 'assets/static/animated.gif', ANIMATED),)),
            'animated-data': ('<img src="data:image/gif;base64,' + base64.b64encode(ANIMATED).decode() + '">', ()),
            'unknown-capability': ('<unreviewed-widget>opaque</unreviewed-widget>', ()),
            'remote-srcset': ('<img srcset="https://example.test/a.png 1x">', ()),
            'remote-image-set': ('<style>.x{background:image-set(url("https://example.test/a.png") 1x)}</style>', ()),
            'remote-feimage': ('<svg><filter><feImage href="https://example.test/a.png"/></filter></svg>', ()),
        }
        for name, (markup, extras) in cases.items():
            with self.subTest(name=name):
                before = copy.deepcopy(load(self.root))
                with self.assertRaises(ValueError):
                    self.attempt_static_edit(name, markup, extras)
                after = load(self.root)
                self.assertEqual(after['editRevision'], before['editRevision'])
                self.assertEqual(after['decisions'], before['decisions'])
                self.assertEqual((self.root / composition).read_bytes(), original)
                self.assertFalse((self.root / 'assets/static/animated.gif').exists())

    def test_local_srcset_and_image_set_candidates_invalidate_static_and_media_identity(self):
        composition = 'compositions/cues/static-responsive.html'
        markup = '''<div><img srcset="assets/static/a.gif 1x, assets/static/b.gif 2x"></div>
<style>.panel { background-image: image-set(url("assets/static/a.gif") 1x, url("assets/static/b.gif") 2x); }</style>'''
        manifest = load(self.root)
        cue = {
            'id': 'static-responsive', 'productionMode': 'animation', 'screenText': ['静态资源'],
            'narration': '静态资源候选', 'finalAnimationDescription': '候选静态资源展示',
            'resolvedTimeline': {'start': '4s', 'duration': '2s'},
            'renderAdapters': {'hyperframes': {'compositionId': 'static-responsive',
                'compositionSrc': composition, 'layoutDependencies': []}},
        }
        files = [self.stage('responsive-layout', composition, markup),
            self.stage('responsive-layout', 'assets/static/a.gif', STILL),
            self.stage('responsive-layout', 'assets/static/b.gif', STILL),
        ]
        model.update(self.root, self.req('responsive-layout', operation='edit',
                                         patch={'cues': [*manifest['cues'], cue]}, files=files,
                                         objectRelations={'static-responsive': {
                                             'kind': 'new', 'basis': {'text': '新增静态候选资源展示',
                                                                      'reference': 'fixture:static-responsive'}}}))
        manifest = load(self.root)
        cue = next(c for c in manifest['cues'] if c['id'] == 'static-responsive')
        with patch('scripts.work_model_jobs.render_storyboard', side_effect=raster):
            board = model.preview(self.root, self.req('responsive-pre-confirm', scope='storyboard', cueIds=[cue['id']]))
        model.update(self.root, self.req('responsive-confirm', operation='decision', kind='confirm-design',
                                         storyboardIds=board['storyboardIds'],
                                         source={'channel': 'chat', 'text': '确认静态候选布局', 'reference': 'fixture:responsive-confirm'}))
        manifest = load(self.root)
        cue = next(c for c in manifest['cues'] if c['id'] == 'static-responsive')
        cue['renderAdapters']['hyperframes']['motionSrc'] = 'compositions/motion/static-responsive.js'
        model.update(self.root, self.req('responsive-motion', operation='edit', patch={'cues': manifest['cues']},
                                         files=[self.stage('responsive-motion', 'compositions/motion/static-responsive.js', '// motion host')],
                                         work={'cueIds': [cue['id']]}))
        manifest = load(self.root)
        cue = next(c for c in manifest['cues'] if c['id'] == 'static-responsive')
        before_media_key = cue_key(self.root, manifest, cue)
        with patch('scripts.work_model_jobs.render_storyboard', side_effect=raster):
            result = model.preview(self.root, self.req('responsive-storyboard', scope='storyboard', cueIds=[cue['id']]))
        artifact = next(a for a in load(self.root)['artifacts'] if a['id'] == result['artifactIds'][0])
        self.assertIn('assets/static/a.gif', artifact['files'])
        self.assertIn('assets/static/b.gif', artifact['files'])
        self.assertTrue(frame_current(self.root, load(self.root), artifact))

        self.attempt_static_edit('candidate-b-change', markup, (
            self.stage('candidate-b-change', 'assets/static/b.gif', STILL + b'changed'),
        ), composition=composition)
        current = load(self.root)
        changed_cue = next(c for c in current['cues'] if c['id'] == cue['id'])
        self.assertNotEqual(cue_key(self.root, current, changed_cue), before_media_key)
        self.assertFalse(frame_current(self.root, current, artifact))
        card = next(c for c in model.status(self.root)['storyboard']['cues'] if c['id'] == cue['id'])
        self.assertFalse(card['frames'][0]['current'])


if __name__ == '__main__':
    unittest.main()
