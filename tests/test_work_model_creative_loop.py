"""Public API regressions for first entry, review handoff and active work."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import work_model as model
from scripts.work_model_store import load, save
from tests import test_work_model_jobs as jobs
from tests.work_model_fixtures import raster


def source(text='测试用户明确决定'):
    return {'channel': 'chat', 'text': text, 'reference': 'fixture:user-turn'}


class FirstEntryTests(unittest.TestCase):
    cold_start = True
    setUp = jobs.JobTests.setUp
    req = jobs.JobTests.req

    def test_existing_motion_files_do_not_authorize_cold_start_full_demo(self):
        with self.assertRaisesRegex(ValueError, '首次|first|制作依据|authorization'):
            model.preview(self.root, self.req('cold-full', scope='full'))
        self.assertEqual(self.calls, [])
        self.assertEqual(load(self.root)['decisions'], [])
        self.assertIsNone(model.status(self.root)['reviewSet'])

    def test_whole_version_cannot_be_relabelled_as_bounded_exploration(self):
        model.update(self.root, self.req('enrol', operation='edit', patch={}))
        m = load(self.root)
        ids = [c['id'] for c in m['cues'] if c['productionMode'] == 'animation']
        with self.assertRaisesRegex(ValueError, 'whole-version'):
            model.update(self.root, self.req('fake-exploration', operation='decision', kind='explore-motion',
                taskId='all', cueIds=ids, range={'start': '0s', 'duration': m['project']['source']['duration']}, source=source()))
        self.assertEqual(load(self.root)['decisions'], [])

    def test_exploration_cannot_expand_its_authorized_time_range(self):
        cue_id = load(self.root)['cues'][0]['id']
        model.update(self.root, self.req('limited', operation='decision', kind='explore-motion',
            taskId='limited', cueIds=[cue_id], range={'start': '0s', 'duration': '1s'}, source=source()))
        with self.assertRaisesRegex(ValueError, 'range|范围'):
            model.preview(self.root, self.req('outside', scope='local', taskId='limited', cueIds=[cue_id],
                range={'start': '1s', 'duration': '1s'}))
        self.assertEqual(self.calls, [])

    def test_imported_motion_dependency_requires_first_or_local_authority(self):
        m = load(self.root)
        motion = self.root / m['cues'][0]['renderAdapters']['hyperframes']['motionSrc']
        shared = motion.parent / 'shared.js'
        shared.write_text('export const travel = 10;')
        motion.write_text('import {travel} from "./shared.js";')
        proposal = self.root / '.staging' / 'shared.js'
        proposal.parent.mkdir(exist_ok=True)
        proposal.write_text('export const travel = 20;')
        with self.assertRaisesRegex(ValueError, 'first design|首次'):
            model.update(self.root, self.req('change-import', operation='edit', patch={},
                files=[{'path': shared.relative_to(self.root).as_posix(), 'source': str(proposal)}]))
        self.assertEqual(shared.read_text(), 'export const travel = 10;')

    def test_local_filtered_context_is_current_but_not_complete(self):
        m = load(self.root)
        cue_id = m['cues'][0]['id']
        with patch('scripts.work_model_jobs.render_storyboard', side_effect=raster):
            boards = model.preview(self.root, self.req('board-a', scope='storyboard', cueIds=[cue_id]))
        model.update(self.root, self.req('confirm-a', operation='decision', kind='confirm-design',
            storyboardIds=boards['storyboardIds'], source=source()))
        result = model.preview(self.root, self.req('local-a', scope='local', cueIds=[cue_id],
            range={'start': '0s', 'duration': '4s'}))
        state = model.status(self.root)
        artifact = next(a for a in state['artifacts'] if a['id'] in result['artifactIds'])
        self.assertEqual(artifact['missingCueIds'], ['second'])
        self.assertTrue(artifact['mediaCurrent'])
        self.assertTrue(artifact['current'])
        self.assertFalse(artifact['complete'])
        self.assertIsNone(state['reviewSet'])

    def test_confirmation_requires_the_whole_current_frame_collection(self):
        cue_id = load(self.root)['cues'][0]['id']
        with patch('scripts.work_model_jobs.render_storyboard', side_effect=raster):
            board = model.preview(self.root, self.req('hero-only', scope='storyboard', cueIds=[cue_id]))
        m = load(self.root)
        m['cues'][0]['storyboard'] = {'frames': [
            {'id': 'hero', 'role': 'hero', 'label': 'Hero', 'time': '0s'},
            {'id': 'closing', 'role': 'auxiliary', 'time': '1s'}]}
        model.update(self.root, self.req('required-aux', operation='edit', patch={'cues': m['cues']}))
        with self.assertRaisesRegex(ValueError, 'current verified'):
            model.update(self.root, self.req('confirm-old', operation='decision', kind='confirm-design',
                storyboardIds=board['storyboardIds'], source=source()))

    def test_requested_still_time_is_not_registered_as_the_design_frame_collection(self):
        from fractions import Fraction
        from scripts.hyperframes_adapter import parse_time
        from scripts.fcpxml_timing import format_time
        cue = load(self.root)['cues'][0]
        at = format_time(parse_time(cue['resolvedTimeline']['start']) + Fraction(1, 2))
        with patch('scripts.work_model_jobs.render_storyboard', side_effect=raster):
            result = model.preview(self.root, self.req('sample', scope='still', cueIds=[cue['id']], time=at))
        self.assertEqual(result['storyboardIds'], [])
        state = model.status(self.root)
        sample = next(a for a in state['artifacts'] if a['id'] == result['artifactIds'][0])
        self.assertEqual(sample['time'], '1/2s')
        self.assertTrue(sample['current'])
        self.assertEqual(load(self.root)['decisions'], [])


class PublicationIdentityTests(unittest.TestCase):
    setUp = jobs.JobTests.setUp
    req = jobs.JobTests.req

    def test_in_flight_storyboard_cannot_attach_to_replacement_object(self):
        before = load(self.root)
        cue_id = before['cues'][0]['id']
        def replace_object(snapshot, manifest, spec, output_dir, log_path):
            frames = raster(snapshot, manifest, spec, output_dir, log_path)
            model.update(self.root, self.req('replace-object', operation='edit', patch={},
                objectRelations={cue_id: {'kind': 'new', 'basis': {
                    'text': '这是新的独立创作对象', 'reference': 'fixture:replacement'}}}))
            return frames
        with patch('scripts.work_model_jobs.render_storyboard', side_effect=replace_object):
            with self.assertRaisesRegex(ValueError, 'inputs changed'):
                model.preview(self.root, self.req('in-flight', scope='storyboard', cueIds=[cue_id]))
        after = load(self.root)
        self.assertEqual(after['storyboards'], before['storyboards'])
        self.assertEqual(after['artifacts'], before['artifacts'])
        self.assertNotEqual(after['cues'][0]['objectId'], before['cues'][0]['objectId'])
        self.assertFalse(model.status(self.root)['storyboard']['cues'][0]['firstConfirmed'])

    def test_task_can_run_local_check_before_its_authorized_full_demo(self):
        ids = [c['id'] for c in load(self.root)['cues'] if c['productionMode'] == 'animation']
        model.update(self.root, self.req('full-commission', operation='decision', kind='authorize-demo',
            taskId='one-logical-task', cueIds=[ids[0]], presentationCueIds=ids, source=source('改 A 后给整版')))
        model.preview(self.root, self.req('local-check', scope='local', taskId='one-logical-task', cueIds=[ids[0]]))
        self.assertEqual(load(self.root)['productionRuns'], [])
        result = model.preview(self.root, {'requestId': 'finish-full', 'expectedRevision': load(self.root)['editRevision'],
            'scope': 'full', 'taskId': 'one-logical-task', 'workCueIds': [ids[0]]})
        self.assertIsNotNone(result['reviewSet'])
        with self.assertRaisesRegex(ValueError, 'completed production'):
            model.preview(self.root, {'requestId': 'future-full', 'expectedRevision': load(self.root)['editRevision'],
                'scope': 'full', 'taskId': 'one-logical-task', 'workCueIds': [ids[0]]})

    def test_explicit_local_work_does_not_modify_another_active_cue(self):
        m = load(self.root)
        target = self.root / m['cues'][-1]['renderAdapters']['hyperframes']['motionSrc']
        proposal = self.root / '.staging' / 'outside.js'
        proposal.parent.mkdir(exist_ok=True)
        proposal.write_text('// outside named work')
        with self.assertRaisesRegex(ValueError, 'creative cue scope'):
            model.update(self.root, self.req('outside-active-work', operation='edit', patch={},
                work={'mode': 'motion', 'cueIds': [m['cues'][0]['id']]},
                files=[{'path': target.relative_to(self.root).as_posix(), 'source': str(proposal)}]))

    def test_named_active_local_task_does_not_require_a_new_approval_fact(self):
        result = model.preview(self.root, self.req('named-local', scope='local', taskId='active-local-edit',
            cueIds=[load(self.root)['cues'][0]['id']]))
        self.assertEqual(result['status'], 'complete')
        self.assertEqual([d['kind'] for d in load(self.root)['decisions']], ['confirm-design'])


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        opened = model.open_project(Path(self.tmp.name) / 'AfterForge', {
            'requestId': 'open', 'expectedRevision': 0, 'episodeTitle': '首次设计'})
        self.root = Path(opened['root'])

    def req(self, name, **kw):
        return {'requestId': name, 'expectedRevision': load(self.root)['editRevision'], **kw}

    def test_empty_review_handoff_never_confirms_design(self):
        request = self.req('handoff', operation='review-submit', storyboardIds=[],
                           feedbackIds=[], drafts=[], source=source('这轮看完了'))
        first = model.update(self.root, request)
        self.assertEqual(model.update(self.root, request), first)
        state = model.status(self.root)
        self.assertEqual(state['decisions'], [])
        self.assertEqual(len(state['storyboard']['rounds']), 1)
        self.assertEqual(state['storyboard']['rounds'][0]['status'], 'submitted')

    def test_new_feedback_does_not_silently_join_submitted_round(self):
        target = {'versionId': load(self.root)['identity']['versionId']}
        first = model.update(self.root, self.req('a', operation='feedback', body='标题下移',
                    target=target, source=source()))['record']
        result = model.update(self.root, self.req('round', operation='review-submit',
                    storyboardIds=[], feedbackIds=[first['id']], drafts=[], source=source()))
        second = model.update(self.root, self.req('b', operation='feedback', body='还有颜色',
                    target=target, source=source()))['record']
        batch = model.status(self.root)['storyboard']['rounds'][0]
        self.assertEqual(batch['feedbackIds'], [first['id']])
        self.assertNotIn(second['id'], batch['feedbackIds'])

    def test_new_series_does_not_manufacture_truman_history(self):
        memory = next((Path(self.tmp.name) / 'AfterForge').rglob('创作记忆.md')).read_text()
        self.assertNotIn('《楚门》', memory)


if __name__ == '__main__':
    unittest.main()
