"""Review prose is immutable evidence, while PNGs and working intent are independent."""
import copy
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

from scripts import work_model as model
from scripts.work_model_store import load, save, sha
from scripts.work_model_storyboard import storyboard_spec, frame_current
from tests import test_work_model_jobs as jobs
from tests.work_model_fixtures import user


class ReviewContentTests(unittest.TestCase):
    setUp = jobs.JobTests.setUp
    req = jobs.JobTests.req

    def edit(self, name, mutate):
        m = load(self.root)
        mutate(m['cues'][0])
        return model.update(self.root, self.req(name, operation='edit', patch={'cues': m['cues']}))

    def board(self, name):
        return model.preview(self.root, self.req(name, scope='storyboard', cueIds=[load(self.root)['cues'][0]['id']]))

    @staticmethod
    def png(root, manifest, cue, frame, target, log):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'PNG fixture ' + frame['inputKey'].encode())

    def test_notes_publish_new_review_without_rendering_or_rewriting_old_evidence(self):
        before = load(self.root)
        old = copy.deepcopy(before['storyboards'][0])
        self.edit('notes', lambda c: c.update(storyboard={'frames': [
            {'id': 'hero', 'role': 'hero', 'label': 'Hero'}], 'animationNotes': [
            {'id': 'travel', 'frameIds': ['hero'], 'text': '旁白说穿越时，进度退回开头并停留。'}]}))
        state = model.status(self.root)
        self.assertFalse(state['storyboard']['cues'][0]['canConfirm'])
        self.assertTrue(state['storyboard']['cues'][0]['firstConfirmed'])
        with self.assertRaisesRegex(ValueError, 'current verified'):
            model.update(self.root, self.req('old-confirm', operation='decision', kind='confirm-design',
                storyboardIds=[old['id']], source=user()))
        with patch('scripts.work_model_storyboard._render_one', side_effect=AssertionError('PNG must be reused')):
            result = self.board('notes-preview')
        after = load(self.root)
        self.assertEqual(after['storyboards'][0], old)
        board = after['storyboards'][-1]
        self.assertNotEqual(board['id'], old['id'])
        self.assertIn('reviewInputKey', board)
        self.assertEqual(board['animationNotes'][0]['id'], 'travel')
        old_frame = next(a for a in before['artifacts'] if a['id'] == old['artifactIds'][0])
        new_frame = next(a for a in after['artifacts'] if a['id'] == result['artifactIds'][0])
        self.assertEqual(old_frame['sha256'], new_frame['sha256'])
        self.assertNotEqual(old_frame['id'], new_frame['id'])
        self.assertTrue(model.status(self.root)['storyboard']['cues'][0]['canConfirm'])

    def test_note_references_validate_on_edit_and_frame_reorder_invalidates_review(self):
        frames = [{'id': 'hero', 'role': 'hero'}, {'id': 'b', 'role': 'auxiliary'}, {'id': 'c', 'role': 'auxiliary'}]
        notes = [{'id': 'one', 'frameIds': ['hero'], 'text': '单帧'},
                 {'id': 'two', 'frameIds': ['hero', 'b'], 'text': '多帧共享'}]
        self.edit('frames', lambda c: c.update(storyboard={'frames': frames, 'animationNotes': notes}))
        with patch('scripts.work_model_storyboard._render_one', side_effect=self.png):
            self.board('frames-preview')
        for bad in (notes + [notes[0]], [{'id': 'missing', 'frameIds': ['gone'], 'text': '失效'}]):
            with self.assertRaises(ValueError):
                self.edit('invalid', lambda c: c['storyboard'].update(animationNotes=bad))
        self.edit('reorder', lambda c: c['storyboard'].update(frames=[frames[2], frames[0], frames[1]]))
        self.assertFalse(model.status(self.root)['storyboard']['cues'][0]['canConfirm'])
        with patch('scripts.work_model_storyboard._render_one', side_effect=AssertionError('reorder reuses pixels')):
            self.board('reordered-preview')
        card = model.status(self.root)['storyboard']['cues'][0]
        self.assertEqual([f['frameId'] for f in card['frames']], ['c', 'hero', 'b'])
        self.assertEqual(card['animationNotes'], notes)
        with self.assertRaises(ValueError):
            self.edit('remove-referenced', lambda c: c['storyboard'].update(frames=[frames[0]]))
        self.edit('regroup', lambda c: c['storyboard'].update(
            frames=[frames[0], {'id': 'd', 'role': 'auxiliary'}], animationNotes=[notes[0]]))
        with patch('scripts.work_model_storyboard._render_one', side_effect=self.png) as renderer:
            self.board('regroup-preview')
        self.assertEqual(renderer.call_count, 1, 'only the new frame needs pixels')
        self.assertEqual([f['frameId'] for f in model.status(self.root)['storyboard']['cues'][0]['frames']], ['hero', 'd'])

    def test_corrupt_png_rebuilds_and_inflight_prose_is_not_published(self):
        m = load(self.root)
        artifact = m['artifacts'][0]
        (self.root / artifact['path']).write_bytes(b'corrupt')
        with patch('scripts.work_model_storyboard._render_one', side_effect=self.png) as renderer:
            self.board('repair')
        self.assertEqual(renderer.call_count, 1)
        before = load(self.root)
        from scripts.work_model_storyboard import render_storyboard
        def concurrent(*args):
            frames = render_storyboard(*args)
            self.edit('concurrent-text', lambda c: c.update(finalAnimationDescription='新的总体意图'))
            return frames
        with patch('scripts.work_model_jobs.render_storyboard', side_effect=concurrent):
            with self.assertRaisesRegex(ValueError, 'inputs changed'):
                self.board('inflight')
        self.assertEqual(load(self.root)['storyboards'], before['storyboards'])

    def test_legacy_contract_reuse_requires_original_input_proof(self):
        # Recreate the old contract explicitly, including prose in its state.
        from scripts.work_model_store import digest
        from scripts.hyperframes_runtime import read_runtime_pin
        m = load(self.root)
        old = m['artifacts'][0]
        snapshot = {k: old[k] for k in ('cueId', 'frameId', 'role', 'label', 'time', 'mode',
            'background', 'duration', 'state', 'backgroundTime', 'backgroundSrc', 'narration',
            'contentContext', 'finalDescription')}
        for k in ('backgroundSample', 'stillSrc', 'sample'):
            if k in old:
                snapshot[k] = old[k]
        cue = m['cues'][0]
        adapter = cue['renderAdapters']['hyperframes']
        old.pop('storyboardContract')
        old['inputKey'] = digest({'storyboardContract': 4, 'runtime': read_runtime_pin(self.root),
            'dimensions': (854, 480), 'frameDuration': m['project']['source']['frameDuration'],
            'compositionId': adapter.get('compositionId'), 'compositionSrc': adapter['compositionSrc'],
            'state': snapshot, 'screenText': cue.get('screenText', []),
            'files': {p: sha(self.root / p) for p in old['files']}})
        board = m['storyboards'][0]
        board.pop('reviewInputKey'); board.pop('animationNotes')
        save(self.root, m)
        self.assertTrue(frame_current(self.root, m, old))
        self.assertTrue(model.status(self.root)['storyboard']['cues'][0]['canConfirm'])
        self.edit('legacy-prose', lambda c: c.update(finalAnimationDescription='新的文字'))
        self.assertFalse(model.status(self.root)['storyboard']['cues'][0]['canConfirm'])
        with patch('scripts.work_model_storyboard._render_one', side_effect=AssertionError('verified legacy PNG should reuse')):
            self.board('legacy-preview')
        self.assertEqual(load(self.root)['artifacts'][-1]['sha256'], old['sha256'])
        self.edit('new-state', lambda c: c.update(storyboard={'frames': [
            {'id': 'hero', 'role': 'hero', 'label': 'Hero', 'state': {'id': 'changed'}}]}))
        with patch('scripts.work_model_storyboard._render_one', side_effect=self.png) as renderer:
            self.board('changed-pixels')
        self.assertEqual(renderer.call_count, 1)

    def test_working_intent_concurrent_writers_conflict_and_copy_does_not_inherit(self):
        entry = {'id': 'focus', 'kind': 'focus', 'text': '只改穿越',
                 'locator': {'description': '穿越段'}, 'source': user()}
        requests = [self.req('concurrent-'+str(i), operation='working-intent', upserts=[{**entry, 'id': str(i)}]) for i in range(2)]
        def write(req):
            try:
                return model.update(self.root, req)['status']
            except ValueError:
                return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(write, requests)), ['conflict', 'updated'])
        self.assertEqual(len(load(self.root)['workingIntent']['items']), 1)
        copied = model.open_project(self.root.parents[3], {'requestId': 'intent-copy', 'expectedRevision':
            model.project_status(self.root.parents[3])['revision'], 'episodeTitle': '新制作版',
            'copyFrom': str(self.root), 'copyMode': 'restart', 'commission': user('隔离测试新版本不继承意图')})
        self.assertEqual(model.status(copied['root'])['workingIntent']['items'], [])

    def test_unprovable_legacy_png_is_rendered_again(self):
        m = load(self.root)
        old = m['artifacts'][0]
        old.pop('storyboardContract')
        old.pop('contentContext')
        save(self.root, m)
        with patch('scripts.work_model_storyboard._render_one', side_effect=self.png) as renderer:
            self.board('unprovable-old-png')
        self.assertEqual(renderer.call_count, 1)

    def test_intent_updated_during_preview_survives_publication_without_invalidating_it(self):
        from scripts.work_model_storyboard import render_storyboard
        def concurrent(*args):
            frames = render_storyboard(*args)
            model.update(self.root, self.req('inflight-intent', operation='working-intent', upserts=[
                {'id': 'keep', 'kind': 'preserve', 'text': '前半段保持', 'locator': {'description': '前半段'}, 'source': user()}]))
            return frames
        with patch('scripts.work_model_jobs.render_storyboard', side_effect=concurrent):
            result = self.board('intent-does-not-stale-preview')
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(model.status(self.root)['workingIntent']['items'][0]['text'], '前半段保持')

    def test_working_intent_is_scoped_mutable_context_only(self):
        model.preview(self.root, self.req('full-before-intent', scope='full'))
        review = model.status(self.root)['reviewSet']
        model.update(self.root, self.req('approve-before-intent', operation='decision', kind='approve-and-deliver',
            reviewSetId=review['id'], source=user('仅在隔离 fixture 中模拟交付资格')))
        before = load(self.root)
        from scripts.work_model_jobs import _spec
        delivery_spec = _spec(self.root, before, 'deliver', {})
        spec = storyboard_spec(self.root, before)
        status = model.status(self.root)
        entry = {'id': 'travel', 'kind': 'focus', 'text': '只修改穿越',
                 'locator': {'cueId': 'missing', 'frameId': 'old', 'description': '穿越段'}, 'source': user()}
        preserve = {**entry, 'id': 'keep', 'kind': 'preserve', 'text': '前面暂时保持'}
        request = self.req('intent', operation='working-intent', upserts=[entry, preserve], removeIds=[])
        result = model.update(self.root, request)
        self.assertEqual(model.update(self.root, request), result)
        after = load(self.root)
        self.assertEqual(set(after) - set(before), {'workingIntent'})
        for key in before:
            if key not in {'requests', 'editRevision'}:
                self.assertEqual(before[key], after[key], key)
        self.assertEqual(storyboard_spec(self.root, after), spec)
        self.assertEqual(_spec(self.root, after, 'deliver', {}), delivery_spec)
        current = model.status(self.root)
        for key in ('production', 'reviewSet', 'availableActions', 'decisions'):
            self.assertEqual(current[key], status[key], key)
        self.assertEqual(len(current['workingIntent']['items']), 2)
        model.update(self.root, self.req('replace', operation='working-intent', upserts=[{**entry, 'text': '穿越只改结尾'}]))
        items = load(self.root)['workingIntent']['items']
        self.assertEqual([i['text'] for i in items], ['穿越只改结尾', '前面暂时保持'])
        stale = self.req('stale', operation='working-intent', removeIds=['keep'])
        model.update(self.root, self.req('remove', operation='working-intent', removeIds=['travel']))
        with self.assertRaisesRegex(ValueError, 'revision|Revision'):
            model.update(self.root, stale)
        self.assertEqual([i['id'] for i in model.status(self.root)['workingIntent']['items']], ['keep'])


if __name__ == '__main__':
    unittest.main()
