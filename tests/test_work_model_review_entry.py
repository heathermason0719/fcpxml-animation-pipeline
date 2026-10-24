"""CLI handoff never changes a completed production receipt or rerenders."""
import copy
import io
import json
import tempfile
import subprocess
from pathlib import Path
from contextlib import redirect_stdout
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch
from scripts import work_model as model
from scripts.work_model_review_entry import handoff
import unittest
from tests import test_work_model_jobs as jobs
from tests import test_work_model_concepts as concepts
from tests.work_model_fixtures import request
from scripts.work_model_store import load

RUN_ROOT = Path(__file__).resolve().parents[1] / 'work/review-integration-20261018/creative-planning-20261023/review-entry'


def fixture_setup(test, setup):
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    with patch.object(tempfile, 'tempdir', str(RUN_ROOT)):
        setup(test)


class ReviewEntryTests(unittest.TestCase):
    def setUp(self):
        fixture_setup(self, jobs.JobTests.setUp)
    req = jobs.JobTests.req
    def test_unavailable_service_preserves_movie_and_original_result(self):
        result=model.preview(self.root,self.req('movie',scope='full'))
        original=copy.deepcopy(result)
        with patch('scripts.work_model_review_entry._verified_service',return_value=None), patch(
                'scripts.work_model_review_entry.subprocess.Popen',side_effect=OSError('service unavailable')):
            response=handoff(self.root,result)
        self.assertEqual(result,original)
        self.assertEqual(response['status'],'complete')
        self.assertFalse(response['reviewEntry']['available'])
        self.assertIn('service unavailable',response['reviewEntry']['error'])
        self.assertEqual(response['reviewEntry']['artifactId'],result['artifactIds'][0])

    def test_live_entry_uses_this_movie_and_service_identity(self):
        first=model.preview(self.root,self.req('first',scope='full'))
        model.preview(self.root,self.req('second',scope='full'))
        with patch('scripts.work_model_review_entry._verified_service',return_value='http://127.0.0.1:12345'), patch(
                'scripts.work_model_review_entry.subprocess.Popen') as start:
            response=handoff(self.root,first)
        start.assert_not_called()
        self.assertIn(first['artifactIds'][0],response['reviewEntry']['url'])
        self.assertEqual(response['artifactIds'],first['artifactIds'])
        self.assertEqual([t['artifactId'] for t in response['reviewEntry']['targets']], first['artifactIds'])

    def test_missing_explicit_video_is_retained_instead_of_selecting_another_result(self):
        result=model.preview(self.root,self.req('movie',scope='full'))
        result['artifactIds'].insert(0, 'missing-result')
        response=handoff(self.root,result,start_service=False)
        self.assertEqual(response['reviewEntry']['artifactId'], 'missing-result')
        self.assertEqual([t['artifactId'] for t in response['reviewEntry']['targets']], result['artifactIds'])

    def test_local_and_storyboard_targets_keep_all_exact_result_ids(self):
        for scope in ('storyboard', 'local'):
            with self.subTest(scope=scope):
                result = model.preview(self.root, self.req('target-' + scope, scope=scope, cueIds=[load(self.root)['cues'][0]['id']]))
                response = handoff(self.root, result, start_service=False)
                targets = response['reviewEntry']['targets']
                expected = result['storyboardIds'] if scope == 'storyboard' else result['artifactIds']
                field = 'storyboardId' if scope == 'storyboard' else 'artifactId'
                self.assertEqual(list(dict.fromkeys(t[field] for t in targets)), expected)
                self.assertTrue(all(t['versionId'] == load(self.root)['identity']['versionId'] for t in targets))
                self.assertTrue(all(t['cueId'] for t in targets) if scope == 'storyboard' else all(t['kind'] == 'local-preview' for t in targets))
                if scope == 'local':
                    self.assertEqual([t['cueId'] for t in targets], ['p1s01_c01_title', 'second'])

    def test_storyboard_history_projection_keeps_original_text_and_images(self):
        first = model.preview(self.root, self.req('old-board', scope='storyboard'))
        before = model.status(self.root)['storyboard']['cues'][0]
        cues = copy.deepcopy(load(self.root)['cues'])
        cues[0]['finalAnimationDescription'] = 'New explanation'
        model.update(self.root, self.req('new-text', operation='edit', patch={'cues': cues}))
        model.preview(self.root, self.req('new-board', scope='storyboard'))
        snapshots = model.status(self.root)['storyboard']['snapshots']
        old = next(s for s in snapshots if s['storyboardId'] == first['storyboardIds'][0])
        self.assertEqual(old['finalAnimationDescription'], before['finalAnimationDescription'])
        self.assertEqual([f['artifactId'] for f in old['frames']], [f['artifactId'] for f in before['frames']])
        self.assertFalse(old['current'])
        self.assertFalse(old['canConfirm'])

    def test_actual_local_handoff_replaces_each_cached_scene_and_keeps_video_text(self):
        """Feed the writer's actual URL and status into the page, including old links."""
        ids = [c['id'] for c in load(self.root)['cues'] if c['productionMode'] == 'animation']
        old_ids, new_ids = [], []
        for generation, output in [('Old', old_ids), ('New', new_ids)]:
            cues = copy.deepcopy(load(self.root)['cues'])
            for cue in cues:
                if cue['id'] not in ids:
                    continue
                cue['finalAnimationDescription'] = generation + ' film ' + cue['id']
                cue['narrationAnchor'] = generation + ' narration ' + cue['id']
                cue['resolvedTimeline'].update(start='0s' if cue['id'] == ids[0] else '5s', duration='2s')
                path = self.root / cue['renderAdapters']['hyperframes']['compositionSrc']
                path.write_text(path.read_text() + '\n<!-- ' + generation + ' ' + cue['id'] + ' -->')
            model.update(self.root, self.req(generation, operation='edit', patch={'cues': cues}))
            for cue_id in ids:
                time = next(c['resolvedTimeline'] for c in cues if c['id'] == cue_id)
                output.extend(model.preview(self.root, self.req(generation + cue_id, scope='local', cueIds=[cue_id],
                    range={k: time[k] for k in ('start', 'duration')}))['artifactIds'])
        entry = handoff(self.root, {'artifactIds': new_ids}, start_service=False)['reviewEntry']
        cues = copy.deepcopy(load(self.root)['cues'])
        for cue in cues:
            cue['finalAnimationDescription'] = 'Later text ' + cue['id']
        model.update(self.root, self.req('later-prose', operation='edit', patch={'cues': cues}))
        data = model.status(self.root)
        data['testCase'] = {'cueIds': ids, 'oldIds': old_ids, 'newIds': new_ids, 'query': entry['query']}
        path = self.root / '.staging/client-state.json'
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(data))
        subprocess.run(['node', 'tests/review_v3_client_harness.cjs', 'handoff-animation', str(path)],
                       cwd=Path(__file__).resolve().parents[1], check=True)
        self.assertTrue(all(t['tab'] == 'storyboard' and t.get('cueId') in ids for t in entry['targets']))
        for artifact_id in new_ids:
            frozen = next(a for a in load(self.root)['artifacts'] if a['id'] == artifact_id)['reviewCues']
            self.assertTrue(all(c['finalAnimationDescription'] == 'New film ' + c['id'] for c in frozen))

    def test_cli_retry_reopens_existing_result_without_render_or_manifest_change(self):
        from scripts.afterforge import main
        req = self.req('retry-local', scope='local', cueIds=[load(self.root)['cues'][0]['id']])
        result = model.preview(self.root, req)
        count = len(self.calls)
        original = (self.root / 'animation-manifest.json').read_bytes()
        path = self.root / '.staging/retry.json'
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(req))
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(['preview', str(self.root), '--request-file', str(path), '--no-review-entry']), 0)
        response = json.loads(output.getvalue())
        self.assertEqual(response['reviewEntry']['artifactId'], result['artifactIds'][0])
        self.assertEqual(len(self.calls), count)
        self.assertEqual((self.root / 'animation-manifest.json').read_bytes(), original)


class ConceptReviewEntryTests(unittest.TestCase):
    def setUp(self):
        fixture_setup(self, concepts.ConceptTests.setUp)

    def test_cli_batch_entry_includes_nonrecommended_candidates_without_writing_urls(self):
        from scripts.afterforge import main
        source = self.root / '.staging/candidate.png'
        source.parent.mkdir(exist_ok=True)
        source.write_bytes(concepts.png_bytes())
        items = [{'cueId': cue, 'imageSource': str(source), 'origin': {'kind': 'user-imported', 'reference': 'fixture'},
                  'idea': 'Candidate', 'motion': 'Reveal', 'recommend': recommend}
                 for cue, recommend in [('poster', True), ('poster', False), ('map', False)]]
        req = request(self.root, 'batch-entry', operation='concept', action='register-batch', items=items)
        path = self.root / '.staging/request.json'
        path.write_text(json.dumps(req))
        output = io.StringIO()
        with redirect_stdout(output), patch('scripts.work_model_review_entry._verified_service', return_value='http://127.0.0.1:12345'):
            self.assertEqual(main(['update', str(self.root), '--request-file', str(path)]), 0)
        response = json.loads(output.getvalue())
        targets = response['reviewEntry']['targets']
        self.assertEqual([t['conceptId'] for t in targets], [r['id'] for r in response['record']])
        query = parse_qs(urlparse(response['reviewEntry']['url']).query)
        self.assertEqual([t['conceptId'] for t in json.loads(query['targets'][0])], [r['id'] for r in response['record']])
        self.assertNotIn('reviewEntry', load(self.root)['requests']['batch-entry']['result'])
        before = (self.root / 'animation-manifest.json').read_bytes()
        with patch('scripts.work_model_review_entry._verified_service', return_value=None), patch(
                'scripts.work_model_review_entry.subprocess.Popen', side_effect=OSError('service unavailable')):
            failed = handoff(self.root, model.update(self.root, req))
        self.assertEqual(failed['status'], 'updated')
        self.assertFalse(failed['reviewEntry']['available'])
        self.assertEqual([t['conceptId'] for t in failed['reviewEntry']['targets']], [r['id'] for r in response['record']])
        self.assertEqual((self.root / 'animation-manifest.json').read_bytes(), before)


class ExactReviewClientTests(unittest.TestCase):
    def test_new_batches_override_old_reading_without_rebinding_drafts(self):
        for scenario in ('batch-storyboard', 'batch-animation', 'batch-concept', 'batch-missing',
                         'batch-missing-animation', 'batch-missing-concept', 'batch-alternatives',
                         'batch-legacy-reading', 'batch-legacy-animation', 'batch-animation-missing-board'):
            with self.subTest(scenario=scenario):
                subprocess.run(['node', 'tests/review_v3_client_harness.cjs', scenario],
                               cwd=Path(__file__).resolve().parents[1], check=True)

    def test_exact_review_results_and_drafts_survive_refresh(self):
        for scenario in ('entry-concept', 'entry-storyboard', 'entry-missing', 'entry-batch', 'entry-local'):
            with self.subTest(scenario=scenario):
                subprocess.run(['node', 'tests/review_v3_client_harness.cjs', scenario],
                               cwd=Path(__file__).resolve().parents[1], check=True)
