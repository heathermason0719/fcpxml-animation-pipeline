"""A published archive remains safely retryable when manifest publication fails."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.build_delivery_package import build_delivery_package
from scripts.workflow_review import record_fcp_acceptance
from scripts.workflow_status import resolve_stage_status
from tests import test_fcpxml_delivery_backend as backend_fixture
from tests.test_hyperframes_single_source import write_json


class ReworkArchiveRetryTests(unittest.TestCase):
    def closed(self, directory: str) -> Path:
        root, _, _ = backend_fixture.DeliveryPackageTests().make_package_version(directory)
        build_delivery_package(root)
        record_fcp_acceptance(root, actor="user")
        manifest_path = root / "animation-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["workflow"]["roundTripRequired"] = False
        write_json(manifest_path, manifest)
        self.assertIsNone(resolve_stage_status(root)["blockingStage"])
        return root

    def test_save_failure_after_archive_publication_reuses_exact_orphan(self) -> None:
        from scripts import rework_lifecycle as api
        with tempfile.TemporaryDirectory() as directory:
            root = self.closed(directory)
            before = (root / "animation-manifest.json").read_bytes()
            with patch.object(api, "save_manifest", side_effect=OSError("manifest disk full")):
                with self.assertRaisesRegex(OSError, "manifest disk full"):
                    api.begin_rework(root, {"p1s01_c01_title": ["motion"]}, "retry archive")
            archive = root / "rework/history/r0000"
            self.assertTrue(archive.is_dir())
            self.assertEqual((root / "animation-manifest.json").read_bytes(), before)
            result = api.begin_rework(root, {"p1s01_c01_title": ["motion"]}, "retry archive")
            self.assertEqual(result["archive"], "rework/history/r0000")
            self.assertEqual(api.verify_rework_history(root)["status"], "valid")

    def test_retry_rejects_nonmatching_orphan_without_overwrite(self) -> None:
        from scripts import rework_lifecycle as api
        with tempfile.TemporaryDirectory() as directory:
            root = self.closed(directory)
            before = (root / "animation-manifest.json").read_bytes()
            with patch.object(api, "save_manifest", side_effect=OSError("manifest disk full")):
                with self.assertRaisesRegex(OSError, "manifest disk full"):
                    api.begin_rework(root, {"p1s01_c01_title": ["motion"]}, "retry archive")
            archived_manifest = root / "rework/history/r0000/files/animation-manifest.json"
            archived_manifest.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "does not match current closed snapshot"):
                api.begin_rework(root, {"p1s01_c01_title": ["motion"]}, "retry archive")
            self.assertEqual((root / "animation-manifest.json").read_bytes(), before)
            self.assertEqual(archived_manifest.read_bytes(), b"tampered")


if __name__ == "__main__":
    unittest.main()
