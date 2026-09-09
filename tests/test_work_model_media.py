from __future__ import annotations

import json
import cmath
import math
import subprocess
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, text=True)


def make_movie(path: Path, *, duration: str, size: str = "854x480", audio: bool = False) -> None:
    command = [
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
        f"color=c=black:s={size}:r=30000/1001:d={duration}",
    ]
    if audio:
        command += ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:d={duration}"]
    command += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if audio:
        command += ["-c:a", "aac", "-shortest"]
    command.append(str(path))
    run(command)


def make_alpha_movie(path: Path, *, foreground_alpha: int = 255, background_alpha: int = 0) -> None:
    run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
        "color=c=red:s=64x64:r=24:d=1",
        "-vf", (
            "format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
            f"a='if(between(X,16,47)*between(Y,16,47),{foreground_alpha},{background_alpha})',format=yuva444p10le"
        ),
        "-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le", str(path),
    ])


def make_temporal_overlay(path: Path, *, lower: bool) -> None:
    x1, x2 = (80, 360) if lower else (250, 540)
    run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "nullsrc=s=854x480:r=24:d=2",
        "-vf", (
            "format=rgba,"
            f"geq=r='if(lt(T,1),{255 if lower else 0},{0 if lower else 255})':"
            f"g='if(lt(T,1),{0 if lower else 255},{255 if lower else 0})':b=0:"
            f"a='if(between(X,{x1},{x2})*between(Y,100,380),min(min(180,180*T),180*(2-T)),0)',format=yuva444p10le"
        ),
        "-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le", str(path),
    ])


def make_two_tone_audio_reference(path: Path) -> None:
    run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=320x180:r=24:d=2",
        "-f", "lavfi", "-i", "sine=frequency=300:sample_rate=48000:d=1",
        "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=48000:d=1",
        "-filter_complex", "[1:a][2:a]concat=n=2:v=0:a=1[a]", "-map", "0:v", "-map", "[a]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path),
    ])


def decoded_frame(path: Path, *, second: str) -> bytes:
    seek = str(float(Fraction(second)))
    return subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", seek, "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        check=True, capture_output=True,
    ).stdout


def tone_energy(path: Path, frequency: int) -> float:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", "0.15", "-t", "0.1", "-i", str(path), "-map", "0:a:0", "-f", "f32le", "-ac", "1", "-ar", "48000", "-"],
        check=True, capture_output=True,
    ).stdout
    import struct
    samples = struct.unpack("<" + "f" * (len(raw) // 4), raw)
    return abs(sum(value * cmath.exp(complex(0, -2 * math.pi * frequency * index / 48000)) for index, value in enumerate(samples)))


class WorkModelMediaTests(unittest.TestCase):
    def test_render_command_uses_pinned_script_and_requested_native_dimensions(self) -> None:
        from scripts.work_model_media import build_render_command

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(json.dumps({"scripts": {
                name: "npm exec --package=hyperframes@0.8.33 -- hyperframes render"
                for name in ("dev", "check", "render", "publish")
            }}), encoding="utf-8")
            command = build_render_command(
                root, {"id": "cue-a", "resolvedTimeline": {"duration": "1s"}, "renderAdapters": {"hyperframes": {
                    "compositionId": "cue-a", "compositionSrc": "compositions/cues/cue-a.html", "motionSrc": "compositions/motion/cue-a.js", "layoutDependencies": ["x"]
                }}}, quality="delivery", target=root / "out.mov"
            )
            self.assertEqual(command[:4], ["npm", "run", "render", "--"])
            self.assertIn("cue-a", command)
            self.assertNotIn("--width", command)
            self.assertNotIn("--height", command)
            self.assertIn("--format", command)
            self.assertNotIn("latest", " ".join(command))

    def test_render_host_mounts_native_canonical_source_and_scales_only_preview(self) -> None:
        from scripts.work_model_media import _render_host_html

        cue = {"id": "cue-a", "resolvedTimeline": {"duration": "1s"}, "renderAdapters": {"hyperframes": {
            "compositionId": "cue-a", "compositionSrc": "compositions/cues/cue-a.html", "motionSrc": "compositions/motion/cue-a.js", "layoutDependencies": ["x"]
        }}}
        preview = _render_host_html(cue, width=854, height=480, fps=Fraction(24), native_width=1920, native_height=1080)
        delivery = _render_host_html(cue, width=1920, height=1080, fps=Fraction(24), native_width=1920, native_height=1080)
        self.assertIn('src="assets/vendor/gsap.min.js"', preview)
        self.assertIn('data-composition-src="compositions/cues/cue-a.html"', preview)
        self.assertIn('data-width="1920" data-height="1080"', preview)
        self.assertIn('transform:scale(0.4447916666666666666666666667,0.4444444444444444444444444444)', preview)
        self.assertIn('transform:scale(1,1)', delivery)
        self.assertNotIn('compositions/motion/cue-a.js', preview)

    def test_composite_command_trims_an_overlapping_cue_from_its_local_offset(self) -> None:
        from scripts.work_model_media import build_composite_command

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            media = root / "rough.mp4"
            overlay = root / "cue.mov"
            media.touch()
            overlay.touch()
            command = build_composite_command(
                root, {"project": {"source": {"frameDuration": "1/24s"}, "preview": {"width": 854, "height": 480}, "renderAdapters": {"hyperframes": {"previewMediaSrc": "rough.mp4"}}}},
                [{"cueId": "cue-a", "path": "cue.mov", "start": "1s", "duration": "2s", "layer": 3}],
                start=Fraction(3, 2), duration=Fraction(1, 1), target=root / "result.mp4", has_audio=False,
            )
            filters = command[command.index("-filter_complex") + 1]
            self.assertIn("trim=start=0.5:duration=1", filters)
            self.assertIn("setpts=PTS-STARTPTS+0/TB", filters)

    def test_composite_preview_preserves_rational_fps_and_reference_audio(self) -> None:
        from scripts.work_model_media import composite_preview

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            media = root / "assets/media/rough.mp4"
            media.parent.mkdir(parents=True)
            make_movie(media, duration="2", size="320x180", audio=True)
            overlay = root / "overlay.mp4"
            make_movie(overlay, duration="1")
            target = root / "preview.mp4"
            result = composite_preview(
                root, {"project": {"source": {"frameDuration": "1001/30000s"}, "preview": {"width": 854, "height": 480}, "renderAdapters": {"hyperframes": {"previewMediaSrc": "assets/media/rough.mp4"}}}},
                [{"cueId": "cue-a", "path": "overlay.mp4", "start": "1001/10000s", "duration": "1001/10000s", "layer": 2}],
                start=Fraction(1001, 10000), duration=Fraction(1001, 10000), target=target, log_path=root / "composite.log",
            )
            self.assertTrue(target.is_file())
            self.assertEqual(result["width"], 854)
            self.assertEqual(result["height"], 480)
            probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,r_frame_rate", "-of", "json", str(target)], check=True, capture_output=True, text=True)
            streams = json.loads(probe.stdout)["streams"]
            self.assertEqual(streams[0]["r_frame_rate"], "30000/1001")
            self.assertIn("audio", [item["codec_type"] for item in streams])

    def test_validate_alpha_requires_real_transparent_and_visible_pixels(self) -> None:
        from scripts.work_model_media import validate_alpha

        with tempfile.TemporaryDirectory() as directory:
            movie = Path(directory) / "alpha.mov"
            make_alpha_movie(movie)
            result = validate_alpha(movie, {"alphaExpectation": {"mode": "transparent", "samples": [{"time": "1/2s", "transparentPoints": [[0, 0]], "opaquePoints": [[32, 32]]}]}})
            self.assertEqual(result["status"], "valid")

    def test_validate_alpha_accepts_real_semitransparent_content(self) -> None:
        from scripts.work_model_media import validate_alpha

        with tempfile.TemporaryDirectory() as directory:
            movie = Path(directory) / "semi-transparent.mov"
            make_alpha_movie(movie, foreground_alpha=153)
            result = validate_alpha(movie, {"alphaExpectation": {"mode": "transparent", "samples": [{"time": "1/2s", "transparentPoints": [[0, 0]]}]}})
            self.assertEqual(result["status"], "valid")
            self.assertTrue(result["samples"][0]["hasVisible"])

    def test_validate_alpha_opaque_mode_rejects_mixed_real_alpha(self) -> None:
        from scripts.work_model_media import validate_alpha

        with tempfile.TemporaryDirectory() as directory:
            movie = Path(directory) / "mixed-alpha.mov"
            make_alpha_movie(movie, foreground_alpha=255, background_alpha=128)
            with self.assertRaisesRegex(ValueError, "fully opaque"):
                validate_alpha(movie, {"alphaExpectation": {"mode": "opaque", "samples": [{"time": "1/2s"}]}})

    def test_composite_local_window_matches_full_timeline_for_overlaps_offsets_and_audio(self) -> None:
        from scripts.work_model_media import composite_preview

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rough = root / "assets/media/rough.mp4"
            rough.parent.mkdir(parents=True)
            make_two_tone_audio_reference(rough)
            low, high = root / "low.mov", root / "high.mov"
            make_temporal_overlay(low, lower=True)
            make_temporal_overlay(high, lower=False)
            manifest = {"project": {"source": {"frameDuration": "1/24s"}, "preview": {"width": 854, "height": 480}, "renderAdapters": {"hyperframes": {"previewMediaSrc": "assets/media/rough.mp4"}}}}
            overlays = [
                {"cueId": "low", "path": "low.mov", "start": "0s", "duration": "2s", "layer": 2},
                {"cueId": "high", "path": "high.mov", "start": "1/2s", "duration": "2s", "layer": 3},
            ]
            full, local = root / "full.mp4", root / "local.mp4"
            composite_preview(root, manifest, overlays, start=Fraction(0), duration=Fraction(2), target=full, log_path=root / "full.log")
            composite_preview(root, manifest, overlays, start=Fraction(1), duration=Fraction(1), target=local, log_path=root / "local.log")
            # These overlays dissolve in and out. At the local boundary both
            # must use their 1s/0.5s local state; equality catches a restart.
            for full_time, local_time in (("1", "0"), ("3/2", "1/2"), ("47/24", "23/24")):
                expected, actual = decoded_frame(full, second=full_time), decoded_frame(local, second=local_time)
                self.assertEqual(len(expected), len(actual))
                self.assertLessEqual(max(abs(left - right) for left, right in zip(expected, actual)), 3)
            self.assertGreater(tone_energy(local, 1000), tone_energy(local, 300) * 3)


if __name__ == "__main__":
    unittest.main()
