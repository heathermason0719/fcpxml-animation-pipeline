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
    def test_existing_unrecommended_images_do_not_prompt_regeneration(self):
        candidate = self.register(recommend=False)
        card = model.status(self.root)['conceptDesign']['cues'][0]
        self.assertIn(candidate['id'], card['conceptIds'])
        self.assertIsNone(card['recommendedId'])
        self.assertFalse(card['canConfirm'])
        self.assertIn('尚未指定推荐', card['confirmationProblems'][0]['message'])
        self.assertNotIn('请先生成', card['confirmationProblems'][0]['message'])

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

    def test_select_reopens_confirmed_direction_atomically_without_confirming(self):
        first = self.register(name='first')
        second = self.register(name='second', recommend=False)
        self.confirm(first)
        old = copy.deepcopy(load(self.root))
        req = request(self.root, 'select-second', operation='concept', action='select',
                      conceptId=second['id'], source=user('换成第二张，稍后重新确认'))
        selected = model.update(self.root, req)['record']
        after = load(self.root)
        self.assertEqual(after['decisions'], old['decisions'])
        self.assertEqual(after['concepts'][:2], old['concepts'])
        self.assertEqual(selected['copiedFromConceptId'], second['id'])
        self.assertEqual(selected['round'], 2)
        self.assertEqual(selected['sha256'], second['sha256'])
        self.assertEqual((self.root / selected['path']).read_bytes(), (self.root / second['path']).read_bytes())
        self.assertFalse(model.status(self.root)['conceptDesign']['cues'][0]['firstConfirmed'])
        self.assertEqual(model.update(self.root, req)['record'], selected)
        self.confirm(selected)

    def test_select_same_confirmed_image_does_not_reopen_and_failed_copy_does_not_mutate(self):
        first = self.register(name='first')
        second = self.register(name='second', recommend=False)
        self.confirm(first)
        model.update(self.root, request(self.root, 'same', operation='concept', action='select',
                     conceptId=first['id'], source=user('保留当前图')))
        self.assertEqual(load(self.root)['creativeObjects'][0]['concept']['round'], 1)
        before = (self.root / 'animation-manifest.json').read_bytes()
        (self.root / second['path']).write_bytes(b'broken')
        with self.assertRaisesRegex(ValueError, 'image|图片'):
            model.update(self.root, request(self.root, 'broken-select', operation='concept', action='select',
                         conceptId=second['id'], source=user('改选第二张')))
        self.assertEqual((self.root / 'animation-manifest.json').read_bytes(), before)

    def test_copied_candidate_keeps_original_feedback_without_blocking_other_candidates(self):
        first = self.register(name='first')
        second = self.register(name='second', recommend=False)
        self.confirm(first)
        feedback = model.update(self.root, request(self.root, 'candidate-opinion', operation='feedback', body='第二张太挤',
            source=user('第二张太挤'), target={'versionId': load(self.root)['identity']['versionId'],
                                            'conceptId': second['id']}))['record']
        from scripts.work_model_feedback_targets import blocking_feedback
        from scripts.work_model_concepts import concept_target
        self.assertEqual(blocking_feedback(load(self.root), concept_target([first])), [])
        selected = model.update(self.root, request(self.root, 'reuse-candidate', operation='concept', action='select',
            conceptId=second['id'], source=user('采用第二张，保留修改意见')))['record']
        self.assertEqual([f['id'] for f in blocking_feedback(load(self.root), concept_target([selected]))], [feedback['id']])
        with self.assertRaisesRegex(ValueError, 'unresolved-feedback'):
            self.confirm(selected)
        model.update(self.root, request(self.root, 'handled-opinion', operation='feedback-status',
            feedbackId=feedback['id'], status='addressed', resolution='已调整并复核原候选意见'))
        self.confirm(selected)
        model.update(self.root, request(self.root, 'reopened-opinion', operation='feedback-status',
            feedbackId=feedback['id'], status='pending'))
        current = load(self.root)
        self.assertEqual([f['id'] for f in blocking_feedback(current, {
            'kind': 'scene', 'objectIds': [selected['objectId']], 'cueIds': ['poster']})], [feedback['id']])

    def test_select_original_reuses_current_copy_and_preserves_its_pending_feedback(self):
        first = self.register(name='first')
        second = self.register(name='second', recommend=False)
        self.confirm(first)
        selected = model.update(self.root, request(self.root, 'select-copy', operation='concept', action='select',
            conceptId=second['id'], source=user('选择历史的第二张')))['record']
        opinion = model.update(self.root, request(self.root, 'copy-opinion', operation='feedback', body='文字太挤，需要改',
            source=user(), target={'versionId': load(self.root)['identity']['versionId'],
                                   'conceptId': selected['id']}))['record']
        count = len(load(self.root)['concepts'])
        again = model.update(self.root, request(self.root, 'select-original-again', operation='concept', action='select',
            conceptId=second['id'], source=user('仍选历史中的这张原图')))['record']
        self.assertEqual(again['id'], selected['id'], 'select must reuse the verified current-round copy')
        self.assertEqual(len(load(self.root)['concepts']), count)
        with self.assertRaisesRegex(ValueError, 'unresolved-feedback'):
            self.confirm(again)
        self.assertEqual(next(f['status'] for f in load(self.root)['feedback'] if f['id'] == opinion['id']), 'pending')
        model.update(self.root, request(self.root, 'handled-copy-opinion', operation='feedback-status',
            feedbackId=opinion['id'], status='addressed', resolution='已检查并处理该图意见'))
        self.confirm(selected)
        retained = model.update(self.root, request(self.root, 'retain-confirmed-original', operation='concept', action='select',
            conceptId=second['id'], source=user('保留这一张已确认的原图')))['record']
        self.assertEqual(retained['id'], selected['id'])
        self.assertEqual(len(load(self.root)['concepts']), count)
        self.assertTrue(model.status(self.root)['conceptDesign']['cues'][0]['firstConfirmed'])

    def test_existing_same_lineage_siblings_share_feedback_but_unrelated_equal_bytes_do_not(self):
        first = self.register(name='first')
        second = self.register(name='second', recommend=False)
        self.confirm(first)
        sibling = model.update(self.root, request(self.root, 'copy-one', operation='concept', action='select',
            conceptId=second['id'], source=user('选择第二张')))['record']
        opinion = model.update(self.root, request(self.root, 'sibling-opinion', operation='feedback', body='同图旧意见',
            source=user(), target={'versionId': load(self.root)['identity']['versionId'],
                                   'conceptId': sibling['id']}))['record']
        manifest = load(self.root)
        # A pre-fix writer could append two siblings in one round. Preserve that
        # history rather than requiring a migration to restore its opinions.
        other = copy.deepcopy(sibling)
        other['id'] = 'historical-sibling'
        manifest['concepts'].append(other)
        from scripts.work_model_feedback_targets import blocking_feedback
        from scripts.work_model_concepts import concept_target
        self.assertEqual([f['id'] for f in blocking_feedback(manifest, concept_target([other]))], [opinion['id']])
        # Equal bytes alone are not proof of reuse: an independently registered
        # candidate and an image belonging to another object remain unrelated.
        independent = copy.deepcopy(other)
        independent['id'] = 'independent-equal-bytes'
        independent.pop('copiedFromConceptId')
        manifest['concepts'].append(independent)
        self.assertEqual(blocking_feedback(manifest, concept_target([independent])), [])
        other['objectId'] = manifest['cues'][1]['objectId']
        self.assertEqual(blocking_feedback(manifest, concept_target([other])), [])
        # Canonical Storyboard/approval targets use the same equivalence after
        # a sibling becomes the confirmed record, including descendant opinions.
        other['objectId'] = sibling['objectId']
        obj = next(o for o in manifest['creativeObjects'] if o['id'] == other['objectId'])
        obj['concept'].update(confirmedId=other['id'], confirmationId='sibling-confirmation')
        manifest['decisions'].append({'id':'sibling-confirmation', 'kind':'confirm-concept',
            'objectIds':[other['objectId']], 'conceptIds':[other['id']]})
        self.assertEqual([f['id'] for f in blocking_feedback(manifest, {
            'kind':'scene', 'objectIds':[other['objectId']]})], [opinion['id']])

    def test_unconfirmed_select_and_historical_round_reuse_do_not_rewrite_old_records(self):
        first = self.register(name='first')
        second = self.register(name='second')
        selected = model.update(self.root, request(self.root, 'select-current', operation='concept', action='select',
            conceptId=first['id'], source=user('先选第一张')))['record']
        self.assertEqual(selected, first)
        self.assertEqual(len(load(self.root)['concepts']), 2)
        self.confirm(first)
        model.update(self.root, request(self.root, 'new-round', operation='concept', action='reopen',
            cueIds=['poster'], source=user('明确重开概念')))
        selected = model.update(self.root, request(self.root, 'select-history', operation='concept', action='select',
            conceptId=second['id'], source=user('重用旧轮的第二张')))['record']
        self.assertEqual(selected['round'], 2)
        self.assertEqual(selected['copiedFromConceptId'], second['id'])
        self.assertEqual(selected['selectionSource'], user('重用旧轮的第二张'))
        self.assertEqual(load(self.root)['concepts'][:2], [first, second])
        self.assertEqual(load(self.root)['creativeObjects'][0]['concept']['round'], 2)

    def test_selection_copy_rolls_back_file_and_round_when_manifest_publication_fails(self):
        first = self.register(name='first')
        second = self.register(name='second', recommend=False)
        self.confirm(first)
        before = (self.root / 'animation-manifest.json').read_bytes()
        paths = set((self.root / 'assets/concepts').iterdir())
        with patch('scripts.work_model.save', side_effect=ValueError('publication failed')):
            with self.assertRaisesRegex(ValueError, 'publication failed'):
                model.update(self.root, request(self.root, 'failed-publication', operation='concept', action='select',
                    conceptId=second['id'], source=user('明确选择第二张')))
        self.assertEqual((self.root / 'animation-manifest.json').read_bytes(), before)
        self.assertEqual(set((self.root / 'assets/concepts').iterdir()), paths)

    def test_copy_lineage_does_not_transfer_opinions_across_object_or_different_bytes(self):
        first = self.register(name='first')
        other = self.register(cue='map', name='other-image')
        from scripts.work_model_feedback_targets import feedback_applies
        from scripts.work_model_concepts import concept_target
        manifest = load(self.root)
        opinion = {'target': {'versionId': manifest['identity']['versionId'], 'conceptId': first['id']}}
        # Even malformed provenance in an inspected historical record cannot
        # attach another object's opinion or a different image's opinion.
        manifest['concepts'][1]['copiedFromConceptId'] = first['id']
        self.assertFalse(feedback_applies(manifest, opinion, concept_target([other])))
        manifest['concepts'][1]['objectId'] = first['objectId']
        self.assertFalse(feedback_applies(manifest, opinion, concept_target([other])))
        manifest['concepts'][1]['sha256'] = first['sha256']
        self.assertFalse(feedback_applies(manifest, opinion, concept_target([other])),
                         'writer copies always point to a strictly earlier round')

    def test_client_cannot_supply_copy_provenance_or_selection_source(self):
        first = self.register(name='first')
        before = (self.root / 'animation-manifest.json').read_bytes()
        for field, value in (('copiedFromConceptId', first['id']), ('selectionSource', user('伪造来源'))):
            with self.assertRaisesRegex(ValueError, 'provenance'):
                model.update(self.root, request(self.root, 'fake-' + field, operation='concept', action='select',
                    conceptId=first['id'], source=user('选择'), **{field: value}))
        self.assertEqual((self.root / 'animation-manifest.json').read_bytes(), before)

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


class ConceptHandoffTests(unittest.TestCase):
    setUp = ConceptTests.setUp
    register = ConceptTests.register
    confirm = ConceptTests.confirm

    def handoff(self, name, selected, excluded, **extra):
        return model.update(self.root, request(self.root, name, operation='concept-handoff',
            cueIds=[c['cueId'] for c in selected], conceptIds=[c['id'] for c in selected],
            excludedCueIds=excluded, source=user('本轮只制作所选场景的分镜，其余暂不推进'), **extra))

    def test_partial_handoff_confirms_selected_and_persists_exact_scope_on_refresh(self):
        poster = self.register(name='poster')
        before = load(self.root)
        result = self.handoff('partial-handoff', [poster], ['map'])
        record = result['record']
        self.assertEqual(record['requestId'], 'partial-handoff')
        self.assertEqual(record['selected'], [{'cueId': 'poster', 'objectId': poster['objectId'], 'conceptId': poster['id']}])
        self.assertEqual(record['excluded'], [{'cueId': 'map', 'objectId': before['cues'][1]['objectId'], 'conceptId': None}])
        self.assertEqual(record['source'], user('本轮只制作所选场景的分镜，其余暂不推进'))
        after = load(self.root)
        self.assertEqual([d['kind'] for d in after['decisions']], ['confirm-concept'])
        self.assertEqual(after['decisions'][0]['conceptIds'], [poster['id']])
        self.assertEqual(after['artifacts'], before['artifacts'])
        self.assertEqual(after['productionRuns'], before['productionRuns'])
        self.assertEqual(after['reviewSets'], before['reviewSets'])
        model.open_project(self.afterforge)
        state = model.status(self.root)
        self.assertTrue(state['conceptDesign']['storyboardHandoff']['current'])
        self.assertEqual(state['conceptDesign']['storyboardHandoff']['id'], record['id'])
        self.assertEqual(state['conceptDesign']['storyboardHandoff']['problems'], [])
        self.assertEqual([c['firstConfirmed'] for c in state['conceptDesign']['cues']], [True, False])

    def test_all_confirmed_still_saves_handoff_and_duplicate_request_is_idempotent(self):
        poster = self.register(name='poster')
        map_image = self.register(cue='map', name='map-image')
        self.confirm(poster, map_image)
        before = load(self.root)
        req = request(self.root, 'already-confirmed-handoff', operation='concept-handoff', cueIds=['poster'],
            conceptIds=[poster['id']], excludedCueIds=['map'], source=user('只推进 poster 的分镜，map 留后'))
        first = model.update(self.root, req)
        self.assertEqual(model.update(self.root, req), first)
        self.assertEqual(load(self.root)['decisions'], before['decisions'])
        self.assertEqual(len(load(self.root)['storyboardHandoffs']), 1)
        self.assertEqual(first['record']['excluded'][0]['conceptId'], map_image['id'])
        second = self.handoff('next-handoff', [map_image], ['poster'])['record']
        self.assertNotEqual(first['record']['id'], second['id'])
        self.assertEqual(load(self.root)['storyboardHandoffs'][0], first['record'])
        self.assertEqual(model.status(self.root)['conceptDesign']['storyboardHandoff']['id'], second['id'])

    def test_handoff_validates_entire_selection_before_confirming_and_rolls_back_failed_save(self):
        poster = self.register(name='poster')
        map_image = self.register(cue='map', name='map-image')
        feedback = model.update(self.root, request(self.root, 'map-opinion', operation='feedback', body='地图太挤',
            source=user(), target={'versionId': load(self.root)['identity']['versionId'], 'conceptId': map_image['id']}))['record']
        before = (self.root / 'animation-manifest.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'unresolved-feedback'):
            self.handoff('blocked-batch', [poster, map_image], [])
        self.assertEqual((self.root / 'animation-manifest.json').read_bytes(), before)
        model.update(self.root, request(self.root, 'map-addressed', operation='feedback-status', feedbackId=feedback['id'],
            status='addressed', resolution='已处理地图意见'))
        before = (self.root / 'animation-manifest.json').read_bytes()
        with patch('scripts.work_model.save', side_effect=ValueError('handoff save failed')):
            with self.assertRaisesRegex(ValueError, 'handoff save failed'):
                self.handoff('failed-batch', [poster, map_image], [])
        self.assertEqual((self.root / 'animation-manifest.json').read_bytes(), before)
        self.assertEqual(load(self.root)['decisions'], [])
        self.assertEqual(load(self.root)['storyboardHandoffs'], [])

    def test_stale_concepts_invalid_partitions_and_revision_conflicts_are_rejected(self):
        poster = self.register(name='poster')
        map_image = self.register(cue='map', name='map-image')
        valid = {'operation': 'concept-handoff', 'cueIds': ['poster'], 'conceptIds': [poster['id']],
                 'excludedCueIds': ['map'], 'source': user('只做 poster 分镜')}
        for index, patch_values in enumerate([
            {'cueIds': []}, {'conceptIds': []}, {'conceptIds': [map_image['id']]},
            {'excludedCueIds': []}, {'excludedCueIds': ['poster', 'map']},
            {'excludedCueIds': ['map', 'map']}, {'excludedCueIds': ['unknown']},
            {'cueIds': ['poster', 'poster'], 'conceptIds': [poster['id'], poster['id']]},
        ]):
            before = (self.root / 'animation-manifest.json').read_bytes()
            with self.assertRaises(ValueError):
                model.update(self.root, request(self.root, 'invalid-handoff-' + str(index), **{**valid, **patch_values}))
            self.assertEqual((self.root / 'animation-manifest.json').read_bytes(), before)
        stale = request(self.root, 'revision-stale', **valid)
        self.register(name='poster-new')
        before = (self.root / 'animation-manifest.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'stale revision'):
            model.update(self.root, stale)
        with self.assertRaisesRegex(ValueError, 'concept-not-current|current recommended'):
            model.update(self.root, request(self.root, 'concept-stale', **valid))
        self.assertEqual((self.root / 'animation-manifest.json').read_bytes(), before)

    def test_handoff_current_is_only_a_scoped_hint_and_keeps_immutable_history(self):
        poster = self.register(name='poster')
        map_image = self.register(cue='map', name='map-image')
        record = self.handoff('scoped-handoff', [poster], ['map'])['record']
        self.register(cue='map', name='excluded-new')
        self.assertTrue(model.status(self.root)['conceptDesign']['storyboardHandoff']['current'])
        manifest = load(self.root)
        model.update(self.root, request(self.root, 'ordinary-summary', operation='edit',
            patch={'brief': {**manifest['brief'], 'summary': '普通制作说明'}}))
        self.assertTrue(model.status(self.root)['conceptDesign']['storyboardHandoff']['current'])
        model.update(self.root, request(self.root, 'new-poster-feedback', operation='feedback', body='本场还要调整',
            source=user(), target={'versionId': manifest['identity']['versionId'], 'conceptId': poster['id']}))
        latest = model.status(self.root)['conceptDesign']['storyboardHandoff']
        self.assertFalse(latest['current'])
        self.assertIn('unresolved-feedback', [p['code'] for p in latest['problems']])
        self.assertEqual(load(self.root)['storyboardHandoffs'][0], record)
        self.assertTrue(model.status(self.root)['conceptDesign']['cues'][0]['firstConfirmed'])

    def test_missing_image_or_changed_scope_only_marks_hint_and_status_never_writes(self):
        poster = self.register(name='poster')
        self.handoff('initial-handoff', [poster], ['map'])
        image = self.root / poster['path']
        image_bytes = image.read_bytes()
        image.unlink()
        before = (self.root / 'animation-manifest.json').read_bytes()
        latest = model.status(self.root)['conceptDesign']['storyboardHandoff']
        self.assertFalse(latest['current'])
        self.assertIn('concept-image-unavailable', [p['code'] for p in latest['problems']])
        self.assertTrue(model.status(self.root)['conceptDesign']['cues'][0]['firstConfirmed'])
        self.assertEqual((self.root / 'animation-manifest.json').read_bytes(), before)
        with self.assertRaisesRegex(ValueError, 'concept-image-unavailable'):
            self.handoff('missing-image-handoff', [poster], ['map'])
        self.assertEqual((self.root / 'animation-manifest.json').read_bytes(), before)
        image.write_bytes(image_bytes)
        self.assertTrue(model.status(self.root)['conceptDesign']['storyboardHandoff']['current'])
        manifest = load(self.root)
        model.update(self.root, request(self.root, 'scope-changed', operation='edit',
            patch={'cues': manifest['cues'][:1]}))
        before = (self.root / 'animation-manifest.json').read_bytes()
        self.assertIn('handoff-scope-changed', [p['code'] for p in model.status(self.root)['conceptDesign']['storyboardHandoff']['problems']])
        self.assertEqual((self.root / 'animation-manifest.json').read_bytes(), before)

    def test_handoff_is_not_a_legacy_upgrade_or_historical_qualification(self):
        poster = self.register(name='poster')
        manifest = load(self.root)
        manifest['workModelVersion'] = '2.1.0'
        save(self.root, manifest)
        before = (self.root / 'animation-manifest.json').read_bytes()
        with self.assertRaisesRegex(ValueError, '2.2'):
            self.handoff('legacy-handoff', [poster], ['map'])
        model.status(self.root)
        self.assertEqual((self.root / 'animation-manifest.json').read_bytes(), before)
        self.assertEqual(load(self.root)['decisions'], [])


class ConceptJobTests(unittest.TestCase):
    """Exercise the existing shared job path with only expensive renderers doubled."""
    from tests.test_work_model_jobs import JobTests as _JobFixture
    cold_start = True
    work_model_version = '2.2.0'
    setUp = _JobFixture.setUp
    req = _JobFixture.req

    def test_handoff_does_not_change_media_identity_or_grant_demo_authority(self):
        activate(self.root)
        from scripts.work_model_inputs import cue_key, timeline_key
        before = load(self.root)
        cues = [c for c in before['cues'] if c['productionMode'] == 'animation']
        keys = [cue_key(self.root, before, c) for c in cues]
        timeline = timeline_key(self.root, before)
        current = next(o for o in before['creativeObjects'] if o['id'] == cues[0]['objectId'])['concept']['recommendedId']
        model.update(self.root, request(self.root, 'qualified-handoff', operation='concept-handoff',
            cueIds=[cues[0]['id']], conceptIds=[current], excludedCueIds=[c['id'] for c in cues[1:]],
            source=user('只推进这一场的分镜，不委托整版 Demo')))
        after = load(self.root)
        self.assertEqual([cue_key(self.root, after, c) for c in cues], keys)
        self.assertEqual(timeline_key(self.root, after), timeline)
        self.assertEqual(after['decisions'], before['decisions'])
        self.assertEqual(after['productionRuns'], before['productionRuns'])
        self.assertEqual(after['artifacts'], before['artifacts'])
        self.assertEqual(after['reviewSets'], before['reviewSets'])
        data = (self.root / 'animation-manifest.json').read_bytes()
        self.assertTrue(model.status(self.root)['conceptDesign']['storyboardHandoff']['current'])
        self.assertEqual((self.root / 'animation-manifest.json').read_bytes(), data)
        with self.assertRaisesRegex(ValueError, 'explicit production authorization'):
            model.preview(self.root, request(self.root, 'not-commissioned-demo', scope='full'))
        self.assertEqual(load(self.root)['decisions'], before['decisions'])

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
