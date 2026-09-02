from __future__ import annotations

import copy
import json
import hashlib
import tempfile
from pathlib import Path

from tests.test_hyperframes_single_source import SingleSourceFixture, write_json

from scripts.layout_lock import freeze_layout
from scripts.sync_storyboard import sync_storyboard


class WorkflowStatusTests(SingleSourceFixture):
    def replace_runtime_pin(self, root: Path, old: str, new: str) -> None:
        package = root / "package.json"
        package.write_text(
            package.read_text(encoding="utf-8").replace(f"hyperframes@{old}", f"hyperframes@{new}"),
            encoding="utf-8",
        )

    def make_locked_version(self, directory: str) -> Path:
        root = self.make_version(directory)
        sync_storyboard(root)
        poster = root / "approved.png"
        poster.write_bytes(b"user approved poster")
        freeze_layout(root, "p1s01_c01_title", poster)
        manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
        manifest["workflow"] = {
            "stageContractVersion": "1.0.0",
            "stageEvidence": {},
        }
        write_json(root / "animation-manifest.json", manifest)
        return root

    def approve_a11(self, root: Path, *, contract_version: str = "1.0.0") -> None:
        manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
        cue = manifest["cues"][0]
        lock = cue["renderAdapters"]["hyperframes"]["layoutLock"]
        manifest["workflow"]["stageEvidence"]["A11"] = {
            "stageId": "A11",
            "contractVersion": contract_version,
            "semanticVersion": 1,
            "status": "approved",
            "comments": [],
            "cueApprovals": {
                cue["id"]: {
                    "status": "approved",
                    "runtimeVersion": lock["runtimeVersion"],
                    "layoutRevision": lock["revision"],
                    "layoutAggregateSha256": lock["aggregateSha256"],
                    "approvedPosterSha256": lock["approvedPosterSha256"],
                    "reviewFrameSetSha256": lock["reviewFrameSetSha256"],
                    "commentRevision": 0,
                }
            },
        }
        write_json(root / "animation-manifest.json", manifest)

    def register_a12(self, root: Path) -> None:
        try:
            from scripts.workflow_status import current_input_fingerprint
        except ImportError:
            self.fail("workflow input fingerprint is not implemented")
        preview = root / "previews/demo.mp4"
        preview.parent.mkdir()
        preview.write_bytes(b"current demo")
        manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
        manifest["workflow"]["stageEvidence"]["A12"] = {
            "stageId": "A12",
            "contractVersion": "1.0.0",
            "semanticVersion": 1,
            "status": "ready",
            "preview": "previews/demo.mp4",
            "sha256": hashlib.sha256(preview.read_bytes()).hexdigest(),
            "inputFingerprint": current_input_fingerprint(root, manifest),
        }
        write_json(root / "animation-manifest.json", manifest)

    def approve_a13(self, root: Path) -> None:
        manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
        demo = manifest["workflow"]["stageEvidence"]["A12"]
        manifest["workflow"]["stageEvidence"]["A13"] = {
            "stageId": "A13",
            "contractVersion": "1.0.0",
            "semanticVersion": 1,
            "status": "approved",
            "comments": [],
            "demoSha256": demo["sha256"],
            "inputFingerprint": demo["inputFingerprint"],
            "commentRevision": 0,
        }
        write_json(root / "animation-manifest.json", manifest)

    def authorize_a14(self, root: Path) -> None:
        manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
        demo = manifest["workflow"]["stageEvidence"]["A12"]
        manifest["workflow"]["stageEvidence"]["A14"] = {
            "stageId": "A14",
            "contractVersion": "1.0.0",
            "semanticVersion": 1,
            "status": "authorized",
            "demoSha256": demo["sha256"],
            "inputFingerprint": demo["inputFingerprint"],
        }
        write_json(root / "animation-manifest.json", manifest)

    def test_layout_lock_without_user_review_evidence_blocks_at_a11(self) -> None:
        try:
            from scripts.workflow_status import resolve_stage_status
        except ModuleNotFoundError:
            self.fail("workflow stage status resolver is not implemented")

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)

            status = resolve_stage_status(root)

            self.assertEqual(status["activeContext"], "A11")
            self.assertEqual(status["blockingStage"], "A11")
            self.assertEqual(status["nextEligibleStage"], "A11")
            self.assertNotIn("A11", status["completedStages"])
            self.assertEqual(status["evidence"]["A11"], "missing")

    def test_current_a11_evidence_bound_to_live_lock_advances_to_a12(self) -> None:
        from scripts.workflow_status import resolve_stage_status

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            self.approve_a11(root)

            status = resolve_stage_status(root)

            self.assertEqual(status["blockingStage"], "A12")
            self.assertEqual(status["nextEligibleStage"], "A12")
            self.assertIn("A11", status["completedStages"])
            self.assertEqual(status["evidence"]["A11"], "current")

    def test_layout_change_after_a11_approval_reopens_a11(self) -> None:
        from scripts.workflow_status import resolve_stage_status

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            self.approve_a11(root)
            composition = root / "compositions/cues/p1s01-c01-title.html"
            composition.write_text(
                composition.read_text(encoding="utf-8").replace("标题", "修改后的标题"),
                encoding="utf-8",
            )

            status = resolve_stage_status(root)

            self.assertEqual(status["blockingStage"], "A11")
            self.assertNotIn("A11", status["completedStages"])
            self.assertEqual(status["evidence"]["A11"], "layout-lock-invalid")

    def test_runtime_pin_change_after_a11_approval_reopens_a11(self) -> None:
        from scripts.workflow_status import resolve_stage_status

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            self.approve_a11(root)
            self.replace_runtime_pin(root, "0.8.26", "0.8.27")

            status = resolve_stage_status(root)

            self.assertEqual(status["blockingStage"], "A11")
            self.assertEqual(status["evidence"]["A11"], "layout-lock-invalid")

    def test_runtime_pin_change_reopens_a12_after_a11_evidence_is_rebound(self) -> None:
        from scripts.workflow_status import resolve_stage_status

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            self.approve_a11(root)
            self.register_a12(root)
            self.replace_runtime_pin(root, "0.8.26", "0.8.27")
            manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
            cue = manifest["cues"][0]
            cue["renderAdapters"]["hyperframes"]["layoutLock"]["runtimeVersion"] = "0.8.27"
            manifest["workflow"]["stageEvidence"]["A11"]["cueApprovals"][cue["id"]]["runtimeVersion"] = "0.8.27"
            write_json(root / "animation-manifest.json", manifest)

            status = resolve_stage_status(root)

            self.assertEqual(status["blockingStage"], "A12")
            self.assertEqual(status["evidence"]["A11"], "current")
            self.assertEqual(status["evidence"]["A12"], "input-fingerprint-mismatch")

    def test_current_demo_bound_to_live_inputs_advances_to_a13(self) -> None:
        from scripts.workflow_status import resolve_stage_status

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            self.approve_a11(root)
            self.register_a12(root)

            status = resolve_stage_status(root)

            self.assertEqual(status["activeContext"], "A13")
            self.assertEqual(status["blockingStage"], "A13")
            self.assertEqual(status["nextEligibleStage"], "A13")
            self.assertIn("A12", status["completedStages"])
            self.assertEqual(status["evidence"]["A12"], "current")

    def test_motion_change_keeps_a11_but_reopens_a12(self) -> None:
        from scripts.workflow_status import resolve_stage_status

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            self.approve_a11(root)
            self.register_a12(root)
            motion = root / "compositions/motion/p1s01-c01-title.js"
            motion.write_text(motion.read_text(encoding="utf-8") + "// changed\n", encoding="utf-8")

            status = resolve_stage_status(root)

            self.assertEqual(status["blockingStage"], "A12")
            self.assertIn("A11", status["completedStages"])
            self.assertNotIn("A12", status["completedStages"])
            self.assertEqual(status["evidence"]["A12"], "input-fingerprint-mismatch")

    def test_video_level_a13_approval_advances_to_a14(self) -> None:
        from scripts.workflow_status import resolve_stage_status

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            self.approve_a11(root)
            self.register_a12(root)
            self.approve_a13(root)

            status = resolve_stage_status(root)

            self.assertEqual(status["activeContext"], "A13")
            self.assertEqual(status["blockingStage"], "A14")
            self.assertEqual(status["nextEligibleStage"], "A14")
            self.assertIn("A13", status["completedStages"])
            self.assertEqual(status["evidence"]["A13"], "current")

    def test_a14_authorization_completes_d1_and_allows_d2(self) -> None:
        from scripts.workflow_status import resolve_stage_status

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            self.approve_a11(root)
            self.register_a12(root)
            self.approve_a13(root)
            self.authorize_a14(root)

            status = resolve_stage_status(root)

            self.assertIsNone(status["activeContext"])
            self.assertEqual(status["blockingStage"], "D2")
            self.assertEqual(status["nextEligibleStage"], "D2")
            self.assertIn("A14", status["completedStages"])
            self.assertIn("D1", status["completedStages"])
            self.assertEqual(status["evidence"]["A14"], "current")

    def render_d2(self, root: Path) -> None:
        from scripts.render_animations import render_animations

        def runner(command, **kwargs):
            output = Path(command[command.index("--output") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"native transparent movie")

        probe = {
            "codec_name": "prores",
            "profile": "4444",
            "width": 1920,
            "height": 1080,
            "pix_fmt": "yuva444p12le",
            "r_frame_rate": "24/1",
            "duration": "2.000000",
        }
        render_animations(root, runner=runner, prober=lambda _: probe)

    def test_valid_d2_ledger_bound_to_current_authorization_advances_to_d3(self) -> None:
        from scripts.workflow_status import resolve_stage_status

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            self.approve_a11(root)
            self.register_a12(root)
            self.approve_a13(root)
            self.authorize_a14(root)
            self.render_d2(root)

            status = resolve_stage_status(root)

            self.assertEqual(status["blockingStage"], "D3")
            self.assertIn("D2", status["completedStages"])
            self.assertEqual(status["evidence"]["D2"], "current")

    def test_existing_render_is_not_d2_complete_after_movie_bytes_change(self) -> None:
        from scripts.workflow_status import resolve_stage_status

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            self.approve_a11(root)
            self.register_a12(root)
            self.approve_a13(root)
            self.authorize_a14(root)
            self.render_d2(root)
            movie = root / "delivery/prores4444/p1s01-c01-title.mov"
            movie.write_bytes(b"changed after validation")

            status = resolve_stage_status(root)

            self.assertEqual(status["blockingStage"], "D2")
            self.assertNotIn("D2", status["completedStages"])
            self.assertEqual(status["evidence"]["D2"], "artifact-hash-mismatch")

    def register_d3(self, root: Path) -> None:
        from scripts.register_delivery_assets import register_delivery_assets

        probe = {
            "codec_name": "prores",
            "profile": "4444",
            "width": 1920,
            "height": 1080,
            "pix_fmt": "yuva444p12le",
            "r_frame_rate": "24/1",
            "duration": "2.000000",
            "audio_streams": 0,
        }
        register_delivery_assets(root, prober=lambda _: probe)

    def test_current_registered_assets_advance_to_d4(self) -> None:
        from scripts.workflow_status import resolve_stage_status

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            self.approve_a11(root)
            self.register_a12(root)
            self.approve_a13(root)
            self.authorize_a14(root)
            self.render_d2(root)
            self.register_d3(root)

            status = resolve_stage_status(root)

            self.assertEqual(status["blockingStage"], "D4")
            self.assertIn("D3", status["completedStages"])
            self.assertEqual(status["evidence"]["D3"], "current")

    def test_delivery_asset_existence_does_not_complete_d3_after_manifest_drift(self) -> None:
        from scripts.workflow_status import resolve_stage_status

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            self.approve_a11(root)
            self.register_a12(root)
            self.approve_a13(root)
            self.authorize_a14(root)
            self.render_d2(root)
            self.register_d3(root)
            manifest_path = root / "animation-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["cues"][0]["deliveryAsset"]["fileName"] = "AF__drift.mov"
            write_json(manifest_path, manifest)

            status = resolve_stage_status(root)

            self.assertEqual(status["blockingStage"], "D3")
            self.assertNotIn("D3", status["completedStages"])
            self.assertEqual(status["evidence"]["D3"], "asset-fingerprint-mismatch")

    def test_a13_static_comment_reopens_a11_without_leaving_demo_context(self) -> None:
        try:
            from scripts.workflow_review import add_review_comment
        except ModuleNotFoundError:
            self.fail("workflow review state mutations are not implemented")
        from scripts.workflow_status import resolve_stage_status

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            self.approve_a11(root)
            self.register_a12(root)
            self.approve_a13(root)
            self.authorize_a14(root)

            comment = add_review_comment(
                root,
                stage_id="A13",
                issue_type="static",
                body="字号需要调整",
                cue_id="p1s01_c01_title",
                time_start="1s",
                actor="user",
            )
            status = resolve_stage_status(root)
            manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(comment["status"], "open")
            self.assertEqual(status["activeContext"], "A13")
            self.assertEqual(status["blockingStage"], "A11")
            self.assertIsNotNone(manifest["cues"][0]["renderAdapters"]["hyperframes"]["layoutLock"])
            self.assertEqual(manifest["cues"][0]["workflowState"], "layout-approved")
            self.assertEqual(manifest["workflow"]["stageEvidence"]["A13"]["status"], "invalidated")
            self.assertEqual(manifest["workflow"]["stageEvidence"]["A14"]["status"], "invalidated")

    def test_a13_comment_can_invalidate_static_and_motion_with_one_record(self) -> None:
        from scripts.workflow_review import add_review_comment
        from scripts.workflow_status import resolve_stage_status

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            self.approve_a11(root)
            self.register_a12(root)
            self.approve_a13(root)
            self.authorize_a14(root)

            comment = add_review_comment(
                root,
                stage_id="A13",
                impact_scopes=["static", "motion"],
                body="标题位置提高，同时收尾减速更沉",
                cue_id="p1s01_c01_title",
                time_start="1s",
                actor="user",
            )
            status = resolve_stage_status(root)
            manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(comment["impactScopes"], ["static", "motion"])
            self.assertNotIn("issueType", comment)
            self.assertEqual(status["activeContext"], "A13")
            self.assertEqual(status["blockingStage"], "A11")
            self.assertIsNotNone(manifest["cues"][0]["renderAdapters"]["hyperframes"]["layoutLock"])
            self.assertEqual(manifest["cues"][0]["workflowState"], "layout-approved")
            self.assertEqual(manifest["workflow"]["stageEvidence"]["A13"]["status"], "invalidated")
            self.assertEqual(manifest["workflow"]["stageEvidence"]["A14"]["status"], "invalidated")

    def test_a13_comment_requires_user_selected_impact_scope(self) -> None:
        from scripts.workflow_review import add_review_comment

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)

            with self.assertRaisesRegex(ValueError, "impactScopes"):
                add_review_comment(
                    root,
                    stage_id="A13",
                    impact_scopes=[],
                    body="没有选择影响范围",
                    cue_id="p1s01_c01_title",
                    time_start="1s",
                    actor="user",
                )

    def test_a13_motion_comment_keeps_a11_lock_and_invalidates_only_downstream_approval(self) -> None:
        from scripts.workflow_review import add_review_comment
        from scripts.workflow_status import resolve_stage_status

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            self.approve_a11(root)
            self.register_a12(root)
            self.approve_a13(root)
            self.authorize_a14(root)

            add_review_comment(
                root,
                stage_id="A13",
                issue_type="motion",
                body="入场节奏太快",
                cue_id="p1s01_c01_title",
                time_start="1s",
                time_end="3/2s",
                actor="user",
            )
            status = resolve_stage_status(root)
            manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(status["blockingStage"], "A13")
            self.assertIn("A11", status["completedStages"])
            self.assertIsNotNone(manifest["cues"][0]["renderAdapters"]["hyperframes"]["layoutLock"])
            self.assertEqual(manifest["workflow"]["stageEvidence"]["A13"]["status"], "invalidated")
            self.assertEqual(manifest["workflow"]["stageEvidence"]["A14"]["status"], "invalidated")

    def test_user_bulk_a11_approval_accepts_addressed_comments_but_agent_cannot_approve(self) -> None:
        try:
            from scripts.workflow_review import address_review_comment, approve_storyboard
        except ImportError:
            self.fail("review comment handling and Storyboard approval are not implemented")
        from scripts.workflow_review import add_review_comment

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            comment = add_review_comment(
                root,
                stage_id="A11",
                issue_type="static",
                body="标题需要重新排版",
                cue_id="p1s01_c01_title",
                frame_id="hero",
                actor="user",
            )
            address_review_comment(root, "A11", comment["id"], actor="agent")
            poster = root / "reapproved.png"
            poster.write_bytes(b"reapproved poster")
            freeze_layout(root, "p1s01_c01_title", poster)

            with self.assertRaisesRegex(ValueError, "only the user may approve Storyboard"):
                approve_storyboard(root, actor="agent")
            result = approve_storyboard(root, actor="user")
            manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
            a11 = manifest["workflow"]["stageEvidence"]["A11"]

            self.assertEqual(result["approvedCueIds"], ["p1s01_c01_title"])
            self.assertEqual(a11["status"], "approved")
            self.assertEqual(a11["comments"][0]["status"], "accepted")
            self.assertEqual(a11["cueApprovals"]["p1s01_c01_title"]["status"], "approved")

    def test_storyboard_can_approve_one_clean_cue_while_another_cue_is_reopened(self) -> None:
        from scripts.workflow_review import add_review_comment, approve_storyboard

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            manifest_path = root / "animation-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            first = manifest["cues"][0]
            second = copy.deepcopy(first)
            second["id"] = "p1s01_c02_second"
            second["renderAdapters"]["hyperframes"]["compositionId"] = "p1s01-c02-second"
            manifest["cues"].insert(1, second)
            write_json(manifest_path, manifest)

            add_review_comment(
                root,
                stage_id="A11",
                impact_scopes=["static"],
                body="第一个镜头仍需修改",
                cue_id=first["id"],
                frame_id="hero",
                actor="user",
            )

            result = approve_storyboard(root, actor="user", cue_ids=[second["id"]])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            a11 = manifest["workflow"]["stageEvidence"]["A11"]

            self.assertEqual(result["status"], "partially-approved")
            self.assertEqual(result["approvedCueIds"], [second["id"]])
            self.assertNotIn(first["id"], a11["cueApprovals"])
            self.assertEqual(a11["cueApprovals"][second["id"]]["status"], "approved")

    def test_register_demo_uses_actual_file_and_current_inputs(self) -> None:
        try:
            from scripts.workflow_review import register_demo
        except ImportError:
            self.fail("A12 Demo registration is not implemented")
        from scripts.workflow_status import resolve_stage_status

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            self.approve_a11(root)
            preview = root / "previews/demo.mp4"
            preview.parent.mkdir()
            preview.write_bytes(b"registered demo")

            result = register_demo(root, "previews/demo.mp4")
            status = resolve_stage_status(root)

            self.assertEqual(result["stageId"], "A12")
            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["sha256"], hashlib.sha256(b"registered demo").hexdigest())
            self.assertEqual(status["blockingStage"], "A13")

    def test_user_approves_complete_demo_then_separately_authorizes_native_render(self) -> None:
        try:
            from scripts.workflow_review import approve_demo, authorize_native_render
        except ImportError:
            self.fail("A13 approval and A14 authorization are not implemented")
        from scripts.workflow_review import add_review_comment, address_review_comment, register_demo
        from scripts.workflow_status import resolve_stage_status

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            self.approve_a11(root)
            preview = root / "previews/demo.mp4"
            preview.parent.mkdir()
            preview.write_bytes(b"approved demo")
            register_demo(root, "previews/demo.mp4")
            comment = add_review_comment(
                root,
                stage_id="A13",
                issue_type="motion",
                body="已修正的节奏问题",
                cue_id="p1s01_c01_title",
                time_start="1s",
                actor="user",
            )
            address_review_comment(root, "A13", comment["id"], actor="agent")

            with self.assertRaisesRegex(ValueError, "only the user may approve the Demo"):
                approve_demo(root, actor="agent")
            approval = approve_demo(root, actor="user")
            self.assertEqual(approval["status"], "approved")
            self.assertEqual(resolve_stage_status(root)["blockingStage"], "A14")

            with self.assertRaisesRegex(ValueError, "only the user may authorize native rendering"):
                authorize_native_render(root, actor="agent")
            authorization = authorize_native_render(root, actor="user")
            status = resolve_stage_status(root)

            self.assertEqual(authorization["status"], "authorized")
            self.assertEqual(status["blockingStage"], "D2")
            manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["workflow"]["stageEvidence"]["A13"]["comments"][0]["status"], "accepted")

    def test_demo_approval_rejects_open_comments(self) -> None:
        from scripts.workflow_review import add_review_comment, approve_demo, register_demo

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            self.approve_a11(root)
            preview = root / "previews/demo.mp4"
            preview.parent.mkdir()
            preview.write_bytes(b"demo with open comment")
            register_demo(root, "previews/demo.mp4")
            add_review_comment(
                root,
                stage_id="A13",
                issue_type="motion",
                body="仍未处理",
                cue_id="p1s01_c01_title",
                time_start="1s",
                actor="user",
            )

            with self.assertRaisesRegex(ValueError, "Demo has open comments"):
                approve_demo(root, actor="user")
