"""Scene acknowledgements bind seen content without commissioning production."""
import unittest
from unittest.mock import patch

from scripts import work_model as model
from scripts.work_model_store import load
from tests import test_work_model_jobs as jobs
from tests.work_model_fixtures import user, raster


class SceneReviewTests(unittest.TestCase):
    setUp = jobs.JobTests.setUp
    req = jobs.JobTests.req

    def acknowledge(self, name, index=0, kind='storyboard', artifact=None):
        manifest = load(self.root)
        cue = [c for c in manifest['cues'] if c['productionMode'] == 'animation'][index]
        target = {'artifactId': artifact['id']} if artifact else {'storyboardId': next(
            b['id'] for b in reversed(manifest['storyboards']) if b['cueId'] == cue['id'])}
        return model.update(self.root, self.req(name, operation='scene-review', kind=kind,
                            cueId=cue['id'], source=user('已看过并确认此场当前呈现'), **target))

    def test_storyboard_acknowledgement_survives_refresh_and_is_not_a_production_decision(self):
        before = load(self.root)
        from scripts.work_model_inputs import cue_key, timeline_key
        media_key = cue_key(self.root, before, before['cues'][0])
        timeline = timeline_key(self.root, before)
        request = self.req('seen', operation='scene-review', kind='storyboard', cueId=before['cues'][0]['id'],
                           storyboardId=before['storyboards'][0]['id'], source=user())
        first = model.update(self.root, request)
        self.assertEqual(model.update(self.root, request), first)
        after = load(self.root)
        self.assertEqual(after['decisions'], before['decisions'])
        self.assertEqual(after['artifacts'], before['artifacts'])
        self.assertEqual(after['productionRuns'], before['productionRuns'])
        self.assertEqual(cue_key(self.root, after, after['cues'][0]), media_key)
        self.assertEqual(timeline_key(self.root, after), timeline)
        record = model.status(self.root)['storyboard']['cues'][0]['sceneReview']['storyboard']
        self.assertTrue(record['current'])
        self.assertEqual(record['reviewInputKey'], before['storyboards'][0]['reviewInputKey'])
        with self.assertRaisesRegex(ValueError, 'stale revision'):
            model.update(self.root, {**request, 'requestId': 'stale'})
        with self.assertRaisesRegex(ValueError, 'another request'):
            model.update(self.root, {**request, 'source': user('换了请求内容')})

    def test_metadata_preserves_progress_but_actual_source_or_placement_change_does_not(self):
        self.acknowledge('seen')
        manifest = load(self.root)
        model.update(self.root, self.req('metadata', operation='edit', patch={'brief': {
            **manifest['brief'], 'summary': '一般制作说明，不更改呈现输入'}}))
        self.assertTrue(model.status(self.root)['storyboard']['cues'][0]['sceneReview']['storyboard']['current'])
        source = self.root / manifest['cues'][0]['renderAdapters']['hyperframes']['compositionSrc']
        original = source.read_bytes()
        source.write_bytes(original + b'\n<div>actual changed picture</div>')
        self.assertFalse(model.status(self.root)['storyboard']['cues'][0]['sceneReview']['storyboard']['current'])
        source.write_bytes(original)
        self.assertTrue(model.status(self.root)['storyboard']['cues'][0]['sceneReview']['storyboard']['current'])
        manifest = load(self.root)
        manifest['cues'][0]['resolvedTimeline']['start'] = '0s'
        model.update(self.root, self.req('placement', operation='edit', patch={'cues': manifest['cues']}))
        self.assertTrue(model.status(self.root)['storyboard']['cues'][0]['sceneReview']['storyboard']['current'],
                        'moving a transparent still does not change its viewed inputs')
        manifest = load(self.root)
        manifest['cues'][0]['storyboard'] = {'frames': [{'id': 'hero', 'role': 'hero', 'background': 'timeline'}]}
        model.update(self.root, self.req('timeline-background', operation='edit', patch={'cues': manifest['cues']}))
        with patch('scripts.work_model_jobs.render_storyboard', side_effect=raster):
            model.preview(self.root, self.req('timeline-board', scope='storyboard', cueIds=[manifest['cues'][0]['id']]))
        self.acknowledge('seen-timeline-board')
        manifest = load(self.root)
        manifest['cues'][0]['resolvedTimeline']['start'] = '1s'
        model.update(self.root, self.req('timeline-placement', operation='edit', patch={'cues': manifest['cues']}))
        self.assertFalse(model.status(self.root)['storyboard']['cues'][0]['sceneReview']['storyboard']['current'])

    def test_only_changed_scene_loses_review_progress_and_feedback_is_visible(self):
        with patch('scripts.work_model_jobs.render_storyboard', side_effect=raster):
            model.preview(self.root, self.req('both-boards', scope='storyboard', cueIds=[c['id'] for c in load(self.root)['cues'] if c['productionMode'] == 'animation']))
        self.acknowledge('first')
        self.acknowledge('second', index=1)
        manifest = load(self.root)
        manifest['cues'][0]['finalAnimationDescription'] = '只修改第一场的说明'
        model.update(self.root, self.req('change-prose', operation='edit', patch={'cues': manifest['cues']}))
        states = model.status(self.root)['storyboard']['cues']
        self.assertFalse(states[0]['sceneReview']['storyboard']['current'])
        self.assertTrue(states[1]['sceneReview']['storyboard']['current'])
        cue = [c for c in manifest['cues'] if c['productionMode'] == 'animation'][1]
        model.update(self.root, self.req('opinion', operation='feedback', body='这个场景还需要调整', source=user(),
            target={'versionId': manifest['identity']['versionId'], 'cueIds': [cue['id']]}))
        record = model.status(self.root)['storyboard']['cues'][1]['sceneReview']['storyboard']
        self.assertTrue(record['current'], 'feedback does not erase the acknowledgement')
        self.assertEqual(record['problems'][0]['code'], 'unresolved-feedback')

    def test_stale_or_missing_storyboard_and_archived_version_reject_without_mutation(self):
        manifest = load(self.root)
        artifact = next(a for a in manifest['artifacts'] if a['id'] == manifest['storyboards'][0]['artifactIds'][0])
        (self.root / artifact['path']).write_bytes(b'corrupt')
        before = (self.root / 'animation-manifest.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'current|当前'):
            self.acknowledge('corrupt')
        self.assertEqual((self.root / 'animation-manifest.json').read_bytes(), before)
        (self.root / '.afterforge-archived').write_text('archived')
        with self.assertRaisesRegex(ValueError, 'read-only'):
            self.acknowledge('archived')

    def test_failed_scene_publication_is_atomic_and_historical_versions_remain_read_only(self):
        before = (self.root / 'animation-manifest.json').read_bytes()
        with patch('scripts.work_model.save', side_effect=ValueError('failed-progress-save')):
            with self.assertRaisesRegex(ValueError, 'failed-progress-save'):
                self.acknowledge('failed-save')
        self.assertEqual((self.root / 'animation-manifest.json').read_bytes(), before)
        # Use a deliberately minimal old manifest: writable load rejects it
        # before attempting to create a version lock or interpret new records.
        import json
        old = self.root / 'historical'
        old.mkdir()
        (old / 'animation-manifest.json').write_text(json.dumps({'schemaVersion': '2.0'}))
        with self.assertRaisesRegex(ValueError, 'read-only'):
            model.update(old, {'requestId': 'old-write', 'expectedRevision': 0, 'operation': 'scene-review'})
        self.assertFalse((old / '.afterforge-manifest.lock').exists())

    def test_animation_acknowledges_actual_video_without_rendering_and_changes_locally(self):
        preview = model.preview(self.root, self.req('full-seen', scope='full'))
        manifest = load(self.root)
        artifact = next(a for a in manifest['artifacts'] if a['id'] == preview['artifactIds'][0])
        with patch('scripts.work_model_jobs._run', side_effect=AssertionError('acknowledgement must not render')):
            self.acknowledge('seen-video', kind='animation', artifact=artifact)
        record = model.status(self.root)['storyboard']['cues'][0]['sceneReview']['animation']
        self.assertTrue(record['current'])
        # The second scene begins after the first ends in this fixture below.
        manifest = load(self.root)
        [c for c in manifest['cues'] if c['productionMode'] == 'animation'][1]['resolvedTimeline'] = {'start': '7s', 'duration': '2s'}
        model.update(self.root, self.req('separate-scenes', operation='edit', patch={'cues': manifest['cues']}))
        preview = model.preview(self.root, self.req('new-full-seen', scope='full'))
        manifest = load(self.root)
        artifact = next(a for a in manifest['artifacts'] if a['id'] == preview['artifactIds'][0])
        self.acknowledge('seen-separated-video', kind='animation', artifact=artifact)
        motion = self.root / [c for c in manifest['cues'] if c['productionMode'] == 'animation'][1]['renderAdapters']['hyperframes']['motionSrc']
        motion.write_text('// unrelated changed second scene')
        self.assertTrue(model.status(self.root)['storyboard']['cues'][0]['sceneReview']['animation']['current'])
        manifest['cues'][0]['finalAnimationDescription'] = '第一场新的说明'
        model.update(self.root, self.req('video-prose', operation='edit', patch={'cues': manifest['cues']}))
        self.assertFalse(model.status(self.root)['storyboard']['cues'][0]['sceneReview']['animation']['current'])

    def test_video_review_rejects_partial_coverage_and_corrupted_bytes_atomically(self):
        manifest = load(self.root)
        cue = manifest['cues'][0]
        preview = model.preview(self.root, self.req('partial-video', scope='local', cueIds=[cue['id']],
            range={'start': cue['resolvedTimeline']['start'], 'duration': '1s'}))
        artifact = next(a for a in load(self.root)['artifacts'] if a['id'] == preview['artifactIds'][0])
        before = (self.root / 'animation-manifest.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'entire cue'):
            self.acknowledge('partial-review', kind='animation', artifact=artifact)
        self.assertEqual((self.root / 'animation-manifest.json').read_bytes(), before)
        preview = model.preview(self.root, self.req('complete-video', scope='full'))
        artifact = next(a for a in load(self.root)['artifacts'] if a['id'] == preview['artifactIds'][0])
        self.acknowledge('complete-review', kind='animation', artifact=artifact)
        (self.root / artifact['path']).write_bytes(b'changed-video')
        self.assertFalse(model.status(self.root)['storyboard']['cues'][0]['sceneReview']['animation']['current'])
        before = (self.root / 'animation-manifest.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'current verified video'):
            self.acknowledge('broken-review', kind='animation', artifact=artifact)
        self.assertEqual((self.root / 'animation-manifest.json').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
