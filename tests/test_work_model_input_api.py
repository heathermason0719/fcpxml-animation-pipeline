"""Regression coverage for public work-model intake request parameters."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


FCPXML = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<fcpxml version=\"1.11\"><resources><format id=\"r1\" frameDuration=\"1/25s\" width=\"1920\" height=\"1080\"/></resources>
<library><event><project name=\"{name}\"><sequence format=\"r1\" duration=\"8s\"><spine/></sequence></project></event></library></fcpxml>"""


class WorkModelInputApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.afterforge = Path(self.directory.name) / "AfterForge"
        self.input_directory = Path(self.directory.name) / "user-inbox" / "rough-cut-v1"
        self.input_directory.mkdir(parents=True)
        (self.input_directory / "alternate.fcpxml").write_text(
            FCPXML.format(name="备用"), encoding="utf-8"
        )
        self.selected_xml = self.input_directory / "current.fcpxml"
        self.selected_xml.write_text(FCPXML.format(name="当前"), encoding="utf-8")
        (self.input_directory / "alternate.mp4").write_bytes(b"alternate video")
        self.selected_video = self.input_directory / "current.mp4"
        self.selected_video.write_bytes(b"current video")

    def test_open_accepts_canonical_input_selection_with_multiple_candidates(self) -> None:
        """Catches an open path that ignores the documented inputSelection parameter."""
        root = self.open_with_selection(
            {"inputSelection": {"fcpxml": "current.fcpxml", "reference_video": "current.mp4"}}
        )
        self.assert_selected_source(root)

    def test_open_accepts_legacy_selections_alias_with_multiple_candidates(self) -> None:
        """Catches an open path that drops the supported selections alias."""
        root = self.open_with_selection(
            {"selections": {"fcpxml": "current.fcpxml", "reference_video": "current.mp4"}}
        )
        self.assert_selected_source(root)

    def test_open_accepts_equivalent_canonical_and_legacy_selections(self) -> None:
        """Catches rejecting two public names that identify the same complete selection."""
        root = self.open_with_selection(
            {
                "inputSelection": {"fcpxml": "./current.fcpxml", "reference_video": "current.mp4"},
                "selections": {
                    "fcpxml": str(self.selected_xml),
                    "reference_video": str(self.selected_video),
                },
            }
        )
        self.assert_selected_source(root)

    def test_open_rejects_conflicting_canonical_and_legacy_selections(self) -> None:
        """Catches choosing a side when the two public selection names disagree."""
        from scripts import work_model as model

        with patch(
            "scripts.validate_delivery.probe_delivery",
            return_value={"r_frame_rate": "25", "duration": "8"},
        ), self.assertRaisesRegex(ValueError, "conflict|冲突|inputSelection|selections"):
            model.open_project(
                self.afterforge,
                {
                    "requestId": "bind-conflict",
                    "expectedRevision": 0,
                    "title": "电影系列",
                    "episodeTitle": "输入选择",
                    "inputDirectory": str(self.input_directory),
                    "inputSelection": {"fcpxml": "current.fcpxml", "reference_video": "current.mp4"},
                    "selections": {"fcpxml": "alternate.fcpxml", "reference_video": "current.mp4"},
                },
            )

    def open_with_selection(self, selection: dict[str, object]) -> Path:
        from scripts import work_model as model

        with patch(
            "scripts.validate_delivery.probe_delivery",
            return_value={"r_frame_rate": "25", "duration": "8"},
        ):
            result = model.open_project(
                self.afterforge,
                {
                    "requestId": "bind-canonical",
                    "expectedRevision": 0,
                    "title": "电影系列",
                    "episodeTitle": "输入选择",
                    "inputDirectory": str(self.input_directory),
                    **selection,
                },
            )
        return Path(result["root"])

    def assert_selected_source(self, root: Path) -> None:
        self.assertIn('project name="当前"', (root / "assets/source/Info.fcpxml").read_text())
        self.assertEqual(
            (root / "assets/source/rough-cut.mp4").read_bytes(),
            self.selected_video.read_bytes(),
        )

    def test_normalize_input_selection_accepts_legacy_alias(self) -> None:
        """Catches removal of the existing public selections compatibility alias."""
        from scripts.intake_project import normalize_input_selection

        actual = normalize_input_selection(
            {
                "selections": {
                    "fcpxml": "current.fcpxml",
                    "reference_video": "current.mp4",
                }
            },
            self.input_directory,
        )

        self.assertEqual(
            actual,
            {
                "fcpxml": self.selected_xml.resolve(),
                "reference_video": self.selected_video.resolve(),
            },
        )

    def test_normalize_input_selection_requires_matching_values_when_both_names_are_present(self) -> None:
        """Catches choosing one public selection name when callers supply conflicting names."""
        from scripts.intake_project import normalize_input_selection

        same = normalize_input_selection(
            {
                "inputSelection": {"fcpxml": "./current.fcpxml"},
                "selections": {"fcpxml": self.selected_xml},
            },
            self.input_directory,
        )
        self.assertEqual(same, {"fcpxml": self.selected_xml.resolve()})
        with self.assertRaisesRegex(ValueError, "conflict|冲突|inputSelection|selections"):
            normalize_input_selection(
                {
                    "inputSelection": {"fcpxml": "current.fcpxml"},
                    "selections": {"fcpxml": "alternate.fcpxml"},
                },
                self.input_directory,
            )
        with self.assertRaisesRegex(ValueError, "conflict|冲突|inputSelection|selections"):
            normalize_input_selection(
                {
                    "inputSelection": {"fcpxml": "current.fcpxml"},
                    "selections": {"reference_video": "current.mp4"},
                },
                self.input_directory,
            )

    def test_normalize_input_selection_rejects_unknown_or_invalid_values(self) -> None:
        """Catches silently ignoring misspelled fields and paths outside the chosen input directory."""
        from scripts.intake_project import normalize_input_selection

        with self.assertRaisesRegex(ValueError, "unknown|未知|字段"):
            normalize_input_selection(
                {"inputSelection": {"video": "current.mp4"}}, self.input_directory
            )
        with self.assertRaisesRegex(ValueError, "input directory|输入目录|目录"):
            normalize_input_selection(
                {"inputSelection": {"fcpxml": "../outside.fcpxml"}}, self.input_directory
            )
        with self.assertRaisesRegex(ValueError, "path|路径"):
            normalize_input_selection(
                {"inputSelection": {"fcpxml": 42}}, self.input_directory
            )
