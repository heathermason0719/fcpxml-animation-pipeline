import concurrent.futures
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from unittest.mock import patch

from scripts import layout_lock
from scripts import manifest_transaction as transactions
from scripts import workflow_review as review
from scripts.hyperframes_adapter import load_manifest, save_manifest
from scripts.migrate_hyperframes_runtime import migrate_hyperframes_runtime
from scripts.serve_workflow_review import apply_review_action, review_state
from tests import test_migrate_hyperframes_runtime as runtime_fixtures
from tests.test_workflow_review_server import ReviewVersionFixture


class ManifestTransactionTests(ReviewVersionFixture):
    @staticmethod
    def make_approved_version(directory):
        return runtime_fixtures.HyperFramesRuntimeMigrationTests().make_approved_version(directory)

    @staticmethod
    def submit_comment(root, body, attempted=None):
        if attempted is not None:
            attempted.set()
        return review.add_review_comment(
            root,
            stage_id="A11",
            cue_id="p1s01_c01_title",
            frame_id="hero",
            body=body,
            actor="user",
        )

    def assert_comment_preserved(self, root, body):
        manifest = json.loads((root / "animation-manifest.json").read_text())
        a11 = manifest["workflow"]["stageEvidence"]["A11"]
        self.assertEqual([comment["body"] for comment in a11.get("comments", [])], [body])
        self.assertEqual(a11["status"], "invalidated")
        self.assertEqual(a11["cueApprovals"]["p1s01_c01_title"]["status"], "invalidated")

    def test_layout_cli_mutations_do_not_overwrite_concurrent_review_comment(self):
        for action in ("freeze_layout", "approve_a11"):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as directory:
                root = self.make_approved_version(directory)
                arrived, release, attempted = threading.Event(), threading.Event(), threading.Event()
                original_save = layout_lock.save_manifest

                def controlled_save(*args, **kwargs):
                    arrived.set()
                    if not release.wait(5):
                        raise RuntimeError("layout writer was never released")
                    return original_save(*args, **kwargs)

                def run_cli():
                    if action == "freeze_layout":
                        return layout_lock.freeze_layout(root, "p1s01_c01_title", root / "approved.png")
                    return layout_lock.approve_a11(root)

                with patch.object(layout_lock, "save_manifest", side_effect=controlled_save), concurrent.futures.ThreadPoolExecutor(2) as pool:
                    writer = pool.submit(run_cli)
                    try:
                        self.assertTrue(arrived.wait(5))
                        comment = pool.submit(self.submit_comment, root, "concurrent layout feedback", attempted)
                        self.assertTrue(attempted.wait(5))
                        try:
                            comment.result(timeout=0.2)
                        except concurrent.futures.TimeoutError:
                            pass
                    finally:
                        release.set()
                    self.assertEqual(writer.result(timeout=5)["status"], "frozen" if action == "freeze_layout" else "approved")
                    comment.result(timeout=5)
                self.assert_comment_preserved(root, "concurrent layout feedback")

    def test_runtime_migration_rollback_does_not_overwrite_concurrent_review_comment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_approved_version(directory)
            before = {name: (root / name).read_bytes() for name in ("package.json", "meta.json")}
            arrived, release, attempted = threading.Event(), threading.Event(), threading.Event()

            def failing_checker(_root, _version):
                arrived.set()
                if not release.wait(5):
                    raise RuntimeError("runtime checker was never released")
                raise ValueError("controlled compatibility failure")

            with concurrent.futures.ThreadPoolExecutor(2) as pool:
                migration = pool.submit(
                    migrate_hyperframes_runtime,
                    root,
                    "0.8.27",
                    compatibility_checker=failing_checker,
                    recorded_at="2026-09-04T00:00:00Z",
                )
                try:
                    self.assertTrue(arrived.wait(5))
                    comment = pool.submit(self.submit_comment, root, "feedback during runtime check", attempted)
                    self.assertTrue(attempted.wait(5))
                    try:
                        comment.result(timeout=0.2)
                    except concurrent.futures.TimeoutError:
                        pass
                finally:
                    release.set()
                with self.assertRaisesRegex(ValueError, "controlled compatibility failure"):
                    migration.result(timeout=5)
                comment.result(timeout=5)

            self.assertEqual({name: (root / name).read_bytes() for name in before}, before)
            self.assert_comment_preserved(root, "feedback during runtime check")

    def test_cooperative_process_lock_survives_atomic_manifest_replacement(self):
        child_code = """
import json
from pathlib import Path
import sys
from scripts.manifest_transaction import manifest_transaction
from scripts.workflow_review import add_review_comment

root = Path(sys.argv[1])
try:
    with manifest_transaction(root, timeout=0.1):
        comment = add_review_comment(
            root, stage_id="A11", cue_id="p1s01_c01_title", frame_id="hero",
            body="child process feedback", actor="user",
        )
    print(json.dumps({"status": "saved", "id": comment["id"]}))
except ValueError as error:
    print(json.dumps({"status": "blocked", "message": str(error)}))
"""
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_approved_version(directory)
            command = [sys.executable, "-B", "-c", child_code, str(root)]

            def run_child():
                completed = subprocess.run(
                    command,
                    cwd=Path(__file__).resolve().parents[1],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=True,
                )
                return json.loads(completed.stdout)

            with transactions.manifest_transaction(root):
                prior_inode = (root / "animation-manifest.json").stat().st_ino
                self.submit_comment(root, "parent process feedback")
                self.assertNotEqual((root / "animation-manifest.json").stat().st_ino, prior_inode)
                blocked = run_child()
                self.assertEqual(blocked["status"], "blocked")
                self.assertIn("busy", blocked["message"])
                self.assert_comment_preserved(root, "parent process feedback")

            saved = run_child()
            self.assertEqual(saved["status"], "saved")
            comments = load_manifest(root)["workflow"]["stageEvidence"]["A11"]["comments"]
            self.assertEqual([item["body"] for item in comments], ["parent process feedback", "child process feedback"])
            self.assertEqual(len({item["id"] for item in comments}), 2)

    def test_optimistic_preparation_allows_comments_but_rejects_stale_commit_and_result(self):
        for writes_manifest in (True, False):
            with self.subTest(writes_manifest=writes_manifest), tempfile.TemporaryDirectory() as directory:
                root = self.make_approved_version(directory)
                original_text = load_manifest(root)["cues"][0]["screenText"]
                arrived, release = threading.Event(), threading.Event()

                @transactions.optimistic_operation
                def long_preparation(version_root):
                    manifest = load_manifest(version_root)
                    arrived.set()
                    if not release.wait(5):
                        raise RuntimeError("optimistic preparation was never released")
                    if writes_manifest:
                        manifest["cues"][0]["screenText"] = ["obsolete preparation"]
                        save_manifest(version_root, manifest)
                    return "prepared against old revision"

                @transactions.optimistic_operation
                def fresh_preparation(version_root):
                    manifest = load_manifest(version_root)
                    manifest["cues"][0]["visualIntent"] += " fresh first write"
                    save_manifest(version_root, manifest)
                    manifest["cues"][0]["visualIntent"] += " fresh second write"
                    save_manifest(version_root, manifest)
                    return "freshly committed"

                with concurrent.futures.ThreadPoolExecutor(1) as pool:
                    preparation = pool.submit(long_preparation, root)
                    try:
                        self.assertTrue(arrived.wait(5))
                        self.submit_comment(root, "feedback while preparing")
                    finally:
                        release.set()
                    with self.assertRaisesRegex(ValueError, "stale"):
                        preparation.result(timeout=5)
                    self.assertEqual(pool.submit(fresh_preparation, root).result(timeout=5), "freshly committed")

                self.assert_comment_preserved(root, "feedback while preparing")
                self.assertEqual(load_manifest(root)["cues"][0]["screenText"], original_text)

    def test_transaction_releases_lock_after_body_stale_check_and_open_exceptions(self):
        for failure in ("body", "stale", "open"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = self.make_approved_version(directory)
                if failure == "body":
                    with self.assertRaisesRegex(RuntimeError, "controlled body failure"):
                        with transactions.manifest_transaction(root):
                            raise RuntimeError("controlled body failure")
                elif failure == "stale":
                    with self.assertRaisesRegex(ValueError, "stale"):
                        with transactions.manifest_transaction(root, expected_sha256="0" * 64):
                            self.fail("stale transaction must not enter its body")
                else:
                    with patch.object(transactions.os, "open", side_effect=OSError("controlled lock open failure")):
                        with self.assertRaisesRegex(OSError, "controlled lock open failure"):
                            with transactions.manifest_transaction(root):
                                self.fail("failed lock acquisition must not enter its body")

                with concurrent.futures.ThreadPoolExecutor(1) as pool:
                    pool.submit(self.submit_comment, root, "feedback after exception").result(timeout=5)
                self.assert_comment_preserved(root, "feedback after exception")

    def test_different_version_roots_do_not_share_a_mutation_lock(self):
        with tempfile.TemporaryDirectory() as first_directory, tempfile.TemporaryDirectory() as second_directory:
            first_root = self.make_approved_version(first_directory)
            second_root = self.make_approved_version(second_directory)
            first_bytes = (first_root / "animation-manifest.json").read_bytes()
            with transactions.manifest_transaction(first_root), concurrent.futures.ThreadPoolExecutor(1) as pool:
                pool.submit(self.submit_comment, second_root, "independent Vn feedback").result(timeout=1)
            self.assertEqual((first_root / "animation-manifest.json").read_bytes(), first_bytes)
            self.assert_comment_preserved(second_root, "independent Vn feedback")

    def test_review_snapshot_and_generated_projections_wait_for_exclusive_maintenance(self):
        from scripts.sync_storyboard import sync_storyboard
        from scripts.sync_delivery import sync_delivery
        from scripts.assemble_hyperframes import assemble_hyperframes

        for operation in (review_state, sync_storyboard, sync_delivery, assemble_hyperframes):
            with self.subTest(operation=operation.__name__), tempfile.TemporaryDirectory() as directory:
                root = self.make_approved_version(directory)
                attempted = threading.Event()

                def run():
                    attempted.set()
                    return operation(root)

                with concurrent.futures.ThreadPoolExecutor(1) as pool:
                    with transactions.manifest_transaction(root):
                        pending = pool.submit(run)
                        self.assertTrue(attempted.wait(5))
                        with self.assertRaises(concurrent.futures.TimeoutError):
                            pending.result(timeout=0.1)
                    self.assertIsInstance(pending.result(timeout=5), dict)

    def test_simultaneous_same_revision_comments_do_not_both_report_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_review_version(directory)
            sha = review_state(root)["manifestSha256"]
            arrived, release = threading.Event(), threading.Event()
            original_save = review.save_manifest
            first = True
            guard = threading.Lock()

            def controlled_save(*args, **kwargs):
                nonlocal first
                with guard:
                    pause = first
                    first = False
                if pause:
                    arrived.set()
                    if not release.wait(5):
                        raise RuntimeError("test writer was never released")
                return original_save(*args, **kwargs)

            def submit(text):
                try:
                    apply_review_action(root, "add-storyboard-comment", {"manifestSha256":sha, "cueId":"p1s01_c01_title", "frameId":"hero", "body":text})
                    return "saved"
                except ValueError as error:
                    return "conflict" if "stale" in str(error) else str(error)

            with patch.object(review, "save_manifest", side_effect=controlled_save), concurrent.futures.ThreadPoolExecutor(2) as pool:
                a = pool.submit(submit, "first")
                self.assertTrue(arrived.wait(5))
                b = pool.submit(submit, "second")
                try:
                    b.result(timeout=0.2)
                except concurrent.futures.TimeoutError:
                    pass
                finally:
                    release.set()
                outcomes = [a.result(timeout=5), b.result(timeout=5)]
            self.assertCountEqual(outcomes, ["saved", "conflict"])
            state = review_state(root)
            apply_review_action(root, "add-storyboard-comment", {"manifestSha256":state["manifestSha256"], "cueId":"p1s01_c01_title", "frameId":"hero", "body":"retry"})
            comments = json.loads((root / "animation-manifest.json").read_text())["workflow"]["stageEvidence"]["A11"]["comments"]
            self.assertEqual(len(comments), 2)
            self.assertEqual(len({c["id"] for c in comments}), 2)
