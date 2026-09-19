"""Public API regressions for creative-object, review, and feedback boundaries."""
import copy
import unittest

from scripts import work_model as model
from scripts.work_model_store import load
from tests import test_work_model_jobs as job_tests
from tests.work_model_fixtures import demo_request, user


class WorkModelBoundaryTests(unittest.TestCase):
    setUp = job_tests.JobTests.setUp
    req = job_tests.JobTests.req

    def update_cues(self, name, cues, relations=None):
        manifest = load(self.root)
        source_only = [cue for cue in manifest["cues"] if cue["productionMode"] != "animation"]
        files = []
        # A static independent object needs a genuinely declarative layout;
        # merely dropping motionSrc while leaving its loader is not static.
        for cue in cues:
            adapter = cue['renderAdapters']['hyperframes']
            if adapter.get('motionSrc') or not (relations or {}).get(cue['id'], {}).get('kind') == 'new':
                continue
            original = adapter['compositionSrc']
            import re
            markup = re.sub(r'<script\b[^>]*>.*?</script>', '', (self.root / original).read_text(), flags=re.S)
            relative = 'compositions/cues/' + cue['id'] + '-static.html'
            staged = self.root / '.staging' / (cue['id'] + '-static.html')
            staged.parent.mkdir(exist_ok=True); staged.write_text(markup)
            adapter['compositionSrc'] = relative
            adapter['layoutDependencies'] = [relative if p == original else p for p in adapter['layoutDependencies']]
            files.append({'path': relative, 'source': str(staged)})
        return model.update(self.root, self.req(name, operation="edit", patch={
            "cues": [*cues, *source_only],
            "brief": manifest["brief"],
        }, objectRelations=relations or {}, files=files))

    def test_delete_recreate_and_rename_require_explicit_object_relations(self):
        original = load(self.root)
        first, second = [cue for cue in original["cues"] if cue["productionMode"] == "animation"]
        first_object = first["objectId"]
        second_object = second["objectId"]

        self.update_cues("delete", [copy.deepcopy(second)])

        recreated = copy.deepcopy(first)
        recreated["id"] = "recreated"
        recreated.pop("objectId", None)
        recreated["renderAdapters"]["hyperframes"].pop("motionSrc", None)
        with self.assertRaisesRegex(ValueError, "objectRelations|creative object"):
            self.update_cues("recreate-without-relation", [copy.deepcopy(second), recreated])
        self.update_cues("recreate", [copy.deepcopy(second), recreated], {
            "recreated": {"kind": "new", "basis": {"text": "这是新出现的标题对象", "reference": "turn:new"}},
        })
        recreated_object = next(c for c in load(self.root)["cues"] if c["id"] == "recreated")["objectId"]
        self.assertNotEqual(recreated_object, first_object)

        renamed = copy.deepcopy(second)
        renamed["id"] = "renamed"
        renamed.pop("objectId", None)
        self.update_cues("rename", [recreated, renamed], {
            "renamed": {"kind": "continue", "objectId": second_object,
                        "basis": {"text": "同一标题对象改名", "reference": "turn:rename"}},
        })
        self.assertEqual(next(c for c in load(self.root)["cues"] if c["id"] == "renamed")["objectId"], second_object)
        confirmed_objects = {
            object_id
            for decision in load(self.root)["decisions"] if decision["kind"] == "confirm-design"
            for object_id in decision["objectIds"]
        }
        self.assertNotIn(recreated_object, confirmed_objects)

    def test_bounded_motion_exploration_allows_only_its_local_cue_scope(self):
        cue_ids = [cue["id"] for cue in load(self.root)["cues"] if cue["productionMode"] == "animation"]
        confirmed = cue_ids[0]
        explored = cue_ids[1]

        local = model.preview(self.root, self.req("active-local", scope="local", cueIds=[confirmed]))
        self.assertEqual(local["status"], "complete")

        model.update(self.root, self.req("explore", operation="decision", kind="explore-motion",
            taskId="explore-second", cueIds=[explored], source=user("只探索第二条动画", "explore:second")))
        with self.assertRaisesRegex(ValueError, "Demo|authorization|制作依据"):
            model.preview(self.root, {"requestId": "explore-not-full", "expectedRevision": load(self.root)["editRevision"],
                "scope": "full", "taskId": "explore-second", "cueIds": [explored],
                "workCueIds": [explored], "presentationCueIds": [explored], "excludedCueIds": [confirmed]})

        result = model.preview(self.root, self.req("explore-local", scope="local", taskId="explore-second",
            cueIds=[explored], workCueIds=[explored]))
        self.assertEqual(result["status"], "complete")
        run = next(item for item in load(self.root)["productionRuns"] if item["taskId"] == "explore-second")
        self.assertEqual(run["taskId"], "explore-second")

    def test_review_submit_does_not_confirm_and_stale_handoff_is_atomic(self):
        boards = [board["id"] for board in load(self.root)["storyboards"]]
        before_decisions = list(load(self.root)["decisions"])
        submitted = model.update(self.root, self.req("submit", operation="review-submit", storyboardIds=boards,
            feedbackIds=[], drafts=[], source=user("本轮没有评论，仅提交审阅", "review:empty")))
        self.assertEqual(submitted["status"], "updated")
        self.assertEqual(load(self.root)["decisions"], before_decisions)

        confirmed = model.update(self.root, self.req("batch-confirm", operation="decision", kind="confirm-design",
            storyboardIds=boards, source=user("确认这两条静帧设计", "review:batch-confirm")))
        self.assertEqual(confirmed["status"], "updated")
        self.assertEqual(len(load(self.root)["decisions"][-1]["objectIds"]), 2)

        artifact_id = load(self.root)["storyboards"][0]["artifactIds"][0]
        composition = self.root / load(self.root)["cues"][0]["renderAdapters"]["hyperframes"]["compositionSrc"]
        composition.write_text("<div>changed after review</div>")
        before = load(self.root)
        with self.assertRaisesRegex(ValueError, "stale frame draft"):
            model.update(self.root, self.req("stale-submit", operation="review-submit", storyboardIds=[], feedbackIds=[],
                drafts=[{"body": "这一帧改小", "source": user("提交过期帧评论", "review:stale"),
                         "target": {"artifactId": artifact_id}}], source=user("提交", "review:handoff")))
        after = load(self.root)
        self.assertEqual(after["feedback"], before["feedback"])
        self.assertEqual(after["reviewRounds"], before["reviewRounds"])

    def test_excluded_or_unavailable_cue_does_not_block_available_local_work_or_form_review(self):
        manifest = load(self.root)
        available, unavailable = [cue for cue in manifest["cues"] if cue["productionMode"] == "animation"]
        unavailable = copy.deepcopy(unavailable)
        unavailable["id"] = "D"
        unavailable.pop("objectId", None)
        unavailable["renderAdapters"]["hyperframes"].pop("motionSrc", None)
        self.update_cues("new-d", [available, unavailable], {
            "D": {"kind": "new", "basis": {"text": "D 是本轮尚未确认的新对象", "reference": "turn:D"}},
        })

        local = model.preview(self.root, self.req("available-a", scope="local", cueIds=[available["id"]]))
        self.assertEqual(local["status"], "complete")
        full = model.preview(self.root, demo_request(self.root, "exclude-d", excludedCueIds=["D"]))
        self.assertIsNone(full["reviewSet"])
        self.assertIsNone(model.status(self.root)["reviewSet"])
        self.assertNotIn(("D", "preview"), self.calls)

    def test_feedback_applicability_and_explicit_acceptance_scope(self):
        review = model.preview(self.root, self.req("full", scope="full"))["reviewSet"]
        target = {"versionId": load(self.root)["identity"]["versionId"]}
        accepted = model.update(self.root, self.req("accepted-feedback", operation="feedback", body="标题再小一点",
            target=target, source=user("标题再小一点", "feedback:accepted")))["record"]
        deferred = model.update(self.root, self.req("deferred-feedback", operation="feedback", body="下一版再试色彩",
            target=target, source=user("下一版再试色彩", "feedback:deferred")))["record"]
        model.update(self.root, self.req("defer", operation="feedback-applicability", feedbackId=deferred["id"],
            kind="deferred", source=user("这条反馈留到下一版", "feedback:defer")))

        model.update(self.root, self.req("approve", operation="decision", kind="approve", reviewSetId=review["id"],
            feedbackIds=[accepted["id"]], source=user("接受第一条反馈并批准本轮", "feedback:approve")))
        records = {item["id"]: item for item in load(self.root)["feedback"]}
        self.assertEqual(records[accepted["id"]]["status"], "accepted")
        self.assertEqual(records[deferred["id"]]["status"], "pending")
        self.assertEqual(records[deferred["id"]]["applicability"]["kind"], "deferred")


if __name__ == "__main__":
    unittest.main()
