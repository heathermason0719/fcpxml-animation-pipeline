from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tests.test_hyperframes_single_source import SingleSourceFixture, write_json

from scripts.layout_lock import freeze_layout
from scripts.sync_storyboard import sync_storyboard
from scripts.workflow_review import approve_storyboard


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class HyperFramesRuntimeMigrationTests(SingleSourceFixture):
    def make_approved_version(self, directory: str) -> Path:
        root = self.make_version(directory)
        sync_storyboard(root)
        poster = root / "approved.png"
        poster.write_bytes(b"approved under 0.8.26")
        freeze_layout(root, "p1s01_c01_title", poster)
        manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
        manifest["workflow"] = {
            "stageContractVersion": "1.0.0",
            "stageEvidence": {},
        }
        write_json(root / "animation-manifest.json", manifest)
        approve_storyboard(root, actor="user")
        return root

    @staticmethod
    def passing_checker(_root: Path, _version: str) -> list[dict[str, str]]:
        return [
            {
                "name": "hyperframes-check",
                "result": "passed",
                "command": "npm run check",
            }
        ]

    def test_explicit_version_change_records_checks_and_invalidates_review_evidence(self) -> None:
        from scripts.hyperframes_runtime import read_runtime_pin
        from scripts.migrate_hyperframes_runtime import migrate_hyperframes_runtime
        from scripts.workflow_status import resolve_stage_status

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_approved_version(directory)

            result = migrate_hyperframes_runtime(
                root,
                "0.8.27",
                compatibility_checker=self.passing_checker,
                recorded_at="2026-09-03T02:00:00Z",
            )

            self.assertEqual(result["status"], "migrated")
            self.assertEqual(read_runtime_pin(root), "0.8.27")
            meta = json.loads((root / "meta.json").read_text(encoding="utf-8"))
            event = meta["toolchain"]["hyperframes"]["migrations"][-1]
            self.assertEqual(event["eventType"], "runtime-upgrade")
            self.assertEqual((event["fromVersion"], event["toVersion"]), ("0.8.26", "0.8.27"))
            self.assertEqual(
                [(item["name"], item["result"]) for item in event["compatibilityChecks"]],
                [
                    ("package-script-pin-consistency", "passed"),
                    ("hyperframes-check", "passed"),
                    ("afterforge-adapter-validation", "passed"),
                ],
            )
            self.assertEqual(event["reviewEvidence"]["preserved"], [])
            self.assertEqual(event["reviewEvidence"]["rebound"], [])
            self.assertEqual(
                [item["stageId"] for item in event["reviewEvidence"]["invalidated"]],
                ["A11"],
            )
            manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["workflow"]["stageEvidence"]["A11"]["status"], "invalidated")
            self.assertEqual(resolve_stage_status(root)["blockingStage"], "A11")

    def test_failed_compatibility_check_restores_package_meta_and_manifest(self) -> None:
        from scripts.migrate_hyperframes_runtime import migrate_hyperframes_runtime

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_approved_version(directory)
            watched = [root / "package.json", root / "meta.json", root / "animation-manifest.json"]
            before = {path.name: path.read_bytes() for path in watched}

            def failing_checker(_root: Path, _version: str) -> list[dict[str, str]]:
                raise ValueError("HyperFrames check failed")

            with self.assertRaisesRegex(ValueError, "HyperFrames check failed"):
                migrate_hyperframes_runtime(
                    root,
                    "0.8.27",
                    compatibility_checker=failing_checker,
                    recorded_at="2026-09-03T02:00:00Z",
                )

            self.assertEqual({path.name: path.read_bytes() for path in watched}, before)

    def test_reconciliation_rebinds_proven_current_a11_without_invalidating_it(self) -> None:
        from scripts.migrate_hyperframes_runtime import migrate_hyperframes_runtime
        from scripts.workflow_status import resolve_stage_status

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_approved_version(directory)
            meta = json.loads((root / "meta.json").read_text(encoding="utf-8"))
            meta.pop("toolchain")
            meta["hyperframesVersion"] = "0.8.16"
            write_json(root / "meta.json", meta)
            manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
            cue = manifest["cues"][0]
            cue["renderAdapters"]["hyperframes"]["layoutLock"].pop("runtimeVersion")
            manifest["workflow"]["stageEvidence"]["A11"]["cueApprovals"][cue["id"]].pop("runtimeVersion")
            write_json(root / "animation-manifest.json", manifest)
            package_before = file_hash(root / "package.json")

            result = migrate_hyperframes_runtime(
                root,
                "0.8.26",
                rebind_current_a11=True,
                compatibility_checker=self.passing_checker,
                recorded_at="2026-09-03T02:00:00Z",
            )

            self.assertEqual(result["status"], "reconciled")
            self.assertEqual(file_hash(root / "package.json"), package_before)
            meta = json.loads((root / "meta.json").read_text(encoding="utf-8"))
            self.assertNotIn("hyperframesVersion", meta)
            self.assertEqual(meta["toolchain"]["hyperframes"]["createdWithVersion"], "0.8.16")
            event = meta["toolchain"]["hyperframes"]["migrations"][-1]
            self.assertEqual(event["eventType"], "reconciliation")
            self.assertEqual(event["reviewEvidence"]["invalidated"], [])
            self.assertEqual(
                [item["stageId"] for item in event["reviewEvidence"]["rebound"]],
                ["A11"],
            )
            manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
            lock = manifest["cues"][0]["renderAdapters"]["hyperframes"]["layoutLock"]
            approval = manifest["workflow"]["stageEvidence"]["A11"]["cueApprovals"]["p1s01_c01_title"]
            self.assertEqual(lock["runtimeVersion"], "0.8.26")
            self.assertEqual(approval["runtimeVersion"], "0.8.26")
            self.assertEqual(resolve_stage_status(root)["blockingStage"], "A12")

    def test_repeating_completed_reconciliation_is_byte_idempotent(self) -> None:
        from scripts.migrate_hyperframes_runtime import migrate_hyperframes_runtime

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_approved_version(directory)
            meta = json.loads((root / "meta.json").read_text(encoding="utf-8"))
            meta.pop("toolchain")
            meta["hyperframesVersion"] = "0.8.16"
            write_json(root / "meta.json", meta)
            manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
            cue = manifest["cues"][0]
            cue["renderAdapters"]["hyperframes"]["layoutLock"].pop("runtimeVersion")
            manifest["workflow"]["stageEvidence"]["A11"]["cueApprovals"][cue["id"]].pop(
                "runtimeVersion"
            )
            write_json(root / "animation-manifest.json", manifest)

            migrate_hyperframes_runtime(
                root,
                "0.8.26",
                rebind_current_a11=True,
                compatibility_checker=self.passing_checker,
                recorded_at="2026-09-03T02:00:00Z",
            )
            watched = [root / "package.json", root / "meta.json", root / "animation-manifest.json"]
            before = {path.name: path.read_bytes() for path in watched}

            result = migrate_hyperframes_runtime(
                root,
                "0.8.26",
                rebind_current_a11=True,
                compatibility_checker=self.passing_checker,
                recorded_at="2026-09-03T03:00:00Z",
            )

            self.assertEqual(result["status"], "already-current")
            self.assertEqual({path.name: path.read_bytes() for path in watched}, before)


if __name__ == "__main__":
    unittest.main()
