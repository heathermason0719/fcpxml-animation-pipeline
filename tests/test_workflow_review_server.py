from __future__ import annotations

import json
import tempfile
import unittest

from scripts.layout_lock import freeze_layout
from scripts.sync_storyboard import sync_storyboard
from scripts.workflow_review import register_demo
from tests.test_hyperframes_single_source import SingleSourceFixture, write_json


class WorkflowReviewServerTests(SingleSourceFixture):
    def make_review_version(self, directory: str):
        root = self.make_version(directory)
        sync_storyboard(root)
        poster = root / "approved.png"
        poster.write_bytes(b"approved poster")
        freeze_layout(root, "p1s01_c01_title", poster)
        manifest_path = root / "animation-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["workflow"] = {"stageContractVersion": "1.0.0", "stageEvidence": {}}
        write_json(manifest_path, manifest)
        return root

    def test_state_is_bound_to_one_vn_and_exposes_storyboard_assets(self) -> None:
        try:
            from scripts.serve_workflow_review import review_state
        except ModuleNotFoundError:
            self.fail("single-Vn Review server is not implemented")

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_review_version(directory)

            state = review_state(root)

            self.assertEqual(state["sourceVersion"], "2026-08-26_V1")
            self.assertEqual(state["stageStatus"]["blockingStage"], "A11")
            self.assertEqual(len(state["manifestSha256"]), 64)
            self.assertEqual(
                state["cues"][0]["approvedPoster"],
                "approvals/a11/p1s01-c01-title.png",
            )
            self.assertEqual(state["cues"][0]["reviewSrc"], "compositions/review/p1s01-c01-title.html")
            self.assertEqual(state["cues"][0]["finalAnimationDescription"], "标题居中落定并保持。")
            self.assertNotIn("designBrief", state["cues"][0])

    def test_repository_review_shell_does_not_consume_vn_frame_snapshot(self) -> None:
        from scripts.serve_workflow_review import INDEX_HTML, review_state

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_review_version(directory)
            (root / "frame.md").write_text(
                "# Project-only visual direction\n\nbody { background: hotpink; }\n",
                encoding="utf-8",
            )
            state = review_state(root)

            self.assertNotIn("frame.md", INDEX_HTML)
            self.assertNotIn("visualSpec", state)
            self.assertNotIn("reviewTheme", state)

    def test_shell_uses_contextual_storyboard_and_demo_controls(self) -> None:
        from scripts.serve_workflow_review import INDEX_HTML

        self.assertIn("add-storyboard-comment", INDEX_HTML)
        self.assertIn("add-demo-comment", INDEX_HTML)
        self.assertIn('id="impactStatic"', INDEX_HTML)
        self.assertIn('id="impactMotion"', INDEX_HTML)
        self.assertIn('id="useRange"', INDEX_HTML)
        self.assertNotIn("stageSelect", INDEX_HTML)
        self.assertNotIn("cueSelect", INDEX_HTML)
        self.assertNotIn('type="time"', INDEX_HTML)
        self.assertIn("最终动画说明", INDEX_HTML)
        self.assertNotIn("表达目的", INDEX_HTML)
        self.assertNotIn("静态构图", INDEX_HTML)
        self.assertNotIn("设计理由", INDEX_HTML)
        self.assertNotIn("已确认补充", INDEX_HTML)
        self.assertIn('id="notice" role="status" aria-live="polite"', INDEX_HTML)
        self.assertIn("showNotice(result.message)", INDEX_HTML)

    def test_storyboard_exposes_locked_main_and_auxiliary_frames(self) -> None:
        from scripts.serve_workflow_review import review_state

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_version(directory)
            sync_storyboard(root)
            hero = root / "hero.png"
            cinema = root / "cinema.png"
            interview = root / "interview.png"
            hero.write_bytes(b"surveillance")
            cinema.write_bytes(b"cinema")
            interview.write_bytes(b"interview")
            freeze_layout(
                root,
                "p1s01_c01_title",
                hero,
                hero_id="surveillance",
                hero_label="最终监控框",
                auxiliary_frames=[
                    ("cinema", "电影院宽银幕", cinema),
                    ("interview", "电视访谈技术框", interview),
                ],
            )
            manifest_path = root / "animation-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["workflow"] = {"stageContractVersion": "1.0.0", "stageEvidence": {}}
            write_json(manifest_path, manifest)

            frames = review_state(root)["cues"][0]["frames"]

            self.assertEqual(
                [(frame["id"], frame["role"], frame["label"]) for frame in frames],
                [
                    ("surveillance", "hero", "最终监控框"),
                    ("cinema", "auxiliary", "电影院宽银幕"),
                    ("interview", "auxiliary", "电视访谈技术框"),
                ],
            )

    def test_storyboard_rejects_approval_without_final_animation_description(self) -> None:
        from scripts.serve_workflow_review import apply_review_action, review_state

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_review_version(directory)
            manifest_path = root / "animation-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["cues"][0].pop("finalAnimationDescription")
            write_json(manifest_path, manifest)
            state = review_state(root)

            self.assertFalse(state["cues"][0]["canApprove"])
            self.assertIn("缺少最终动画说明", state["cues"][0]["approvalBlockers"])
            with self.assertRaisesRegex(ValueError, "finalAnimationDescription"):
                apply_review_action(
                    root,
                    "approve-storyboard",
                    {"manifestSha256": state["manifestSha256"]},
                )

    def test_storyboard_disables_approval_when_the_live_layout_lock_is_invalid(self) -> None:
        from scripts.serve_workflow_review import review_state

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_review_version(directory)
            composition = root / "compositions/cues/p1s01-c01-title.html"
            composition.write_text(
                composition.read_text(encoding="utf-8").replace("标题", "已变化的标题"),
                encoding="utf-8",
            )

            state = review_state(root)

            self.assertFalse(state["cues"][0]["canApprove"])
            self.assertEqual(state["stageStatus"]["blockingStage"], "A11")

    def test_actions_require_fresh_manifest_and_use_user_authority(self) -> None:
        from scripts.serve_workflow_review import apply_review_action, review_state

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_review_version(directory)
            first = review_state(root)

            result = apply_review_action(
                root,
                "approve-storyboard",
                {"manifestSha256": first["manifestSha256"]},
            )

            self.assertEqual(result["result"]["status"], "approved")
            with self.assertRaisesRegex(ValueError, "stale Review state"):
                apply_review_action(
                    root,
                    "approve-storyboard",
                    {"manifestSha256": first["manifestSha256"]},
                )

    def test_storyboard_action_derives_a11_static_context_and_persists_on_refresh(self) -> None:
        from scripts.serve_workflow_review import apply_review_action, review_state

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_review_version(directory)
            state = review_state(root)

            result = apply_review_action(
                root,
                "add-storyboard-comment",
                {
                    "manifestSha256": state["manifestSha256"],
                    "cueId": "p1s01_c01_title",
                    "frameId": "hero",
                    "body": "标题与画面主体再拉开一些",
                },
            )
            refreshed = review_state(root)
            comment = result["result"]

            self.assertEqual(comment["stageId"], "A11")
            self.assertEqual(comment["impactScopes"], ["static"])
            self.assertEqual(comment["cueId"], "p1s01_c01_title")
            self.assertEqual(comment["frameId"], "hero")
            self.assertNotIn("timeStart", comment)
            self.assertEqual(refreshed["cues"][0]["comments"], [comment])
            self.assertEqual(result["message"], "评论已保存")
            self.assertEqual(
                refreshed["cues"][0]["frames"][0]["src"],
                state["cues"][0]["frames"][0]["src"],
            )
            self.assertEqual(refreshed["cues"][0]["layoutRevision"], 1)
            self.assertEqual(refreshed["cues"][0]["approvalBlockers"], ["存在未处理 comment"])

    def test_demo_action_derives_a13_and_binds_player_context(self) -> None:
        from scripts.serve_workflow_review import apply_review_action, review_state

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_review_version(directory)
            state = review_state(root)
            apply_review_action(root, "approve-storyboard", {"manifestSha256": state["manifestSha256"]})
            preview = root / "previews/demo.mp4"
            preview.parent.mkdir(parents=True, exist_ok=True)
            preview.write_bytes(b"demo")
            register_demo(root, "previews/demo.mp4")
            state = review_state(root)

            result = apply_review_action(
                root,
                "add-demo-comment",
                {
                    "manifestSha256": state["manifestSha256"],
                    "impactScopes": ["static", "motion"],
                    "cueId": "p1s01_c01_title",
                    "timeStart": "1s",
                    "timeEnd": "3/2s",
                    "body": "终态提高，同时减速更沉",
                },
            )
            refreshed = review_state(root)
            comment = result["result"]

            self.assertEqual(comment["stageId"], "A13")
            self.assertEqual(comment["impactScopes"], ["static", "motion"])
            self.assertEqual(comment["cueId"], "p1s01_c01_title")
            self.assertEqual(comment["timeStart"], "1s")
            self.assertEqual(comment["timeEnd"], "3/2s")
            self.assertEqual(refreshed["demo"]["comments"], [comment])

    def test_demo_action_requires_the_player_time_context(self) -> None:
        from scripts.serve_workflow_review import apply_review_action, review_state

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_review_version(directory)
            state = review_state(root)

            with self.assertRaisesRegex(ValueError, "timeStart"):
                apply_review_action(
                    root,
                    "add-demo-comment",
                    {
                        "manifestSha256": state["manifestSha256"],
                        "impactScopes": ["motion"],
                        "body": "运动问题必须绑定播放器时间",
                    },
                )

    def test_demo_state_and_motion_comment_roundtrip_through_api_core(self) -> None:
        from scripts.serve_workflow_review import apply_review_action, review_state

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_review_version(directory)
            state = review_state(root)
            apply_review_action(root, "approve-storyboard", {"manifestSha256": state["manifestSha256"]})
            preview = root / "previews/demo.mp4"
            preview.parent.mkdir(parents=True, exist_ok=True)
            preview.write_bytes(b"demo")
            register_demo(root, "previews/demo.mp4")
            state = review_state(root)

            result = apply_review_action(
                root,
                "add-comment",
                {
                    "manifestSha256": state["manifestSha256"],
                    "stageId": "A13",
                    "issueType": "motion",
                    "body": "节奏需要调整",
                    "cueId": "p1s01_c01_title",
                    "timeStart": "1s",
                },
            )

            self.assertEqual(state["demo"]["src"], "previews/demo.mp4")
            self.assertEqual(result["result"]["impactScopes"], ["motion"])
            self.assertEqual(review_state(root)["comments"][0]["status"], "open")


if __name__ == "__main__":
    unittest.main()
