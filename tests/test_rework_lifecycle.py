"""Closed deliveries can re-enter work without consuming their historical evidence."""
import copy
import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import test_fcpxml_delivery_backend as backend_fixture
from tests.test_hyperframes_single_source import write_json
from scripts.build_delivery_package import build_delivery_package
from scripts.workflow_review import record_fcp_acceptance
from scripts.workflow_status import resolve_stage_status


class ReworkLifecycleTests(unittest.TestCase):
    def lifecycle(self):
        try:
            return importlib.import_module("scripts.rework_lifecycle")
        except ModuleNotFoundError:
            self.fail("closed-invocation rework lifecycle is not implemented")

    def closed(self, directory):
        root, _, _ = backend_fixture.DeliveryPackageTests().make_package_version(directory)
        package = build_delivery_package(root)
        record_fcp_acceptance(root, actor="user")
        manifest = json.loads((root / "animation-manifest.json").read_text())
        manifest["workflow"]["roundTripRequired"] = False
        write_json(root / "animation-manifest.json", manifest)
        self.assertIsNone(resolve_stage_status(root)["blockingStage"])
        return root, Path(package["packagePath"])

    def test_motion_reopen_preserves_a11_and_archives_exact_closed_facts(self):
        api = self.lifecycle()
        with tempfile.TemporaryDirectory() as directory:
            root, package = self.closed(directory)
            original = (root / "animation-manifest.json").read_bytes()
            before = json.loads(original)
            movies = {p.name: p.read_bytes() for p in package.iterdir()}
            result = api.begin_rework(root, {"p1s01_c01_title": ["motion"]}, "adjust entrance")
            current = json.loads((root / "animation-manifest.json").read_text())
            self.assertEqual(result["revision"], 1)
            self.assertEqual(current["workflow"]["stageEvidence"]["A11"], before["workflow"]["stageEvidence"]["A11"])
            self.assertEqual((root / result["archive"] / "files/animation-manifest.json").read_bytes(), original)
            self.assertEqual({p.name: p.read_bytes() for p in package.iterdir()}, movies)
            self.assertEqual(resolve_stage_status(root)["blockingStage"], "A12")
            self.assertTrue(set(f"A{i}" for i in range(1, 12)).issubset(resolve_stage_status(root)["completedStages"]))
            self.assertEqual(current["workflow"]["stageEvidence"]["A13"]["comments"], [])
            self.assertNotIn("D5", current["workflow"]["stageEvidence"])
            self.assertEqual(api.verify_rework_history(root)["status"], "valid")

    def test_closed_non_review_writers_reject_before_touching_artifacts(self):
        from scripts.layout_lock import freeze_layout
        from scripts.assemble_hyperframes import assemble_hyperframes
        from scripts.sync_delivery import sync_delivery
        from scripts.sync_storyboard import sync_storyboard
        from scripts.render_animations import render_animations
        from scripts.register_delivery_assets import register_delivery_assets
        from scripts.serve_workflow_review import review_state
        from scripts.demo_evidence import write_demo_generation_evidence
        with tempfile.TemporaryDirectory() as directory:
            root, _ = self.closed(directory)
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            for operation in [assemble_hyperframes, sync_delivery, sync_storyboard,
                              render_animations, register_delivery_assets,
                              lambda r: write_demo_generation_evidence(r, 'missing.mp4', inputs={}, probe={}),
                              lambda r: freeze_layout(r, 'p1s01_c01_title', r / 'missing.png')]:
                with self.assertRaisesRegex(ValueError, 'closed.*rework'):
                    operation(root)
            after = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            self.assertEqual(before, after)
            self.assertTrue(review_state(root)['closed'])
            self.assertEqual(build_delivery_package(root)['status'], 'reused')

    def test_static_reopen_invalidates_only_requested_cue_approval(self):
        api = self.lifecycle()
        with tempfile.TemporaryDirectory() as directory:
            root, _ = self.closed(directory)
            before = json.loads((root / "animation-manifest.json").read_text())
            api.begin_rework(root, {"p1s01_c01_title": ["static", "motion"]}, "revise title")
            current = json.loads((root / "animation-manifest.json").read_text())
            approvals = current["workflow"]["stageEvidence"]["A11"]["cueApprovals"]
            self.assertEqual(approvals["p1s01_c01_title"]["status"], "invalidated")
            self.assertEqual(approvals["p1s01_c02_card"], before["workflow"]["stageEvidence"]["A11"]["cueApprovals"]["p1s01_c02_card"])
            self.assertEqual(resolve_stage_status(root)["blockingStage"], "A11")

    def test_open_workflow_cannot_be_reopened_twice(self):
        api = self.lifecycle()
        with tempfile.TemporaryDirectory() as directory:
            root, _ = self.closed(directory)
            api.begin_rework(root, {"p1s01_c01_title": ["motion"]}, "first")
            before = (root / "animation-manifest.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "closed"):
                api.begin_rework(root, {"p1s01_c01_title": ["motion"]}, "second")
            self.assertEqual((root / "animation-manifest.json").read_bytes(), before)
            self.assertFalse((root / "rework/history/r0001").exists())

    def test_old_decimal_comments_are_archived_unchanged_and_new_review_is_schema_valid(self):
        api = self.lifecycle()
        from scripts.manifest_schema import validate_manifest_schema
        with tempfile.TemporaryDirectory() as directory:
            root, _ = self.closed(directory)
            path = root / "animation-manifest.json"
            manifest = json.loads(path.read_text())
            manifest["workflow"]["stageEvidence"]["A13"]["comments"] = [{
                "id": "A13-C0001", "stageId": "A13", "revision": 1,
                "author": "user", "body": "old opinion", "status": "accepted",
                "impactScopes": ["motion"], "timeStart": "2.900s",
            }]
            manifest["workflow"]["stageEvidence"]["A13"]["commentRevision"] = 1
            write_json(path, manifest)
            original = path.read_bytes()
            result = api.begin_rework(root, {"p1s01_c01_title": ["motion"]}, "another entrance")
            self.assertEqual((root / result["archive"] / "files/animation-manifest.json").read_bytes(), original)
            validate_manifest_schema(json.loads(path.read_text()))

    def test_archive_write_failure_never_reopens_active_manifest(self):
        api = self.lifecycle()
        with tempfile.TemporaryDirectory() as directory:
            root, _ = self.closed(directory)
            before = (root / "animation-manifest.json").read_bytes()
            with patch.object(api.shutil, "copy2", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    api.begin_rework(root, {"p1s01_c01_title": ["motion"]}, "test")
            self.assertEqual((root / "animation-manifest.json").read_bytes(), before)
            self.assertFalse((root / "rework/history/r0000").exists())

    def test_archived_inputs_are_copied_not_hardlinked_and_tampering_is_detected(self):
        api = self.lifecycle()
        with tempfile.TemporaryDirectory() as directory:
            root, _ = self.closed(directory)
            result = api.begin_rework(root, {"p1s01_c01_title": ["motion"]}, "test")
            relative = "compositions/motion/p1s01-c01-title.js"
            archived = root / result["archive"] / "files" / relative
            old = archived.read_bytes()
            (root / relative).write_bytes(b"new working copy")
            self.assertEqual(archived.read_bytes(), old)
            archived.write_bytes(b"corrupted archive")
            with self.assertRaisesRegex(ValueError, "archive"):
                api.verify_rework_history(root)

    def test_unknown_or_source_only_cue_cannot_open_rework(self):
        api = self.lifecycle()
        with tempfile.TemporaryDirectory() as directory:
            root, _ = self.closed(directory)
            before = (root / "animation-manifest.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "animated cue"):
                api.begin_rework(root, {"unknown": ["motion"]}, "test")
            self.assertEqual((root / "animation-manifest.json").read_bytes(), before)

    def test_archived_working_copy_rejects_controlled_writes(self):
        api = self.lifecycle()
        from scripts.manifest_transaction import manifest_transaction
        with tempfile.TemporaryDirectory() as directory:
            root, _ = self.closed(directory)
            result = api.begin_rework(root, {"p1s01_c01_title": ["motion"]}, "test")
            with self.assertRaisesRegex(ValueError, "archived"):
                with manifest_transaction(root / result["archive"] / "files"):
                    pass

    def test_closed_review_cannot_mutate_before_formal_reopen(self):
        from scripts.workflow_review import add_review_comment
        from scripts.serve_workflow_review import review_state
        with tempfile.TemporaryDirectory() as directory:
            root, _ = self.closed(directory)
            self.assertTrue(review_state(root)["closed"])
            self.assertEqual(review_state(root)["reworkRevision"], 0)
            before = (root / "animation-manifest.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "rework|重开"):
                add_review_comment(root, stage_id="A11", body="new request", actor="user", cue_id="p1s01_c01_title", frame_id="hero")
            self.assertEqual((root / "animation-manifest.json").read_bytes(), before)

    def test_registered_demo_reopens_when_concrete_generation_input_changes(self):
        from scripts.workflow_review import register_demo
        from tests.test_hyperframes_single_source import SingleSourceFixture
        with tempfile.TemporaryDirectory() as directory:
            root, _ = self.closed(directory)
            self.lifecycle().begin_rework(root, {"p1s01_c01_title": ["motion"]}, "test")
            relative = "previews/new.mp4"
            (root / relative).write_bytes(b"new demo")
            SingleSourceFixture().write_demo_evidence(root, relative)
            register_demo(root, relative)
            (root / "assets/media/rough-cut.m4v").write_bytes(b"different rough cut")
            self.assertEqual(resolve_stage_status(root)["blockingStage"], "A12")

    def test_new_revision_rejects_old_demo_evidence_even_when_inputs_unchanged(self):
        api = self.lifecycle()
        with tempfile.TemporaryDirectory() as directory:
            root, _ = self.closed(directory)
            original = json.loads((root / "animation-manifest.json").read_text())
            api.begin_rework(root, {"p1s01_c01_title": ["motion"]}, "test")
            current = json.loads((root / "animation-manifest.json").read_text())
            current["workflow"]["stageEvidence"]["A12"] = original["workflow"]["stageEvidence"]["A12"]
            write_json(root / "animation-manifest.json", current)
            status = resolve_stage_status(root)
            self.assertEqual(status["blockingStage"], "A12")
            self.assertEqual(status["evidence"]["A12"], "rework-revision-mismatch")

    def test_two_rework_cycles_publish_separate_outputs_and_preserve_history(self):
        api = self.lifecycle()
        from scripts.workflow_review import register_demo, approve_demo, authorize_native_render
        from scripts.render_animations import render_animations
        from scripts.register_delivery_assets import register_delivery_assets
        from scripts.rework_state import render_ledger_path
        from tests.test_hyperframes_single_source import SingleSourceFixture
        with tempfile.TemporaryDirectory() as directory:
            root, first_package = self.closed(directory)
            original = {p.name: p.read_bytes() for p in first_package.iterdir()}
            package_names = {first_package.name}
            for revision in (1, 2):
                api.begin_rework(root, {"p1s01_c01_title": ["motion"]}, f"revision {revision}")
                preview = f"previews/rework-{revision}.mp4"
                (root / preview).write_bytes(f"new demo {revision}".encode())
                SingleSourceFixture().write_demo_evidence(root, preview)
                register_demo(root, preview)
                approve_demo(root, actor="user")
                authorize_native_render(root, actor="user")
                def runner(command, **kwargs):
                    path = Path(command[command.index("--output") + 1])
                    path.write_bytes(f"render {revision} {path.name}".encode())
                render_animations(root, runner=runner, prober=lambda _: backend_fixture.valid_asset_probe())
                register_delivery_assets(root, prober=lambda _: backend_fixture.valid_asset_probe())
                published = build_delivery_package(root)
                self.assertNotIn(Path(published["packagePath"]).name, package_names)
                package_names.add(Path(published["packagePath"]).name)
                self.assertEqual(resolve_stage_status(root)["blockingStage"], "D5")
                record_fcp_acceptance(root, actor="user")
                self.assertIsNone(resolve_stage_status(root)["blockingStage"])
                current = json.loads((root / "animation-manifest.json").read_text())
                ledger = json.loads(render_ledger_path(root, current).read_text())
                self.assertEqual(ledger["reworkRevision"], revision)
                self.assertEqual(current["workflow"]["stageEvidence"]["D5"]["reworkRevision"], revision)
                self.assertEqual(api.verify_rework_history(root)["archiveCount"], revision)
            self.assertEqual({p.name: p.read_bytes() for p in first_package.iterdir()}, original)


if __name__ == "__main__":
    unittest.main()
