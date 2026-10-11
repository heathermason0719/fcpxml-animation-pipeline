"""Concept images qualify a design before canonical code or rendering exists."""
import copy
import http.client
import json
import struct
import subprocess
import tempfile
import threading
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from scripts import work_model as model
from scripts.work_model_store import load, save
from tests.work_model_fixtures import request, user, raster, activate


def png_bytes(color=(220, 130, 40)):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 32, 24, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress((b'\0' + bytes(color) * 32) * 24)) + chunk(b'IEND', b''))


class ConceptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.afterforge = Path(self.tmp.name) / 'AfterForge'
        self.root = Path(model.open_project(self.afterforge, {'requestId': 'open', 'expectedRevision': 0,
                         'title': 'Concept test', 'episodeTitle': 'Two origins'})['root'])
        self.cues = [{'id': cid, 'productionMode': 'animation', 'narrationAnchor': '人们通过画面理解关系',
                      'screenText': [{'text': '观察与被观察'}], 'finalAnimationDescription': '先出现人物，再连起视线',
                      'renderAdapters': {'hyperframes': {'compositionId': cid,
                          'compositionSrc': f'compositions/cues/{cid}.html'}}} for cid in ('poster', 'map')]
        model.update(self.root, request(self.root, 'plan', operation='edit', patch={'cues': self.cues}))

    def register(self, cue='poster', name='one', **extra):
        source = self.root / '.staging' / (name + '.png')
        source.parent.mkdir(exist_ok=True)
        source.write_bytes(png_bytes((100, 140, len(name) * 10)))
        return model.update(self.root, request(self.root, 'concept-' + name, operation='concept', action='register',
                            cueId=cue, imageSource=str(source), origin={'kind': 'user-imported', 'reference': 'fixture:external'},
                            idea='人物与视线形成关系', motion='先人物、后视线，收尾停住', **extra))['record']

    def confirm(self, *records, **extra):
        return model.update(self.root, request(self.root, 'confirm-' + str(load(self.root)['editRevision']),
                            operation='decision', kind='confirm-concept', conceptIds=[r['id'] for r in records],
                            source=user('就用这几张，按这个方向做'), **extra))

    def publish(self, name='code'):
        path = self.root / '.staging' / 'layout.html'
        path.write_text('<div data-composition-id="poster">观察与被观察</div>')
        return model.update(self.root, request(self.root, name, operation='edit',
                            files=[{'path': 'compositions/cues/poster.html', 'source': str(path)}]))

    def test_external_candidate_is_owned_persistent_media_but_does_not_qualify_code(self):
        record = self.register()
        self.assertEqual((self.root / record['path']).read_bytes(), png_bytes((100, 140, 30)))
        (self.root / '.staging/one.png').unlink()
        state = model.status(self.root)
        self.assertEqual(state['conceptDesign']['cues'][0]['recommendedId'], record['id'])
        self.assertFalse(state['conceptDesign']['cues'][0]['firstConfirmed'])
        self.assertIn(record['path'], [c['path'] for c in model.media_status(self.root)['concepts']])
        with self.assertRaisesRegex(ValueError, 'concept|概念'):
            self.publish()
        with self.assertRaisesRegex(ValueError, 'concept|概念'):
            model.preview(self.root, request(self.root, 'early-preview', scope='storyboard', cueIds=['poster']))
        self.assertFalse((self.root / 'compositions/cues/poster.html').exists())
        self.assertEqual(load(self.root)['artifacts'], [])

    def test_unconfirmed_recommendations_are_free_and_feedback_stays_on_its_image(self):
        first = self.register(name='first')
        feedback = model.update(self.root, request(self.root, 'opinion', operation='feedback', body='旧稿太挤',
                                source=user('旧稿太挤'), target={'versionId': load(self.root)['identity']['versionId'],
                                'conceptId': first['id'], 'cueIds': ['poster']}))['record']
        second = self.register(name='second')
        self.confirm(second)
        state = model.status(self.root)
        self.assertEqual(state['conceptDesign']['cues'][0]['confirmedId'], second['id'])
        self.assertEqual(state['feedback'][0]['target']['conceptId'], first['id'])
        self.assertEqual(state['feedback'][0]['status'], 'pending')
        self.assertEqual(len(load(self.root)['concepts']), 2)
        self.publish()

    def test_mixed_origin_batch_confirmation_is_atomic_and_replaces_first_storyboard_confirmation(self):
        first = self.register(name='imported')
        source = self.root / '.staging/generated.png'
        source.write_bytes(png_bytes())
        second = model.update(self.root, request(self.root, 'generated', operation='concept', action='register', cueId='map',
                              imageSource=str(source), origin={'kind': 'codex-generated', 'reference': 'fixture:image-tool'},
                              idea='观察关系图', motion='线条依次出现'))['record']
        before = (self.root / 'animation-manifest.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'concept|概念'):
            self.confirm(first, {'id': 'missing'})
        self.assertEqual((self.root / 'animation-manifest.json').read_bytes(), before)
        self.confirm(first, second)
        self.assertTrue(all(c['firstConfirmed'] for c in model.status(self.root)['conceptDesign']['cues']))
        self.assertFalse(any(c['canConfirm'] for c in model.status(self.root)['storyboard']['cues']))
        self.assertEqual([d['kind'] for d in load(self.root)['decisions']], ['confirm-concept'])
        self.publish()

    def test_confirmed_design_changes_only_when_user_opens_a_concept_revision(self):
        first = self.register()
        self.confirm(first)
        self.publish()
        model.update(self.root, request(self.root, 'ordinary-feedback', operation='edit',
                     patch={'brief': {'summary': '普通实现调整继续沿用已确认方向', 'segments': []}}))
        self.assertTrue(model.status(self.root)['conceptDesign']['cues'][0]['firstConfirmed'])
        with self.assertRaisesRegex(ValueError, 'confirmed|确认'):
            self.register(name='unrequested-replacement')
        with self.assertRaises(ValueError):
            model.update(self.root, request(self.root, 'missing-user', operation='concept', action='reopen', cueIds=['poster']))
        model.update(self.root, request(self.root, 'reopen', operation='concept', action='reopen', cueIds=['poster'],
                     source=user('我想换掉概念图的构图，重新出稿')))
        with self.assertRaisesRegex(ValueError, 'concept|概念'):
            model.preview(self.root, request(self.root, 'pending-preview', scope='storyboard', cueIds=['poster']))
        second = self.register(name='revision')
        self.confirm(second)
        self.assertEqual(model.status(self.root)['conceptDesign']['cues'][0]['confirmedId'], second['id'])
        self.assertEqual(len([d for d in load(self.root)['decisions'] if d['kind'] == 'confirm-concept']), 2)

    def test_explicit_import_and_adopt_confirms_in_one_transaction_and_rejects_false_rasters(self):
        record = self.register(adopt=True, source=user('采用这张外部图片作为 poster 的概念图'))
        self.assertEqual(model.status(self.root)['conceptDesign']['cues'][0]['confirmedId'], record['id'])
        source = self.root / '.staging/invalid.png'
        source.write_bytes(b'<svg><script>alert(1)</script></svg>')
        before = (self.root / 'animation-manifest.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'image|raster|图片'):
            model.update(self.root, request(self.root, 'invalid', operation='concept', action='register', cueId='map',
                         imageSource=str(source), origin={'kind': 'user-imported', 'reference': 'fixture:bad'},
                         idea='bad', motion='bad'))
        self.assertEqual((self.root / 'animation-manifest.json').read_bytes(), before)

    def test_review_confirmation_and_image_access_survive_server_restart_and_reopen(self):
        from scripts.work_model_review import serve
        records = [self.register(name='external'), self.register(cue='map', name='generated')]
        version = load(self.root)['identity']['versionId']
        def call(server, method, path, body=None):
            client = http.client.HTTPConnection('127.0.0.1', server.server_port)
            client.request(method, path, json.dumps(body) if body is not None else None,
                           {'content-type': 'application/json'} if body is not None else {})
            response = client.getresponse()
            value = response.read()
            client.close()
            return response.status, value
        for iteration in range(2):
            server = serve(self.afterforge, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                if iteration == 0:
                    status, value = call(server, 'POST', '/api/action', {'version': version, 'action': 'update',
                        'request': request(self.root, 'web-confirm', operation='decision', kind='confirm-concept',
                        conceptIds=[r['id'] for r in records], source={'channel': 'review',
                            'text': '确认所选两张概念图', 'reference': 'fixture:review'})})
                    self.assertEqual(status, 200, value)
                else:
                    reopened = model.open_project(self.afterforge)
                    self.assertEqual(reopened['projectId'], load(self.root)['identity']['projectId'])
                status, value = call(server, 'GET', '/api/state?' + urlencode({'version': version}))
                self.assertEqual(status, 200)
                self.assertTrue(all(c['firstConfirmed'] for c in json.loads(value)['conceptDesign']['cues']))
                for record in records:
                    status, image = call(server, 'GET', '/media?' + urlencode({'version': version, 'path': record['path']}))
                    self.assertEqual(status, 200)
                    self.assertEqual(image, (self.root / record['path']).read_bytes())
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_pending_image_feedback_can_be_explicitly_resolved_with_confirmation(self):
        record = self.register()
        feedback = model.update(self.root, request(self.root, 'concept-feedback', operation='feedback', body='这里要再检查',
                     source=user('这里要再检查'), target={'versionId': load(self.root)['identity']['versionId'],
                     'conceptId': record['id']}))['record']
        with self.assertRaisesRegex(ValueError, 'unresolved-feedback'):
            self.confirm(record)
        self.confirm(record, feedbackResolutions=[{'feedbackId': feedback['id'], 'action': 'withdraw'}])
        self.assertEqual(load(self.root)['feedback'][0]['applicability']['kind'], 'not-applicable')

    def test_missing_confirmed_image_is_reported_without_revoking_confirmation(self):
        record = self.register()
        self.confirm(record)
        image = self.root / record['path']
        original = image.read_bytes()
        manifest = (self.root / 'animation-manifest.json').read_bytes()
        harness = Path(__file__).with_name('review_v3_client_harness.cjs')
        for contents in (None, png_bytes()):
            with self.subTest(image='missing' if contents is None else 'changed'):
                if contents is None:
                    image.unlink()
                else:
                    image.write_bytes(contents)
                state = model.status(self.root)
                cue = state['conceptDesign']['cues'][0]
                self.assertTrue(cue['firstConfirmed'])
                self.assertFalse(cue['canConfirm'])
                self.assertFalse(cue['revisionPending'])
                self.assertIn('concept-image-unavailable', [p['code'] for p in cue['confirmationProblems']])
                with self.assertRaisesRegex(ValueError, 'confirmed concept image unavailable'):
                    model.preview(self.root, request(self.root, 'unavailable-preview', scope='storyboard', cueIds=['poster']))
                with tempfile.NamedTemporaryFile('w', suffix='.json') as fixture:
                    json.dump(state, fixture)
                    fixture.flush()
                    subprocess.run(['node', str(harness), 'concept-image-unavailable', fixture.name],
                                   check=True, cwd=Path(__file__).parents[1])
                self.assertEqual((self.root / 'animation-manifest.json').read_bytes(), manifest)
        image.write_bytes(original)
        state = model.status(self.root)
        self.assertTrue(state['conceptDesign']['cues'][0]['firstConfirmed'])
        self.assertEqual(state['conceptDesign']['cues'][0]['confirmationProblems'], [])
        with tempfile.NamedTemporaryFile('w', suffix='.json') as fixture:
            json.dump(state, fixture)
            fixture.flush()
            subprocess.run(['node', str(harness), 'concept-image-restored', fixture.name],
                           check=True, cwd=Path(__file__).parents[1])
        self.assertEqual((self.root / 'animation-manifest.json').read_bytes(), manifest)
        self.publish('restored-image-code')

    def test_concept_confirmation_uses_its_notes_without_a_final_animation_description(self):
        cues = copy.deepcopy(load(self.root)['cues'])
        cues[0].pop('finalAnimationDescription')
        cues[1]['finalAnimationDescription'] = '   '
        model.update(self.root, request(self.root, 'concept-stage-copy', operation='edit', patch={'cues': cues}))
        records = [self.register(name='poster-direction'), self.register(cue='map', name='map-direction')]
        self.confirm(*records)
        state = model.status(self.root)
        self.assertTrue(all(c['firstConfirmed'] for c in state['conceptDesign']['cues']))
        self.assertEqual([c['idea'] for c in state['concepts']], ['人物与视线形成关系'] * 2)
        self.assertEqual([c['motion'] for c in state['concepts']], ['先人物、后视线，收尾停住'] * 2)
        self.assertNotIn('finalAnimationDescription', load(self.root)['cues'][0])
        self.assertEqual(load(self.root)['cues'][1]['finalAnimationDescription'], '   ')


class ConceptJobTests(unittest.TestCase):
    """Exercise the existing shared job path with only expensive renderers doubled."""
    from tests.test_work_model_jobs import JobTests as _JobFixture
    cold_start = True
    work_model_version = '2.2.0'
    setUp = _JobFixture.setUp
    req = _JobFixture.req

    def test_preview_cache_and_resume_revalidate_concept_round_without_extra_entry_points(self):
        activate(self.root)
        cue = load(self.root)['cues'][0]
        result = model.preview(self.root, self.req('local', scope='local', cueIds=[cue['id']], taskId='named-technical-work'))
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(load(self.root)['productionRuns'], [])
        count = len(self.calls)
        # Same pixels and concept basis can reuse existing Cue media.
        model.preview(self.root, self.req('again', scope='local', cueIds=[cue['id']]))
        self.assertEqual(len(self.calls), count)
        with patch('scripts.work_model_jobs.composite_preview', side_effect=ValueError('interrupted')):
            with self.assertRaisesRegex(ValueError, 'interrupted'):
                model.preview(self.root, self.req('interrupted', scope='local', cueIds=[cue['id']], range={'start':'0s','duration':'3s'}))
        job = next(t for t in model.status(self.root)['tasks'] if t['status'] == 'failed')
        model.update(self.root, self.req('revise', operation='concept', action='reopen', cueIds=[cue['id']],
                                       source=user('换一张概念图重新确认')))
        with self.assertRaisesRegex(ValueError, 'concept|概念'):
            model.resume(self.root, self.req('resume-pending', jobId=job['id']))
        with self.assertRaisesRegex(ValueError, 'concept|概念'):
            model.preview(self.root, self.req('cached-pending', scope='local', cueIds=[cue['id']]))
        self.assertEqual(len(self.calls), count)

    def test_interrupted_preview_resumes_with_the_same_persisted_concept(self):
        activate(self.root)
        cue = load(self.root)['cues'][0]
        with patch('scripts.work_model_jobs.composite_preview', side_effect=ValueError('interrupted')):
            with self.assertRaisesRegex(ValueError, 'interrupted'):
                model.preview(self.root, self.req('interrupted-valid', scope='local', cueIds=[cue['id']]))
        job = next(t for t in model.status(self.root)['tasks'] if t['status'] == 'failed')
        count = len(self.calls)
        result = model.resume(self.root, self.req('resume-valid', jobId=job['id']))
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(len(self.calls), count)
        self.assertTrue(model.status(self.root)['conceptDesign']['cues'][0]['firstConfirmed'])

    def test_inflight_concept_revision_prevents_old_preview_publication(self):
        activate(self.root)
        cue = load(self.root)['cues'][0]
        from scripts import work_model_jobs as jobs
        original = jobs.composite_preview
        before = copy.deepcopy(load(self.root)['artifacts'])
        def revise(*args, **kwargs):
            original(*args, **kwargs)
            model.update(self.root, self.req('during', operation='concept', action='reopen', cueIds=[cue['id']],
                                           source=user('这次需要重新构思概念图')))
        with patch('scripts.work_model_jobs.composite_preview', side_effect=revise):
            with self.assertRaisesRegex(ValueError, 'concept|概念'):
                model.preview(self.root, self.req('inflight', scope='local', cueIds=[cue['id']]))
        self.assertEqual(load(self.root)['artifacts'], before)
