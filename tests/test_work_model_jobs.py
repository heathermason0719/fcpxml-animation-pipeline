"""Cache invalidation, interruption and approval boundaries of shared jobs."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import work_model as model
from scripts.work_model_store import load, save, sha
from scripts.work_model_inputs import cue_key
from tests.test_hyperframes_single_source import SingleSourceFixture
from tests.test_work_model_delivery import SOURCE
from tests.work_model_fixtures import activate, user, demo_request


class JobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name).resolve()
        legacy = base / 'legacy'
        legacy.mkdir()
        SingleSourceFixture().make_version(str(legacy))
        opened = model.open_project(base / 'AfterForge', {'requestId':'open','expectedRevision':0,'episodeTitle':'开场','copyFrom':str(legacy),'copyMode':'restart','commission':user('明确沿用旧设计创建测试副本')})
        self.root = Path(opened['root'])
        m = load(self.root)
        source = self.root / 'assets/source/Info.fcpxml'
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(SOURCE.replace(b'4s', b'10s'))
        media = self.root / m['project']['renderAdapters']['hyperframes']['previewMediaSrc']
        m['project']['source']['fcpxml'] = 'assets/source/Info.fcpxml'
        m['sourceHashes'] = {'fcpxml':sha(source),'referenceVideo':sha(media)}
        second = copy.deepcopy(m['cues'][0])
        second['id']='second'
        second.pop('objectId', None)
        second['resolvedTimeline']={'start':'2s','duration':'2s'}
        # Independent motion dependency permits meaningful incremental checks.
        p = self.root/'compositions/motion/second.js'
        p.write_text('// second motion')
        adapter = second['renderAdapters']['hyperframes']
        old_composition, old_motion = adapter['compositionSrc'], adapter['motionSrc']
        second_composition = 'compositions/cues/second.html'
        (self.root / second_composition).write_text((self.root / old_composition).read_text().replace(old_motion, p.relative_to(self.root).as_posix()))
        adapter['compositionSrc'] = second_composition
        adapter['layoutDependencies'] = [second_composition if path == old_composition else path for path in adapter['layoutDependencies']]
        second['renderAdapters']['hyperframes']['motionSrc']=p.relative_to(self.root).as_posix()
        m['cues'].append(second)
        save(self.root,m)
        self.calls=[]
        def render(root, manifest, cue, *, quality, target, log_path):
            self.calls.append((cue['id'],quality))
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((cue['id']+quality+cue_key(root,manifest,cue,quality)).encode())
            return {}
        def composite(root,manifest,overlays,*,start,duration,target,log_path):
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(('preview'+str(start)+str(duration)+str(overlays)).encode())
            return {}
        for name, impl in [('render_cue',render),('composite_preview',composite)]:
            p=patch('scripts.work_model_jobs.'+name,side_effect=impl)
            p.start();self.addCleanup(p.stop)
        p=patch('scripts.work_model_jobs._validate_media',return_value={'probe':{'width':1920,'height':1080,'r_frame_rate':'24','duration':'2'},'alpha':{'status':'valid'}})
        p.start();self.addCleanup(p.stop)
        if not getattr(self, 'cold_start', False):
            activate(self.root)
    def req(self,name,**kw):
        if kw.get('scope') == 'full' and not getattr(self, 'cold_start', False):
            return demo_request(self.root, name, **kw)
        return {'requestId':name,'expectedRevision':load(self.root)['editRevision'],**kw}
    def edit(self,name,mutate):
        m=load(self.root); mutate(m)
        return model.update(self.root,self.req(name,operation='edit',patch={'cues':m['cues'],'brief':m['brief']}))
    def test_active_full_review_uses_explicit_task_and_retry_reuses_media(self):
        request=self.req('full',scope='full')
        first=model.preview(self.root,request)
        self.assertEqual(len(self.calls),2)
        self.assertIsNotNone(model.status(self.root)['reviewSet'])
        self.assertEqual(model.preview(self.root,request),first)
        self.assertEqual([d['kind'] for d in load(self.root)['decisions']], ['confirm-design', 'authorize-demo'])
        self.assertEqual(len(self.calls),2)
    def test_prose_and_placement_reuse_but_motion_and_duration_rebuild(self):
        model.preview(self.root,self.req('full',scope='full'))
        review=model.status(self.root)['reviewSet']['id']
        self.edit('prose',lambda m:m['cues'][0].update(finalAnimationDescription='纯说明变化'))
        self.assertEqual(model.status(self.root)['reviewSet']['id'],review)
        self.edit('move',lambda m:m['cues'][0]['resolvedTimeline'].update(start='0s'))
        self.assertIsNone(model.status(self.root)['reviewSet'])
        model.preview(self.root,self.req('local',cueIds=[load(self.root)['cues'][0]['id']]))
        self.assertEqual(len(self.calls),2)
        self.edit('duration',lambda m:m['cues'][0]['resolvedTimeline'].update(duration='3s'))
        model.preview(self.root,self.req('duration-p',scope='full'))
        self.assertEqual(len(self.calls),3)
        m=load(self.root); motion=self.root/m['cues'][-1]['renderAdapters']['hyperframes']['motionSrc']
        motion.write_text('// changed motion')
        model.preview(self.root,self.req('motion-p',scope='full'))
        self.assertEqual(len(self.calls),4)
    def test_failed_job_resumes_and_preserves_concurrent_feedback(self):
        original=__import__('scripts.work_model_jobs',fromlist=['composite_preview']).composite_preview
        with patch('scripts.work_model_jobs.composite_preview',side_effect=ValueError('interrupted')):
            with self.assertRaisesRegex(ValueError,'interrupted'):
                model.preview(self.root,self.req('fail',scope='full'))
        task=model.status(self.root)['tasks'][0]
        identity=load(self.root)['identity']
        model.update(self.root,self.req('feedback',operation='feedback',body='标题向下',source={'channel':'chat','text':'标题向下','reference':'turn'},target={'versionId':identity['versionId']}))
        model.resume(self.root,self.req('resume',jobId=task['id']))
        self.assertEqual(len(self.calls),2)
        self.assertEqual(len(load(self.root)['feedback']),1)
    def test_stale_and_incomplete_artifacts_cannot_authorize(self):
        self.edit('draft',lambda m:m['cues'][0].update(status='draft'))
        model.preview(self.root,self.req('draft-p',scope='full',allowDraft=True))
        self.assertIsNone(model.status(self.root)['reviewSet'])
        with self.assertRaisesRegex(ValueError,'review|审阅'):
            model.deliver(self.root,self.req('bad'))
        self.edit('ready',lambda m:m['cues'][0].update(status='ready'))
        model.preview(self.root,self.req('ready-p',scope='full'))
        review=model.status(self.root)['reviewSet']
        with self.assertRaisesRegex(ValueError,'author|授权|approve'):
            model.deliver(self.root,self.req('unauthorized'))
        (self.root/load(self.root)['artifacts'][-1]['path']).write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError,'review|审阅'):
            model.update(self.root,self.req('stale',operation='decision',kind='approve-and-deliver',reviewSetId=review['id'],source={'channel':'chat','text':'交付这版','reference':'turn2'}))

if __name__=='__main__': unittest.main()

class DisplayCacheTests(unittest.TestCase):
    setUp=JobTests.setUp
    req=JobTests.req

    def test_display_cache_never_authorizes_tampered_media(self):
        import os
        model.preview(self.root,self.req('full',scope='full'))
        with patch('scripts.work_model.current_review_set',wraps=model.current_review_set) as check:
            current=model.status(self.root)
            model.status(self.root)
            self.assertEqual(check.call_count,1)
        artifact=load(self.root)['artifacts'][-1]
        path=self.root/artifact['path']; stat=path.stat()
        path.write_bytes(b'x'*stat.st_size)
        os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        with self.assertRaisesRegex(ValueError,'review'):
            model.update(self.root,self.req('approve',operation='decision',kind='approve',reviewSetId=current['reviewSet']['id'],source={'channel':'chat','text':'批准','reference':'test'}))

class ScopedInputTests(unittest.TestCase):
    setUp=JobTests.setUp
    req=JobTests.req

    def test_unused_asset_does_not_invalidate_and_declared_font_affects_only_one_cue(self):
        m=load(self.root)
        font=self.root/'assets/fonts/second.woff2';font.write_bytes(b'font-v1')
        m['cues'][-1]['renderAdapters']['hyperframes']['layoutDependencies'].append('assets/fonts/second.woff2')
        save(self.root,m)
        model.preview(self.root,self.req('full',scope='full'))
        review=model.status(self.root)['reviewSet']['id']
        (self.root/'assets/unused.jpg').write_bytes(b'unused bytes')
        self.assertEqual(model.status(self.root)['reviewSet']['id'],review)
        font.write_bytes(b'font-v2')
        self.assertIsNone(model.status(self.root)['reviewSet'])
        model.preview(self.root,self.req('changed-font',scope='full'))
        self.assertEqual(self.calls.count(('second','preview')),2)
        self.assertEqual(len(self.calls),3)
