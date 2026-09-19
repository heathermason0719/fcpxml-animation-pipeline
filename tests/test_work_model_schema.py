"""New work facts are validated while historical schema-3 data stays readable."""
import copy
import unittest

from scripts.manifest_schema import validate_manifest_schema
from scripts.work_model_store import load
from tests import test_work_model_jobs as jobs
from tests.work_model_fixtures import user


class FactSchemaTests(unittest.TestCase):
    setUp = jobs.JobTests.setUp

    def test_malformed_new_authority_facts_are_rejected(self):
        before = load(self.root)
        examples = [
            {'kind': 'confirm-design', 'storyboardIds': [], 'objectIds': []},
            {'kind': 'authorize-demo', 'taskId': 'task', 'cueIds': [], 'objectIds': []},
            {'kind': 'explore-motion', 'taskId': 'task', 'cueIds': [], 'objectIds': []},
            {'kind': 'adopt-direction', 'cueIds': ['a']},
        ]
        for fields in examples:
            with self.subTest(fields['kind']):
                broken = copy.deepcopy(before)
                broken['decisions'].append({'id': 'bad', 'createdAt': 'test', 'source': user(), **fields})
                with self.assertRaisesRegex(ValueError, 'manifest schema'):
                    validate_manifest_schema(broken)

    def test_exploration_frame_uses_same_state_contract_as_canonical_frame(self):
        state = load(self.root)
        cue = copy.deepcopy(state['cues'][0])
        cue.pop('objectId', None)
        cue['storyboard'] = {'frames': [{'id': 'hero', 'role': 'hero', 'state': {'id': 'comparison'}}]}
        state['explorations'] = [{'id': 'direction', 'question': '字形', 'createdAt': 'test',
            'variants': [{'id': 'a', 'label': 'a', 'cues': [cue]}]}]
        validate_manifest_schema(state)
        cue['storyboard']['frames'][0]['state'] = {'arbitraryJavascript': 'bad'}
        with self.assertRaisesRegex(ValueError, 'manifest schema'):
            validate_manifest_schema(state)
