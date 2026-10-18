"""The reviewed movie owns feedback and the next commission, even after edits."""
from scripts import work_model as model
from scripts.work_model_store import load
from tests import test_work_model_jobs as jobs
from tests.work_model_fixtures import user


import unittest


class DemoReworkTests(unittest.TestCase):
    setUp = jobs.JobTests.setUp
    req = jobs.JobTests.req
    edit = jobs.JobTests.edit
    # Reuse setup, without inheriting the job suite here.
    def test_reviewed_demo_freezes_mapping_and_rework_scope(self):
        first = model.preview(self.root, self.req('movie-one', scope='full'))
        movie = next(a for a in load(self.root)['artifacts'] if a['id'] == first['artifactIds'][0])
        self.assertEqual(movie['reviewCues'][0]['resolvedTimeline']['start'], load(self.root)['cues'][0]['resolvedTimeline']['start'])
        original = load(self.root)['cues'][0]['id']
        self.edit('move', lambda m: m['cues'][0]['resolvedTimeline'].update(start='6s'))
        model.preview(self.root, self.req('movie-two', scope='full'))
        note = model.update(self.root, self.req('note', operation='feedback', body='慢一点', source=user(),
            target={'versionId':load(self.root)['identity']['versionId'], 'artifactId':movie['id'],
                    'cueIds':[original], 'timeStart':'1s'}))['record']
        request = self.req('revise', operation='review-submit', storyboardIds=[], feedbackIds=[note['id']],
            artifactId=movie['id'], decision={'kind':'authorize-demo', 'taskId':'revision-task', 'cueIds':[original],
                                             'source':user('按这些意见修改并更新 Demo')}, source=user())
        receipt = model.update(self.root, request)
        self.assertEqual(model.update(self.root, request), receipt)
        pending = model.status(self.root)['storyboard']['productionRequest']
        self.assertEqual(pending['taskId'], 'revision-task')
        self.assertEqual(pending['cueIds'], [original])
        self.assertEqual(pending['presentationCueIds'], movie['coverage']['presentedCueIds'])
        self.assertEqual(pending['reviewArtifactId'], movie['id'])
        self.assertEqual(pending['status'], 'pending')
        self.assertEqual(len([d for d in load(self.root)['decisions'] if d.get('taskId') == 'revision-task']), 1)

    def test_already_submitted_round_can_be_explicitly_commissioned(self):
        result=model.preview(self.root,self.req('one',scope='full'))
        movie=result['artifactIds'][0]
        note=model.update(self.root,self.req('note',operation='feedback',body='改这条',source=user(),
            target={'versionId':load(self.root)['identity']['versionId'],'artifactId':movie}))['record']
        submitted=model.update(self.root,self.req('submit',operation='review-submit',feedbackIds=[note['id']],source=user()))['record']
        cid=load(self.root)['cues'][0]['id']
        model.update(self.root,self.req('commission-saved',operation='review-submit',roundId=submitted['id'],feedbackIds=[note['id']],artifactId=movie,
            decision={'kind':'authorize-demo','taskId':'saved-round','cueIds':[cid],'source':user()},source=user()))
        self.assertEqual(len(load(self.root)['reviewRounds']),1)
        self.assertEqual(model.status(self.root)['storyboard']['productionRequest']['taskId'],'saved-round')

    def test_unmapped_old_movie_accepts_time_only_and_mapped_movie_rejects_wrong_scene(self):
        from scripts.work_model_store import save
        result=model.preview(self.root,self.req('one',scope='full'))
        m=load(self.root);movie=next(a for a in m['artifacts'] if a['id']==result['artifactIds'][0])
        movie.pop('reviewCues');save(self.root,m)
        note=model.update(self.root,self.req('unmapped',operation='feedback',body='仍可留言',source=user(),
            target={'versionId':m['identity']['versionId'],'artifactId':movie['id'],'timeStart':'1s'}))['record']
        self.assertFalse(note['target'].get('cueIds'))
        self.assertFalse(note['target'].get('objectIds'))
        mapped=model.preview(self.root,self.req('two',scope='full'))
        with self.assertRaisesRegex(ValueError,'reviewed artifact time'):
            model.update(self.root,self.req('wrong-scene',operation='feedback',body='不能套新版',source=user(),
                target={'versionId':m['identity']['versionId'],'artifactId':mapped['artifactIds'][0],'timeStart':'1s','cueIds':['second']}))

    def test_rework_does_not_transfer_a_reviewed_scope_to_reused_cue_identity(self):
        from scripts.work_model_feedback import rework_decision
        result=model.preview(self.root,self.req('one',scope='full'));m=load(self.root)
        note=model.update(self.root,self.req('note',operation='feedback',body='修改旧对象',source=user(),
            target={'versionId':m['identity']['versionId'],'artifactId':result['artifactIds'][0]}))['record']
        m=load(self.root);m['cues'][0]['objectId']='a-different-product'
        with self.assertRaisesRegex(ValueError,'product scope changed'):
            rework_decision(self.root,m,{'artifactId':result['artifactIds'][0],
                'decision':{'kind':'authorize-demo','taskId':'new','cueIds':[m['cues'][0]['id']],'source':user()}}, {'id':'round','feedbackIds':[note['id']]})

    def test_plain_submit_has_no_commission_and_mixed_movie_rework_rolls_back(self):
        first=model.preview(self.root,self.req('one',scope='full'))
        second=model.preview(self.root,self.req('two',scope='full'))
        notes=[]
        for n, result in enumerate([first,second]):
            notes.append(model.update(self.root,self.req('note'+str(n),operation='feedback',body='改',source=user(),
                target={'versionId':load(self.root)['identity']['versionId'],'artifactId':result['artifactIds'][0]}))['record']['id'])
        before=load(self.root)
        with self.assertRaisesRegex(ValueError,'reviewed|artifact'):
            model.update(self.root,self.req('mixed',operation='review-submit',storyboardIds=[],feedbackIds=notes,
                artifactId=first['artifactIds'][0],decision={'kind':'authorize-demo','taskId':'new','cueIds':[], 'source':user()},source=user()))
        self.assertEqual(load(self.root),before)
        model.update(self.root,self.req('plain',operation='review-submit',feedbackIds=notes,source=user()))
        self.assertEqual(load(self.root)['decisions'],before['decisions'])
