"""Confirmation audit regressions through the shared work-model fixtures."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts import work_model as model
from scripts.work_model_confirmation import apply_feedback_resolutions, confirmation_problems
from scripts.work_model_store import load
from tests import test_work_model_jobs as jobs
from tests.work_model_fixtures import raster, user


class ConfirmationAuditTests(unittest.TestCase):
    cold_start = True
    setUp = jobs.JobTests.setUp
    req = jobs.JobTests.req

    def test_linked_segment_narration_is_real_review_content_and_invalidates_snapshot(self):
        m=load(self.root);cue=m['cues'][0]
        for key in ('narration', 'narrationAnchor', 'screenText'):
            cue.pop(key,None)
        cue['segmentIds']=['narration-one']
        cue['contentContext']={
            'narration': {'state': 'present'},
            'screenText': {'state': 'none', 'basis': {
                'text': '本 fixture 只验证关联旁白，不制作屏幕文字。',
                'reference': 'fixture:linked-segment',
            }},
        }
        m['brief']['segments']=[{'id':'narration-one','narration':'来自实际关联段落的旁白'}]
        model.update(self.root,self.req('linked',operation='edit',patch={'cues':m['cues'],'brief':m['brief']}))
        with patch('scripts.work_model_jobs.render_storyboard',side_effect=raster):
            result=model.preview(self.root,self.req('linked-board',scope='storyboard',cueIds=[cue['id']]))
        card=next(c for c in model.status(self.root)['storyboard']['cues'] if c['id']==cue['id'])
        self.assertEqual(card['narration'],'来自实际关联段落的旁白')
        self.assertTrue(card['canConfirm'])
        from scripts.work_model_inputs import cue_key
        before=cue_key(self.root,load(self.root),load(self.root)['cues'][0])
        m=load(self.root);m['brief']['segments'][0]['narration']='修改过的旁白'
        model.update(self.root,self.req('narration-edit',operation='edit',patch={'brief':m['brief']}))
        self.assertFalse(model.status(self.root)['storyboard']['cues'][0]['canConfirm'])
        self.assertEqual(cue_key(self.root,load(self.root),load(self.root)['cues'][0]),before)
        with self.assertRaisesRegex(ValueError,'current verified'):
            model.update(self.root,self.req('stale-linked-confirm',operation='decision',kind='confirm-design',storyboardIds=result['storyboardIds'],source=user('确认旧旁白')))

    def boards(self):
        model.update(self.root, self.req('enrol', operation='edit', patch={}))
        with patch('scripts.work_model_jobs.render_storyboard', side_effect=raster):
            result = model.preview(self.root, self.req('boards', scope='storyboard'))
        manifest = load(self.root)
        return manifest, [next(board for board in manifest['storyboards'] if board['id'] == key)
                          for key in result['storyboardIds']]

    def feedback(self, manifest, name, *, target=None, status='pending', applicability=None):
        record = {
            'id': name, 'body': name, 'source': user(name, 'fixture:' + name),
            'target': target or {'versionId': manifest['identity']['versionId']},
            'status': status, 'createdAt': '2026-09-19T00:00:00Z',
        }
        if applicability:
            record['applicability'] = {'kind': applicability, 'source': user('scope', 'fixture:scope')}
        manifest['feedback'].append(record)
        return record

    def add_feedback(self, name, cue_id):
        identity = load(self.root)['identity']
        return model.update(self.root, self.req('feedback-' + name, operation='feedback', body=name,
            source=user(name, 'fixture:' + name), target={
                'versionId': identity['versionId'], 'cueIds': [cue_id]}))

    def confirm(self, name, boards, **extra):
        return model.update(self.root, self.req(name, operation='decision', kind='confirm-design',
            storyboardIds=[board['id'] for board in boards], source=user('确认设计', 'fixture:' + name), **extra))

    def test_current_storyboard_requires_description_content_and_open_feedback(self):
        manifest, boards = self.boards()
        cue = next(c for c in manifest['cues'] if c['id'] == boards[0]['cueId'])
        boards[0]['finalAnimationDescription'] = '   '
        cue.pop('narrationAnchor', None)
        cue.pop('narration', None)
        cue['screenText'] = []
        self.feedback(manifest, 'pending', target={'versionId': manifest['identity']['versionId'],
                      'storyboardId': boards[0]['id'], 'artifactId': boards[0]['artifactIds'][0],
                      'frameId': next(a for a in manifest['artifacts'] if a['id'] == boards[0]['artifactIds'][0])['frameId'],
                      'cueIds': [cue['id']]})
        self.feedback(manifest, 'clarify', target={'versionId': manifest['identity']['versionId'],
                      'cueIds': [cue['id']]}, status='needs-clarification')
        problems = confirmation_problems(self.root, manifest, boards)
        self.assertEqual({item['code'] for item in problems}, {
            'storyboard-not-current', 'missing-final-animation-description',
            'unknown-narration-content', 'unknown-screen-text-content', 'unresolved-feedback'})
        blocker = next(item for item in problems if item['code'] == 'unresolved-feedback')
        self.assertEqual(blocker['feedbackIds'], ['clarify', 'pending'])

    def test_screen_text_content_requires_actual_text_or_content_fields(self):
        from scripts.work_model_content import content_context
        manifest = {'brief': {'segments': []}}
        self.assertEqual(content_context(manifest, {'screenText': [{'text': '屏幕文字'}]})['screenText']['state'], 'present')
        self.assertEqual(content_context(manifest, {'screenText': [{'content': '屏幕文字'}]})['screenText']['state'], 'present')
        self.assertEqual(content_context(manifest, {'screenText': [{'id': 'not-copy', 'role': 'title'}]})['screenText']['state'], 'unknown')

    def test_old_frame_feedback_still_blocks_but_unrelated_and_deferred_do_not(self):
        manifest, boards = self.boards()
        selected = boards[0]
        other = boards[1]
        self.feedback(manifest, 'old-frame', target={'versionId': manifest['identity']['versionId'],
                      'storyboardId': selected['id'], 'artifactId': selected['artifactIds'][0],
                      'frameId': next(a for a in manifest['artifacts'] if a['id'] == selected['artifactIds'][0])['frameId'],
                      'cueIds': [selected['cueId']]})
        self.feedback(manifest, 'other', target={'versionId': manifest['identity']['versionId'],
                      'cueIds': [other['cueId']]})
        self.feedback(manifest, 'later', target={'versionId': manifest['identity']['versionId'],
                      'cueIds': [selected['cueId']]}, applicability='deferred')
        problems = confirmation_problems(self.root, manifest, [selected])
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]['feedbackIds'], ['old-frame'])

    def test_resolution_batch_is_scoped_atomic_and_preserves_addressed_status(self):
        manifest, boards = self.boards()
        selected = boards[0]
        other = boards[1]
        target = {'versionId': manifest['identity']['versionId'], 'cueIds': [selected['cueId']]}
        self.feedback(manifest, 'accept-me', target=target)
        self.feedback(manifest, 'defer-me', target=target)
        self.feedback(manifest, 'addressed', target=target, status='addressed')
        self.feedback(manifest, 'other', target={'versionId': manifest['identity']['versionId'], 'cueIds': [other['cueId']]})
        request = {'source': user('本轮处理意见', 'fixture:resolution'), 'feedbackResolutions': [
            {'feedbackId': 'accept-me', 'action': 'accept'},
            {'feedbackId': 'defer-me', 'action': 'defer'},
        ]}
        self.assertEqual(apply_feedback_resolutions(manifest, request, [selected]), request['feedbackResolutions'])
        records = {item['id']: item for item in manifest['feedback']}
        self.assertEqual(records['accept-me']['status'], 'accepted')
        self.assertEqual(records['accept-me']['acceptedSource'], request['source'])
        self.assertEqual(records['defer-me']['applicability']['kind'], 'deferred')
        self.assertEqual(records['addressed']['status'], 'addressed')
        self.feedback(manifest, 'valid-next', target=target)
        snapshot = [dict(item) for item in manifest['feedback']]
        with self.assertRaisesRegex(ValueError, 'confirmation object|duplicate'):
            apply_feedback_resolutions(manifest, {'source': user(), 'feedbackResolutions': [
                {'feedbackId': 'valid-next', 'action': 'accept'},
                {'feedbackId': 'other', 'action': 'withdraw'},
            ]}, [selected])
        self.assertEqual(manifest['feedback'], snapshot)

    def test_currentness_failure_does_not_revoke_existing_confirmation_history(self):
        manifest, boards = self.boards()
        model.update(self.root, self.req('confirm', operation='decision', kind='confirm-design',
            storyboardIds=[boards[0]['id']], source=user('确认设计')))
        manifest = load(self.root)
        cue = next(c for c in manifest['cues'] if c['id'] == boards[0]['cueId'])
        cue['finalAnimationDescription'] = 'changed'
        self.assertTrue(any(d['kind'] == 'confirm-design' for d in manifest['decisions']))
        self.assertTrue(any(item['code'] == 'storyboard-not-current'
                            for item in confirmation_problems(self.root, manifest, [boards[0]])))

    def test_status_and_confirm_design_reject_open_feedback(self):
        _, boards = self.boards()
        self.add_feedback('open-feedback', boards[0]['cueId'])
        state = model.status(self.root)
        card = next(item for item in state['storyboard']['cues'] if item['storyboardId'] == boards[0]['id'])
        self.assertFalse(card['canConfirm'])
        with self.assertRaisesRegex(ValueError, 'feedback|confirmation|确认'):
            self.confirm('reject-open', [boards[0]])
        self.assertEqual(load(self.root)['decisions'], [])

    def test_withdraw_and_confirm_are_one_successful_transaction(self):
        _, boards = self.boards()
        self.add_feedback('withdraw-me', boards[0]['cueId'])
        record = self.confirm('withdraw-confirm', [boards[0]], feedbackResolutions=[
            {'feedbackId': next(item['id'] for item in load(self.root)['feedback'] if item['body'] == 'withdraw-me'),
             'action': 'withdraw'}])
        manifest = load(self.root)
        self.assertEqual(record['record']['feedbackResolutions'][0]['action'], 'withdraw')
        self.assertEqual(manifest['feedback'][0]['applicability']['kind'], 'not-applicable')
        self.assertEqual([item['kind'] for item in manifest['decisions']], ['confirm-design'])

    def test_confirmation_batch_conflict_and_remaining_blocker_leave_no_partial_save(self):
        _, boards = self.boards()
        selected, other = boards
        self.add_feedback('selected', selected['cueId'])
        self.add_feedback('other', other['cueId'])
        before = load(self.root)
        selected_id = next(item['id'] for item in before['feedback'] if item['body'] == 'selected')
        other_id = next(item['id'] for item in before['feedback'] if item['body'] == 'other')
        with self.assertRaisesRegex(ValueError, 'confirmation object|反馈|feedback'):
            self.confirm('conflicting-batch', [selected], feedbackResolutions=[
                {'feedbackId': selected_id, 'action': 'withdraw'},
                {'feedbackId': other_id, 'action': 'withdraw'}])
        after = load(self.root)
        self.assertEqual(after['feedback'], before['feedback'])
        self.assertEqual(after['decisions'], before['decisions'])

        # A valid resolution also rolls back if a second applicable comment
        # remains open and therefore keeps the confirmation blocked.
        self.add_feedback('remaining', selected['cueId'])
        remaining_before = load(self.root)
        with self.assertRaisesRegex(ValueError, 'feedback|confirmation|确认'):
            self.confirm('remaining-blocker', [selected], feedbackResolutions=[
                {'feedbackId': selected_id, 'action': 'withdraw'}])
        self.assertEqual(load(self.root)['feedback'], remaining_before['feedback'])

    def test_blank_description_snapshot_rejects_confirmation_after_public_edit_and_board(self):
        for index, value in enumerate((None, '', '   ')):
            manifest = load(self.root)
            cue = manifest['cues'][0]
            cue.pop('finalAnimationDescription', None)
            if value is not None:
                cue['finalAnimationDescription'] = value
            model.update(self.root, self.req('description-' + str(index), operation='edit', patch={'cues': manifest['cues']}))
            with patch('scripts.work_model_jobs.render_storyboard', side_effect=raster):
                result = model.preview(self.root, self.req('board-' + str(index), scope='storyboard', cueIds=[cue['id']]))
            board = next(item for item in load(self.root)['storyboards'] if item['id'] == result['storyboardIds'][0])
            with self.assertRaisesRegex(ValueError, 'description|confirmation|确认'):
                self.confirm('blank-' + str(index), [board])

    def test_active_confirmation_keeps_motion_edit_available_and_handoff_is_not_approval(self):
        _, boards = self.boards()
        self.confirm('active', [boards[1]])
        manifest = load(self.root)
        cue = next(item for item in manifest['cues'] if item['id'] == boards[1]['cueId'])
        original = self.root / cue['renderAdapters']['hyperframes']['motionSrc']
        staged = self.root / '.staging' / 'active-motion.js'
        staged.parent.mkdir(exist_ok=True)
        staged.write_text('// explicitly changed active motion')
        model.update(self.root, self.req('active-motion', operation='edit', patch={},
            work={'mode': 'motion', 'cueIds': [cue['id']]},
            files=[{'path': original.relative_to(self.root).as_posix(), 'source': str(staged)}]))
        model.update(self.root, self.req('handoff', operation='review-submit', storyboardIds=[boards[1]['id']],
            feedbackIds=[], drafts=[], source=user('交棒给下一轮', 'fixture:handoff')))
        decisions = load(self.root)['decisions']
        self.assertEqual([item['kind'] for item in decisions], ['confirm-design'])


if __name__ == '__main__':
    unittest.main()
