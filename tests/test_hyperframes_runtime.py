from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


def write_package(root: Path, versions: dict[str, str]) -> None:
    scripts = {
        name: f"npm exec --yes --package=hyperframes@{version} -- hyperframes {name}"
        for name, version in versions.items()
    }
    (root / "package.json").write_text(
        json.dumps({"private": True, "scripts": scripts}, indent=2) + "\n",
        encoding="utf-8",
    )


class HyperFramesRuntimePinTests(unittest.TestCase):
    def test_reads_one_exact_pin_from_every_managed_script(self) -> None:
        from scripts.hyperframes_runtime import read_runtime_pin

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_package(
                root,
                {"dev": "0.8.26", "check": "0.8.26", "render": "0.8.26", "publish": "0.8.26"},
            )

            self.assertEqual(read_runtime_pin(root), "0.8.26")

    def test_rejects_mixed_or_floating_runtime_pins(self) -> None:
        from scripts.hyperframes_runtime import read_runtime_pin

        cases = [
            {"dev": "0.8.25", "check": "0.8.26", "render": "0.8.26", "publish": "0.8.26"},
            {"dev": "latest", "check": "latest", "render": "latest", "publish": "latest"},
            {"dev": "^0.8.26", "check": "^0.8.26", "render": "^0.8.26", "publish": "^0.8.26"},
        ]
        for versions in cases:
            with self.subTest(versions=versions), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                write_package(root, versions)

                with self.assertRaisesRegex(ValueError, "exact|same"):
                    read_runtime_pin(root)


class HyperFramesCreationVersionTests(unittest.TestCase):
    def test_explicit_exact_version_does_not_query_npm(self) -> None:
        from scripts.hyperframes_runtime import resolve_creation_version

        def unexpected_runner(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("npm must not be queried for an explicit version")

        self.assertEqual(resolve_creation_version("0.8.26", runner=unexpected_runner), "0.8.26")

    def test_default_resolution_queries_npm_once_and_returns_exact_version(self) -> None:
        from scripts.hyperframes_runtime import resolve_creation_version

        calls: list[list[str]] = []
        cache_paths: list[Path] = []

        def fake_runner(command, **kwargs):  # type: ignore[no-untyped-def]
            calls.append(command)
            cache = Path(kwargs["env"]["NPM_CONFIG_CACHE"])
            self.assertTrue(cache.is_dir())
            self.assertNotEqual(cache, Path(os.environ.get("NPM_CONFIG_CACHE", "")))
            cache_paths.append(cache)
            return subprocess.CompletedProcess(command, 0, stdout='"0.8.26"\n', stderr="")

        self.assertEqual(resolve_creation_version(None, runner=fake_runner), "0.8.26")
        self.assertEqual(calls, [["npm", "view", "hyperframes", "version", "--json"]])
        self.assertEqual(len(cache_paths), 1)
        self.assertFalse(cache_paths[0].exists())

    def test_resolution_rejects_non_exact_registry_result(self) -> None:
        from scripts.hyperframes_runtime import resolve_creation_version

        def fake_runner(command, **kwargs):  # type: ignore[no-untyped-def]
            return subprocess.CompletedProcess(command, 0, stdout='"latest"\n', stderr="")

        with self.assertRaisesRegex(ValueError, "exact semantic version"):
            resolve_creation_version(None, runner=fake_runner)


if __name__ == "__main__":
    unittest.main()
