"""Bounded compatibility for actual FCP 1.14 Basic Title re-exports."""

import sys
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from scripts.compare_fcpxml_roundtrip import compare_roundtrip
from tests import test_fcpxml_delivery_backend as fixtures


BASIC_TITLE = ".../Titles.localized/Bumper:Opener.localized/Basic Title.localized/Basic Title.moti"
PARAGRAPH = "9999/999166631/999166633/2/354/"
FONT = "9999/999166631/999166633/5/999166635/83"


class TextStyleRoundTripTests(unittest.TestCase):
    def fixture(self, directory, *, color=None, defaults=False):
        delivered, exported, manifest = fixtures.RoundTripTests().make_roundtrip_fixture(directory)
        doc = ET.parse(delivered)
        root = doc.getroot()
        root.set("version", "1.14")
        ET.SubElement(root.find("resources"), "effect", {"id": "basic", "uid": BASIC_TITLE})
        title = ET.SubElement(root.find(".//project/sequence/spine/clip"), "title", {
            "ref": "basic", "name": "Original title", "lane": "5", "offset": "102s", "duration": "1s",
        })
        if defaults:
            for paragraph_id in ("999169573", "3456789"):
                ET.SubElement(title, "param", {"name": "对齐", "key": PARAGRAPH + paragraph_id + "/401", "value": "0 (左)"})
            ET.SubElement(title, "param", {"name": "字体", "key": FONT, "value": "1 0"})
        text = ET.SubElement(title, "text")
        ET.SubElement(text, "text-style", {"ref": "original-style"}).text = "First line\n第二行"
        style = ET.SubElement(ET.SubElement(title, "text-style-def", {"id": "original-style"}), "text-style", {
            "font": "Helvetica", "fontFace": "Regular", "fontSize": "63", "fontColor": "1 1 1 1",
        })
        if color:
            style.set(color[0], color[1])
            if color[0] == "strokeColor":
                style.set("strokeWidth", "-3")
        doc.write(delivered)
        doc.write(exported)
        return delivered, exported, manifest

    def rewrite(self, exported, *, color=None, remove_defaults=False):
        doc = ET.parse(exported)
        title = doc.find(".//title[@name='Original title']")
        if color:
            title.find("text-style-def/text-style").set(*color)
        if remove_defaults:
            for parameter in list(title.findall("param")):
                title.remove(parameter)
        doc.write(exported)
        return doc

    @unittest.skipUnless(sys.platform == "darwin", "actual macOS ColorSync conversion")
    def test_accepts_reproduced_generic_rgb_srgb_roundtrip_not_raw_color_tolerance(self):
        examples = [
            ("strokeColor", "0 0.280365 0.2931 1", "0.0357131 0.280287 0.293106 1"),
            ("fontColor", "0.756586 0.155105 0 1", "0.756584 0.155011 0.0178087 1"),
        ]
        for attribute, original, actual in examples:
            with self.subTest(attribute=attribute), tempfile.TemporaryDirectory() as directory:
                delivered, exported, manifest = self.fixture(directory, color=(attribute, original))
                self.rewrite(exported, color=(attribute, actual))
                before = (delivered.read_bytes(), exported.read_bytes())
                result = compare_roundtrip(delivered, exported, manifest)
                self.assertEqual(result["status"], "valid")
                self.assertEqual(result["normalizations"][0]["rule"], "basic-title-colorsync-rgb")
                self.assertEqual(result["normalizations"][0]["before"], original)
                self.assertEqual(result["normalizations"][0]["after"], actual)
                self.assertEqual(before, (delivered.read_bytes(), exported.read_bytes()))

    def test_accepts_only_redundant_basic_title_default_selectors(self):
        with tempfile.TemporaryDirectory() as directory:
            delivered, exported, manifest = self.fixture(directory, defaults=True)
            self.rewrite(exported, remove_defaults=True)
            result = compare_roundtrip(delivered, exported, manifest)
            self.assertEqual(result["status"], "valid")
            self.assertEqual(len(result["normalizations"]), 3)
            self.assertEqual({n["rule"] for n in result["normalizations"]}, {"basic-title-default-selector"})

    def test_equivalent_color_number_spelling_is_audited_without_a_color_transform(self):
        with tempfile.TemporaryDirectory() as directory:
            delivered, exported, manifest = self.fixture(directory)
            self.rewrite(exported, color=("fontColor", "1.0 1.00 1 1.000"))
            with patch("scripts.fcpxml_text_style.generic_rgb_roundtrip", side_effect=AssertionError("unnecessary conversion")):
                result = compare_roundtrip(delivered, exported, manifest)
            self.assertEqual(result["normalizations"][0]["rule"], "text-color-number-spelling")

    def test_delivery_source_validation_does_not_use_roundtrip_normalization(self):
        from scripts.validate_fcpxml_package import _assert_source_sequence_unchanged
        with tempfile.TemporaryDirectory() as directory:
            delivered, exported, _ = self.fixture(directory, color=("strokeColor", "0 0.280365 0.2931 1"))
            original = ET.parse(delivered).getroot()
            _assert_source_sequence_unchanged(original, ET.parse(exported).getroot(), set())
            self.rewrite(exported, color=("strokeColor", "0.0357131 0.280287 0.293106 1"))
            with self.assertRaisesRegex(ValueError, "source sequence changed"):
                _assert_source_sequence_unchanged(original, ET.parse(exported).getroot(), set())

    def test_rejects_unknown_or_nondefault_parameter_removal_and_changed_actual_style(self):
        mutations = {
            "center selector": lambda title: title.find("param").set("value", "1 (Center)"),
            "unknown font selector": lambda title: title.findall("param")[-1].set("value", "2 0"),
            "animated selector": lambda title: ET.SubElement(title.find("param"), "keyframeAnimation"),
            "unknown selector": lambda title: title.find("param").set("key", "9999/unknown"),
            "font not explicit": lambda title: title.find("text-style-def/text-style").attrib.pop("font"),
            "centered text": lambda title: title.find("text-style-def/text-style").set("alignment", "center"),
            "right to left text": lambda title: setattr(title.find("text/text-style"), "text", "مرحبا"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                delivered, exported, manifest = self.fixture(directory, defaults=True)
                doc = ET.parse(delivered)
                mutate(doc.find(".//title[@name='Original title']"))
                doc.write(delivered)
                doc.write(exported)
                self.rewrite(exported, remove_defaults=True)
                with self.assertRaisesRegex(ValueError, "source storyline changed"):
                    compare_roundtrip(delivered, exported, manifest)

        for attribute, value in (("font", "Courier"), ("fontSize", "64"), ("alignment", "right")):
            with self.subTest(attribute=attribute), tempfile.TemporaryDirectory() as directory:
                delivered, exported, manifest = self.fixture(directory, defaults=True)
                doc = self.rewrite(exported, remove_defaults=True)
                doc.find(".//title/text-style-def/text-style").set(attribute, value)
                doc.write(exported)
                with self.assertRaisesRegex(ValueError, "source storyline changed"):
                    compare_roundtrip(delivered, exported, manifest)

    def test_compatibility_does_not_apply_to_custom_templates_or_unverified_xml_versions(self):
        for kind in ("template", "version"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                delivered, exported, manifest = self.fixture(directory, defaults=True)
                doc = ET.parse(delivered)
                if kind == "template":
                    doc.find("resources/effect[@id='basic']").set("uid", "/custom/Basic Title.moti")
                else:
                    doc.getroot().set("version", "1.13")
                doc.write(delivered)
                doc.write(exported)
                self.rewrite(exported, remove_defaults=True)
                with self.assertRaisesRegex(ValueError, "source storyline changed"):
                    compare_roundtrip(delivered, exported, manifest)

    def test_default_selector_compatibility_preserves_text_and_timeline_checks(self):
        mutations = {
            "text": lambda title: setattr(title.find("text/text-style"), "text", "Changed words"),
            "offset": lambda title: title.set("offset", "103s"),
            "duration": lambda title: title.set("duration", "2s"),
            "new parameter": lambda title: ET.SubElement(title, "param", {"key": "unexpected", "value": "1"}),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                delivered, exported, manifest = self.fixture(directory, defaults=True)
                doc = self.rewrite(exported, remove_defaults=True)
                mutate(doc.find(".//title[@name='Original title']"))
                doc.write(exported)
                with self.assertRaisesRegex(ValueError, "source storyline changed"):
                    compare_roundtrip(delivered, exported, manifest)

    @unittest.skipUnless(sys.platform == "darwin", "actual macOS ColorSync conversion")
    def test_rejects_color_edits_even_near_the_expected_conversion_and_alpha_changes(self):
        for color in ("0.0357141 0.280287 0.293106 1", "0.0357131 0.280287 0.293106 0.9", "0 0.3 0.3 1"):
            with self.subTest(color=color), tempfile.TemporaryDirectory() as directory:
                delivered, exported, manifest = self.fixture(directory, color=("strokeColor", "0 0.280365 0.2931 1"))
                self.rewrite(exported, color=("strokeColor", color))
                with self.assertRaisesRegex(ValueError, "source storyline changed"):
                    compare_roundtrip(delivered, exported, manifest)

    def test_missing_color_validation_environment_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            delivered, exported, manifest = self.fixture(directory, color=("strokeColor", "0 0.280365 0.2931 1"))
            self.rewrite(exported, color=("strokeColor", "0.0357131 0.280287 0.293106 1"))
            with patch("scripts.fcpxml_text_style.generic_rgb_roundtrip", side_effect=ValueError("ColorSync unavailable")):
                with self.assertRaisesRegex(ValueError, "ColorSync unavailable"):
                    compare_roundtrip(delivered, exported, manifest)
