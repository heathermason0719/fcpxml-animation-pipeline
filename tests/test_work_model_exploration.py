"""Public API boundaries for optional visual explorations."""
import copy
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import work_model as model
from scripts.work_model_store import layout, load
from tests import test_work_model_jobs as job_tests
from tests.work_model_fixtures import raster, user


class WorkModelExplorationTests(unittest.TestCase):
    setUp = job_tests.JobTests.setUp
    req = job_tests.JobTests.req

    def animation_cues(self):
        return [cue for cue in load(self.root)["cues"] if cue["productionMode"] == "animation"]

    def exploration(self, exploration_id="explore-options"):
        cue = copy.deepcopy(self.animation_cues()[0])
        cue.pop("objectId", None)
        cue.pop("deliveryAsset", None)
        return {
            "id": exploration_id,
            "question": "标题进场采用哪种视觉节奏？",
            "description": "只供比较，不改变正式制作源。",
            "variants": [
                {"id": "soft", "label": "柔和", "description": "渐显", "cues": [cue]},
                {"id": "sharp", "label": "锐利", "description": "切入", "cues": [copy.deepcopy(cue)]},
            ],
        }

    def register(self, exploration=None):
        value = exploration or self.exploration()
        return model.update(self.root, self.req("register-" + value["id"], operation="exploration", exploration=value))

    def test_absent_or_unadopted_exploration_does_not_block_storyboard_or_active_work(self):
        cue_id = self.animation_cues()[0]["id"]
        with patch("scripts.work_model_jobs.render_storyboard", side_effect=raster):
            storyboard = model.preview(self.root, self.req("storyboard-without-exploration", scope="storyboard", cueIds=[cue_id]))
        self.assertTrue(storyboard["storyboardIds"])
        self.assertEqual(model.preview(self.root, self.req("active-without-exploration", scope="local", cueIds=[cue_id]))["status"], "complete")

        canonical_before = copy.deepcopy(load(self.root)["cues"])
        self.register()
        self.assertEqual(load(self.root)["cues"], canonical_before)
        self.assertFalse(load(self.root)["explorations"][0]["adoptions"])

    def test_exploration_preview_registers_snapshot_artifacts_without_first_design_authority(self):
        self.register()
        before_decisions = copy.deepcopy(load(self.root)["decisions"])
        before_boards = copy.deepcopy(load(self.root)["storyboards"])
        canonical_before = copy.deepcopy(load(self.root)["cues"])

        with patch("scripts.work_model_jobs.render_storyboard", side_effect=raster):
            result = model.preview(self.root, self.req("soft-preview", scope="exploration",
                explorationId="explore-options", variantId="soft", cueIds=[self.animation_cues()[0]["id"]]))

        state = load(self.root)
        variant = state["explorations"][0]["variants"][0]
        artifact_ids = variant["artifactIds"]
        artifacts = [artifact for artifact in state["artifacts"] if artifact["id"] in artifact_ids]
        self.assertEqual(result["artifactIds"], artifact_ids)
        self.assertTrue(artifacts)
        self.assertTrue(all(artifact["purpose"] == "exploration" for artifact in artifacts))
        self.assertTrue(all(artifact["explorationId"] == "explore-options" for artifact in artifacts))
        self.assertEqual(state["decisions"], before_decisions)
        self.assertEqual(state["storyboards"], before_boards)
        self.assertEqual(state["cues"], canonical_before)

    def test_adoption_is_scoped_to_selected_canonical_cues_and_preserves_series_defaults(self):
        self.register()
        afterforge, _ = layout(self.root)
        series_frame = afterforge / "工程/frame.md"
        series_frame.parent.mkdir(parents=True, exist_ok=True)
        series_frame.write_bytes(b"# Series default\nblue title\n")
        series_before = series_frame.read_bytes()
        cues = copy.deepcopy(load(self.root)["cues"])
        selected = self.animation_cues()[0]["id"]
        next(cue for cue in cues if cue["id"] == selected)["finalAnimationDescription"] = "采用柔和渐显"

        response = model.update(self.root, self.req("adopt-soft", operation="exploration-adopt",
            explorationId="explore-options", variantId="soft", cueIds=[selected],
            patch={"cues": cues}, source=user("采用柔和候选用于当前标题", "exploration:adopt")))

        state = load(self.root)
        decision = response["record"]
        self.assertEqual(decision["kind"], "adopt-direction")
        self.assertEqual(decision["cueIds"], [selected])
        self.assertIn(decision, state["explorations"][0]["adoptions"])
        self.assertEqual(series_frame.read_bytes(), series_before)

        out_of_scope = copy.deepcopy(state["cues"])
        for cue in out_of_scope:
            if cue["productionMode"] == "animation":
                cue["finalAnimationDescription"] += " 改动"
        before = copy.deepcopy(load(self.root))
        with self.assertRaisesRegex(ValueError, "selected cue scope"):
            model.update(self.root, self.req("adopt-too-wide", operation="exploration-adopt",
                explorationId="explore-options", variantId="sharp", cueIds=[selected],
                patch={"cues": out_of_scope}, source=user("只采用标题但同时改了别处", "exploration:too-wide")))
        self.assertEqual(load(self.root)["decisions"], before["decisions"])
        self.assertEqual(load(self.root)["explorations"], before["explorations"])

    def test_adoption_failure_rolls_back_decision_adoption_and_unselected_source_file(self):
        self.register()
        animations = self.animation_cues()
        selected, unselected = animations[0], animations[1]
        staged = self.root / ".staging/exploration-unselected.html"
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_text("changed unselected composition")
        target_name = unselected["renderAdapters"]["hyperframes"]["compositionSrc"]
        target = self.root / target_name
        target_before = target.read_bytes()
        cues = copy.deepcopy(load(self.root)["cues"])
        next(cue for cue in cues if cue["id"] == selected["id"])["finalAnimationDescription"] = "只改选中标题"
        before = copy.deepcopy(load(self.root))

        with self.assertRaisesRegex(ValueError, "unselected cue"):
            model.update(self.root, self.req("adopt-shared-file", operation="exploration-adopt",
                explorationId="explore-options", variantId="soft", cueIds=[selected["id"]], patch={"cues": cues},
                files=[{"path": target_name, "source": str(staged)}],
                source=user("采用标题，不应改第二条素材", "exploration:rollback")))

        after = load(self.root)
        self.assertEqual(after["decisions"], before["decisions"])
        self.assertEqual(after["explorations"], before["explorations"])
        self.assertEqual(target.read_bytes(), target_before)


if __name__ == "__main__":
    unittest.main()
