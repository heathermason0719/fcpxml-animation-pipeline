"""Focused facts for Cue narration and on-screen-copy declarations."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts import work_model as model
from scripts.work_model_store import load
from tests import test_work_model_jobs as jobs
from tests.work_model_fixtures import raster, user


class ContentContextTests(unittest.TestCase):
    def test_absent_declarations_derive_present_only_from_real_linked_content(self):
        from scripts.work_model_content import content_context

        manifest = {"brief": {"segments": [
            {"id": "voice", "narration": "关联旁白"},
        ]}}
        cue = {"id": "cue", "segmentIds": ["voice"],
               "screenText": [{"text": "屏幕标题"}]}

        self.assertEqual(content_context(manifest, cue), {
            "narration": {"state": "present", "text": "关联旁白"},
            "screenText": {"state": "present", "text": "屏幕标题"},
        })

    def test_unknown_channel_still_blocks_when_the_other_channel_has_text(self):
        from scripts.work_model_content import content_context, content_problems

        manifest = {"brief": {"segments": []}}
        cue = {
            "id": "cue", "screenText": ["可见标题"],
            "contentContext": {
                "narration": {"state": "unknown"},
                "screenText": {"state": "present"},
            },
        }

        self.assertEqual(content_context(manifest, cue)["narration"], {"state": "unknown"})
        self.assertEqual(
            [problem["code"] for problem in content_problems(manifest, cue)],
            ["unknown-narration-content"],
        )

    def test_pure_visual_with_two_evidenced_none_facts_is_complete(self):
        from scripts.work_model_content import content_context, content_problems

        manifest = {"brief": {"segments": []}}
        cue = {
            "id": "pure-visual",
            "contentContext": {
                "narration": {"state": "none", "basis": {
                    "text": "用户明确此 Cue 没有对应旁白", "reference": "turn:visual"}},
                "screenText": {"state": "none", "basis": {
                    "text": "用户明确画面不显示文字", "reference": "turn:visual"}},
            },
        }

        self.assertEqual(content_context(manifest, cue), cue["contentContext"])
        self.assertEqual(content_problems(manifest, cue), [])

    def test_declarations_reject_missing_evidence_and_conflicting_or_missing_text(self):
        from scripts.work_model_content import validate_content_declarations

        manifest = {"brief": {"segments": []}}
        cases = [
            ({"contentContext": {"narration": {"state": "none"},
                                  "screenText": {"state": "unknown"}}},
             "none-content-requires-basis"),
            ({"narration": "实际旁白", "contentContext": {
                "narration": {"state": "none", "basis": {"text": "错误", "reference": "turn"}},
                "screenText": {"state": "unknown"}}},
             "none-narration-conflicts-with-text"),
            ({"contentContext": {"narration": {"state": "present"},
                                  "screenText": {"state": "unknown"}}},
             "present-narration-requires-text"),
            ({"contentContext": {"narration": {"state": "unknown", "basis": {"text": "why"}},
                                  "screenText": {"state": "unknown"}}},
             "invalid-content-basis"),
        ]
        for cue, expected in cases:
            with self.subTest(expected=expected):
                self.assertIn(expected, [item["code"] for item in validate_content_declarations(manifest, cue)])


class ContentContextPublicIntegrationTests(unittest.TestCase):
    """Exercise declaration checks at the public writer and confirmation path."""

    cold_start = True
    setUp = jobs.JobTests.setUp
    req = jobs.JobTests.req

    @staticmethod
    def _none(text, reference):
        return {"state": "none", "basis": {"text": text, "reference": reference}}

    def _board(self):
        model.update(self.root, self.req("enrol", operation="edit", patch={}))
        with patch("scripts.work_model_jobs.render_storyboard", side_effect=raster):
            result = model.preview(self.root, self.req("board", scope="storyboard"))
        manifest = load(self.root)
        return manifest, [next(item for item in manifest["storyboards"] if item["id"] == key)
                          for key in result["storyboardIds"]]

    def test_public_writer_rejects_a_none_fact_that_conflicts_with_actual_copy(self):
        manifest = load(self.root)
        cue = manifest["cues"][0]
        cue["contentContext"] = {
            "narration": {"state": "present"},
            "screenText": self._none("fixture incorrectly claims no title", "fixture:conflict"),
        }

        with self.assertRaisesRegex(ValueError, "content|text|内容"):
            model.update(self.root, self.req("reject-conflicting-none", operation="edit",
                                              patch={"cues": manifest["cues"]}))

    def test_unknown_narration_blocks_confirmation_despite_actual_screen_copy(self):
        manifest = load(self.root)
        cue = manifest["cues"][0]
        cue.pop("narration", None)
        cue.pop("narrationAnchor", None)
        cue["contentContext"] = {
            "narration": {"state": "unknown"},
            "screenText": {"state": "present"},
        }
        model.update(self.root, self.req("unknown-narration", operation="edit",
                                          patch={"cues": manifest["cues"]}))
        _, boards = self._board()

        card = next(item for item in model.status(self.root)["storyboard"]["cues"]
                    if item["id"] == cue["id"])
        self.assertIn("unknown-narration-content",
                      [problem["code"] for problem in card["confirmationProblems"]])
        with self.assertRaisesRegex(ValueError, "content|confirmation|内容"):
            model.update(self.root, self.req("reject-unknown", operation="decision", kind="confirm-design",
                                              storyboardIds=[boards[0]["id"]],
                                              source=user("确认未知旁白的设计", "fixture:unknown")))

    def test_explicit_visual_only_facts_allow_confirmation_and_no_narration_input(self):
        manifest = load(self.root)
        for cue in manifest["cues"]:
            cue.pop("narration", None)
            cue.pop("narrationAnchor", None)
            cue["screenText"] = []
            cue["contentContext"] = {
                "narration": self._none("fixture 是纯视觉 Cue，没有对应旁白", "fixture:visual-only"),
                "screenText": self._none("fixture 是纯视觉 Cue，没有屏幕文字", "fixture:visual-only"),
            }
        model.update(self.root, self.req("visual-only", operation="edit", patch={"cues": manifest["cues"]}))
        manifest, boards = self._board()
        self.assertFalse(any(item["confirmationProblems"] for item in model.status(self.root)["storyboard"]["cues"]))
        model.update(self.root, self.req("confirm-visual-only", operation="decision", kind="confirm-design",
                                          storyboardIds=[board["id"] for board in boards],
                                          source=user("确认纯视觉设计", "fixture:visual-only")))

        from scripts.work_model_inputs import source_paths
        self.assertEqual(len(source_paths(self.root, load(self.root))), 2)
