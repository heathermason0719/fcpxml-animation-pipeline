import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.work_model_storyboard import frame_current, render_storyboard, storyboard_spec


class StoryboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "compositions/cues").mkdir(parents=True)
        (self.root / "assets/fonts").mkdir(parents=True)
        (self.root / "assets/vendor").mkdir(parents=True)
        (self.root / "package.json").write_text(json.dumps({"scripts": {
            name: "npm exec --package=hyperframes@0.8.33 -- hyperframes render" for name in ("dev", "check", "render", "publish")
        }}))
        (self.root / "hyperframes.json").write_text("{}")
        (self.root / "frame.md").write_text("frame")
        (self.root / "assets/fonts/title.woff2").write_bytes(b"font-1")
        (self.root / "assets/vendor/gsap.min.js").write_text("window.gsap={timeline:()=>({})}")
        (self.root / "compositions/cues/title.html").write_text("<template><div data-composition-id='title'>Title</div></template>")
        self.manifest = {"project": {"preview": {"width": 854, "height": 480}, "source": {"frameDuration": "1/24s"}}, "cues": [{
            "id": "title", "productionMode": "animation", "narration": "Opening line", "finalAnimationDescription": "Large title",
            "renderAdapters": {"hyperframes": {"compositionId": "title", "compositionSrc": "compositions/cues/title.html", "layoutDependencies": ["assets/fonts/title.woff2"]}}
        }]}

    def test_cold_start_layout_does_not_need_motion_and_renders_png(self):
        spec = storyboard_spec(self.root, self.manifest, {})
        frame = spec["frames"][0]
        self.assertEqual(frame["mode"], "layout")
        self.assertNotIn("motionSrc", " ".join(frame["files"]))
        commands = []
        def renderer(command, *, cwd, log_path):
            commands.append(command)
            output = Path(command[command.index("--output") + 1])
            output.mkdir(parents=True)
            (output / "frame.png").write_bytes(b"png")
        with patch("scripts.work_model_storyboard._run_command", side_effect=renderer):
            records = render_storyboard(self.root, self.manifest, spec, self.root / "storyboards", self.root / "jobs/storyboard.log")
        self.assertTrue((self.root / records[0]["path"]).is_file())
        self.assertIn("snapshot", commands[0])
        self.assertIn("--no-end", commands[0])
        self.assertIn("false", commands[0])
        self.assertTrue(frame_current(self.root, self.manifest, records[0]))

    def test_changed_layout_source_invalidates_rendered_frame(self):
        spec = storyboard_spec(self.root, self.manifest, {})
        def renderer(command, *, cwd, log_path):
            output = Path(command[command.index("--output") + 1])
            output.mkdir(parents=True)
            (output / "frame.png").write_bytes(b"png")
        with patch("scripts.work_model_storyboard._run_command", side_effect=renderer):
            record = render_storyboard(self.root, self.manifest, spec, self.root / "storyboards", self.root / "jobs/storyboard.log")[0]
        (self.root / "compositions/cues/title.html").write_text("<template><div>Changed</div></template>")
        self.assertFalse(frame_current(self.root, self.manifest, record))

    def test_layout_strips_a_relative_motion_loader(self):
        from scripts.work_model_storyboard import _strip_motion
        motion = self.root / "compositions/motion/title.js"
        motion.parent.mkdir()
        motion.write_text("motion")
        composition = self.root / "compositions/cues/title.html"
        clean = _strip_motion(self.root, composition, '<script src="../motion/title.js"></script><div>layout</div>', "compositions/motion/title.js")
        self.assertNotIn("motion/title.js", clean)
        self.assertIn("layout", clean)

    def test_layout_resolves_declared_root_motion_even_when_it_is_absent(self):
        from scripts.work_model_storyboard import _strip_motion
        cue = self.manifest['cues'][0]
        cue['renderAdapters']['hyperframes']['motionSrc'] = 'compositions/motion/title.js'
        path = self.root / 'compositions/cues/title.html'
        markup = '<script src="compositions/motion/title.js"></script><div>静态</div>'
        path.write_text(markup)
        spec = storyboard_spec(self.root, self.manifest)
        self.assertNotIn('compositions/motion/title.js', spec['files'])
        self.assertNotIn('<script', _strip_motion(self.root, path, markup, 'compositions/motion/title.js'))

    def test_remote_dependency_is_rejected_before_snapshot(self):
        (self.root / "compositions/cues/title.html").write_text('<img src="https://example.test/image.png">')
        with self.assertRaisesRegex(ValueError, "must be local"):
            storyboard_spec(self.root, self.manifest, {})

    def test_explicit_still_time_preserves_global_to_local_rational_conversion(self):
        self.manifest['cues'][0]['resolvedTimeline'] = {'start': '1001/300s', 'duration': '2s'}
        spec = storyboard_spec(self.root, self.manifest, {'scope': 'still', 'cueIds': ['title'], 'time': '1001/250s'})
        self.assertEqual(spec['frames'][0]['time'], '1001/1500s')
        self.assertTrue(spec['frames'][0]['sample'])
        self.assertEqual(spec['frames'][0]['frameId'], 'sample')
        from scripts.work_model_storyboard import _snapshot_command
        command = _snapshot_command('0.8.33', '23/3s', self.root / 'snapshots')
        from decimal import Decimal
        self.assertLess(abs(Decimal(command[command.index('--at') + 1]) - Decimal(23) / Decimal(3)), Decimal('1e-22'))

    def test_cold_start_source_none_and_static_state_are_supported(self):
        self.manifest["project"]["source"] = None
        self.manifest["cues"][0]["storyboard"] = {"frames": [
            {"id": "hero", "role": "hero", "label": "Hero", "time": "0s", "mode": "layout", "background": "none", "state": {"id": "review"}}
        ]}
        frame = storyboard_spec(self.root, self.manifest, {})["frames"][0]
        self.assertEqual(frame["state"], {"id": "review"})
        self.assertIsNone(frame["backgroundSrc"])

    def test_local_cached_cli_requires_exact_package_version(self):
        from scripts.work_model_runtime import local_cached_cli
        cache = self.root / "npm-cache"
        package = cache / "entry/node_modules/hyperframes/package.json"
        package.parent.joinpath("bin").mkdir(parents=True)
        package.write_text('{"version":"0.8.33"}')
        package.parent.joinpath("bin/hyperframes.mjs").write_text("// cli")
        self.assertEqual(local_cached_cli("0.8.33", cache_root=cache), ["node", str(package.parent / "bin/hyperframes.mjs")])
        self.assertIsNone(local_cached_cli("0.8.34", cache_root=cache))


if __name__ == "__main__":
    unittest.main()
