"""Source ownership, not a motion filename or animation keyword, gates publication."""
import copy
import unittest
from unittest.mock import patch
from pathlib import Path
from scripts import work_model as model
from scripts.work_model_store import load, sha
from tests import test_work_model_jobs as jobs
from tests.work_model_fixtures import raster, user

class SourcePublicationTests(unittest.TestCase):
    cold_start=True
    setUp=jobs.JobTests.setUp
    req=jobs.JobTests.req

    def publish(self,name,files,**extra):
        staged=[]
        for i,(path,text) in enumerate(files.items()):
            source=self.root/'.staging'/name/str(i);source.parent.mkdir(parents=True,exist_ok=True);source.write_text(text)
            staged.append({'path':path,'source':str(source)})
        return model.update(self.root,self.req(name,operation='edit',patch=extra.pop('patch',{}),files=staged,**extra))

    def test_cold_inline_and_equivalent_sources_are_rejected_without_any_decisions(self):
        path=load(self.root)['cues'][0]['renderAdapters']['hyperframes']['compositionSrc'];before=(self.root/path).read_text()
        cases={
          'gsap':'<script>gsap.timeline().to("#root",{x:200});</script>',
          'waapi':'<script>document.body.animate([{opacity:0},{opacity:1}],2000);</script>',
          'css':'<style>#root{animation:enter 2s}@keyframes enter{to{opacity:1}}</style>',
          'style-attribute':'<div style="animation:enter 2s">x</div>',
          'svg':'<svg><animate attributeName="opacity" from="0" to="1" dur="2s" /></svg>',
          'loader':'<script src="compositions/helpers/plain.txt"></script>',
        }
        for name,addition in cases.items():
            with self.subTest(name=name):
                files={path:before+addition}
                if name=='loader': files['compositions/helpers/plain.txt']='document.body.animate([{opacity:0},{opacity:1}],2000);'
                with self.assertRaisesRegex(ValueError,'first|首次|Motion|motion'):
                    self.publish(name,files)
                self.assertEqual((self.root/path).read_text(),before)
                self.assertEqual(load(self.root)['decisions'],[])

    def test_detaching_motion_declaration_does_not_hide_its_changed_dependency(self):
        m=load(self.root);cue=m['cues'][0];motion=cue['renderAdapters']['hyperframes'].pop('motionSrc');before=sha(self.root/motion)
        with self.assertRaisesRegex(ValueError,'first|首次|Motion|motion'):
            self.publish('detach',{motion:'const tl=gsap.timeline();tl.to("#root",{x:400});'},patch={'cues':m['cues']})
        self.assertEqual(sha(self.root/motion),before)

    def test_static_layout_change_does_not_require_first_confirmation(self):
        path=load(self.root)['cues'][0]['renderAdapters']['hyperframes']['compositionSrc']
        self.publish('font',{path:(self.root/path).read_text().replace('标题','较小的真实标题')})
        self.assertIn('较小的真实标题',(self.root/path).read_text())
        self.assertEqual(load(self.root)['decisions'],[])

    def test_active_motion_and_bounded_exploration_preserve_publication_freedom(self):
        model.update(self.root,self.req('enroll',operation='edit',patch={}))
        m=load(self.root);first,second=[c for c in m['cues'] if c['productionMode']=='animation']
        # Scope to the independent second Motion file; the first layout is shared.
        model.update(self.root,self.req('explore',operation='decision',kind='explore-motion',taskId='one-cue',cueIds=[second['id']],source=user('只试做第二条')))
        motion=second['renderAdapters']['hyperframes']['motionSrc']
        self.publish('explore-src',{motion:'const timeline=gsap.timeline({paused:true});'},work={'taskId':'one-cue','cueIds':[second['id']]})
        self.assertFalse(any(d['kind']=='confirm-design' for d in load(self.root)['decisions']))
        with patch('scripts.work_model_jobs.render_storyboard',side_effect=raster):
            b=model.preview(self.root,self.req('boards',scope='storyboard'))
        model.update(self.root,self.req('confirm',operation='decision',kind='confirm-design',storyboardIds=b['storyboardIds'],source=user('确认这两个静态设计')))
        self.publish('active-src',{motion:'const timeline=gsap.timeline({paused:true});timeline.to("#title",{x:4});'},work={'cueIds':[second['id']]})
        self.assertTrue(all(c['firstConfirmed'] for c in model.status(self.root)['storyboard']['cues']))

    def test_true_open_without_motion_rejects_inline_publication_and_keeps_static_edit(self):
        result=model.open_project(Path(self.tmp.name)/'true-cold',{'requestId':'fresh','expectedRevision':0,'episodeTitle':'从零'})
        self.root=Path(result['root'])
        cue={'id':'A','productionMode':'animation','screenText':['标题'],'finalAnimationDescription':'标题保持',
             'renderAdapters':{'hyperframes':{'compositionId':'A','compositionSrc':'compositions/A.html','layoutDependencies':[]}}}
        self.publish('layout',{'compositions/A.html':'<div>标题</div>'},patch={'cues':[cue]})
        with self.assertRaisesRegex(ValueError,'first|首次'):
            self.publish('inline',{'compositions/A.html':'<div>标题</div><script>document.body.animate([],2000)</script>'})
        self.assertEqual(load(self.root)['decisions'],[])
        self.assertEqual((self.root/'compositions/A.html').read_text(),'<div>标题</div>')

    def test_orphan_motion_and_candidate_workspace_cannot_publish_unowned_motion(self):
        with self.assertRaisesRegex(ValueError,'canonical Cue owner'):
            self.publish('orphan',{'compositions/orphan.js':'buildWholeMovie();'})
        m=load(self.root);candidate=copy.deepcopy(m['cues'][0]);candidate.pop('objectId',None)
        relative='compositions/explorations/visual/a.html'
        candidate['renderAdapters']['hyperframes']={'compositionId':'a','compositionSrc':relative,'layoutDependencies':[]}
        staged=self.root/'.staging/candidate.html';staged.parent.mkdir(exist_ok=True);staged.write_text('<script>buildWholeMovie()</script>')
        with self.assertRaisesRegex(ValueError,'exploration cannot publish Motion|static markup contains executable'):
            model.update(self.root,self.req('candidate',operation='exploration',exploration={'id':'visual','question':'比较字号',
                'variants':[{'id':'a','label':'A','cues':[candidate]}]},files=[{'path':relative,'source':str(staged)}]))
        self.assertFalse((self.root/relative).exists())

    def test_runtime_vendor_replacement_uses_same_cold_boundary(self):
        vendor=self.root/'assets/vendor/gsap.min.js';before=sha(vendor)
        with patch('scripts.work_model_runtime.runtime_files',return_value={'assets/vendor/gsap.min.js':b'buildWholeMovie();'}):
            with self.assertRaisesRegex(ValueError,'first|首次'):
                model.update(self.root,self.req('vendor',operation='runtime',version='0.8.26'))
        self.assertEqual(sha(vendor),before)

    def test_existing_detached_script_attachment_cannot_hide_behind_unchanged_bytes(self):
        m=load(self.root);cue=m['cues'][0];path=cue['renderAdapters']['hyperframes']['compositionSrc']
        helper=self.root/'compositions/detached.js';helper.write_text('animateAll();')
        with self.assertRaisesRegex(ValueError,'first|首次'):
            self.publish('attach',{path:(self.root/path).read_text()+'<script src="compositions/detached.js"></script>'})

    def test_authorized_full_source_update_uses_creative_scope_not_presentation_as_changed_set(self):
        with patch('scripts.work_model_jobs.render_storyboard',side_effect=raster):
            b=model.preview(self.root,self.req('boards',scope='storyboard'))
        model.update(self.root,self.req('confirm',operation='decision',kind='confirm-design',storyboardIds=b['storyboardIds'],source=user('确认所有静帧')))
        cues=[c for c in load(self.root)['cues'] if c['productionMode']=='animation'];ids=[c['id'] for c in cues]
        model.update(self.root,self.req('task',operation='decision',kind='authorize-demo',taskId='edit-and-full',cueIds=ids[:1],presentationCueIds=ids,source=user('只改 A，给整版')))
        motion=cues[0]['renderAdapters']['hyperframes']['motionSrc']
        self.publish('full-source',{motion:'const tl=gsap.timeline({paused:true});'},work={'scope':'full','cueIds':ids[:1],'taskId':'edit-and-full'})
        self.assertEqual(load(self.root)['productionRuns'],[])
        with self.assertRaisesRegex(ValueError,'shared dependency'):
            self.publish('global',{'frame.md':'new font for every cue'},work={'cueIds':ids[:1]})
