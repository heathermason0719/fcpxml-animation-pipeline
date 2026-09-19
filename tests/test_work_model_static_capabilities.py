"""The static profile closes resources and time, rather than known keywords."""
import base64
import tempfile
import unittest
from pathlib import Path
from scripts.work_model_sources import inspect_sources, static_markup
from tests.test_work_model_sources import cue

GIF_HEADER = b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\x00\x00\x00\x00\xff'
GIF_FRAME = b'\x21\xf9\x04\x04\x0a\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00'
STILL = GIF_HEADER + GIF_FRAME + b'\x3b'
ANIMATED = GIF_HEADER + GIF_FRAME + GIF_FRAME.replace(b'\x44\x01', b'\x4c\x01') + b'\x3b'


class StaticCapabilitiesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); (self.root/'compositions').mkdir()

    def source(self, text):
        (self.root/'compositions/cue.html').write_text(text)
        return inspect_sources(self.root, cue())

    def test_standard_resource_forms_reject_remote_and_missing_inputs(self):
        for url in ('https://example.test/a.png', 'missing.png'):
            forms = [f'<img srcset="{url} 1x">', f'<picture><source srcset="{url} 2x"><img></picture>',
                     f'<style>.x{{background:image-set("{url}" 1x)}}</style>',
                     f'<svg><filter><feImage href="{url}"/></filter></svg>',
                     f'<svg><rect fill="url({url}#paint)"/></svg>']
            for text in forms:
                with self.subTest(text=text), self.assertRaises(ValueError): self.source(text)

    def test_all_candidates_and_nested_svg_are_in_the_closure(self):
        for name in ('a.gif','b.gif'): (self.root/'compositions'/name).write_bytes(STILL)
        (self.root/'compositions/p.svg').write_text('<svg><image href="b.gif"/></svg>')
        result=self.source('<img srcset="a.gif 1x, b.gif 2x"><style>.x{background:image-set("a.gif" 1x,url(p.svg) 2x)}</style>')
        self.assertEqual(set(result['files']), {'compositions/cue.html','compositions/a.gif','compositions/b.gif','compositions/p.svg'})
        self.assertEqual(result['motionFiles'], [])

    def test_motion_raster_uses_content_not_extension_or_data_mime(self):
        for name in ('animated.gif','disguised.png'):
            (self.root/'compositions'/name).write_bytes(ANIMATED)
            text=f'<img src="{name}">'; result=self.source(text)
            self.assertIn('compositions/'+name,result['motionFiles'])
            with self.assertRaises(ValueError): static_markup(self.root,cue(),text)
        uri='data:image/gif;base64,'+base64.b64encode(ANIMATED).decode()
        result=self.source(f'<img src="{uri}">')
        self.assertIn('compositions/cue.html',result['motionFiles'])

    def test_single_frame_images_and_literal_css_text_remain_static(self):
        uri='data:image/gif;base64,'+base64.b64encode(STILL).decode()
        text=f'<img src="{uri}"><style>.x::after{{content:"image-set(ghost.png) animation:";color:var(--ink, red)}}</style>'
        self.assertEqual(self.source(text)['motionFiles'], [])
        self.assertEqual(static_markup(self.root,cue(),text),text)

    def test_unknown_capabilities_do_not_default_to_static(self):
        for text in ('<unreviewed-widget>x</unreviewed-widget>', '<div mystery-loader="x"></div>',
                     '<style>.x{new-browser-property:1}</style>', '<style>.x{background:new-image-function("x")}</style>'):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError,'unsupported|capability'): self.source(text)

    def test_marquee_is_time_driven_but_static_svg_is_not(self):
        self.assertEqual(self.source('<marquee>x</marquee>')['motionFiles'], ['compositions/cue.html'])
        self.assertEqual(self.source('<svg><defs><linearGradient id="g"><stop offset="0" stop-color="red"/></linearGradient></defs><rect fill="url(#g)"/></svg>')['motionFiles'], [])

    def test_css_token_context_handles_escapes_variables_and_imports(self):
        (self.root/'compositions/a.gif').write_bytes(STILL)
        (self.root/'compositions/a.css').write_text('.x{--picture:image-set("a.gif" 1x);background:var(--picture)}')
        text='<style>@import "a.css"; .x{background:im\\61 ge-set("a.gif" 2x)}</style>'
        self.assertEqual(set(self.source(text)['files']), {'compositions/cue.html','compositions/a.gif','compositions/a.css'})

    def test_blob_and_unverifiable_image_data_are_rejected(self):
        for uri in ('blob:anything','data:image/gif;base64,AA==','data:unknown/type;base64,AA=='):
            with self.subTest(uri=uri),self.assertRaises(ValueError):self.source(f'<img src="{uri}">')

    def test_png_and_webp_animation_containers_have_motion_capability(self):
        import struct
        import zlib
        def chunk(kind, data):
            return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
        png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB',1,1,8,6,0,0,0))+chunk(b'acTL',struct.pack('>II',2,0))+chunk(b'IEND',b'')
        webp=b'RIFF'+struct.pack('<I',34)+b'WEBP'+b'ANIM'+struct.pack('<I',6)+b'\0'*6+(b'ANMF'+struct.pack('<I',0))*2
        from scripts.work_model_capabilities import raster_motion
        one_frame_png=png.replace(struct.pack('>II',2,0),struct.pack('>II',1,0))
        self.assertFalse(raster_motion(one_frame_png,required=True))
        self.assertFalse(raster_motion(webp[:-8],required=True))
        for name,data in [('a.png',png),('b.webp',webp)]:
            (self.root/'compositions'/name).write_bytes(data)
            self.assertIn('compositions/'+name,self.source(f'<img src="{name}">')['motionFiles'])

    def test_srcset_svg_context_preserves_nested_resources_and_time(self):
        (self.root/'compositions/nested.svg').write_text('<svg><image href="motion.gif"/></svg>')
        (self.root/'compositions/motion.gif').write_bytes(ANIMATED)
        result=self.source('<img srcset="nested.svg 1x">')
        self.assertIn('compositions/motion.gif',result['motionFiles'])

    def test_unknown_binary_cannot_be_hidden_in_css_resource(self):
        (self.root/'compositions/mystery.bin').write_bytes(b'not a supported image or font')
        with self.assertRaisesRegex(ValueError,'unverifiable'):
            self.source('<style>.x{background:url(mystery.bin)}</style>')

    def test_renderer_guard_denies_network_and_surfaces_dependency_failure(self):
        from scripts.work_model_capabilities import guarded_host, validate_render_resources
        host=guarded_host('<html><head></head><body></body></html>')
        self.assertIn('Content-Security-Policy',host)
        self.assertIn("connect-src &#x27;self&#x27;",host)
        self.assertNotIn('https:',host)
        for diagnostic in ['Loading the image violates the following Content Security Policy directive',
                           'REQUESTFAILED http://127.0.0.1:8765/unknown.png net::ERR_FAILED',
                           'HTTPERROR http://127.0.0.1:8765/unknown.png 404',
                           '[FileServer] 404 Not Found: /unregistered.png',
                           'Failed to load resource: the server responded with a status of 404 (Not Found)']:
            with self.assertRaisesRegex(ValueError,'renderer rejected'): validate_render_resources(diagnostic)
        validate_render_resources('Captured 1 frames successfully')

    def test_computed_resource_candidate_cannot_evade_static_closure(self):
        with self.assertRaisesRegex(ValueError, 'computed image-set'):
            self.source('<style>.x{--image:"https://example.test/a.png";background:image-set(var(--image) 1x)}</style>')

    def test_autoplay_inputs_require_a_fixed_frame_or_seekable_motion_adapter(self):
        from scripts.work_model_inputs import dependencies
        c=cue(motionSrc='compositions/motion.js')
        (self.root/'compositions/motion.js').write_text('// declared seekable adapter')
        (self.root/'compositions/motion.gif').write_bytes(ANIMATED)
        for text in ['<marquee>x</marquee>', '<img src="motion.gif">']:
            self.source(text)
            with self.assertRaisesRegex(ValueError, 'fixed sample or seekable'):
                dependencies(self.root, c)

    def test_svg_image_and_font_resources_cannot_skip_capability_validation(self):
        (self.root/'compositions/mystery.bin').write_bytes(b'unknown format')
        for tag in ['image', 'feImage']:
            for attribute in ['href', 'xlink:href']:
                with self.assertRaisesRegex(ValueError, 'unverifiable'):
                    self.source(f'<svg><{tag} {attribute}="mystery.bin"/></svg>')
        with self.assertRaisesRegex(ValueError, 'unsupported CSS function'):
            self.source('<style>@font-face{font-family:test;src:local("Arial")}</style>')

    def test_navigation_and_autoplay_media_require_seekable_implementation(self):
        (self.root/'compositions/clip.mp4').write_bytes(b'media-fixture')
        for text in ['<meta http-equiv="refresh" content="1">', '<video src="clip.mp4" autoplay></video>']:
            self.assertEqual(self.source(text)['unseekableFiles'], ['compositions/cue.html'])
        # Framework-owned playback can seek a regular video element; it is
        # Motion, but not autonomous browser autoplay.
        self.assertEqual(self.source('<video src="clip.mp4" data-start="0" data-duration="1"></video>')['unseekableFiles'], [])


    def test_duplicate_attributes_cannot_disagree_with_browser_resource_selection(self):
        (self.root/'compositions/still.gif').write_bytes(STILL)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.source('<img src="https://example.test/a.png" src="still.gif">')
