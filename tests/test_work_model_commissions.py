"""Task goals and explicit object continuity are not inferred from job success."""
import copy
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import work_model as model
from scripts.work_model_store import load, save, sha, atomic_json
from tests import test_work_model_jobs as jobs
from tests.work_model_fixtures import raster, request, user


class CommissionTests(unittest.TestCase):
    cold_start = True
    setUp = jobs.JobTests.setUp
    req = jobs.JobTests.req

    def confirm(self, ids, name):
        with patch('scripts.work_model_jobs.render_storyboard', side_effect=raster):
            boards = model.preview(self.root, self.req(name+'-board', scope='storyboard', cueIds=ids))
        model.update(self.root, self.req(name+'-confirm', operation='decision', kind='confirm-design',
            storyboardIds=boards['storyboardIds'], source=user('确认指定镜头')))

    def enroll(self):
        model.update(self.root, self.req('enroll', operation='edit', patch={}))
        return [c['id'] for c in load(self.root)['cues'] if c['productionMode']=='animation']

    def authorize(self, ids, excluded=()):
        model.update(self.root, self.req('authorize', operation='decision', kind='authorize-demo', taskId='one-task',
            cueIds=[], presentationCueIds=[i for i in ids if i not in excluded], excludedCueIds=list(excluded), source=user('按这些呈现对象给整版')))

    def test_full_goal_is_not_filtered_before_first_qualification_and_reuses_task_after_confirmation(self):
        ids=self.enroll();self.confirm(ids[:1],'a');self.authorize(ids)
        before=load(self.root)
        with self.assertRaisesRegex(ValueError,'target|目标|first|首次'):
            model.preview(self.root,self.req('too-early',scope='full',taskId='one-task',workCueIds=[]))
        self.assertEqual(self.calls,[])
        self.assertEqual(load(self.root)['productionRuns'],[])
        self.assertEqual(load(self.root)['artifacts'],before['artifacts'])
        self.confirm(ids[1:],'b')
        result=model.preview(self.root,self.req('finish',scope='full',taskId='one-task',workCueIds=[]))
        self.assertIsNotNone(result['reviewSet'])
        self.assertEqual(len(load(self.root)['productionRuns']),1)
        with self.assertRaisesRegex(ValueError,'completed production'):
            model.preview(self.root,self.req('another',scope='full',taskId='one-task'))

    def test_missing_implementation_is_not_silently_removed_and_draft_does_not_finish_task(self):
        ids=self.enroll();self.confirm(ids,'both');self.authorize(ids)
        m=load(self.root);path=self.root/m['cues'][-1]['renderAdapters']['hyperframes']['motionSrc'];original=path.read_bytes();path.unlink()
        with self.assertRaisesRegex(ValueError,'target|目标|missing'):
            model.preview(self.root,self.req('missing',scope='full',taskId='one-task'))
        draft=model.preview(self.root,self.req('draft',scope='full',taskId='one-task',allowDraft=True))
        self.assertIsNone(draft['reviewSet'])
        self.assertEqual(load(self.root)['productionRuns'],[])
        path.write_bytes(original)
        complete=model.preview(self.root,self.req('after-repair',scope='full',taskId='one-task'))
        self.assertIsNotNone(complete['reviewSet'])

    def test_explicit_exclusion_can_finish_commission_without_being_a_complete_review(self):
        ids=self.enroll();self.confirm(ids[:1],'a');self.authorize(ids,ids[1:])
        result=model.preview(self.root,self.req('exclude',scope='full',taskId='one-task',excludedCueIds=ids[1:]))
        self.assertIsNone(result['reviewSet'])
        self.assertEqual(len(load(self.root)['productionRuns']),1)
        self.assertEqual({cid for cid,_ in self.calls},set(ids[:1]))
        self.assertIsNone(model.status(self.root)['reviewSet'])

    def test_false_historical_completion_is_corrected_without_rewriting_old_run(self):
        ids=self.enroll();self.confirm(ids,'both');self.authorize(ids)
        m=load(self.root)
        old={'taskId':'one-task','jobId':'job-old-incomplete','inputKey':'old-input','createdAt':'old'}
        m['productionRuns'].append(old)
        # A faithful old job/artifact records success of A-only, not the A+B goal.
        m['artifacts'].append({'id':'old-artifact','kind':'full-preview','path':'previews/old.mp4','sha256':'0'*64,
            'inputKey':'old-input','range':{'start':'0s','duration':'10s'},'cueIds':ids[:1],'complete':False,
            'missingCueIds':ids[1:],'excludedCueIds':[], 'eventId':'job-old-incomplete'})
        save(self.root,m)
        atomic_json(self.root/'jobs/job-old-incomplete.json',{'id':'job-old-incomplete','status':'complete',
            'request':{'scope':'full','taskId':'one-task'},'result':{'artifactIds':['old-artifact']}})
        r=model.preview(self.root,self.req('recover-unfinished',scope='full',taskId='one-task'))
        self.assertIsNotNone(r['reviewSet'])
        current=load(self.root)
        self.assertEqual(current['productionRuns'][0],old)
        self.assertEqual(current['artifacts'][len(m['artifacts'])-1],m['artifacts'][-1])
        self.assertTrue(current.get('productionCorrections'))

    def test_explicit_cross_version_continuity_preserves_qualification_only(self):
        ids=self.enroll();self.confirm(ids,'both')
        source=load(self.root);before=sha(self.root/'animation-manifest.json')
        relations={c['id']:{'kind':'continue','sourceObjectId':c['objectId']} for c in source['cues'] if c['productionMode']=='animation'}
        result=model.open_project(Path(self.tmp.name)/'continued',{'requestId':'continue','expectedRevision':0,
            'episodeTitle':'继续设计','copyFrom':str(self.root),'commission':user('沿用首次资格继续制作'), 'objectContinuity':relations})
        target=Path(result['root']);current=load(target)
        self.assertTrue(all(c['firstConfirmed'] for c in model.status(target)['storyboard']['cues']))
        self.assertEqual(current['decisions'],[])
        self.assertEqual(current['reviewSets'],[])
        self.assertEqual(current['productionRuns'],[])
        self.assertEqual(sha(self.root/'animation-manifest.json'),before)
        renamed=copy.deepcopy(current['cues']);renamed[0]['id']='technical-rename';oid=renamed[0].pop('objectId')
        model.update(target,request(target,'rename',operation='edit',patch={'cues':renamed},objectRelations={
            'technical-rename':{'kind':'continue','objectId':oid,'basis':{'text':'同对象改名','reference':'test'}}}))
        self.assertTrue(model.status(target)['storyboard']['cues'][0]['firstConfirmed'])

    def test_cross_version_restart_mixed_and_ambiguous_are_distinct(self):
        ids=self.enroll();self.confirm(ids,'both');m=load(self.root)
        common={'requestId':'copy','expectedRevision':0,'episodeTitle':'新版本','copyFrom':str(self.root),'commission':user('复制此版')}
        with self.assertRaisesRegex(ValueError,'continuity|关系|copyMode'):
            model.open_project(Path(self.tmp.name)/'ambiguous',common)
        restarted=model.open_project(Path(self.tmp.name)/'restart',{**common,'copyMode':'restart'})
        self.assertFalse(any(c['firstConfirmed'] for c in model.status(restarted['root'])['storyboard']['cues']))
        relations={ids[0]:{'kind':'continue','sourceObjectId':m['cues'][0]['objectId']},ids[1]:{'kind':'new'}}
        mixed=model.open_project(Path(self.tmp.name)/'mixed',{**common,'objectContinuity':relations})
        self.assertEqual([c['firstConfirmed'] for c in model.status(mixed['root'])['storyboard']['cues']],[True,False])
        relations[ids[0]]['sourceObjectId']='nonexistent'
        with self.assertRaisesRegex(ValueError,'source object|源对象'):
            model.open_project(Path(self.tmp.name)/'bad-source',{**common,'objectContinuity':relations})

    def test_first_writer_enrolls_identity_without_approvals_and_read_is_unchanged(self):
        m=load(self.root);m['workModelVersion']='2.0.0'
        for key in ('creativeObjects','storyboards','reviewRounds','explorations','productionRuns'):m.pop(key,None)
        for cue in m['cues']:cue.pop('objectId',None)
        save(self.root,m);before=sha(self.root/'animation-manifest.json');model.status(self.root)
        self.assertEqual(sha(self.root/'animation-manifest.json'),before)
        req=self.req('first-feedback',operation='feedback',body='改字体',source=user('改字体'),target={'versionId':m['identity']['versionId']})
        result=model.update(self.root,req);enrolled=load(self.root)
        self.assertEqual(enrolled['workModelVersion'],'2.1.0')
        self.assertEqual(len(enrolled['creativeObjects']),2)
        self.assertEqual(enrolled['decisions'],[])
        self.assertTrue(all(c.get('objectId') for c in enrolled['cues'] if c['productionMode']=='animation'))
        self.assertEqual(model.update(self.root,req),result)
        self.assertEqual(load(self.root)['creativeObjects'],enrolled['creativeObjects'])
        with patch('scripts.work_model_jobs.render_storyboard',side_effect=raster):
            boards=model.preview(self.root,self.req('first-boards',scope='storyboard'))
        self.assertEqual(len(boards['storyboardIds']),2)

    def test_first_preview_enrollment_has_stable_snapshot_and_failed_writer_rolls_back(self):
        m=load(self.root);m['workModelVersion']='2.0.0'
        for key in ('creativeObjects','storyboards','reviewRounds','explorations','productionRuns'):m.pop(key,None)
        for cue in m['cues']:cue.pop('objectId',None)
        save(self.root,m);before=sha(self.root/'animation-manifest.json')
        with self.assertRaises(ValueError):
            model.update(self.root,self.req('invalid-feedback',operation='feedback',body='',target={}))
        self.assertEqual(sha(self.root/'animation-manifest.json'),before)
        with patch('scripts.work_model_jobs.render_storyboard',side_effect=raster):
            boards=model.preview(self.root,self.req('first-preview',scope='storyboard'))
        self.assertEqual(len(boards['storyboardIds']),2)
        self.assertEqual(len(load(self.root)['creativeObjects']),2)
        self.assertEqual(load(self.root)['decisions'],[])

    def test_partial_bounded_time_sample_does_not_consume_exploration_goal(self):
        ids=self.enroll()
        model.update(self.root,self.req('limited',operation='decision',kind='explore-motion',taskId='limited',
            cueIds=ids[:1],range={'start':'0s','duration':'4s'},source=user('只试第一条，给 0 到 4 秒')))
        sample=model.preview(self.root,self.req('sample',scope='local',taskId='limited',cueIds=ids[:1],range={'start':'1s','duration':'1s'}))
        self.assertEqual(sample['status'],'complete')
        self.assertEqual(load(self.root)['productionRuns'],[])
        goal=model.preview(self.root,self.req('goal',scope='local',taskId='limited',cueIds=ids[:1],range={'start':'0s','duration':'4s'}))
        self.assertEqual(goal['status'],'complete')
        self.assertEqual(len(load(self.root)['productionRuns']),1)

    def test_unconfirmed_cross_version_continuation_and_second_generation_never_invent_qualification(self):
        ids=self.enroll();self.confirm(ids[:1],'a')
        origin=self.root
        for index in range(2):
            m=load(origin)
            relations={c['id']:{'kind':'continue','sourceObjectId':c['objectId']} for c in m['cues'] if c['productionMode']=='animation'}
            result=model.open_project(Path(self.tmp.name)/('generation'+str(index)),{'requestId':'continue','expectedRevision':0,
                'episodeTitle':'继续','copyFrom':str(origin),'commission':user('同一创作对象继续'), 'objectContinuity':relations})
            origin=Path(result['root'])
            self.assertEqual([c['firstConfirmed'] for c in model.status(origin)['storyboard']['cues']],[True,False])
            self.assertEqual(load(origin)['decisions'],[])

    def test_old_writer_transaction_failure_does_not_persist_half_enrollment(self):
        m=load(self.root);m['workModelVersion']='2.0.0'
        for key in ('creativeObjects','storyboards','reviewRounds','explorations','productionRuns'):m.pop(key,None)
        for cue in m['cues']:cue.pop('objectId',None)
        save(self.root,m);before=sha(self.root/'animation-manifest.json')
        with patch('scripts.work_model.save',side_effect=ValueError('injected schema save failure')):
            with self.assertRaisesRegex(ValueError,'injected'):
                model.update(self.root,self.req('save-fail',operation='feedback',body='字号',source=user('字号'),target={'versionId':m['identity']['versionId']}))
        self.assertEqual(sha(self.root/'animation-manifest.json'),before)
