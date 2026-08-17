from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.init_user_workspace import ensure_user_workspace


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI = REPO_ROOT / "scripts" / "init_user_workspace.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class UserWorkspaceTests(unittest.TestCase):
    def test_creates_afterforge_without_touching_existing_project_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            existing = project_root / "existing-project-file.txt"
            existing.write_text("keep me", encoding="utf-8")
            before = digest(existing)

            result = ensure_user_workspace(project_root)

            target = project_root / "AfterForge"
            self.assertEqual(result["status"], "created")
            self.assertTrue(result["created"])
            self.assertEqual(result["skill_id"], "fcpxml-animation-pipeline")
            self.assertEqual(result["display_name"], "AfterForge")
            self.assertEqual(result["path"], str(target.resolve()))
            self.assertTrue(target.is_dir())
            self.assertEqual(list(target.iterdir()), [])
            self.assertEqual(digest(existing), before)

    def test_existing_directory_is_reused_without_changing_its_contents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            target = project_root / "AfterForge"
            target.mkdir()
            sentinel = target / "user-content.txt"
            sentinel.write_text("do not alter", encoding="utf-8")
            before = digest(sentinel)

            result = ensure_user_workspace(project_root)

            self.assertEqual(result["status"], "existing")
            self.assertFalse(result["created"])
            self.assertEqual(digest(sentinel), before)
            self.assertEqual([item.name for item in target.iterdir()], ["user-content.txt"])

    def test_same_named_file_blocks_without_overwriting_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            collision = project_root / "AfterForge"
            collision.write_text("not a directory", encoding="utf-8")
            before = digest(collision)

            result = ensure_user_workspace(project_root)

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["error"]["code"], "workspace_path_not_directory")
            self.assertFalse(result["created"])
            self.assertEqual(digest(collision), before)

    def test_display_name_is_replaceable_without_changing_internal_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)

            result = ensure_user_workspace(project_root, display_name="StudioGate")

            self.assertEqual(result["display_name"], "StudioGate")
            self.assertEqual(result["skill_id"], "fcpxml-animation-pipeline")
            self.assertTrue((project_root / "StudioGate").is_dir())
            self.assertFalse((project_root / "AfterForge").exists())


class UserWorkspaceCliTests(unittest.TestCase):
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
