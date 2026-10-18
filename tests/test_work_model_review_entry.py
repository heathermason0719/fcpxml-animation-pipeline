"""CLI handoff never changes a completed production receipt or rerenders."""
import copy
from unittest.mock import patch
from scripts import work_model as model
from scripts.work_model_review_entry import handoff
import unittest
from tests import test_work_model_jobs as jobs


class ReviewEntryTests(unittest.TestCase):
    setUp = jobs.JobTests.setUp
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
