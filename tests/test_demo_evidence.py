from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from scripts.layout_lock import freeze_layout
from scripts.render_demo import build_demo_command, render_demo
from scripts.sync_storyboard import sync_storyboard
from scripts.workflow_review import approve_storyboard, register_demo
from tests.test_hyperframes_single_source import SingleSourceFixture, write_json
from tests.demo_fixture import write_simulated_demo_evidence


class DemoEvidenceTests(SingleSourceFixture):
    def make_approved_version(self, directory: str) -> Path:
        root = self.make_version(directory)
        sync_storyboard(root)
        poster = root / "approved.png"
        poster.write_bytes(b"approved")
        freeze_layout(root, "p1s01_c01_title", poster)
        manifest_path = root / "animation-manifest.json"
        import json
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["workflow"] = {"stageContractVersion": "1.0.0", "stageEvidence": {}}
        write_json(manifest_path, manifest)
        approve_storyboard(root, actor="user")
        return root

    def test_register_rejects_plain_preview_without_producer_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_approved_version(directory)
            preview = root / "previews/demo.mp4"
            preview.parent.mkdir()
            preview.write_bytes(b"old demo")
            with self.assertRaisesRegex(ValueError, "generation evidence"):
                register_demo(root, "previews/demo.mp4")

    def test_producer_and_registration_require_current_a11(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_approved_version(directory)
            manifest_path = root / "animation-manifest.json"
            import json
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["workflow"]["stageEvidence"]["A11"]["status"] = "pending"
            write_json(manifest_path, manifest)
            preview = root / "previews/demo.mp4"
            preview.parent.mkdir()
            preview.write_bytes(b"demo")
            with self.assertRaisesRegex(ValueError, "current A11"):
                write_simulated_demo_evidence(root, "previews/demo.mp4")
            self.assertFalse((root / "previews/demo.mp4.evidence.json").exists())

        with tempfile.TemporaryDirectory() as directory:
            root = self.make_approved_version(directory)
            preview = root / "previews/demo.mp4"
            preview.parent.mkdir()
            preview.write_bytes(b"demo")
            write_simulated_demo_evidence(root, "previews/demo.mp4")
            manifest_path = root / "animation-manifest.json"
            import json
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["workflow"]["stageEvidence"]["A11"]["status"] = "pending"
            write_json(manifest_path, manifest)
            before = manifest_path.read_bytes()
            with self.assertRaisesRegex(ValueError, "current A11"):
                register_demo(root, "previews/demo.mp4")
            self.assertEqual(manifest_path.read_bytes(), before)

    def test_motion_change_cannot_rebind_old_demo(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_approved_version(directory)
            preview = root / "previews/demo.mp4"
            preview.parent.mkdir()
            preview.write_bytes(b"old demo")
            write_simulated_demo_evidence(root, "previews/demo.mp4")
            motion = root / "compositions/motion/p1s01-c01-title.js"
            motion.write_text(motion.read_text(encoding="utf-8") + "\n// changed\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match current execution inputs"):
                register_demo(root, "previews/demo.mp4")

    def test_render_is_full_preview_and_writes_matching_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_approved_version(directory)
            commands: list[list[str]] = []

            def runner(command, **kwargs):
                commands.append(command)
                output = Path(command[command.index("--output") + 1])
                output.write_bytes(b"mp4")

            result = render_demo(
                root,
                runner=runner,
                prober=lambda _: {"width": 854, "height": 480, "r_frame_rate": "24/1", "duration": "10"},
            )
            self.assertEqual(result["status"], "rendered")
            self.assertIn("--format", commands[0])
            self.assertIn("mp4", commands[0])
            self.assertIn("--composition", commands[0])
            self.assertIn("index.html", commands[0])
            self.assertNotIn("--width", commands[0])
            self.assertNotIn("--height", commands[0])
            self.assertTrue((root / result["preview"]).is_file())
            self.assertTrue((root / result["generationEvidence"]).is_file())
            registered = register_demo(root, result["preview"])
            self.assertEqual(registered["sha256"], result["sha256"])
            self.assertEqual(len(registered["generationEvidenceSha256"]), 64)

    def test_render_rejects_input_drift_before_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_approved_version(directory)

            def runner(command, **kwargs):
                output = Path(command[command.index("--output") + 1])
                output.write_bytes(b"mp4")
                motion = root / "compositions/motion/p1s01-c01-title.js"
                motion.write_text(motion.read_text(encoding="utf-8") + "\n// drift\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "inputs changed during rendering"):
                render_demo(
                    root,
                    runner=runner,
                    prober=lambda _: {"width": 854, "height": 480, "r_frame_rate": "24/1", "duration": "10"},
                )
            self.assertFalse(list((root / "previews").glob("*.mp4")) if (root / "previews").exists() else [])

    def test_demo_command_uses_index_html_and_exact_fps(self) -> None:
        command = build_demo_command(Path("/tmp/version"), Path("/tmp/demo.mp4"), fps=__import__("fractions").Fraction(24000, 1001))
        self.assertEqual(command[:4], ["npm", "run", "render", "--"])
        self.assertEqual(command[command.index("--composition") + 1], "index.html")
        self.assertEqual(command[command.index("--fps") + 1], "24000/1001")

    def test_config_drift_changes_preview_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_approved_version(directory)
            outputs: list[str] = []
            def runner(command, **kwargs):
                output = Path(command[command.index("--output") + 1])
                output.write_bytes(b"mp4")
                outputs.append(str(output))
            probe = lambda _: {"width": 854, "height": 480, "r_frame_rate": "24/1", "duration": "10"}
            render_demo(root, runner=runner, prober=probe)
            config = root / "hyperframes.json"
            config.write_text(config.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            render_demo(root, runner=runner, prober=probe)
            self.assertNotEqual(Path(outputs[0]).name, Path(outputs[1]).name)

    def test_sidecar_failure_removes_preview_and_allows_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_approved_version(directory)
            def runner(command, **kwargs):
                Path(command[command.index("--output") + 1]).write_bytes(b"mp4")
            probe = lambda _: {"width": 854, "height": 480, "r_frame_rate": "24/1", "duration": "10"}
            with patch("scripts.render_demo.write_demo_generation_evidence", side_effect=OSError("sidecar failed")):
                with self.assertRaisesRegex(OSError, "sidecar failed"):
                    render_demo(root, runner=runner, prober=probe)
            self.assertFalse(list((root / "previews").glob("*.mp4")))
            self.assertEqual(render_demo(root, runner=runner, prober=probe)["status"], "rendered")
