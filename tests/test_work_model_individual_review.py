"""Individual complete animation reviews can authorize the existing release path."""
import unittest
from scripts import work_model as model
from scripts.work_model_store import load
from tests import test_work_model_jobs as fixture

SOURCE = {'channel': 'chat', 'text': '已逐场看完全部当前动画，直接交付高清素材', 'reference': 'synthetic-review'}


class IndividualReviewTests(unittest.TestCase):
    work_model_version = '2.2.0'
    setUp = fixture.JobTests.setUp
    req = fixture.JobTests.req

    def previews(self):
        m = load(self.root)
        for cue, start in zip([c for c in m['cues'] if c['productionMode'] == 'animation'], ('0s', '5s')):
            cue['resolvedTimeline'] = {'start': start, 'duration': '2s'}
        model.update(self.root, self.req('place', operation='edit', patch={'cues': m['cues']}))
        for cue in [c for c in m['cues'] if c['productionMode'] == 'animation']:
            model.preview(self.root, self.req('local-' + cue['id'], cueIds=[cue['id']]))
        return [a['id'] for a in load(self.root)['artifacts'] if a['kind'] == 'local-preview']

    def collect(self, ids, name='collect'):
        return model.update(self.root, self.req(name, operation='collect-review', artifactIds=ids, source=SOURCE))['record']

    def test_individual_review_delivers_all_cues_without_demo_or_implicit_approval(self):
        ids = self.previews()
        count = len(self.calls)
        review = self.collect(ids)
        self.assertEqual(review['kind'], 'individual-cues')
        self.assertEqual(len(self.calls), count)
        self.assertEqual(model.status(self.root)['reviewSet']['id'], review['id'])
        m = load(self.root)
        self.assertFalse(any(a['kind'] == 'full-preview' for a in m['artifacts']))
        self.assertFalse(any(d['kind'] == 'authorize-demo' for d in m['decisions']))
        with self.assertRaisesRegex(ValueError, 'author|批准|approve'):
            model.deliver(self.root, self.req('no-approval'))
        result = model.deliver(self.root, self.req('deliver', decision={
            'kind': 'approve-and-deliver', 'reviewSetId': review['id'], 'source': SOURCE}))
        self.assertEqual(result['status'], 'complete')
        record = result['delivery']
        self.assertEqual({x['cueId'] for x in record['media']}, {c['id'] for c in m['cues'] if c['productionMode'] == 'animation'})
        package = self.root.parents[3] / record['packagePath']
        self.assertTrue((package / record['xmlFileName']).is_file())
        self.assertEqual(len(list(package.glob('*.mov'))), 2)
        self.assertEqual(load(self.root)['productionRuns'], m['productionRuns'])

    def test_missing_duplicate_and_unknown_artifacts_rejected_atomically(self):
        ids = self.previews()
        for name, selected in [('missing', ids[:1]), ('duplicate', ids + ids[:1]), ('unknown', ids[:1] + ['unknown'])]:
            before = (self.root / 'animation-manifest.json').read_bytes()
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'individual review'):
                self.collect(selected, name)
            self.assertEqual((self.root / 'animation-manifest.json').read_bytes(), before)

    def test_tampered_media_and_changed_motion_invalidate_collection_and_approval(self):
        ids = self.previews()
        review = self.collect(ids)
        m = load(self.root)
        movie = self.root / next(a for a in m['artifacts'] if a['id'] == ids[0])['path']
        original = movie.read_bytes()
        movie.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'individual review'):
            self.collect(ids, 'tampered')
        with self.assertRaisesRegex(ValueError, 'review'):
            model.deliver(self.root, self.req('stale-approve', decision={'kind':'approve-and-deliver','reviewSetId':review['id'],'source':SOURCE}))
        movie.write_bytes(original)
        motion = self.root / m['cues'][0]['renderAdapters']['hyperframes']['motionSrc']
        motion.write_text(motion.read_text() + '\n// changed source')
        with self.assertRaisesRegex(ValueError, 'individual review'):
            self.collect(ids, 'changed-motion')

    def test_partial_preview_cannot_stand_for_entire_animation(self):
        ids = self.previews()
        cue = load(self.root)['cues'][0]
        model.preview(self.root, self.req('partial', cueIds=[cue['id']], range={'start':'0s','duration':'1s'}))
        partial = load(self.root)['artifacts'][-1]['id']
        with self.assertRaisesRegex(ValueError, 'individual review'):
            self.collect([partial, ids[1]])

    def test_collection_retry_is_idempotent(self):
        ids = self.previews()
        request = self.req('collect', operation='collect-review', artifactIds=ids, source=SOURCE)
        first = model.update(self.root, request)
        self.assertEqual(model.update(self.root, request), first)
        self.assertEqual(len(load(self.root)['reviewSets']), 1)

    def test_timeline_change_invalidates_collected_review(self):
        ids = self.previews()
        review = self.collect(ids)
        m = load(self.root)
        m['cues'][0]['resolvedTimeline']['start'] = '1s'
        model.update(self.root, self.req('move', operation='edit', patch={'cues':m['cues']}))
        self.assertIsNone(model.status(self.root)['reviewSet'])
        with self.assertRaisesRegex(ValueError, 'review'):
            model.deliver(self.root, self.req('old-review', decision={'kind':'approve-and-deliver','reviewSetId':review['id'],'source':SOURCE}))

    def test_pending_feedback_still_blocks_delivery(self):
        ids = self.previews()
        review = self.collect(ids)
        m = load(self.root)
        model.update(self.root, self.req('feedback', operation='feedback', body='需要修改', source=SOURCE,
            target={'versionId':m['identity']['versionId'], 'artifactId':ids[0]}))
        with self.assertRaisesRegex(ValueError, 'feedback'):
            model.deliver(self.root, self.req('blocked', decision={'kind':'approve-and-deliver','reviewSetId':review['id'],'source':SOURCE}))
        self.assertFalse(load(self.root)['deliveries'])

    def test_collection_requires_actual_user_source(self):
        ids = self.previews()
        with self.assertRaises(ValueError):
            model.update(self.root, self.req('no-source', operation='collect-review', artifactIds=ids))
        self.assertFalse(load(self.root)['reviewSets'])
