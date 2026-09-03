from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.layout_lock import freeze_layout
from scripts.sync_storyboard import sync_storyboard
from tests.test_hyperframes_single_source import SingleSourceFixture, write_json


class WorkflowStageMigrationTests(SingleSourceFixture):
    def make_legacy_version(self, directory: str) -> Path:
        root = self.make_version(directory)
        sync_storyboard(root)
        poster = root / "approved.png"
        poster.write_bytes(b"legacy approved poster")
        freeze_layout(root, "p1s01_c01_title", poster)
        preview = root / "previews/legacy-demo.mp4"
        preview.parent.mkdir(parents=True, exist_ok=True)
        preview.write_bytes(b"legacy demo")
        manifest_path = root / "animation-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.pop("workflow", None)
        manifest["reviews"] = {
            "a11": {"status": "approved", "approvedCueIds": ["p1s01_c01_title"]},
            "a12": {
                "status": "pending-user-review",
                "preview": "previews/legacy-demo.mp4",
                "sha256": hashlib.sha256(preview.read_bytes()).hexdigest(),
                "width": 854,
                "height": 480,
            },
        }
        write_json(manifest_path, manifest)
        return root

    def test_preserves_legacy_reviews_but_requires_new_a11_user_approval(self) -> None:
        try:
            from scripts.migrate_workflow_stage_contract import migrate_workflow_stage_contract
        except ModuleNotFoundError:
            self.fail("workflow stage contract migration is not implemented")
        from scripts.workflow_status import resolve_stage_status
        from scripts.workflow_inputs import input_fingerprint

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_legacy_version(directory)
            before = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))

            result = migrate_workflow_stage_contract(root)

            manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["reviews"], before["reviews"])
            self.assertEqual(manifest["workflow"]["stageContractVersion"], "1.0.0")
            self.assertEqual(manifest["workflow"]["migration"]["source"], "legacy-unversioned")
            self.assertNotIn("A11", manifest["workflow"]["stageEvidence"])
            self.assertEqual(manifest["workflow"]["stageEvidence"]["A12"]["status"], "ready")
            migrated_demo = manifest["workflow"]["stageEvidence"]["A12"]
            self.assertEqual(migrated_demo.get("inputFingerprintVersion"), 1)
            self.assertEqual(migrated_demo["inputFingerprint"], input_fingerprint(root, manifest, version=1))
            self.assertNotEqual(migrated_demo["inputFingerprint"], input_fingerprint(root, manifest, version=2))
            self.assertEqual(resolve_stage_status(root)["blockingStage"], "A11")
            self.assertEqual(result["preservedLegacyReviewStages"], ["a11", "a12"])

            from scripts.workflow_review import approve_storyboard

            approve_storyboard(root, actor="user")
            status = resolve_stage_status(root)
            self.assertEqual(status["blockingStage"], "A12")
            self.assertEqual(status["nextEligibleStage"], "A12")
            self.assertEqual(status["evidence"]["A12"], "compatible-historical")

    def test_migration_is_byte_idempotent(self) -> None:
        from scripts.migrate_workflow_stage_contract import migrate_workflow_stage_contract

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_legacy_version(directory)
            migrate_workflow_stage_contract(root)
            first = (root / "animation-manifest.json").read_bytes()

            result = migrate_workflow_stage_contract(root)

            self.assertEqual((root / "animation-manifest.json").read_bytes(), first)
            self.assertEqual(result["status"], "already-current")


if __name__ == "__main__":
    unittest.main()
