import tempfile
import unittest
from pathlib import Path

from scripts.work_model_sources import inspect_sources, static_markup


def cue(**adapter):
    return {"id": "cue", "renderAdapters": {"hyperframes": {
        "compositionSrc": "compositions/cue.html", "layoutDependencies": [], **adapter}}}


class WorkModelSourcesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "compositions").mkdir()

    def tearDown(self): self.tmp.cleanup()

    def put(self, name, text):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)

    def put_bytes(self, name, data):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)

    def test_inline_scripts_are_motion_even_without_library_keywords(self):
        self.put("compositions/cue.html", '<script>element.animate([], {duration: 1})</script>')
        self.assertEqual(inspect_sources(self.root, cue())["motionFiles"], ["compositions/cue.html"])

    def test_external_javascript_is_motion_but_its_pure_loader_is_not(self):
        self.put("compositions/cue.html", '<script src="motion.js"></script>')
        self.put("compositions/motion.js", 'import "./helper.mjs"')
        self.put("compositions/helper.mjs", 'export const frame = 1')
        result = inspect_sources(self.root, cue())
        self.assertEqual(result["files"], ["compositions/cue.html", "compositions/helper.mjs", "compositions/motion.js"])
        self.assertEqual(result["motionFiles"], ["compositions/helper.mjs", "compositions/motion.js"])

    def test_script_execution_context_marks_non_javascript_extension_as_motion(self):
        self.put("compositions/cue.html", '<script src=motion.payload></script>')
        self.put_bytes("compositions/motion.payload", b"\x00not utf8\xff")
        result = inspect_sources(self.root, cue())
        self.assertEqual(result["motionFiles"], ["compositions/motion.payload"])

    def test_declared_missing_motion_loader_resolves_to_the_declared_root_path(self):
        self.put("compositions/cue.html", '<script src="motion.js"></script>')
        result = inspect_sources(self.root, cue(motionSrc="compositions/motion.js"))
        self.assertEqual(result["files"], ["compositions/cue.html", "compositions/motion.js"])
        self.assertEqual(result["motionFiles"], ["compositions/motion.js"])

    def test_dynamic_composition_remains_motion_when_motion_declaration_is_removed(self):
        self.put("compositions/cue.html", '<script>window.t = 0</script>')
        self.assertEqual(inspect_sources(self.root, cue())["motionFiles"], ["compositions/cue.html"])

    def test_declared_motion_source_is_motion_even_when_its_contents_are_comments(self):
        self.put("compositions/cue.html", '<div>layout</div>')
        self.put("compositions/motion.js", '// intentionally empty')
        self.assertEqual(inspect_sources(self.root, cue(motionSrc="compositions/motion.js"))["motionFiles"],
            ["compositions/motion.js"])

    def test_escaped_css_and_svg_animation_or_events_are_motion(self):
        self.put("compositions/cue.html", '<link href="../assets/motion.css"><svg onload="go()"><animate attributeName="x" /></svg>')
        self.put("assets/motion.css", '.x { \\61 nimation: fade 1s }')
        result = inspect_sources(self.root, cue())
        self.assertEqual(result["motionFiles"], ["assets/motion.css", "compositions/cue.html"])

    def test_static_markup_and_strict_json_remain_static(self):
        self.put("compositions/cue.html", '<link href="../assets/layout.css"><script type="application/json">{"x": 1}</script><svg><path d="M0 0" /></svg>')
        self.put("assets/layout.css", '@font-face { src: url(font.woff2) } .x { color: red }')
        self.put_bytes("assets/font.woff2", b"wOF2font-fixture")
        result = inspect_sources(self.root, cue())
        self.assertEqual(result["motionFiles"], [])
        self.assertEqual(result["files"], ["assets/font.woff2", "assets/layout.css", "compositions/cue.html"])

    def test_css_comments_and_string_content_do_not_create_motion(self):
        self.put("compositions/cue.html", '<link href="../assets/layout.css">')
        self.put("assets/layout.css", '/* animation: fade 1s */ .x::after { content: "@keyframes animation:" }')
        self.assertEqual(inspect_sources(self.root, cue())["motionFiles"], [])

    def test_static_markup_removes_only_declared_or_vendor_loaders(self):
        self.put("compositions/cue.html", '<div>layout</div>')
        result = static_markup(self.root, cue(motionSrc="compositions/motion.js"),
            '<script src="motion.js"></script><script src="../assets/vendor/gsap.min.js"></script><div>layout</div>')
        self.assertEqual(result, '<div>layout</div>')
        legacy = static_markup(self.root, cue(motionSrc="compositions/motion.js"),
            '<script type="module"> import "motion.js"; </script><div>layout</div>')
        self.assertEqual(legacy, '<div>layout</div>')
        unquoted = static_markup(self.root, cue(motionSrc="compositions/motion.js"),
            '<script src=motion.js></script><div>layout</div>')
        self.assertEqual(unquoted, '<div>layout</div>')

    def test_static_markup_rejects_other_executable_and_remote_sources(self):
        self.put("compositions/cue.html", '<div>layout</div>')
        with self.assertRaisesRegex(ValueError, "executable"):
            static_markup(self.root, cue(motionSrc="compositions/motion.js"), '<script src="other.js"></script>')
        with self.assertRaisesRegex(ValueError, "local"):
            inspect_sources(self.root, cue(), {"compositions/cue.html": b'<script src="https://bad.test/a.js"></script>'})

    def test_inline_style_and_active_svg_urls_cannot_pass_as_static(self):
        self.put("compositions/cue.html", '<div style="animation: fade 1s"></div>')
        self.assertEqual(inspect_sources(self.root, cue())["motionFiles"], ["compositions/cue.html"])
        with self.assertRaisesRegex(ValueError, "executable"):
            static_markup(self.root, cue(), '<div style="animation: fade 1s"></div>')
        with self.assertRaisesRegex(ValueError, "local|active"):
            inspect_sources(self.root, cue(), {"compositions/cue.html": b'<svg><a href="javascript:go()" /></svg>'})
        with self.assertRaisesRegex(ValueError, "active"):
            inspect_sources(self.root, cue(), {"compositions/cue.html": b'<svg><image href="data:image/svg+xml,x" /></svg>'})

    def test_invalid_json_script_is_not_silently_static(self):
        self.put("compositions/cue.html", '<script type="application/json">{bad}</script>')
        with self.assertRaisesRegex(ValueError, "strict JSON"):
            inspect_sources(self.root, cue())

    def test_stylesheet_loader_is_parsed_by_its_execution_context_not_extension(self):
        self.put("compositions/cue.html", '<link rel="stylesheet" href="theme.payload">')
        self.put("compositions/theme.payload", '@keyframes appear { from { opacity: 0 } }')
        result = inspect_sources(self.root, cue())
        self.assertEqual(result["motionFiles"], ["compositions/theme.payload"])

    def test_active_data_stylesheets_cannot_bypass_static_boundary(self):
        for markup in ('<link rel="stylesheet" href="data:text/css,%40keyframes%20x%7Bto%7Bopacity:0%7D%7D">',
                       '<style>@import url("data:text/css,%40keyframes%20x{}");</style>',
                       '<link rel="stylesheet" href="data:application/octet-stream,body{animation:x}">'):
            with self.subTest(markup=markup):
                self.put('compositions/cue.html', markup)
                with self.assertRaisesRegex(ValueError, 'active|local'):
                    static_markup(self.root, cue(), markup)

    def test_static_layout_cannot_embed_playing_media_or_rebase_dependencies(self):
        self.put_bytes('assets/background.mp4',b'video')
        for tag in ('video', 'audio'):
            markup=f'<{tag} src="assets/background.mp4" autoplay></{tag}>'
            self.put('compositions/cue.html',markup)
            with self.assertRaisesRegex(ValueError,'executable'):
                static_markup(self.root,cue(),markup)
        with self.assertRaisesRegex(ValueError,'base URL'):
            static_markup(self.root,cue(),'<base href="https://example.test/"><img src="x.png">')

    def test_css_import_url_loader_preserves_nested_motion_dependency(self):
        self.put("compositions/cue.html", '<link rel="stylesheet" href="../assets/base.css">')
        self.put("assets/base.css", '@import url("nested.css");')
        self.put("assets/nested.css", '.card { animation: enter 1s }')
        result = inspect_sources(self.root, cue())
        self.assertEqual(result["files"], ["assets/base.css", "assets/nested.css", "compositions/cue.html"])
        self.assertEqual(result["motionFiles"], ["assets/nested.css"])

    def test_escaped_css_import_loader_preserves_nested_dependency(self):
        self.put("compositions/cue.html", '<link rel="stylesheet" href="../assets/base.css">')
        self.put("assets/base.css", '@im\\70 ort url("nested.css");')
        self.put("assets/nested.css", '.card { animation: enter 1s }')
        result = inspect_sources(self.root, cue())
        self.assertEqual(result["files"], ["assets/base.css", "assets/nested.css", "compositions/cue.html"])
        self.assertEqual(result["motionFiles"], ["assets/nested.css"])

    def test_nested_composition_markup_contributes_its_dynamic_source(self):
        self.put("compositions/cue.html", '<div data-composition-src="nested.html"></div>')
        self.put("compositions/nested.html", '<script>const frame = 0</script>')
        result = inspect_sources(self.root, cue())
        self.assertEqual(result["files"], ["compositions/cue.html", "compositions/nested.html"])
        self.assertEqual(result["motionFiles"], ["compositions/nested.html"])

    def test_non_javascript_module_loader_is_motion_and_binds_to_its_owner(self):
        self.put("compositions/cue.html", '<script type="module" src="runtime.code"></script>')
        self.put("compositions/runtime.code", 'opaque executable payload')
        result = inspect_sources(self.root, cue())
        self.assertEqual(result["motionFiles"], ["compositions/runtime.code"])
        self.assertEqual(result["motionBindings"], [("compositions/cue.html", "compositions/runtime.code")])

    def test_unclosed_script_is_rejected_before_static_snapshot(self):
        self.put("compositions/cue.html", '<script src="motion.js">')
        with self.assertRaisesRegex(ValueError, "unclosed"):
            inspect_sources(self.root, cue(motionSrc="compositions/motion.js"))

    def test_static_markup_removes_vendor_loader_and_declared_motion_helper_closure(self):
        self.put("compositions/cue.html", '<script src="motion/main.mjs"></script><script src="../assets/vendor/gsap.min.js"></script><div>layout</div>')
        self.put("compositions/motion/main.mjs", 'import "./helper.mjs"')
        self.put("compositions/motion/helper.mjs", 'export const setup = () => {}')
        self.put("assets/vendor/gsap.min.js", 'window.gsap = {}')
        source = cue(motionSrc="compositions/motion/main.mjs", layoutDependencies=["assets/vendor/gsap.min.js"])
        original = inspect_sources(self.root, source)
        self.assertEqual(original["motionFiles"], ["assets/vendor/gsap.min.js", "compositions/motion/helper.mjs", "compositions/motion/main.mjs"])
        self.assertEqual(static_markup(self.root, source, (self.root / "compositions/cue.html").read_text()), '<div>layout</div>')
