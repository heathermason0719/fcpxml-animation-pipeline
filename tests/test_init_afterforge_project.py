from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from scripts.init_afterforge_project import initialize_afterforge_project
except ModuleNotFoundError:
    initialize_afterforge_project = None


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI = REPO_ROOT / "scripts" / "init_afterforge_project.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def initialize(project_root: Path, display_name: str = "AfterForge") -> dict:
    if initialize_afterforge_project is None:
        raise AssertionError("init_afterforge_project implementation is missing")
    return initialize_afterforge_project(project_root, display_name)


class AfterForgeProjectInitTests(unittest.TestCase):
    def test_creates_only_project_agent_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            afterforge = project_root / "AfterForge"
            afterforge.mkdir()
            user_inbox = project_root / "user-inbox"
            user_inbox.mkdir()
            source = user_inbox / "rough-cut.fcpxml"
            source.write_text("<fcpxml/>", encoding="utf-8")
            before = digest(source)

            result = initialize(project_root)

            self.assertEqual(result["status"], "created")
            self.assertEqual(result["created"], ["AGENTS.md", "CLAUDE.md"])
            self.assertEqual(result["preserved"], [])
            self.assertTrue((afterforge / "AGENTS.md").is_file())
            self.assertTrue((afterforge / "CLAUDE.md").is_file())
            self.assertFalse((afterforge / "frame.md").exists())
            self.assertEqual(
                sorted(path.name for path in afterforge.iterdir()),
                ["AGENTS.md", "CLAUDE.md"],
            )
            self.assertEqual(digest(source), before)

    def test_repeated_init_preserves_files_byte_for_byte(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            afterforge = project_root / "AfterForge"
            afterforge.mkdir()
            first = initialize(project_root)
            self.assertEqual(first["status"], "created")
            before = {
                name: digest(afterforge / name) for name in ("AGENTS.md", "CLAUDE.md")
            }

            second = initialize(project_root)

            self.assertEqual(second["status"], "existing")
            self.assertEqual(second["created"], [])
            self.assertEqual(second["preserved"], ["AGENTS.md", "CLAUDE.md"])
            self.assertEqual(
                {name: digest(afterforge / name) for name in before},
                before,
            )

    def test_missing_sibling_is_created_without_updating_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            afterforge = project_root / "AfterForge"
            afterforge.mkdir()
            agents = afterforge / "AGENTS.md"
            agents.write_text("user-maintained project rules\n", encoding="utf-8")
            before = digest(agents)

            result = initialize(project_root)

            self.assertEqual(result["status"], "created")
            self.assertEqual(result["created"], ["CLAUDE.md"])
            self.assertEqual(result["preserved"], ["AGENTS.md"])
            self.assertEqual(digest(agents), before)

    def test_invalid_asset_blocks_before_creating_sibling(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            afterforge = project_root / "AfterForge"
            afterforge.mkdir()
            (afterforge / "CLAUDE.md").mkdir()

            result = initialize(project_root)

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["error"]["code"], "project_asset_not_file")
            self.assertFalse((afterforge / "AGENTS.md").exists())

    def test_display_name_cannot_escape_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)

            result = initialize(project_root, "../outside")

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["error"]["code"], "invalid_display_name")
            self.assertFalse((project_root.parent / "outside" / "AGENTS.md").exists())


class AfterForgeProjectInitCliTests(unittest.TestCase):
    def test_cli_is_idempotent_and_emits_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            (project_root / "AfterForge").mkdir()

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
