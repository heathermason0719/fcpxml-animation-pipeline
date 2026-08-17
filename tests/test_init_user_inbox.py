from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.init_user_inbox import ensure_user_inbox


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI = REPO_ROOT / "scripts" / "init_user_inbox.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class UserInboxTests(unittest.TestCase):
    def test_creates_empty_user_inbox_without_touching_afterforge_or_project_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            afterforge = project_root / "AfterForge"
            afterforge.mkdir()
            skill_file = afterforge / "existing-output.json"
            skill_file.write_text('{"keep": true}', encoding="utf-8")
            project_file = project_root / "rough-cut.fcpxml"
            project_file.write_text("<fcpxml/>", encoding="utf-8")
            before = {
                "skill": digest(skill_file),
                "project": digest(project_file),
            }

            result = ensure_user_inbox(project_root)

            inbox = project_root / "user-inbox"
            self.assertEqual(result["status"], "created")
            self.assertTrue(result["created"])
            self.assertEqual(result["skill_id"], "fcpxml-animation-pipeline")
            self.assertEqual(result["directory_name"], "user-inbox")
            self.assertEqual(result["access_mode"], "skill-read-only")
            self.assertEqual(result["path"], str(inbox.resolve()))
            self.assertTrue(inbox.is_dir())
            self.assertEqual(list(inbox.iterdir()), [])
            self.assertEqual(digest(skill_file), before["skill"])
            self.assertEqual(digest(project_file), before["project"])

    def test_existing_user_versions_and_materials_are_not_changed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            version = project_root / "user-inbox" / "2026-08-17_V1"
            version.mkdir(parents=True)
            materials = {
                "fcpxml": version / "rough-cut.fcpxml",
                "video": version / "rough_proxy.mov",
                "srt": version / "narration.srt",
                "notes": version / "notes.txt",
            }
            for name, path in materials.items():
                path.write_bytes(f"unchanged-{name}".encode())
            before = {name: digest(path) for name, path in materials.items()}
            before_names = sorted(path.name for path in version.iterdir())

            result = ensure_user_inbox(project_root)

            self.assertEqual(result["status"], "existing")
            self.assertFalse(result["created"])
            self.assertEqual(
                {name: digest(path) for name, path in materials.items()},
                before,
            )
            self.assertEqual(sorted(path.name for path in version.iterdir()), before_names)

    def test_does_not_create_or_increment_version_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)

            ensure_user_inbox(project_root)

            self.assertEqual(list((project_root / "user-inbox").iterdir()), [])

    def test_same_named_file_blocks_without_overwriting_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            collision = project_root / "user-inbox"
            collision.write_text("user content", encoding="utf-8")
            before = digest(collision)

            result = ensure_user_inbox(project_root)

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["error"]["code"], "user_inbox_path_not_directory")
            self.assertFalse(result["created"])
            self.assertEqual(digest(collision), before)


class UserInboxCliTests(unittest.TestCase):
    def test_cli_emits_json_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = subprocess.run(
                [sys.executable, str(CLI), directory],
                check=False,
                capture_output=True,
                text=True,
            )
            second = subprocess.run(
                [sys.executable, str(CLI), directory],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(json.loads(first.stdout)["status"], "created")
            self.assertEqual(json.loads(second.stdout)["status"], "existing")


if __name__ == "__main__":
    unittest.main()
