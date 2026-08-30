from __future__ import annotations

import tempfile
import unittest
from fractions import Fraction

from tests.test_hyperframes_single_source import SingleSourceFixture

try:
    from scripts.render_animations import build_render_command, build_render_jobs
    from scripts.validate_delivery import DeliveryExpectation, validate_probe
except ModuleNotFoundError:
    build_render_command = None
    build_render_jobs = None
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
