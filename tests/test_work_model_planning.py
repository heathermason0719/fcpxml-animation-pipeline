"""Recover creative discussions and bound autonomous image calls, not production."""
import copy
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from scripts import work_model as model
from scripts.work_model_store import load
from tests.work_model_fixtures import request, user
from tests.test_work_model_concepts import png_bytes


class PlanningTests(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).resolve().parents[1] / 'work/review-integration-20261018/creative-planning-20261023/tmp'
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(model.open_project(Path(self.temp.name) / 'AfterForge',
            {'requestId': 'open', 'expectedRevision': 0, 'episodeTitle': 'Synthetic planning'})['root'])
        cues = [{'id': cid, 'productionMode': 'animation', 'title': cid,
                 'purpose': '解释人物的观察关系', 'visualPlan': '人物通过视线连接',
                 'narrationAnchor': '有人观察，也有人被观察', 'screenText': ['观察关系'],
                 'finalAnimationDescription': '先出现人物，再连起视线',
                 'renderAdapters': {'hyperframes': {'compositionId': cid,
                    'compositionSrc': f'compositions/cues/{cid}.html'}}} for cid in ('A', 'B')]
        model.update(self.root, request(self.root, 'cues', operation='edit', patch={'cues': cues}))
        self.serial = 0

    def update(self, action, **kwargs):
        self.serial += 1
        return model.update(self.root, request(self.root, f'planning-{self.serial}',
            operation='creative-planning', action=action, **kwargs))['record']

    def present(self, **kwargs):
        return self.update('present', summary='A 展示人物关系，B 展示观察方向',
                           question='以上是完整制作清单，还有需要新增的吗？', **kwargs)

    def align(self, **kwargs):
        plan = self.present(**kwargs)
        self.update('close', planId=plan['id'], source=user('没有新增，按这份清单开始生图'))
        return plan

    def begin(self, targets=None):
        return self.update('begin-image', targets=targets or [
            {'cueId': 'A', 'directionId': 'diagram', 'direction': '简洁关系图', 'kind': 'direction'}])

    def register(self, attempt=None, cue='A', name='candidate', recommend=False):
        self.serial += 1
        image = self.root / '.staging' / f'{self.serial}.png'
        image.parent.mkdir(exist_ok=True)
        image.write_bytes(png_bytes())
        extra = {'planningAttemptId': attempt['id']} if attempt else {}
        return model.update(self.root, request(self.root, f'image-{self.serial}', operation='concept', action='register',
            cueId=cue, imageSource=str(image), origin={'kind':'codex-generated' if attempt else 'user-imported',
            'reference':'fixture:tool-result'}, idea=name, motion='逐个出现', recommend=recommend, **extra))['record']

    def finish(self, attempt, disposition='continue', resolved=None, count=1):
        evaluations = []
        for target in attempt['targets']:
            cue = next(c for c in load(self.root)['cues'] if c['objectId'] == target['objectId'])
            ids = [self.register(attempt, cue=cue['id'])['id'] for _ in range(count)]
            row = {'objectId': target['objectId'], 'conceptIds': ids, 'disposition': disposition,
                   'note': '合成测试结果，不代表真实生图或审美验收'}
            if resolved is not None:
                row['problemResolved'] = resolved
            evaluations.append(row)
        return self.update('finish-image', attemptId=attempt['id'], outcome='generated',
            toolReference='fixture:tool-'+attempt['id'], note='实际工具调用的模拟回执', evaluations=evaluations)

    def state(self):
        return model.status(self.root)['creativePlanning']

    def test_discussion_waits_for_reply_and_restores_current_and_replaced_ideas(self):
        before_files = {p.relative_to(self.root) for p in self.root.rglob('*.md')}
        plan = self.present()
        self.assertEqual([o['state'] for o in self.state()['objects']], ['waiting-response', 'waiting-response'])
        with self.assertRaisesRegex(ValueError, 'discussion|reply'):
            self.begin()
        self.update('close', planId=plan['id'], source=user('没有新增，开始生图'))
        self.assertEqual(self.state()['objects'][0]['state'], 'ready')
        model.update(self.root, request(self.root, 'opinion', operation='feedback', body='后面再调颜色',
            source=user(), target={'versionId':load(self.root)['identity']['versionId']}))
        self.assertEqual(self.state()['objects'][0]['state'], 'ready')
        model.update(self.root, request(self.root, 'change-idea', operation='edit',
            cueUpdates=[{'cueId':'A','changes':{'visualPlan':'改为嵌套窗口'}}]))
        self.assertEqual(self.state()['objects'][0]['state'], 'needs-discussion')
        replacement = self.present(cueIds=['A'])
        self.update('close', planId=replacement['id'], source=user('A 就用嵌套窗口，其余保持'))
        state = self.state()
        self.assertEqual(state['objects'][0]['planId'], replacement['id'])
        self.assertEqual(state['objects'][1]['planId'], plan['id'])
        old = state['history']['plans'][0]
        self.assertEqual(old['objects'][0]['content']['visualPlan'], '人物通过视线连接')
        self.assertEqual(old['supersededObjectIds'], [state['objects'][0]['objectId']])
        detail = model.status(self.root,view='cue',cue_id='A')['creativePlanning']
        self.assertEqual(len(detail['objects']), 1)
        self.assertEqual(len(detail['history']['plans']), 2)
        summary = model.status(self.root,view='summary')['creativePlanning']
        self.assertNotIn('history',summary)
        self.assertEqual(summary['objects'][0]['planId'],replacement['id'])
        self.assertEqual({p.relative_to(self.root) for p in self.root.rglob('*.md')}, before_files)

    def test_new_object_invalidates_whole_list_reply_without_blocking_ordinary_edit(self):
        plan=self.align()
        cues=copy.deepcopy(load(self.root)['cues']);new=copy.deepcopy(cues[0]);new.update(id='C');new.pop('objectId')
        model.update(self.root,request(self.root,'add-object',operation='edit',patch={'cues':cues+[new]},
            objectRelations={'C':{'kind':'new','basis':{'text':'用户新增一条','reference':'fixture:add'}}}))
        with self.assertRaisesRegex(ValueError,'changed|scope'):
            self.update('close',planId=plan['id'],source=user('这是旧回复'))
        self.assertEqual(self.state()['objects'][-1]['state'],'unrecorded')
        self.assertEqual(load(self.root)['decisions'],[])

    def test_nine_calls_include_failures_and_retries_but_not_receipt_retries(self):
        self.align()
        for index in range(9):
            attempt=self.begin()
            payload=request(self.root,'failed-'+str(index),operation='creative-planning',action='finish-image',
                attemptId=attempt['id'],outcome='failed',toolReference=f'fixture:call-{index}',note='工具实际失败')
            result=model.update(self.root,payload)
            self.assertEqual(model.update(self.root,payload),result)
        state=self.state()['rounds'][0]
        self.assertEqual(state['actualCalls'],9)
        self.assertEqual(state['pendingCalls'],0)
        self.assertEqual(state['state'],'stopped')
        with self.assertRaisesRegex(ValueError,'9|limit'):
            self.begin()
        self.register(name='超限后外部候选仍可归档')
        self.assertEqual(self.state()['rounds'][0]['actualCalls'],9)
        self.update('continue',cueIds=['A'],source=user('再开一轮，继续探索'))
        self.assertEqual(self.state()['rounds'][0]['actualCalls'],0)
        self.begin()

    def test_pending_call_blocks_restart_and_not_called_releases_reservation(self):
        self.align();attempt=self.begin()
        self.assertEqual(self.state()['rounds'][0]['pendingCalls'],1)
        self.assertEqual(self.state()['rounds'][0]['actualCalls'],0)
        with self.assertRaisesRegex(ValueError,'pending|unresolved'):
            self.begin()
        with self.assertRaisesRegex(ValueError,'pending|unresolved'):
            self.update('continue',cueIds=['A'],source=user('继续'))
        self.update('finish-image',attemptId=attempt['id'],outcome='not-called',note='确认工具未发出')
        self.assertEqual(self.state()['rounds'][0]['pendingCalls'],0)
        self.begin()

    def test_three_directions_stop_and_multiple_images_count_one_call(self):
        self.align()
        for index in range(3):
            attempt=self.begin([{'cueId':'A','directionId':f'd{index}','direction':f'方向 {index}','kind':'direction'}])
            self.finish(attempt,count=2)
        round_state=self.state()['rounds'][0]
        self.assertEqual(round_state['actualCalls'],3)
        self.assertEqual(round_state['directionCount'],3)
        self.assertEqual(len(load(self.root)['concepts']),6)
        with self.assertRaisesRegex(ValueError,'direction|limit'):
            self.begin()

    def test_three_unsolved_corrections_stop_but_resolved_problem_resets_streak(self):
        self.align();self.finish(self.begin())
        target={'cueId':'A','directionId':'diagram','direction':'简洁关系图','kind':'correction',
                'problemId':'crowded','problem':'人物和标注重叠'}
        self.finish(self.begin([target]),resolved=False)
        self.finish(self.begin([target]),resolved=True)
        for _ in range(3):
            self.finish(self.begin([target]),resolved=False)
        self.assertEqual(self.state()['rounds'][0]['problemStreaks'],{'crowded':3})
        self.assertEqual(self.state()['rounds'][0]['directionCount'],1)
        with self.assertRaisesRegex(ValueError,'correction|limit'):
            self.begin([target])

    def test_multi_object_call_uses_one_slot_each_and_rename_keeps_round(self):
        self.align()
        targets=[{'cueId':cid,'directionId':'diagram','direction':'简洁关系图','kind':'direction'} for cid in ('A','B')]
        attempt=self.begin(targets);self.finish(attempt)
        self.assertEqual([r['actualCalls'] for r in self.state()['rounds']],[1,1])
        old=load(self.root);cues=copy.deepcopy(old['cues']);oid=cues[0]['objectId'];cues[0]['id']='renamed'
        model.update(self.root,request(self.root,'rename',operation='edit',patch={'cues':cues},
            objectRelations={'renamed':{'kind':'continue','objectId':oid,'basis':{'text':'同一个动画技术改名','reference':'fixture:rename'}}}))
        self.assertEqual(self.state()['rounds'][0]['actualCalls'],1)
        self.assertEqual(self.state()['objects'][0]['state'],'ready')

    def test_satisfactory_result_ends_early_and_metadata_keeps_concept_confirmation(self):
        self.align();attempt=self.begin();self.finish(attempt,disposition='satisfied')
        self.assertEqual(self.state()['rounds'][0]['actualCalls'],1)
        with self.assertRaisesRegex(ValueError,'stopped|ended'):
            self.begin()
        first=self.register(name='明确采用',recommend=True)
        model.update(self.root,request(self.root,'confirm',operation='decision',kind='confirm-concept',
            conceptIds=[first['id']],source=user('确认这张')))
        before=copy.deepcopy(load(self.root))
        self.update('continue',cueIds=['A'],source=user('继续探索图片，不改变已确认方向'))
        after=load(self.root)
        for key in ('cues','creativeObjects','decisions','artifacts','reviewSets','productionRuns'):
            self.assertEqual(after[key],before[key])
        staged=self.root/'.staging/layout.html';staged.write_text('<div data-composition-id="A">观察关系</div>')
        model.update(self.root,request(self.root,'ordinary-production',operation='edit',
            files=[{'path':'compositions/cues/A.html','source':str(staged)}]))

    def test_stale_generated_result_is_archived_without_replacing_recommendation(self):
        self.align();current=self.register(name='现有推荐',recommend=True);attempt=self.begin()
        model.update(self.root,request(self.root,'changed-during-call',operation='edit',
            cueUpdates=[{'cueId':'A','changes':{'visualPlan':'现在改为嵌套窗口'}}]))
        late=self.register(attempt,name='迟到候选',recommend=True)
        self.assertTrue((self.root/late['path']).is_file())
        self.assertEqual(model.status(self.root)['conceptDesign']['cues'][0]['recommendedId'],current['id'])
        self.assertEqual(late['planningAttemptId'],attempt['id'])
        before=(self.root/'animation-manifest.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'stale|current|selection'):
            model.update(self.root,request(self.root,'propose-late',operation='concept',action='propose',conceptId=late['id']))
        self.assertEqual((self.root/'animation-manifest.json').read_bytes(),before)

    def test_registered_output_cannot_be_reconciled_as_not_called(self):
        self.align()
        attempt=self.begin([{'cueId':cid,'directionId':'diagram','direction':'简洁关系图','kind':'direction'} for cid in ('A','B')])
        self.register(attempt,cue='B',recommend=False)
        before=(self.root/'animation-manifest.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'registered|output'):
            self.update('finish-image',attemptId=attempt['id'],outcome='not-called',note='错误清零')
        self.assertEqual((self.root/'animation-manifest.json').read_bytes(),before)
        self.assertEqual([r['pendingCalls'] for r in self.state()['rounds']],[1,1])

    def test_user_selection_during_call_is_preserved_and_current_finished_images_can_be_proposed(self):
        self.align();initial=self.register(recommend=True);chosen=self.register(name='用户选择')
        attempt=self.begin()
        model.update(self.root,request(self.root,'select-during-call',operation='concept',action='select',
            conceptId=chosen['id'],source=user('采用这一张')))
        late=self.register(attempt,recommend=True)
        self.assertEqual(model.status(self.root)['conceptDesign']['cues'][0]['recommendedId'],chosen['id'])
        with self.assertRaisesRegex(ValueError,'stale|current|selection'):
            model.update(self.root,request(self.root,'propose-after-select',operation='concept',action='propose',conceptId=late['id']))
        self.finish(attempt)
        next_attempt=self.begin();result=self.finish(next_attempt)
        good=result['outcome']['evaluations'][0]['conceptIds'][0]
        model.update(self.root,request(self.root,'propose-valid',operation='concept',action='propose',conceptId=good))
        self.assertEqual(model.status(self.root)['conceptDesign']['cues'][0]['recommendedId'],good)

    def test_old_version_queries_do_not_create_planning_or_rewrite_manifest(self):
        before=(self.root/'animation-manifest.json').read_bytes()
        self.assertEqual(self.state()['history']['plans'],[])
        self.assertEqual((self.root/'animation-manifest.json').read_bytes(),before)
        self.assertNotIn('creativePlanning',load(self.root))

    def test_conflicting_preflights_cannot_reserve_two_calls_and_retry_is_idempotent(self):
        self.align()
        payload=request(self.root,'reserve',operation='creative-planning',action='begin-image',targets=[
            {'cueId':'A','directionId':'diagram','direction':'简洁关系图','kind':'direction'}])
        def invoke(value):
            try:
                return model.update(self.root,value)
            except ValueError as error:
                return str(error)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(invoke,[payload,{**payload,'requestId':'conflict'}]))
        self.assertEqual(sum(isinstance(r,dict) for r in responses),1)
        self.assertTrue(any('stale revision' in r for r in responses if isinstance(r,str)))
        saved=next(r for r in responses if isinstance(r,dict))
        winner=payload if isinstance(responses[0],dict) else {**payload,'requestId':'conflict'}
        before=(self.root/'animation-manifest.json').read_bytes()
        self.assertEqual(model.update(self.root,winner),saved)
        self.assertEqual((self.root/'animation-manifest.json').read_bytes(),before)
        self.assertEqual(self.state()['rounds'][0]['pendingCalls'],1)

    def test_invalid_second_target_and_false_tool_receipt_are_atomic(self):
        self.align()
        before=(self.root/'animation-manifest.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'correction'):
            self.begin([{'cueId':'A','directionId':'first','direction':'关系图','kind':'direction'},
                        {'cueId':'B','directionId':'unseen','direction':'未生成','kind':'correction',
                         'problemId':'text','problem':'文字拥挤'}])
        self.assertEqual((self.root/'animation-manifest.json').read_bytes(),before)
        attempt=self.begin();before=(self.root/'animation-manifest.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'toolReference'):
            self.update('finish-image',attemptId=attempt['id'],outcome='failed',note='无调用来源不能说实际失败')
        self.assertEqual((self.root/'animation-manifest.json').read_bytes(),before)


class PlanningMediaIsolationTests(unittest.TestCase):
    def setUp(self):
        from tests.test_work_model_jobs import JobTests
        JobTests.setUp(self)

    def test_planning_does_not_invalidate_render_review_or_historical_policy(self):
        from scripts.work_model_inputs import cue_key, timeline_inputs
        before=load(self.root)
        cue_keys=[cue_key(self.root,before,c) for c in before['cues'] if c['productionMode']=='animation']
        timeline=timeline_inputs(self.root,before)
        boards=copy.deepcopy(model.status(self.root)['storyboard']['cues'])
        plan=model.update(self.root,request(self.root,'present-plan',operation='creative-planning',action='present',
            summary='讨论这两个既有动画',question='还有新增吗？'))['record']
        model.update(self.root,request(self.root,'close-plan',operation='creative-planning',action='close',
            planId=plan['id'],source=user('没有新增')))
        after=load(self.root)
        self.assertEqual(after['workModelVersion'],'2.1.0')
        self.assertEqual([cue_key(self.root,after,c) for c in after['cues'] if c['productionMode']=='animation'],cue_keys)
        self.assertEqual(timeline_inputs(self.root,after),timeline)
        self.assertEqual(model.status(self.root)['storyboard']['cues'],boards)
        for key in ('creativeObjects','cues','concepts','decisions','artifacts','reviewSets','productionRuns'):
            self.assertEqual(after.get(key),before.get(key))
        self.assertEqual(self.calls,[])


if __name__ == '__main__':
    unittest.main()
