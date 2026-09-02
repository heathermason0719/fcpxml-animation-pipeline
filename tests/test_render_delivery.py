from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from fractions import Fraction

from scripts.layout_lock import freeze_layout
from scripts.sync_storyboard import sync_storyboard
from scripts.workflow_review import approve_demo, approve_storyboard, authorize_native_render, register_demo
from tests.test_hyperframes_single_source import SingleSourceFixture

try:
    from scripts.render_animations import build_render_command, build_render_jobs, render_animations
    from scripts.validate_delivery import DeliveryExpectation, validate_probe
except ModuleNotFoundError:
    build_render_command = None
    build_render_jobs = None
    render_animations = None
    DeliveryExpectation = None
    validate_probe = None


class RenderPlanningTests(SingleSourceFixture):
    def test_jobs_include_only_animated_native_delivery_hosts_without_resolution_override(self) -> None:
        self.assertIsNotNone(build_render_jobs, "render backend is missing")
        self.assertIsNotNone(build_render_command, "render command builder is missing")
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_version(directory)

            jobs = build_render_jobs(root)
            command = build_render_command(root, jobs[0], root / "delivery/.partial/test.mov")

            self.assertEqual([job.cue_id for job in jobs], ["p1s01_c01_title"])
            self.assertEqual(jobs[0].composition_src, "compositions/delivery/p1s01-c01-title.html")
            self.assertEqual(jobs[0].width, 1920)
            self.assertEqual(jobs[0].height, 1080)
            self.assertEqual(jobs[0].fps, Fraction(24, 1))
            self.assertEqual(jobs[0].duration, Fraction(2, 1))
            self.assertIn("--composition", command)
            self.assertIn("compositions/delivery/p1s01-c01-title.html", command)
            self.assertIn("--format", command)
            self.assertIn("mov", command)
            self.assertNotIn("--resolution", command)
            self.assertFalse(any("scale=" in part for part in command))

    def make_locked_version(self, directory: str) -> Path:
        root = self.make_version(directory)
        sync_storyboard(root)
        poster = root / "approved.png"
        poster.write_bytes(b"approved")
        freeze_layout(root, "p1s01_c01_title", poster)
        return root

    def authorize(self, root: Path) -> None:
        import json

        manifest_path = root / "animation-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["workflow"] = {"stageContractVersion": "1.0.0", "stageEvidence": {}}
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        approve_storyboard(root, actor="user")
        preview = root / "previews/demo.mp4"
        preview.parent.mkdir(parents=True, exist_ok=True)
        preview.write_bytes(b"demo")
        register_demo(root, "previews/demo.mp4")
        approve_demo(root, actor="user")
        authorize_native_render(root, actor="user")

    def test_native_render_blocks_before_writes_without_a14_authorization(self) -> None:
        self.assertIsNotNone(render_animations, "render backend is missing")
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)

            with self.assertRaisesRegex(ValueError, "A14|authorization"):
                render_animations(root, runner=lambda *args, **kwargs: None)

            self.assertFalse((root / "delivery").exists())

    def test_authorized_render_ledger_binds_current_authorization_and_inputs(self) -> None:
        self.assertIsNotNone(render_animations, "render backend is missing")
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_locked_version(directory)
            self.authorize(root)

            def runner(command, **kwargs):
                output = Path(command[command.index("--output") + 1])
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"native transparent movie")
                return None

            probe = {
                "codec_name": "prores",
                "profile": "4444",
                "width": 1920,
                "height": 1080,
                "pix_fmt": "yuva444p12le",
                "r_frame_rate": "24/1",
                "duration": "2.000000",
            }

            ledger = render_animations(root, runner=runner, prober=lambda _: probe)

            self.assertEqual(ledger["stageId"], "D2")
            self.assertEqual(ledger["contractVersion"], "1.0.0")
            self.assertEqual(ledger["semanticVersion"], 1)
            self.assertEqual(len(ledger["authorizationFingerprint"]), 64)
            self.assertEqual(len(ledger["inputFingerprint"]), 64)
            self.assertEqual(len(ledger["items"][0]["sha256"]), 64)


class DeliveryValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertIsNotNone(DeliveryExpectation, "delivery validator is missing")
        self.assertIsNotNone(validate_probe, "delivery validator is missing")
        self.expected = DeliveryExpectation(
            width=1920,
            height=1080,
            fps=Fraction(24, 1),
            duration=Fraction(161, 24),
        )
        self.valid_probe = {
            "codec_name": "prores",
            "profile": "4444",
            "width": 1920,
            "height": 1080,
            "pix_fmt": "yuva444p12le",
            "r_frame_rate": "24/1",
            "duration": "6.708333",
        }

    def test_valid_native_alpha_prores_has_no_findings(self) -> None:
        self.assertEqual(validate_probe(self.valid_probe, self.expected), [])

    def test_wrong_dimensions_are_rejected(self) -> None:
        probe = {**self.valid_probe, "width": 854, "height": 480}
        self.assertEqual(validate_probe(probe, self.expected), ["dimensions_mismatch"])

    def test_missing_alpha_is_rejected(self) -> None:
        probe = {**self.valid_probe, "pix_fmt": "yuv444p12le"}
        self.assertEqual(validate_probe(probe, self.expected), ["alpha_missing"])

    def test_wrong_codec_or_profile_is_rejected(self) -> None:
        probe = {**self.valid_probe, "codec_name": "h264", "profile": "High"}
        self.assertEqual(validate_probe(probe, self.expected), ["codec_mismatch"])

    def test_wrong_frame_rate_is_rejected(self) -> None:
        probe = {**self.valid_probe, "r_frame_rate": "30/1"}
        self.assertEqual(validate_probe(probe, self.expected), ["frame_rate_mismatch"])

    def test_duration_beyond_one_frame_is_rejected(self) -> None:
        probe = {**self.valid_probe, "duration": "6.80"}
        self.assertEqual(validate_probe(probe, self.expected), ["duration_mismatch"])


if __name__ == "__main__":
    unittest.main()
