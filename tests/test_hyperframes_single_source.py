from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from scripts.assemble_hyperframes import assemble_hyperframes
    from scripts.layout_lock import freeze_layout, verify_layouts
    from scripts.sync_storyboard import sync_storyboard
    from scripts.validate_hyperframes_adapter import validate_project
    from scripts.migrate_single_source import migrate_version
except ModuleNotFoundError:
    assemble_hyperframes = None
    freeze_layout = None
    verify_layouts = None
    sync_storyboard = None
    validate_project = None
    migrate_version = None

try:
    from scripts.sync_delivery import sync_delivery
except ModuleNotFoundError:
    sync_delivery = None


GENERATED_MARKER = "generated-by: fcpxml-animation-pipeline sync_storyboard"


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def manifest_fixture() -> dict:
    return {
        "schemaVersion": "2.0",
        "sourceVersion": "2026-08-26_V1",
        "reviews": {
            "a11": {"status": "approved"},
            "a13": {"status": "pending"},
        },
        "project": {
            "name": "test",
            "source": {
                "width": 3840,
                "height": 2160,
                "frameDuration": "100/2400s",
                "frameRate": 24,
                "duration": "240/24s",
            },
            "preview": {"width": 854, "height": 480},
            "delivery": {"width": 1920, "height": 1080, "videoCodec": "prores-4444"},
            "creativeDirection": {
                "visualSpec": {
                    "canonical": "../frame.md",
                    "snapshot": "frame.md",
                    "snapshotSha256": "abc",
                },
                "motionDirection": {"character": "克制"},
            },
            "renderAdapters": {
                "hyperframes": {"previewMediaSrc": "assets/media/rough-cut.m4v"}
            },
        },
        "cues": [
            {
                "id": "p1s01_c01_title",
                "productionMode": "animation",
                "workflowState": "layout-built",
                "narrationAnchor": "测试旁白",
                "finalAnimationDescription": "标题居中落定并保持。",
                "resolvedTimeline": {"start": "24/24s", "duration": "48/24s", "authority": "fcpxml"},
                "designRoute": {
                    "functions": {"primary": "强调", "secondary": []},
                    "sourceRelationship": {"primary": "A-overlay-led", "secondary": None},
                    "referenceLanguages": {"primary": "字幕", "secondary": []},
                    "rationale": "测试",
                },
                "type": "title",
                "visualIntent": "显示标题",
                "screenText": ["标题"],
                "hierarchy": ["标题"],
                "composition": "居中",
                "motionIntent": "落定",
                "renderAdapters": {
                    "hyperframes": {
                        "compositionId": "p1s01-c01-title",
                        "compositionSrc": "compositions/cues/p1s01-c01-title.html",
                        "motionSrc": "compositions/motion/p1s01-c01-title.js",
                        "reviewSrc": "compositions/review/p1s01-c01-title.html",
                        "stillSrc": "assets/stills/cue-01.png",
                        "heroTime": 1.2,
                        "layoutDependencies": [
                            "compositions/cues/p1s01-c01-title.html",
                            "assets/styles/project-tokens.css",
                            "assets/fonts/test.woff2",
                        ],
                        "layoutLock": None,
                    }
                },
            },
            {
                "id": "p1s01_c02_hold",
                "productionMode": "source-only",
                "workflowState": "layout-approved",
                "narrationAnchor": "保留原画",
                "resolvedTimeline": {"start": "72/24s", "duration": "24/24s", "authority": "fcpxml"},
                "designRoute": {
                    "functions": {"primary": "保持原画", "secondary": []},
                    "sourceRelationship": {"primary": "B-source-led", "secondary": None},
                    "referenceLanguages": {"primary": None, "secondary": []},
                    "rationale": "测试",
                },
                "type": "no-animation",
                "visualIntent": "保留原画",
                "screenText": [],
                "hierarchy": ["原画"],
                "composition": "无包装",
                "motionIntent": "无",
                "renderAdapters": {
                    "hyperframes": {
                        "reviewSrc": "compositions/review/p1s01-c02-hold.html",
                        "stillSrc": "assets/stills/cue-02.png",
                        "heroTime": 0.1,
                    }
                },
            },
        ],
    }


class SingleSourceFixture(unittest.TestCase):
    def make_version(self, directory: str) -> Path:
        root = Path(directory)
        for relative in (
            "compositions/cues",
            "compositions/motion",
            "compositions/review",
            "compositions/delivery",
            "assets/fonts",
            "assets/media",
            "assets/stills",
            "assets/styles",
            "approvals/a11",
        ):
            (root / relative).mkdir(parents=True, exist_ok=True)
        (root / "frame.md").write_text("visual spec\n", encoding="utf-8")
        (root / "assets/media/rough-cut.m4v").write_bytes(b"video")
        (root / "assets/stills/cue-01.png").write_bytes(b"still one")
        (root / "assets/stills/cue-02.png").write_bytes(b"still two")
        (root / "assets/styles/project-tokens.css").write_text(":root { --ink: #fff; }\n", encoding="utf-8")
        (root / "assets/fonts/test.woff2").write_bytes(b"font")
        (root / "compositions/cues/p1s01-c01-title.html").write_text(
            """<!doctype html><html><body><template>
<style>@import url(\"assets/styles/project-tokens.css\"); #root{position:absolute;inset:0}</style>
<div id=\"root\" data-composition-id=\"p1s01-c01-title\" data-width=\"1920\" data-height=\"1080\" data-duration=\"2\"><div data-role=\"title\">标题</div></div>
<script src=\"compositions/motion/p1s01-c01-title.js\"></script>
</template></body></html>\n""",
            encoding="utf-8",
        )
        (root / "compositions/motion/p1s01-c01-title.js").write_text(
            "window.__timelines = window.__timelines || {};\n"
            "window.__timelines[\"p1s01-c01-title\"] = gsap.timeline({ paused: true });\n",
            encoding="utf-8",
        )
        write_json(
            root / "package.json",
            {
                "private": True,
                "scripts": {
                    name: f"npm exec --yes --package=hyperframes@0.8.26 -- hyperframes {command}"
                    for name, command in {
                        "dev": "preview",
                        "check": "check",
                        "render": "render",
                        "publish": "publish",
                    }.items()
                },
            },
        )
        write_json(
            root / "meta.json",
            {
                "id": "test-2026-08-26-v1",
                "version": "2026-08-26_V1",
                "toolchain": {
                    "hyperframes": {
                        "createdWithVersion": "0.8.26",
                        "migrations": [],
                    }
                },
            },
        )
        write_json(root / "animation-manifest.json", manifest_fixture())
        return root


class StoryboardSyncTests(SingleSourceFixture):
    def test_review_projection_mounts_canonical_composition_and_source_only_has_no_mount(self) -> None:
        self.assertIsNotNone(sync_storyboard, "sync_storyboard implementation is missing")
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_version(directory)
            cue_before = (root / "compositions/cues/p1s01-c01-title.html").read_bytes()

            result = sync_storyboard(root)

            self.assertEqual(result["status"], "synced")
            animated_review = (root / "compositions/review/p1s01-c01-title.html").read_text(encoding="utf-8")
            source_review = (root / "compositions/review/p1s01-c02-hold.html").read_text(encoding="utf-8")
            storyboard = (root / "STORYBOARD.md").read_text(encoding="utf-8")
            self.assertIn(GENERATED_MARKER, animated_review)
            self.assertIn('id="review-overlay-p1s01-c01-title"', animated_review)
            self.assertIn('data-composition-src="compositions/cues/p1s01-c01-title.html"', animated_review)
            self.assertIn('data-width="1920" data-height="1080"', animated_review)
            self.assertIn('scale(0.444791666667, 0.444444444444)', animated_review)
            self.assertIn('src="assets/stills/cue-01.png"', animated_review)
            self.assertNotIn("data-composition-src", source_review)
            self.assertIn("- src: compositions/review/p1s01-c01-title.html", storyboard)
            self.assertIn("- poster: 1.2s", storyboard)
            self.assertEqual((root / "compositions/cues/p1s01-c01-title.html").read_bytes(), cue_before)

    def test_refuses_to_overwrite_handwritten_review_file(self) -> None:
        self.assertIsNotNone(sync_storyboard, "sync_storyboard implementation is missing")
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_version(directory)
            review = root / "compositions/review/p1s01-c01-title.html"
            review.write_text("hand written\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "generated review"):
                sync_storyboard(root)

            self.assertEqual(review.read_text(encoding="utf-8"), "hand written\n")


class AssemblyTests(SingleSourceFixture):
    def test_preview_mounts_canonical_cue_and_skips_source_only(self) -> None:
        self.assertIsNotNone(assemble_hyperframes, "assemble_hyperframes implementation is missing")
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_version(directory)

            result = assemble_hyperframes(root)

            self.assertEqual(result["animatedCueIds"], ["p1s01_c01_title"])
            self.assertEqual(result["skippedCueIds"], ["p1s01_c02_hold"])
            index = (root / "index.html").read_text(encoding="utf-8")
            self.assertIn('data-composition-src="compositions/cues/p1s01-c01-title.html"', index)
            self.assertIn('data-width="1920" data-height="1080"', index)
            self.assertIn('scale(0.444791666667, 0.444444444444)', index)
            self.assertNotIn("p1s01-c02-hold", index)
            self.assertIn('data-start="1"', index)
            self.assertIn('data-duration="2"', index)


class DeliveryProjectionTests(SingleSourceFixture):
    def test_delivery_projection_mounts_each_animation_at_native_delivery_dimensions(self) -> None:
        self.assertIsNotNone(sync_delivery, "sync_delivery implementation is missing")
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_version(directory)

            result = sync_delivery(root)

            self.assertEqual(result["animatedCueIds"], ["p1s01_c01_title"])
            self.assertEqual(result["skippedCueIds"], ["p1s01_c02_hold"])
            delivery = (root / "compositions/delivery/p1s01-c01-title.html").read_text(encoding="utf-8")
            self.assertIn('data-composition-id="delivery-p1s01-c01-title"', delivery)
            self.assertIn('data-width="1920" data-height="1080"', delivery)
            self.assertIn('id="delivery-host-p1s01-c01-title"', delivery)
            self.assertIn('data-composition-src="compositions/cues/p1s01-c01-title.html"', delivery)
            self.assertFalse((root / "compositions/delivery/p1s01-c02-hold.html").exists())


class LayoutLockTests(SingleSourceFixture):
    def test_cli_does_not_offer_legacy_a11_approval(self) -> None:
        script = Path(__file__).resolve().parents[1] / "scripts/layout_lock.py"
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertNotIn("approve", result.stdout)

    def test_freeze_and_verify_cover_all_storyboard_review_frames(self) -> None:
        self.assertIsNotNone(sync_storyboard, "sync_storyboard implementation is missing")
        self.assertIsNotNone(freeze_layout, "layout_lock implementation is missing")
        self.assertIsNotNone(verify_layouts, "layout_lock implementation is missing")
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_version(directory)
            sync_storyboard(root)
            hero = root / "hero.png"
            cinema = root / "cinema.png"
            interview = root / "interview.png"
            hero.write_bytes(b"surveillance")
            cinema.write_bytes(b"cinema")
            interview.write_bytes(b"interview")

            freeze_layout(
                root,
                "p1s01_c01_title",
                hero,
                hero_id="surveillance",
                hero_label="最终监控框",
                auxiliary_frames=[
                    ("cinema", "电影院宽银幕", cinema),
                    ("interview", "电视访谈技术框", interview),
                ],
            )
            manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
            lock = manifest["cues"][0]["renderAdapters"]["hyperframes"]["layoutLock"]

            self.assertEqual(
                [(frame["id"], frame["role"], frame["label"]) for frame in lock["reviewFrames"]],
                [
                    ("surveillance", "hero", "最终监控框"),
                    ("cinema", "auxiliary", "电影院宽银幕"),
                    ("interview", "auxiliary", "电视访谈技术框"),
                ],
            )
            self.assertEqual(len(lock["reviewFrameSetSha256"]), 64)
            self.assertEqual(lock["runtimeVersion"], "0.8.26")
            self.assertEqual(verify_layouts(root)["status"], "valid")

            (root / lock["reviewFrames"][1]["path"]).write_bytes(b"changed cinema")
            changed = verify_layouts(root)

            self.assertEqual(changed["status"], "invalid")
            self.assertEqual(changed["invalidCueIds"], ["p1s01_c01_title"])

    def test_runtime_pin_change_invalidates_layout_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_version(directory)
            sync_storyboard(root)
            poster = root / "approved.png"
            poster.write_bytes(b"approved under 0.8.26")
            freeze_layout(root, "p1s01_c01_title", poster)
            package = root / "package.json"
            package.write_text(
                package.read_text(encoding="utf-8").replace("hyperframes@0.8.26", "hyperframes@0.8.27"),
                encoding="utf-8",
            )

            changed = verify_layouts(root)

            self.assertEqual(changed["status"], "invalid")
            self.assertEqual(changed["invalidCueIds"], ["p1s01_c01_title"])
            self.assertEqual(changed["details"][0]["error"], "runtime pin changed from 0.8.26 to 0.8.27")

    def test_freeze_increments_preserved_revision_after_lock_invalidation(self) -> None:
        self.assertIsNotNone(sync_storyboard, "sync_storyboard implementation is missing")
        self.assertIsNotNone(freeze_layout, "layout_lock implementation is missing")
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_version(directory)
            manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
            adapter = manifest["cues"][0]["renderAdapters"]["hyperframes"]
            adapter["layoutRevision"] = 1
            write_json(root / "animation-manifest.json", manifest)
            sync_storyboard(root)
            poster = root / "approved.png"
            poster.write_bytes(b"approved revision two")

            result = freeze_layout(root, "p1s01_c01_title", poster)

            self.assertEqual(result["revision"], 2)
            updated = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
            updated_adapter = updated["cues"][0]["renderAdapters"]["hyperframes"]
            self.assertEqual(updated_adapter["layoutRevision"], 2)
            self.assertEqual(updated_adapter["layoutLock"]["revision"], 2)

    def test_freeze_then_verify_detects_review_projection_change(self) -> None:
        self.assertIsNotNone(sync_storyboard, "sync_storyboard implementation is missing")
        self.assertIsNotNone(freeze_layout, "layout_lock implementation is missing")
        self.assertIsNotNone(verify_layouts, "layout_lock implementation is missing")
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_version(directory)
            sync_storyboard(root)
            poster = root / "approved.png"
            poster.write_bytes(b"approved hero")

            freeze_layout(root, "p1s01_c01_title", poster)
            review = root / "compositions/review/p1s01-c01-title.html"
            review.write_text(review.read_text(encoding="utf-8") + "<!-- changed -->\n", encoding="utf-8")
            changed = verify_layouts(root)

            self.assertEqual(changed["status"], "invalid")
            self.assertEqual(changed["invalidCueIds"], ["p1s01_c01_title"])

    def test_freeze_then_verify_detects_layout_dependency_change(self) -> None:
        self.assertIsNotNone(freeze_layout, "layout_lock implementation is missing")
        self.assertIsNotNone(verify_layouts, "layout_lock implementation is missing")
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_version(directory)
            manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
            manifest["reviews"]["a11"] = {"status": "pending"}
            write_json(root / "animation-manifest.json", manifest)
            sync_storyboard(root)
            poster = root / "approved.png"
            poster.write_bytes(b"approved hero")

            freeze = freeze_layout(root, "p1s01_c01_title", poster)
            clean = verify_layouts(root)
            (root / "assets/styles/project-tokens.css").write_text(":root { --ink: #000; }\n", encoding="utf-8")
            changed = verify_layouts(root)

            self.assertEqual(freeze["status"], "frozen")
            self.assertEqual(clean["status"], "valid")
            self.assertEqual(changed["status"], "invalid")
            self.assertEqual(changed["invalidCueIds"], ["p1s01_c01_title"])
            saved = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
            cue = saved["cues"][0]
            lock = cue["renderAdapters"]["hyperframes"]["layoutLock"]
            self.assertEqual(saved["reviews"]["a11"]["status"], "approved")
            self.assertEqual(saved["reviews"]["a11"]["approvedCueIds"], ["p1s01_c01_title"])
            self.assertEqual(cue["workflowState"], "layout-approved")
            self.assertEqual(lock["revision"], 1)
            self.assertTrue((root / lock["approvedPoster"]).is_file())


class AdapterValidationTests(SingleSourceFixture):
    def test_validation_rejects_canonical_dimensions_that_do_not_match_delivery(self) -> None:
        self.assertIsNotNone(sync_storyboard, "sync_storyboard implementation is missing")
        self.assertIsNotNone(assemble_hyperframes, "assemble_hyperframes implementation is missing")
        self.assertIsNotNone(validate_project, "validator implementation is missing")
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_version(directory)
            composition = root / "compositions/cues/p1s01-c01-title.html"
            composition.write_text(
                composition.read_text(encoding="utf-8")
                .replace('data-width="1920"', 'data-width="854"')
                .replace('data-height="1080"', 'data-height="480"'),
                encoding="utf-8",
            )
            sync_storyboard(root)
            assemble_hyperframes(root)

            result = validate_project(root)

            self.assertEqual(result["status"], "invalid")
            self.assertIn(
                "composition_dimensions_mismatch",
                [finding["code"] for finding in result["findings"]],
            )

    def test_validation_accepts_single_source_project_and_rejects_layout_motion(self) -> None:
        self.assertIsNotNone(sync_storyboard, "sync_storyboard implementation is missing")
        self.assertIsNotNone(assemble_hyperframes, "assemble_hyperframes implementation is missing")
        self.assertIsNotNone(validate_project, "validator implementation is missing")
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_version(directory)
            sync_storyboard(root)
            assemble_hyperframes(root)

            valid = validate_project(root)
            (root / "compositions/motion/p1s01-c01-title.js").write_text(
                "window.__timelines[\"p1s01-c01-title\"] = gsap.timeline({ paused: true }).to(\"[data-role=title]\", { left: 10 });\n",
                encoding="utf-8",
            )
            invalid = validate_project(root)

            self.assertEqual(valid["status"], "valid")
            self.assertEqual(invalid["status"], "invalid")
            self.assertIn("motion_layout_property", [finding["code"] for finding in invalid["findings"]])


class LegacyMigrationTests(unittest.TestCase):
    def test_migration_splits_latest_animation_without_modifying_legacy_files(self) -> None:
        self.assertIsNotNone(migrate_version, "migration implementation is missing")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in ("compositions/frames", "compositions/animation", "assets/stills", "assets/fonts", "assets/media"):
                (root / relative).mkdir(parents=True, exist_ok=True)
            legacy_animation = """<template>
<style>#root{position:absolute;inset:0}</style>
<div id=\"root\" data-composition-id=\"anim-cue-one\" data-width=\"854\" data-height=\"480\" data-duration=\"2\"><div data-role=\"title\">标题</div></div>
<script>window.__timelines[\"anim-cue-one\"] = gsap.timeline({ paused: true }).fromTo(\"[data-role=title]\", {opacity:0}, {opacity:1,duration:.5});</script>
</template>\n"""
            animation_path = root / "compositions/animation/cue-one.html"
            animation_path.write_text(legacy_animation, encoding="utf-8")
            frame_path = root / "compositions/frames/cue-one.html"
            frame_path.write_text("legacy frame\n", encoding="utf-8")
            hold_path = root / "compositions/frames/cue-two.html"
            hold_path.write_text("legacy hold\n", encoding="utf-8")
            (root / "assets/stills/cue-01.png").write_bytes(b"one")
            (root / "assets/stills/cue-02.png").write_bytes(b"two")
            (root / "assets/fonts/font.woff2").write_bytes(b"font")
            (root / "assets/media/rough-cut.m4v").write_bytes(b"video")
            (root / "assets/storyboard.css").write_text("#root{}\n", encoding="utf-8")
            legacy_manifest = {
                "schemaVersion": "draft-v0.2",
                "sourceVersion": "2026-08-26_V1",
                "reviewStatus": "pending-a13",
                "a12Review": {"preview": "previews/review.mp4"},
                "project": {
                    "name": "test",
                    "source": {"width": 3840, "height": 2160, "frameDuration": "100/2400s", "frameRate": 24, "duration": "96/24s"},
                    "preview": {"width": 854, "height": 480},
                    "delivery": {"width": 1920, "height": 1080, "videoCodec": "prores-4444"},
                    "creativeDirection": {"visualSpec": {}, "motionDirection": {}},
                },
                "cues": [
                    {
                        "id": "cue_one",
                        "type": "title",
                        "narrationAnchor": "one",
                        "resolvedTimeline": {"start": "0/24s", "duration": "48/24s", "authority": "fcpxml"},
                        "designRoute": {"functions": {"primary": "强调"}, "sourceRelationship": {"primary": "A"}, "referenceLanguages": {"primary": "字幕"}, "rationale": "one"},
                        "screenText": ["标题"], "composition": "居中", "motionIntent": "出现",
                        "storyboard": {"src": "compositions/frames/cue-one.html", "still": "assets/stills/cue-01.png", "poster": 0.1},
                        "reviewStatus": "approved-a11",
                    },
                    {
                        "id": "cue_two",
                        "type": "no-animation",
                        "narrationAnchor": "two",
                        "resolvedTimeline": {"start": "48/24s", "duration": "48/24s", "authority": "fcpxml"},
                        "designRoute": {"functions": {"primary": "保持原画"}, "sourceRelationship": {"primary": "B"}, "referenceLanguages": {"primary": None}, "rationale": "two"},
                        "screenText": [], "composition": "无", "motionIntent": "无",
                        "storyboard": {"src": "compositions/frames/cue-two.html", "still": "assets/stills/cue-02.png", "poster": 0.1},
                        "reviewStatus": "approved-a11",
                    },
                ],
            }
            write_json(root / "animation-manifest.json", legacy_manifest)
            (root / "STORYBOARD.md").write_text("---\nmessage: \"test message\"\narc: \"one to two\"\naudience: \"viewer\"\n---\n", encoding="utf-8")
            animation_before = animation_path.read_bytes()
            frame_before = frame_path.read_bytes()

            result = migrate_version(root, {"cue_one": 0.8})

            self.assertEqual(result["status"], "migrated")
            self.assertEqual(animation_path.read_bytes(), animation_before)
            self.assertEqual(frame_path.read_bytes(), frame_before)
            canonical = (root / "compositions/cues/cue-one.html").read_text(encoding="utf-8")
            motion = (root / "compositions/motion/cue-one.js").read_text(encoding="utf-8")
            self.assertNotIn("gsap.timeline", canonical)
            self.assertIn('<script src="compositions/motion/cue-one.js"></script>', canonical)
            self.assertIn('window.__timelines["anim-cue-one"]', motion)
            self.assertTrue(motion.startswith("(() => {\n"))
            self.assertTrue(motion.endswith("})();\n"))
            migrated = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(migrated["schemaVersion"], "2.0")
            self.assertEqual(migrated["project"]["message"], "test message")
            self.assertEqual(migrated["cues"][0]["productionMode"], "animation")
            self.assertEqual(migrated["cues"][0]["workflowState"], "motion-built")
            self.assertEqual(migrated["cues"][0]["renderAdapters"]["hyperframes"]["heroTime"], 0.8)
            self.assertEqual(migrated["cues"][1]["productionMode"], "source-only")
            self.assertFalse((root / "compositions/cues/cue-two.html").exists())
            self.assertIn("compositions/cues/cue-one.html", (root / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
