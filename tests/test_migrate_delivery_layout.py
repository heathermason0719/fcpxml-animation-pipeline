from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.test_hyperframes_single_source import SingleSourceFixture, write_json

try:
    from scripts.migrate_delivery_layout import migrate_delivery_layout
except ModuleNotFoundError:
    migrate_delivery_layout = None


class DeliveryLayoutMigrationTests(SingleSourceFixture):
    def make_legacy_version(self, directory: str) -> Path:
        root = self.make_version(directory)
        composition = root / "compositions/cues/p1s01-c01-title.html"
        composition.write_text(
            composition.read_text(encoding="utf-8")
            .replace("#root{position:absolute;inset:0}", "#root{position:absolute;inset:0;width:854px;height:480px;overflow:hidden}")
            .replace('data-width="1920"', 'data-width="854"')
            .replace('data-height="1080"', 'data-height="480"'),
            encoding="utf-8",
        )
        manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
        manifest["cues"][0]["workflowState"] = "layout-approved"
        manifest["cues"][0]["renderAdapters"]["hyperframes"]["layoutLock"] = {
            "revision": 1,
            "algorithm": "sha256",
            "files": [],
            "aggregateSha256": "0" * 64,
            "approvedPoster": "approvals/a11/old.png",
            "approvedPosterSha256": "1" * 64,
        }
        manifest["reviews"]["a11"] = {"status": "approved", "approvedCueIds": ["p1s01_c01_title"]}
        write_json(root / "animation-manifest.json", manifest)
        return root

    def test_migration_wraps_legacy_layout_without_changing_motion_and_is_idempotent(self) -> None:
        self.assertIsNotNone(migrate_delivery_layout, "delivery layout migration is missing")
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_legacy_version(directory)
            motion = root / "compositions/motion/p1s01-c01-title.js"
            motion_before = motion.read_bytes()

            first = migrate_delivery_layout(root)
            second = migrate_delivery_layout(root)

            canonical = (root / "compositions/cues/p1s01-c01-title.html").read_text(encoding="utf-8")
            self.assertEqual(first["status"], "migrated")
            self.assertEqual(first["migratedCueIds"], ["p1s01_c01_title"])
            self.assertEqual(second["status"], "unchanged")
            self.assertIn('data-width="1920" data-height="1080"', canonical)
            self.assertIn('data-afterforge-legacy-stage="854x480"', canonical)
            self.assertIn("scale(2.248243559719, 2.25)", canonical)
            self.assertIn('<div data-role="title">标题</div>', canonical)
            self.assertEqual(motion.read_bytes(), motion_before)
            manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
            cue = manifest["cues"][0]
            self.assertEqual(manifest["reviews"]["a11"]["status"], "pending-migration-equivalence")
            self.assertNotIn("approvedCueIds", manifest["reviews"]["a11"])
            self.assertEqual(cue["workflowState"], "layout-built")
            adapter = cue["renderAdapters"]["hyperframes"]
            self.assertIsNone(adapter["layoutLock"])
            self.assertEqual(adapter["layoutRevision"], 1)

    def test_incompatible_dimensions_block_without_modifying_project(self) -> None:
        self.assertIsNotNone(migrate_delivery_layout, "delivery layout migration is missing")
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_legacy_version(directory)
            composition = root / "compositions/cues/p1s01-c01-title.html"
            composition.write_text(
                composition.read_text(encoding="utf-8")
                .replace('data-width="854"', 'data-width="1280"'),
                encoding="utf-8",
            )
            composition_before = composition.read_bytes()
            manifest_before = (root / "animation-manifest.json").read_bytes()

            with self.assertRaisesRegex(ValueError, "neither preview nor delivery"):
                migrate_delivery_layout(root)

            self.assertEqual(composition.read_bytes(), composition_before)
            self.assertEqual((root / "animation-manifest.json").read_bytes(), manifest_before)


if __name__ == "__main__":
    unittest.main()
