"""Narrow, auditable Basic Title normalization for FCPXML 1.14 round-trips.

This is not used when generating or validating a delivery against its source.
The two real, unedited FCP exports and macOS ColorSync reproduce these rules.
Unknown templates, versions, selectors and changed effective styles stay strict.
"""
from __future__ import annotations

import ctypes
import re
import sys
import unicodedata
from fractions import Fraction
from functools import lru_cache


BASIC_TITLE = ".../Titles.localized/Bumper:Opener.localized/Basic Title.localized/Basic Title.moti"
PROFILE = "fcpxml-1.14-basic-title-v1"
_ALIGNMENT_KEY = re.compile(r"9999/999166631/999166633/2/354/[0-9]+/401")
_FONT_KEY = "9999/999166631/999166633/5/999166635/83"


@lru_cache(maxsize=1)
def _core_graphics():
    if sys.platform != "darwin":
        raise ValueError("macOS ColorSync is required to verify FCP text color normalization")
    try:
        cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        pointer, component = ctypes.c_void_p, ctypes.c_double
        signatures = {
            "CGColorSpaceCreateWithName": (pointer, [pointer]),
            "CGColorCreate": (pointer, [pointer, ctypes.POINTER(component)]),
            "CGColorCreateCopyByMatchingToColorSpace": (pointer, [pointer, ctypes.c_int, pointer, pointer]),
            "CGColorGetComponents": (ctypes.POINTER(component), [pointer]),
            "CGColorGetNumberOfComponents": (ctypes.c_size_t, [pointer]),
            "CGColorRelease": (None, [pointer]),
            "CGColorSpaceRelease": (None, [pointer]),
        }
        for name, (result, arguments) in signatures.items():
            function = getattr(cg, name)
            function.restype, function.argtypes = result, arguments
        return cg
    except (OSError, AttributeError) as error:
        raise ValueError("macOS ColorSync is unavailable for FCP text color verification") from error


def generic_rgb_roundtrip(components):
    """Use the OS color engine, not a guessed RGB tolerance or project palette."""
    cg = _core_graphics()
    spaces, colors = [], []
    try:
        for name in ("kCGColorSpaceGenericRGB", "kCGColorSpaceSRGB"):
            space = cg.CGColorSpaceCreateWithName(ctypes.c_void_p.in_dll(cg, name))
            if not space:
                raise ValueError("ColorSync could not create the required RGB color space")
            spaces.append(space)
        color = cg.CGColorCreate(spaces[0], (ctypes.c_double * 4)(*components))
        if not color:
            raise ValueError("ColorSync could not create the source color")
        colors.append(color)
        # FCP imports Generic RGB text colors into sRGB and exports Generic RGB.
        # Gamut clipping can change a zero component. Raw epsilon comparisons
        # would either reject that round-trip or accept unrelated color edits.
        for space in (spaces[1], spaces[0]):
            color = cg.CGColorCreateCopyByMatchingToColorSpace(space, 0, color, None)
            if not color or cg.CGColorGetNumberOfComponents(color) != 4:
                if color:
                    cg.CGColorRelease(color)
                raise ValueError("ColorSync could not verify the FCP color conversion")
            colors.append(color)
        return tuple(cg.CGColorGetComponents(color)[:4])
    finally:
        for color in reversed(colors):
            cg.CGColorRelease(color)
        for space in reversed(spaces):
            cg.CGColorSpaceRelease(space)


def _rgba(value):
    try:
        values = tuple(Fraction(part) for part in value.split())
    except (AttributeError, ValueError, ZeroDivisionError):
        return None
    return values if len(values) == 4 and all(0 <= part <= 1 for part in values) else None


def _explicit_style_runs(title):
    """Resolve local text-style-def references; never assume a missing font."""
    definitions = {}
    for definition in title.findall("text-style-def"):
        if not definition.get("id") or definition.get("id") in definitions or len(definition) != 1:
            return None
        style = definition[0]
        if style.tag != "text-style" or len(style) or style.get("ref"):
            return None
        definitions[definition.get("id")] = style.attrib
    resolved = []
    for text in title.findall("text"):
        if text.text and text.text.strip():
            return None
        for run in text:
            if run.tag != "text-style" or len(run) or (run.tail and run.tail.strip()):
                return None
            reference = run.get("ref")
            if reference and reference not in definitions:
                return None
            style = {**definitions.get(reference, {}), **run.attrib}
            style.pop("ref", None)
            if any(not style.get(key) for key in ("font", "fontFace", "fontSize")):
                return None
            resolved.append((run.text or "", style))
    return resolved or None


def _left_to_right(runs):
    text = "".join(content for content, _ in runs)
    # Missing alignment uses natural alignment. Only the observed LTR case is
    # supported; RTL, bidi controls and directionless text are not generalized.
    directions = {unicodedata.bidirectional(character) for character in text}
    return "L" in directions and not directions.intersection({"R", "AL", "RLE", "RLO", "LRE", "LRO", "RLI", "LRI", "FSI", "PDI", "PDF"})


class TextStyleNormalization:
    def __init__(self, delivered_root, reexported_root):
        self.enabled = delivered_root.get("version") == reexported_root.get("version") == "1.14"
        self.records = []
        self.colors = {}

    def is_basic_title(self, left, right, left_resources, right_resources):
        identity = ("effect", "uid", BASIC_TITLE)
        return (self.enabled and left.tag == right.tag == "title"
                and left_resources.get(left.get("ref")) == right_resources.get(right.get("ref")) == identity)

    def color_equal(self, attribute, before, after, path):
        if attribute not in {"fontColor", "strokeColor"}:
            return False
        left, right = _rgba(before), _rgba(after)
        if left is None or right is None or left[3] != right[3]:
            return False
        if left == right:
            self.records.append({"rule": "text-color-number-spelling", "path": path,
                                 "attribute": attribute, "before": before, "after": after})
            return True
        if left not in self.colors:
            self.colors[left] = generic_rgb_roundtrip(tuple(float(value) for value in left))
        converted = self.colors[left]
        # The observed FCP serializer writes six significant digits. Compare
        # exact decimal values after that serialization; no perceptual epsilon.
        expected = tuple(Fraction(format(value, ".6g")) for value in converted[:3])
        if right[:3] != expected:
            return False
        self.records.append({"rule": "basic-title-colorsync-rgb", "path": path,
                             "attribute": attribute, "before": before, "after": after,
                             "transform": "Generic RGB -> sRGB -> Generic RGB",
                             "serializedRgb": [format(value, ".6g") for value in converted[:3]]})
        return True

    def children(self, left, right, path):
        """Omit only FCP's redundant default selectors on unchanged rich text."""
        left_runs, right_runs = _explicit_style_runs(left), _explicit_style_runs(right)
        if not left_runs or left_runs != right_runs or not _left_to_right(left_runs):
            return list(left)
        if any(style.get("alignment", "left") != "left" for _, style in left_runs):
            return list(left)
        right_keys = {item.get("key") for item in right.findall("param")}
        left_keys = [item.get("key") for item in left.findall("param")]
        if len(set(left_keys)) != len(left_keys):
            return list(left)
        children = []
        for item in left:
            key, value = item.get("key", ""), item.get("value", "")
            removable = (item.tag == "param" and key not in right_keys and not len(item)
                         and not (item.text or "").strip() and set(item.attrib) <= {"name", "key", "value"}
                         and ((_ALIGNMENT_KEY.fullmatch(key) and re.fullmatch(r"0(?: \([^()]*\))?", value))
                              or (key == _FONT_KEY and value == "1 0")))
            if removable:
                self.records.append({"rule": "basic-title-default-selector", "path": path,
                                     "parameter": dict(item.attrib), "effectiveAlignment": "left",
                                     "effectiveFonts": sorted({style["font"] for _, style in left_runs})})
            else:
                children.append(item)
        return children
