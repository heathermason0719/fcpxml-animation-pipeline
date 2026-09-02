from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

try:
    from scripts.scaffold_hyperframes import scaffold_hyperframes_version
except ModuleNotFoundError:
    scaffold_hyperframes_version = None


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scaffold(project_root: Path, version: str = "2026-08-26_V1") -> dict:
    if scaffold_hyperframes_version is None:
        raise AssertionError("scaffold_hyperframes implementation is missing")
    return scaffold_hyperframes_version(
        project_root,
        version,
        "0.8.14",
        compatibility_checker=lambda _root, _version: None,
    )


class HyperFramesScaffoldTests(unittest.TestCase):
    def make_project(self, directory: str) -> tuple[Path, Path]:
        project_root = Path(directory)
        afterforge = project_root / "AfterForge"
        afterforge.mkdir()
        (afterforge / "AGENTS.md").write_text("project agents\n", encoding="utf-8")
        (afterforge / "CLAUDE.md").write_text("project claude\n", encoding="utf-8")
        (afterforge / "frame.md").write_text("---\ncolors: {}\n---\n", encoding="utf-8")
        fonts = afterforge / "assets" / "fonts" / "family"
        fonts.mkdir(parents=True)
        (fonts / "font.woff2").write_bytes(b"font snapshot")
        return project_root, afterforge

    def test_creates_isolated_version_with_frame_and_font_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root, afterforge = self.make_project(directory)
            protected = {
                name: digest(afterforge / name)
                for name in ("AGENTS.md", "CLAUDE.md", "frame.md")
            }

            result = scaffold(project_root)

            target = afterforge / "2026-08-26_V1"
            self.assertEqual(result["status"], "created")
            self.assertEqual(Path(result["path"]), target.resolve())
            self.assertEqual(
                sorted(path.name for path in target.iterdir()),
                [
                    "approvals",
                    "assets",
                    "compositions",
                    "frame.md",
                    "hyperframes.json",
                    "index.html",
                    "meta.json",
                    "package.json",
                ],
            )
            self.assertEqual(
                sorted(path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_dir()),
                [
                    "approvals",
                    "approvals/a11",
                    "assets",
                    "assets/fonts",
                    "assets/fonts/family",
                    "assets/media",
                    "assets/stills",
                    "assets/styles",
                    "assets/vendor",
                    "compositions",
                    "compositions/cues",
                    "compositions/motion",
                    "compositions/review",
                ],
            )
            self.assertEqual((target / "frame.md").read_bytes(), (afterforge / "frame.md").read_bytes())
            self.assertEqual(
                (target / "assets" / "fonts" / "family" / "font.woff2").read_bytes(),
                b"font snapshot",
            )
            self.assertFalse((target / "AGENTS.md").exists())
            self.assertFalse((target / "CLAUDE.md").exists())
            self.assertEqual(
                {name: digest(afterforge / name) for name in protected},
                protected,
            )
            meta = json.loads((target / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["version"], "2026-08-26_V1")
            self.assertNotIn("hyperframesVersion", meta)
            self.assertEqual(
                meta["toolchain"]["hyperframes"],
                {"createdWithVersion": "0.8.14", "migrations": []},
            )
            self.assertEqual(meta["visualSpec"]["canonical"], "../frame.md")
            self.assertEqual(meta["visualSpec"]["snapshot"], "frame.md")
            self.assertEqual(meta["visualSpec"]["snapshotSha256"], digest(target / "frame.md"))
            package = json.loads((target / "package.json").read_text(encoding="utf-8"))
            self.assertEqual(
                package["scripts"]["check"],
                "npm exec --yes --package=hyperframes@0.8.14 -- hyperframes check",
            )

    def test_default_creation_resolves_once_and_checks_staging_before_publish(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root, afterforge = self.make_project(directory)
            resolver_calls: list[str | None] = []
            checked: list[tuple[Path, str]] = []

            def resolve(value: str | None) -> str:
                resolver_calls.append(value)
                return "0.8.26"

            def check(root: Path, version: str) -> None:
                from scripts.hyperframes_runtime import read_runtime_pin

                self.assertNotEqual(root, afterforge / "2026-08-26_V1")
                self.assertEqual(read_runtime_pin(root), "0.8.26")
                checked.append((root, version))

            result = scaffold_hyperframes_version(
                project_root,
                "2026-08-26_V1",
                version_resolver=resolve,
                compatibility_checker=check,
            )

            target = afterforge / "2026-08-26_V1"
            self.assertEqual(result["status"], "created")
            self.assertEqual(resolver_calls, [None])
            self.assertEqual(len(checked), 1)
            self.assertEqual(checked[0][1], "0.8.26")
            package = json.loads((target / "package.json").read_text(encoding="utf-8"))
            meta = json.loads((target / "meta.json").read_text(encoding="utf-8"))
            self.assertIn("hyperframes@0.8.26", package["scripts"]["render"])
            self.assertEqual(meta["toolchain"]["hyperframes"]["createdWithVersion"], "0.8.26")

    def test_compatibility_failure_leaves_no_target_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root, afterforge = self.make_project(directory)

            def fail_check(_root: Path, _version: str) -> None:
                raise ValueError("compatibility check failed")

            result = scaffold_hyperframes_version(
                project_root,
                "2026-08-26_V1",
                "0.8.26",
                compatibility_checker=fail_check,
            )

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["error"]["code"], "version_create_failed")
            self.assertFalse((afterforge / "2026-08-26_V1").exists())
            self.assertEqual(
                [path.name for path in afterforge.iterdir() if path.name.startswith(".scaffold-")],
                [],
            )

    def test_existing_version_blocks_without_modification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root, afterforge = self.make_project(directory)
            target = afterforge / "2026-08-26_V1"
            target.mkdir()
            sentinel = target / "keep.txt"
            sentinel.write_text("keep\n", encoding="utf-8")

            result = scaffold(project_root)

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["error"]["code"], "version_exists")
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep\n")

    def test_lowercase_version_is_created_and_preserved_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root, afterforge = self.make_project(directory)

            result = scaffold(project_root, "2026-08-26_v1")

            target = afterforge / "2026-08-26_v1"
            self.assertEqual(result["status"], "created")
            self.assertEqual(result["version"], "2026-08-26_v1")
            self.assertEqual(Path(result["path"]), target.resolve())
            meta = json.loads((target / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["version"], "2026-08-26_v1")
            self.assertEqual(meta["name"], f"{project_root.name}-2026-08-26_v1")

    def test_case_only_version_collision_blocks_without_modification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root, afterforge = self.make_project(directory)
            existing = afterforge / "2026-08-26_V1"
            existing.mkdir()
            sentinel = existing / "keep.txt"
            sentinel.write_text("keep\n", encoding="utf-8")

            result = scaffold(project_root, "2026-08-26_v1")

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["error"]["code"], "version_case_collision")
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep\n")
            self.assertEqual(
                [path.name for path in afterforge.iterdir() if path.name.casefold() == "2026-08-26_v1"],
                ["2026-08-26_V1"],
            )

    def test_missing_canonical_frame_blocks_before_creating_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root, afterforge = self.make_project(directory)
            (afterforge / "frame.md").unlink()

            result = scaffold(project_root)

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["error"]["code"], "canonical_frame_missing")
            self.assertFalse((afterforge / "2026-08-26_V1").exists())

    def test_version_name_cannot_escape_afterforge(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root, afterforge = self.make_project(directory)

            result = scaffold(project_root, "../outside")

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["error"]["code"], "invalid_version_name")
            self.assertFalse((afterforge.parent / "outside").exists())


if __name__ == "__main__":
    unittest.main()
