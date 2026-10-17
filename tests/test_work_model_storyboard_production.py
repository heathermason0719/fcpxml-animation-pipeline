"""Storyboard approval hands explicit production scope to the Agent."""
import copy
import unittest
from scripts import work_model as model
from scripts.work_model_store import load
from tests import test_work_model_jobs
from tests.work_model_fixtures import request, user


class StoryboardProductionTests(unittest.TestCase):
    setUp = test_work_model_jobs.JobTests.setUp
    work_model_version = '2.2.0'

    def commission(self, **changes):
        state = model.status(self.root)
        cards = state['storyboard']['cues']
        return request(self.root, 'handoff', operation='decision', kind='authorize-demo',
            taskId='storyboard-production', cueIds=[cards[0]['id']],
            presentationCueIds=[cards[0]['id']], excludedCueIds=[cards[1]['id']],
            storyboardIds=[cards[0]['storyboardId']], source=user('通过第一条并制作，第二条暂缓'), **changes)

    def test_handoff_persists_scope_without_render_or_second_confirmation(self):
        before = load(self.root)
        req = self.commission()
        result = model.update(self.root, req)
        after = load(self.root)
        self.assertEqual(after['artifacts'], before['artifacts'])
        self.assertEqual(after['decisions'][:-1], before['decisions'])
        self.assertEqual(self.calls, [])
        self.assertEqual(result['record']['storyboardIds'], req['storyboardIds'])
        pending = model.status(self.root)['storyboard']['productionRequest']
        self.assertEqual(pending['status'], 'pending')
        self.assertEqual(pending['cueIds'], req['cueIds'])
        self.assertEqual(pending['excludedCueIds'], req['excludedCueIds'])
        self.assertEqual(pending['taskId'], req['taskId'])
        self.assertEqual(model.update(self.root, req), result)

    def test_snapshot_scope_and_feedback_are_checked_atomically(self):
        req = self.commission()
        for patch in ({'storyboardIds':['missing']}, {'presentationCueIds':[]}, {'excludedCueIds':[]},
                      {'storyboardIds':[s['id'] for s in load(self.root)['storyboards']]}):
            before = copy.deepcopy(load(self.root))
            with self.assertRaises(ValueError):
                model.update(self.root, {**req, **patch})
            self.assertEqual(load(self.root), before)
        model.update(self.root, request(self.root, 'feedback', operation='feedback', body='改一下位置',
            target={'versionId':load(self.root)['identity']['versionId'], 'cueIds':req['cueIds']}, source=user()))
        with self.assertRaisesRegex(ValueError, 'Storyboard'):
            model.update(self.root, self.commission())

    def test_stale_source_rejects_handoff(self):
        req = self.commission()
        cue = load(self.root)['cues'][0]
        path = self.root / cue['renderAdapters']['hyperframes']['compositionSrc']
        path.write_text(path.read_text()+'\n<!-- changed -->')
        with self.assertRaisesRegex(ValueError, 'Storyboard'):
            model.update(self.root, req)
