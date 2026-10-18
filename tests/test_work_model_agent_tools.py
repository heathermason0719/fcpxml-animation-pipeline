"""Agent-facing projections and small writes retain the existing domain checks."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from scripts import work_model as model
from scripts.work_model_store import load
from tests import test_work_model_jobs as jobs
from tests import test_work_model_concepts as concepts
from tests.work_model_fixtures import request, user


class AgentQueryTests(unittest.TestCase):
    setUp = jobs.JobTests.setUp
    req = jobs.JobTests.req
    edit = jobs.JobTests.edit

    def test_cli_short_query_preserves_global_and_old_video_feedback(self):
        first=model.preview(self.root,self.req('first',scope='full'))
        cid=load(self.root)['cues'][0]['id'];vid=load(self.root)['identity']['versionId']
        for name,target in [('global',{}),('old',{'artifactId':first['artifactIds'][0],'cueIds':[cid],'timeStart':'1s'}),
                            ('range',{'timeStart':'2s','timeEnd':'3s'})]:
            model.update(self.root,self.req(name,operation='feedback',body=name,source=user(),target={'versionId':vid,**target}))
        self.edit('move',lambda m:m['cues'][0]['resolvedTimeline'].update(start='6s'))
        before=(self.root/'animation-manifest.json').read_bytes()
        proc=subprocess.run([sys.executable,'-B','scripts/afterforge.py','status',str(self.root),'--summary'],capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
        summary=json.loads(proc.stdout)
        self.assertEqual({f['body'] for f in summary['feedbackIndex']},{'global','old','range'})
        self.assertEqual(summary['workingIntent'],{'items':[]})
        self.assertNotIn('artifacts',summary)
        self.assertEqual((self.root/'animation-manifest.json').read_bytes(),before)
        detail=model.status(self.root,view='cue',cue_id=cid)
        self.assertEqual(detail['cue']['id'],cid)
        self.assertTrue({'global','old'}.issubset({f['body'] for f in detail['feedback']}))
        old=next(f for f in summary['feedbackIndex'] if f['body']=='old')
        self.assertEqual(model.status(self.root,view='feedback',feedback_id=old['id'])['feedback']['target']['artifactId'],first['artifactIds'][0])

    def test_old_video_opinion_stays_current_after_new_timing_and_can_commission(self):
        first=model.preview(self.root,self.req('first',scope='full'));m=load(self.root);cid=m['cues'][0]['id']
        note=model.update(self.root,self.req('old',operation='feedback',body='仍修改旧片 A',source=user(),
            target={'versionId':m['identity']['versionId'],'artifactId':first['artifactIds'][0],'cueIds':[cid],'timeStart':'1s'}))['record']
        self.edit('retime',lambda m:m['cues'][0]['resolvedTimeline'].update(start='6s'))
        model.preview(self.root,self.req('second',scope='full'))
        state=model.status(self.root);old=next(a for a in state['artifacts'] if a['id']==first['artifactIds'][0])
        self.assertFalse(old['current'])
        self.assertEqual(state['feedback'][0].get('applicability',{}).get('kind','current'),'current')
        model.update(self.root,self.req('rework',operation='review-submit',feedbackIds=[note['id']],artifactId=old['id'],
            decision={'kind':'authorize-demo','taskId':'old-rework','cueIds':[cid],'source':user()},source=user()))
        self.assertEqual(model.status(self.root)['storyboard']['productionRequest']['taskId'],'old-rework')

    def test_short_index_keeps_deferred_opinion_and_detail_returns_untruncated_source(self):
        text='原始意见不可丢失。'*80
        note=model.update(self.root,self.req('long',operation='feedback',body=text,source=user(text),
            target={'versionId':load(self.root)['identity']['versionId']}))['record']
        model.update(self.root,self.req('defer',operation='feedback-applicability',feedbackId=note['id'],kind='deferred',source=user('后续处理')))
        summary=model.status(self.root,view='summary');row=summary['feedbackIndex'][0]
        self.assertTrue(row['bodyTruncated'])
        self.assertEqual(row['applicability']['kind'],'deferred')
        self.assertEqual(row['appliesToCueIds'],[])
        detail=model.status(self.root,view='feedback',feedback_id=note['id'])['feedback']
        self.assertEqual(detail['body'],text)
        self.assertEqual(detail['source']['text'],text)

    def test_missing_detail_and_nonstatus_flags_cannot_fall_back_or_write(self):
        before=(self.root/'animation-manifest.json').read_bytes()
        for opts in ({'view':'cue','cue_id':'missing'},{'view':'feedback','feedback_id':'missing'},
                     {'view':'summary','cue_id':'wrong-view'}):
            with self.subTest(opts=opts),self.assertRaises(ValueError):
                model.status(self.root,**opts)
        result=subprocess.run([sys.executable,'-B','scripts/afterforge.py','preview',str(self.root),'--summary'],capture_output=True,text=True)
        self.assertEqual(result.returncode,2)
        self.assertEqual((self.root/'animation-manifest.json').read_bytes(),before)

    def test_latest_preview_in_summary_does_not_hide_a_newer_local_result(self):
        model.preview(self.root,self.req('full',scope='full'))
        cid=load(self.root)['cues'][0]['id']
        latest=model.preview(self.root,self.req('local',scope='local',cueIds=[cid]))
        self.assertEqual(model.status(self.root,view='summary')['latestPreview']['id'],latest['artifactIds'][0])


class CueUpdateTests(unittest.TestCase):
    setUp = jobs.JobTests.setUp
    req = jobs.JobTests.req

    def test_partial_edit_preserves_omitted_fields_and_replaces_arrays(self):
        before=load(self.root);cid=before['cues'][0]['id']
        payload=self.req('partial',operation='edit',cueUpdates=[{'cueId':cid,'changes':{
            'finalAnimationDescription':'修改这条说明','resolvedTimeline':{'start':'1/2s'},'screenText':['替换文案']}}])
        result=model.update(self.root,payload)
        self.assertEqual(model.update(self.root,payload),result)
        after=load(self.root)
        self.assertEqual(after['cues'][1],before['cues'][1])
        self.assertEqual(after['cues'][0]['renderAdapters'],before['cues'][0]['renderAdapters'])
        self.assertEqual(after['cues'][0]['resolvedTimeline']['duration'],before['cues'][0]['resolvedTimeline']['duration'])
        self.assertEqual(after['cues'][0]['screenText'],['替换文案'])
        self.assertEqual(after['cues'][0]['objectId'],before['cues'][0]['objectId'])
        self.assertEqual(after['editRevision'],before['editRevision']+1)

    def test_invalid_or_ambiguous_partial_edit_is_atomic(self):
        before=load(self.root);cid=before['cues'][0]['id']
        cases=[{'cueUpdates':[{'cueId':'missing','changes':{'title':'x'}}]},
               {'cueUpdates':[{'cueId':cid,'changes':{'id':'renamed'}}]},
               {'cueUpdates':[{'cueId':cid,'changes':{'objectId':'another'}}]},
               {'cueUpdates':[{'cueId':cid,'changes':{'resolvedTimeline':{'duration':'-1s'}}}]},
               {'cueUpdates':[{'cueId':cid,'changes':{'title':'x'}},{'cueId':cid,'changes':{'title':'y'}}]},
               {'cueUpdates':[{'cueId':cid,'changes':[{'op':'remove','path':'/title'}]}]},
               {'cueUpdates':[{'cueId':cid,'changes':{'title':'x'}}],'patch':{'cues':before['cues']}}]
        for index,extra in enumerate(cases):
            with self.subTest(index=index),self.assertRaises(ValueError):
                model.update(self.root,self.req('invalid-'+str(index),operation='edit',**extra))
            self.assertEqual(load(self.root),before)

    def test_partial_cue_does_not_hide_shared_source_impact(self):
        before=load(self.root);cid=before['cues'][0]['id']
        staged=self.root/'.staging/frame.md';staged.parent.mkdir(exist_ok=True);staged.write_text('changed shared visual defaults')
        with self.assertRaisesRegex(ValueError,'shared dependency|scope'):
            model.update(self.root,self.req('shared',operation='edit',cueUpdates=[{'cueId':cid,'changes':{'title':'只改 A'}}],
                files=[{'path':'frame.md','source':str(staged)}],work={'cueIds':[cid]}))
        self.assertEqual(load(self.root),before)


class ConceptBatchTests(unittest.TestCase):
    setUp = concepts.ConceptTests.setUp

    def item(self,name,cue='poster',recommend=False):
        path=self.root/'.staging'/name;path.parent.mkdir(exist_ok=True);path.write_bytes(concepts.png_bytes())
        return {'cueId':cue,'imageSource':str(path),'origin':{'kind':'user-imported','reference':'fixture:'+name},
                'idea':'关系图','motion':'逐一出现','recommend':recommend}

    def test_batch_keeps_all_candidates_and_explicit_recommendation_without_confirmation(self):
        items=[self.item('one',recommend=True),self.item('two'),self.item('three','map')]
        payload=request(self.root,'batch',operation='concept',action='register-batch',items=items)
        result=model.update(self.root,payload)
        self.assertEqual(model.update(self.root,payload),result)
        m=load(self.root);self.assertEqual(len(m['concepts']),3)
        self.assertEqual([c['origin']['reference'] for c in m['concepts']],['fixture:one','fixture:two','fixture:three'])
        state=model.status(self.root)['conceptDesign']['cues']
        self.assertEqual(state[0]['recommendedId'],result['record'][0]['id'])
        self.assertIsNone(state[1]['recommendedId'])
        self.assertTrue(all(not c['firstConfirmed'] for c in state))
        self.assertEqual(m['decisions'],[])

    def test_bad_later_image_or_duplicate_recommendation_rolls_back_whole_batch(self):
        items=[self.item('one',recommend=True),self.item('two',recommend=True)]
        before=load(self.root)
        for label,values in [('two-recommendations',items),('missing-recommend',[{k:v for k,v in items[0].items() if k!='recommend'}]),
                             ('adopt',[{**items[0],'adopt':True}])]:
            with self.subTest(label=label),self.assertRaises(ValueError):
                model.update(self.root,request(self.root,label,operation='concept',action='register-batch',items=values))
            self.assertEqual(load(self.root),before)
        items[1]['recommend']=False;Path(items[1]['imageSource']).write_bytes(b'invalid image')
        with self.assertRaises(ValueError):
            model.update(self.root,request(self.root,'bad-image',operation='concept',action='register-batch',items=items))
        self.assertEqual(load(self.root),before)
        self.assertEqual(list((self.root/'assets/concepts').glob('*')),[])
        with self.assertRaisesRegex(ValueError,'cannot adopt'):
            model.update(self.root,request(self.root,'outer-adopt',operation='concept',action='register-batch',adopt=True,items=[items[0]]))
        self.assertEqual(load(self.root),before)

    def test_schema_publication_failure_rolls_back_all_candidate_images(self):
        items=[self.item('one'),self.item('two')];before=load(self.root)
        with patch('scripts.work_model.save',side_effect=ValueError('publication failed')):
            with self.assertRaisesRegex(ValueError,'publication failed'):
                model.update(self.root,request(self.root,'fail-save',operation='concept',action='register-batch',items=items))
        self.assertEqual(load(self.root),before)
        self.assertEqual(list((self.root/'assets/concepts').glob('*')),[])
