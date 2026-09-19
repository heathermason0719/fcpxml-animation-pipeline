"""Regression coverage for shared design/review/delivery feedback targeting."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.work_model_feedback_targets import blocking_feedback, design_target, feedback_applies, review_target
from scripts.work_model_feedback import add_feedback
from scripts.work_model_exploration import adoption, set_exploration, variant_lineage
from scripts import work_model as model
from scripts.work_model_store import load
from tests import test_work_model_jobs as job_tests
from tests.work_model_fixtures import raster, user


class FeedbackApplicabilityTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {
            "identity": {"versionId": "v1"},
            "cues": [
                {"id": "a", "objectId": "object-a", "segmentIds": ["s1"], "resolvedTimeline": {"start": "0s", "duration": "2s"}},
                {"id": "b", "objectId": "object-b", "segmentIds": ["s2"], "resolvedTimeline": {"start": "2s", "duration": "2s"}},
            ],
            "artifacts": [{"id": "board-a", "purpose": "storyboard", "cueIds": ["a"]},
                          {"id": "full", "purpose": "full-preview", "cueIds": ["a"]},
                          {"id": "candidate-frame", "purpose": "exploration", "explorationId": "style", "variantId": "soft", "variantRevision": 2, "variantContentIdentity": "candidate-v2", "cueIds": ["a"]}],
            "storyboards": [{"id": "old-board-a", "cueId": "a", "objectId": "object-a", "artifactIds": ["board-a"]}],
            "explorations": [{"id": "style", "variants": [{"id": "soft", "revision": 2, "contentIdentity": "candidate-v2", "cues": []}], "adoptions": []}],
            "feedback": [],
            "decisions": [],
        }
        self.design_a = design_target(self.manifest, ["old-board-a"])
        self.review = review_target(self.manifest, {"id": "review-1", "artifactIds": ["full"], "productionBasis": {"presentationCueIds": ["a", "b"], "presentationObjectIds": ["object-a", "object-b"]}})

    def feedback(self, name, target, **extra):
        return {"id": name, "status": "pending", "target": {"versionId": "v1", **target}, **extra}

    def test_historical_storyboard_identity_and_unmodified_presented_cue_remain_covered(self):
        comment = self.feedback("old-frame", {"storyboardId": "old-board-a", "artifactId": "board-a"})
        self.assertTrue(feedback_applies(self.manifest, comment, self.design_a))
        comment_b = self.feedback("presented-b", {"cueIds": ["b"]})
        self.assertTrue(feedback_applies(self.manifest, comment_b, self.review))

    def test_historical_artifact_does_not_follow_a_reused_technical_cue(self):
        replacement = copy.deepcopy(self.manifest)
        replacement["cues"][0]["objectId"] = "replacement-object"
        old_frame = self.feedback("old-artifact", {"artifactId": "board-a"})
        old_target = design_target(replacement, ["old-board-a"])
        new_target = {**old_target, "objectIds": ["replacement-object"]}
        self.assertTrue(feedback_applies(replacement, old_frame, old_target))
        self.assertFalse(feedback_applies(replacement, old_frame, new_target))

    def test_unowned_location_scope_does_not_block_unrelated_objects(self):
        for anchor in [{'segmentIds': ['s2']}, {'timeStart': '2s', 'timeEnd': '3s'}]:
            self.assertFalse(feedback_applies(self.manifest, self.feedback('unrelated', anchor), self.design_a))

    def test_object_feedback_is_not_resolved_by_placement_or_segment_changes(self):
        comment = self.feedback('move', {'objectIds': ['object-a'], 'cueIds': ['a'],
            'segmentIds': ['s1'], 'timeStart': '0s', 'timeEnd': '1s'})
        self.manifest['cues'][0].update(segmentIds=['s2'], resolvedTimeline={'start':'10s','duration':'2s'})
        self.assertTrue(feedback_applies(self.manifest, comment, self.design_a))

    def test_frozen_object_identity_survives_technical_rename_and_reused_id(self):
        comment = self.feedback("frozen", {"cueIds": ["a"], "objectIds": ["object-a"]})
        renamed = copy.deepcopy(self.manifest)
        renamed["cues"][0]["id"] = "renamed-a"
        continued = {"kind": "design", "cueIds": ["renamed-a"], "objectIds": ["object-a"]}
        self.assertTrue(feedback_applies(renamed, comment, continued))
        replacement = copy.deepcopy(renamed)
        replacement["cues"].append({"id": "a", "objectId": "replacement-object", "segmentIds": [],
                                     "resolvedTimeline": {"start": "4s", "duration": "1s"}})
        replacement_target = {"kind": "design", "cueIds": ["a"], "objectIds": ["replacement-object"]}
        self.assertFalse(feedback_applies(replacement, comment, replacement_target))

    def test_candidate_lineage_covers_staged_resources_and_background_samples(self):
        from tests.test_work_model_static_capabilities import STILL
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            markup = b'<img src="image.gif">'
            variant = {'id':'v', 'label':'v', 'cues':[{'id':'c',
                'storyboard':{'frames':[{'id':'hero','role':'hero','stillSrc':'back.gif'}]},
                'renderAdapters':{'hyperframes':{'compositionSrc':'candidate.html','layoutDependencies':[]}}}]}
            staged = {'candidate.html':markup, 'image.gif':STILL, 'back.gif':STILL}
            before = variant_lineage(variant, root, staged)
            self.assertEqual(set(before['files']), set(staged))
            changed = {**staged, 'back.gif':STILL.replace(b'\xff\x00\x00', b'\x00\xff\x00')}
            self.assertNotEqual(before['contentIdentity'], variant_lineage(variant, root, changed)['contentIdentity'])
            for name, data in staged.items(): (root / name).write_bytes(data)
            self.assertEqual(before['contentIdentity'], variant_lineage(variant, root)['contentIdentity'])

    def test_motion_sample_lineage_includes_executable_closure_and_vendor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "compositions").mkdir()
            (root / "assets/vendor").mkdir(parents=True)
            (root / "compositions/candidate.html").write_text('<script src="motion.js"></script>')
            (root / "compositions/motion.js").write_text("const a = 1")
            (root / "assets/vendor/gsap.min.js").write_text("vendor-a")
            variant = {"id": "motion", "label": "Motion", "cues": [{"id": "candidate",
                "storyboard": {"frames": [{"id": "hero", "role": "hero", "mode": "motion", "time": "1s"}]},
                "renderAdapters": {"hyperframes": {"compositionSrc": "compositions/candidate.html", "motionSrc": "compositions/motion.js", "layoutDependencies": []}}}]}
            before = variant_lineage(variant, root)
            variant["revision"] = before["revision"]
            variant["contentIdentity"] = before["contentIdentity"]
            (root / "compositions/motion.js").write_text("const a = 2")
            changed_motion = variant_lineage(variant, root)
            (root / "assets/vendor/gsap.min.js").write_text("vendor-b")
            changed_vendor = variant_lineage(variant, root)
            self.assertEqual(changed_motion["revision"], before["revision"] + 1)
            self.assertNotEqual(changed_motion["contentIdentity"], before["contentIdentity"])
            self.assertNotEqual(changed_vendor["contentIdentity"], changed_motion["contentIdentity"])

    def test_unused_candidate_comment_is_not_a_blocker_but_matching_frozen_adoption_is(self):
        candidate = self.feedback("candidate", {"artifactId": "candidate-frame", "explorationId": "style", "variantId": "soft", "variantRevision": 2, "variantContentIdentity": "candidate-v2"})
        self.assertFalse(feedback_applies(self.manifest, candidate, self.design_a))
        self.manifest["explorations"][0]["adoptions"].append({"variantId": "soft", "variantRevision": 2,
            "variantContentIdentity": "candidate-v2", "objectIds": ["object-a"], "cueIds": ["a"]})
        self.assertTrue(feedback_applies(self.manifest, candidate, self.design_a))
        stale = copy.deepcopy(candidate)
        stale["target"]["variantContentIdentity"] = "candidate-v1"
        self.assertFalse(feedback_applies(self.manifest, stale, self.design_a))

    def test_out_of_scope_deferred_and_not_applicable_feedback_do_not_block(self):
        out_of_scope = self.feedback("b-only", {"cueIds": ["b"]})
        deferred = self.feedback("deferred", {"cueIds": ["a"]}, applicability={"kind": "deferred"})
        not_applicable = self.feedback("na", {"cueIds": ["a"]}, applicability={"kind": "not-applicable"})
        self.manifest["feedback"] = [out_of_scope, deferred, not_applicable]
        self.assertEqual(blocking_feedback(self.manifest, self.design_a), [])

    def test_writer_freezes_artifact_candidate_identity_and_adoption_scope(self):
        self.manifest["brief"] = {"segments": []}
        self.manifest["project"] = {}
        comment = add_feedback(self.manifest, {"body": "采用后标题仍应慢一点", "source": {"channel": "chat", "text": "候选慢一点", "reference": "turn:1"},
            "target": {"versionId": "v1", "artifactId": "candidate-frame"}})
        self.assertEqual(comment["target"]["explorationId"], "style")
        self.assertEqual(comment["target"]["variantRevision"], 2)
        self.assertEqual(comment["target"]["variantContentIdentity"], "candidate-v2")

        legacy_artifact = copy.deepcopy(self.manifest)
        legacy_artifact["brief"] = {"segments": []}
        legacy_artifact["project"] = {}
        legacy_artifact["artifacts"][2].pop("variantRevision", None)
        legacy_artifact["artifacts"][2].pop("variantContentIdentity", None)
        unknown = add_feedback(legacy_artifact, {"body": "旧候选是否要慢一点", "source": {"channel": "chat", "text": "旧候选", "reference": "turn:legacy"},
            "target": {"versionId": "v1", "artifactId": "candidate-frame"}})
        self.assertNotIn("variantRevision", unknown["target"])
        self.assertNotIn("variantContentIdentity", unknown["target"])
        legacy_artifact["explorations"][0]["adoptions"].append({"variantId": "soft", "variantRevision": 2,
            "variantContentIdentity": "candidate-v2", "objectIds": ["object-a"]})
        self.assertFalse(feedback_applies(legacy_artifact, unknown, self.design_a))

        value = {"id": "new-style", "question": "哪种标题？", "variants": [{"id": "soft", "label": "Soft", "cues": []}]}
        set_exploration(self.manifest, {"exploration": value})
        variant = next(item for item in self.manifest["explorations"] if item["id"] == "new-style")["variants"][0]
        self.assertEqual(variant["revision"], 1)
        self.assertTrue(variant["contentIdentity"])

        request = {"explorationId": "style", "variantId": "soft", "cueIds": ["a"], "patch": {"cues": []},
                   "source": {"channel": "chat", "text": "将 soft 应用于 A", "reference": "turn:2"}}
        legacy_variant = self.manifest["explorations"][0]["variants"][0]
        legacy_variant.pop("revision")
        legacy_variant.pop("contentIdentity")
        record = adoption(self.manifest, request)
        self.assertEqual(record["objectIds"], ["object-a"])
        self.assertEqual(record["variantRevision"], 1)
        self.assertTrue(record["variantContentIdentity"])


if __name__ == "__main__":
    unittest.main()


class FeedbackPublicIntegrationTests(unittest.TestCase):
    """Public update/preview boundaries share the same applicability facts."""
    setUp = job_tests.JobTests.setUp
    req = job_tests.JobTests.req

    def _cues(self):
        return [cue for cue in load(self.root)["cues"] if cue["productionMode"] == "animation"]

    def _exploration(self, label="Soft"):
        candidate = copy.deepcopy(self._cues()[0])
        candidate.pop("objectId", None)
        candidate.pop("deliveryAsset", None)
        return {"id": "style", "question": "标题采用哪个节奏？", "variants": [
            {"id": "soft", "label": label, "cues": [candidate]},
        ]}

    def _candidate_feedback(self, name, label="Soft"):
        model.update(self.root, self.req("register-" + name, operation="exploration", exploration=self._exploration(label)))
        with patch("scripts.work_model_jobs.render_storyboard", side_effect=raster):
            preview = model.preview(self.root, self.req("candidate-" + name, scope="exploration",
                explorationId="style", variantId="soft", cueIds=[self._cues()[0]["id"]]))
        artifact = preview["artifactIds"][0]
        return model.update(self.root, self.req("feedback-" + name, operation="feedback", body="标题节奏应再慢一点",
            target={"versionId": load(self.root)["identity"]["versionId"], "artifactId": artifact},
            source=user("候选标题应再慢一点", "candidate:" + name)))["record"]

    def _review(self, name):
        return model.preview(self.root, self.req("full-" + name, scope="full"))["reviewSet"]

    def _approve_and_deliver_decision(self, name, review):
        return model.update(self.root, self.req("approve-" + name, operation="decision", kind="approve-and-deliver",
            reviewSetId=review["id"], source=user("批准并授权交付当前完整审阅", "approve:" + name)))

    def _adopt(self, name):
        cues = copy.deepcopy(load(self.root)["cues"])
        selected = self._cues()[0]["id"]
        next(cue for cue in cues if cue["id"] == selected)["finalAnimationDescription"] = "采用 soft 标题节奏"
        model.update(self.root, self.req("adopt-" + name, operation="exploration-adopt", explorationId="style",
            variantId="soft", cueIds=[selected], patch={"cues": cues},
            source=user("将 soft 候选用于标题", "adopt:" + name)))

    def _stage_candidate(self, name, markup):
        path = self.root / ".staging" / name / "candidate.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markup)
        return {"path": "compositions/explorations/style/candidate.html", "source": str(path)}

    def _same_path_exploration(self):
        candidate = copy.deepcopy(self._cues()[0])
        candidate.pop("objectId", None)
        candidate.pop("deliveryAsset", None)
        adapter = candidate["renderAdapters"]["hyperframes"]
        adapter.pop("motionSrc", None)
        adapter["compositionSrc"] = "compositions/explorations/style/candidate.html"
        adapter["layoutDependencies"] = []
        return {"id": "style", "question": "标题采用哪个节奏？", "variants": [
            {"id": "soft", "label": "Soft", "cues": [candidate]},
        ]}

    def test_unused_exploration_feedback_allows_approval_and_delivery_gate(self):
        self._candidate_feedback("unused")
        review = self._review("unused")
        self._approve_and_deliver_decision("unused", review)
        from scripts.work_model_jobs import _approved
        self.assertEqual(_approved(self.root, load(self.root))["id"], review["id"])

    def test_adopted_relevant_candidate_feedback_blocks_approval(self):
        self._candidate_feedback("adopted")
        self._adopt("adopted")
        review = self._review("adopted")
        with self.assertRaisesRegex(ValueError, "pending feedback"):
            self._approve_and_deliver_decision("adopted", review)

    def test_later_candidate_comment_cannot_contaminate_an_older_adoption(self):
        old = self._candidate_feedback("old")
        self._adopt("old")
        model.update(self.root, self.req("defer-old", operation="feedback-applicability", feedbackId=old["id"],
            kind="deferred", source=user("旧候选意见已经延后", "candidate:old-defer")))
        self._candidate_feedback("later", label="Sharper")
        review = self._review("later")
        self._approve_and_deliver_decision("later", review)

    def test_canonical_overlap_blocks_but_deferred_feedback_does_not(self):
        review = self._review("canonical")
        version_id = load(self.root)["identity"]["versionId"]
        cue = self._cues()[0]["id"]
        blocking = model.update(self.root, self.req("canonical-feedback", operation="feedback", body="标题小一点",
            target={"versionId": version_id, "cueIds": [cue]}, source=user("标题小一点", "canonical:block")))["record"]
        with self.assertRaisesRegex(ValueError, "pending feedback"):
            self._approve_and_deliver_decision("canonical-blocked", review)
        model.update(self.root, self.req("canonical-defer", operation="feedback-applicability", feedbackId=blocking["id"],
            kind="deferred", source=user("这条延后", "canonical:defer")))
        self._approve_and_deliver_decision("canonical-deferred", review)

    def test_same_path_candidate_rewrite_gets_new_lineage_and_cannot_match_old_adoption(self):
        exploration = self._same_path_exploration()
        model.update(self.root, self.req("candidate-a", operation="exploration", exploration=exploration,
            files=[self._stage_candidate("candidate-a", "<div>A</div>")]))
        before = copy.deepcopy(load(self.root)["explorations"][0]["variants"][0])
        self._adopt("same-path-a")
        model.update(self.root, self.req("candidate-b", operation="exploration", exploration=exploration,
            files=[self._stage_candidate("candidate-b", "<div>B changed</div>")]))
        after = load(self.root)["explorations"][0]["variants"][0]
        self.assertEqual(after["revision"], before["revision"] + 1)
        self.assertNotEqual(after["contentIdentity"], before["contentIdentity"])
        with patch("scripts.work_model_jobs.render_storyboard", side_effect=raster):
            preview = model.preview(self.root, self.req("candidate-b-preview", scope="exploration",
                explorationId="style", variantId="soft", cueIds=[self._cues()[0]["id"]]))
        comment = model.update(self.root, self.req("candidate-b-comment", operation="feedback", body="B 需要再慢一点",
            target={"versionId": load(self.root)["identity"]["versionId"], "artifactId": preview["artifactIds"][0]},
            source=user("B 需要再慢一点", "candidate:b-comment")))["record"]
        state = load(self.root)
        self.assertFalse(feedback_applies(state, comment, design_target(state, [state["storyboards"][0]])))
