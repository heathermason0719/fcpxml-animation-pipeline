import json
import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator

from scripts import workflow_review as review
from scripts.serve_workflow_review import apply_review_action, review_state
from tests.test_hyperframes_single_source import write_json
from tests.test_workflow_review_server import ReviewVersionFixture


class ReviewSchemaConsistencyTests(ReviewVersionFixture):
    def assert_schema(self, root):
        schema = json.loads((Path(__file__).parents[1] / "references/animation-manifest.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        manifest = json.loads((root / "animation-manifest.json").read_text())
        failures = [f"{list(error.path)}: {error.message}" for error in Draft202012Validator(schema).iter_errors(manifest)]
        self.assertEqual(failures, [])
        return manifest

    def test_first_comment_and_each_storyboard_transition_satisfy_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_review_version(directory)
            self.assert_schema(root)
            for text in ("first opinion", "second opinion"):
                comment = review.add_review_comment(root, stage_id="A11", body=text, actor="user", cue_id="p1s01_c01_title", frame_id="hero")
                self.assert_schema(root)
                review.address_review_comment(root, "A11", comment["id"], actor="agent")
                self.assert_schema(root)
            review.approve_storyboard(root, actor="user")
            state = self.assert_schema(root)
            self.assertEqual([c["status"] for c in state["workflow"]["stageEvidence"]["A11"]["comments"]], ["accepted", "accepted"])
            self.assertNotIn("A14", state["workflow"]["stageEvidence"])

    def test_clean_approval_does_not_create_empty_downstream_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_review_version(directory)
            review.approve_storyboard(root, actor="user")
            manifest = self.assert_schema(root)
            self.assertEqual(set(manifest["workflow"]["stageEvidence"]), {"A11"})

    def test_demo_point_range_and_mixed_scope_comments_satisfy_schema(self):
        for scopes in (["motion"], ["static"], ["static", "motion"]):
            with self.subTest(scopes=scopes), tempfile.TemporaryDirectory() as directory:
                root = self.make_review_version(directory)
                review.approve_storyboard(root, actor="user")
                (root / "demo.mp4").write_bytes(b"test preview")
                review.register_demo(root, "demo.mp4")
                self.assert_schema(root)
                comment = review.add_review_comment(root, stage_id="A13", body="mixed feedback", actor="user", cue_id="p1s01_c01_title", time_start="1s", time_end="3/2s", impact_scopes=scopes)
                self.assert_schema(root)
                review.address_review_comment(root, "A13", comment["id"], actor="agent")
                self.assert_schema(root)
                if "static" in scopes:
                    review.approve_storyboard(root, actor="user")
                    self.assert_schema(root)
                review.approve_demo(root, actor="user")
                self.assert_schema(root)
                review.authorize_native_render(root, actor="user")
                self.assert_schema(root)

    def test_schema_invalid_comment_cannot_be_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_review_version(directory)
            path = root / "animation-manifest.json"
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "frameId|schema"):
                review.add_review_comment(root, stage_id="A11", body="wrong anchor type", actor="user", cue_id="p1s01_c01_title", frame_id=42)
            self.assertEqual(path.read_bytes(), before)

    def test_actual_player_decimal_payload_is_persisted_as_exact_rational_time(self):
        for end in (None, "14.420s"):
            with self.subTest(end=end), tempfile.TemporaryDirectory() as directory:
                root = self.make_review_version(directory)
                manifest_path = root / "animation-manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["project"]["source"]["duration"] = "360/24s"
                manifest["cues"][0]["resolvedTimeline"] = {
                    "start": "17/2s",
                    "duration": "49/8s",
                    "authority": "fcpxml",
                }
                write_json(manifest_path, manifest)
                review.approve_storyboard(root, actor="user")
                (root / "demo.mp4").write_bytes(b"test preview")
                review.register_demo(root, "demo.mp4")
                payload = {"manifestSha256":review_state(root)["manifestSha256"], "body":"player feedback",
                           "cueId":"p1s01_c01_title", "timeStart":"11.000s", "impactScopes":["motion"]}
                if end is not None:
                    payload["timeEnd"] = end
                apply_review_action(root, "add-demo-comment", payload)
                manifest = self.assert_schema(root)
                comment = manifest["workflow"]["stageEvidence"]["A13"]["comments"][0]
                self.assertEqual(comment["timeStart"], "11s")
                if end is not None:
                    self.assertEqual(comment["timeEnd"], "721/50s")
                else:
                    self.assertNotIn("timeEnd", comment)
