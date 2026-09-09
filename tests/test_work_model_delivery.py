"""Schema-3 immutable release package backend."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from scripts.work_model_delivery import prepare_release, publish_release, verify_release


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


SOURCE = b'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.10"><resources><format id="r1" name="FFVideoFormat1080p24" frameDuration="1/24s" width="1920" height="1080"/></resources><library><event name="Source"><project name="Cut"><sequence duration="4s" format="r1"><spine><gap name="base" offset="0s" start="0s" duration="4s"/></spine></sequence></project></event></library></fcpxml>\n'''


class WorkModelDeliveryTests(unittest.TestCase):
    def make_inputs(self, directory: str) -> tuple[Path, Path, dict]:
        afterforge = Path(directory) / "AfterForge"
        afterforge.mkdir()
        root = afterforge / "工程" / "episodes" / "ep-01" / "v3"
        root.mkdir(parents=True)
        (afterforge / "工程" / "project.json").write_text(json.dumps({
            "schemaVersion": "2.0", "episodes": [{"id": "ep-01", "versions": [
                {"root": "工程/episodes/ep-01/v3"}
            ]}],
        }), encoding="utf-8")
        source = root / "source.fcpxml"
        source.write_bytes(SOURCE)
        movie = root / "renders" / "cue.mov"
        movie.parent.mkdir()
        movie.write_bytes(b"mov bytes")
        font = root / "fonts" / "face.otf"
        font.parent.mkdir()
        font.write_bytes(b"font bytes")
        manifest = {
            "schemaVersion": "3.0",
            "identity": {
                "projectId": "project-01", "episodeId": "ep-01", "versionId": "v3",
                "episodeTitle": "Episode / One", "versionTitle": "Cut three",
            },
            "sourceVersion": "2026-09-09_v3", "editRevision": 0,
            "sourceHashes": {"fcpxml": sha256(source)},
            "project": {
                "source": {"fcpxml": "source.fcpxml", "frameDuration": "1/24s"},
                "preview": {"width": 854, "height": 480},
                "delivery": {"width": 1920, "height": 1080},
            },
            "cues": [{
                "id": "cue_one", "productionMode": "animation",
                "resolvedTimeline": {"start": "1s", "duration": "2s"}, "layer": 4,
                "deliveryAsset": {"fileName": "AF__cue.mov", "relativePath": "renders/cue.mov",
                                  "width": 1920, "height": 1080, "frameRate": "24", "duration": "2s",
                                  "sha256": sha256(movie)},
            }],
        }
        return root, afterforge, manifest

    def test_prepares_publishes_and_verifies_immutable_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, afterforge, manifest = self.make_inputs(directory)
            input_root = Path(directory) / "frozen-input"
            for relative in ("source.fcpxml", "renders/cue.mov", "fonts/face.otf"):
                source = root / relative
                target = input_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                source.write_bytes(b"live data changed after input snapshot")
            prepared = prepare_release(
                root, manifest, afterforge_root=afterforge, release_id="d0001",
                input_key="input-abc", dependency_paths=["fonts/face.otf"], input_root=input_root,
            )
            self.assertTrue(Path(prepared["stagingPackage"]).is_dir())
            self.assertEqual(prepared["packagePath"], "交付/Episode-One--ep-01/交付0001/Episode-One.fcpxmld")
            self.assertEqual(prepared["snapshotPath"], "releases/d0001")
            frozen = prepared["manifest"]
            self.assertEqual(frozen["delivery"]["identity"], "AfterForge__project-01__ep-01__v3__d0001")
            self.assertEqual(frozen["delivery"]["protocolVersion"], "2")
            self.assertEqual(frozen["project"]["source"]["fcpxml"], "source/source.fcpxml")
            self.assertEqual(frozen["cues"][0]["deliveryAsset"]["relativePath"], "delivery-assets/AF__cue.mov")
            self.assertNotEqual((Path(prepared["stagingSnapshot"]) / "delivery-assets" / "AF__cue.mov").stat().st_ino,
                                (root / "renders" / "cue.mov").stat().st_ino)
            self.assertEqual((Path(prepared["stagingSnapshot"]) / "files/fonts/face.otf").read_bytes(), b"font bytes")
            staged_root = ET.parse(Path(prepared["stagingPackage"]) / "Info.fcpxml").getroot()
            anchor = next(item for item in staged_root.iter("asset-clip") if item.get("name") == "AF__cue_one")
            self.assertEqual(anchor.get("lane"), "4")

            record = publish_release(root, prepared)
            self.assertEqual(record["id"], "d0001")
            self.assertEqual(record["media"], [{"cueId": "cue_one", "path": "releases/d0001/delivery-assets/AF__cue.mov"}])
            self.assertTrue(verify_release(root, afterforge, record))
            self.assertTrue((afterforge / record["packagePath"] / "Info.fcpxml").is_file())
            self.assertTrue((root / record["snapshotPath"] / record["manifestPath"]).is_file())

    def test_verify_rejects_extra_or_symlinked_member(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, afterforge, manifest = self.make_inputs(directory)
            prepared = prepare_release(root, manifest, afterforge_root=afterforge, release_id="d0001", input_key="i", dependency_paths=[])
            record = publish_release(root, prepared)
            package = afterforge / record["packagePath"]
            (package / "extra.txt").write_text("bad", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "contents|inventory"):
                verify_release(root, afterforge, record)

    def test_schema3_layers_stack_above_source_and_normalize_relative_source_media(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, afterforge, manifest = self.make_inputs(directory)
            source = root / "source.fcpxml"
            source.write_bytes(SOURCE.replace(
                b"</resources>",
                b'<asset id="r2" name="roughcut" start="0s" duration="4s" hasVideo="1" format="r1"><media-rep kind="original-media" src="roughcut.mov"/></asset></resources>',
            ).replace(
                b'<gap name="base" offset="0s" start="0s" duration="4s"/>',
                b'<gap name="base" offset="0s" start="0s" duration="4s"><asset-clip name="source" ref="r2" lane="3" offset="0s" start="0s" duration="4s"/></gap>',
            ))
            manifest["sourceHashes"]["fcpxml"] = sha256(source)
            manifest["provenance"] = {"sourceReferenceBase": str(root / "original-media")}
            movie = root / "renders/cue-two.mov"
            movie.write_bytes(b"second mov")
            second = dict(manifest["cues"][0])
            second.update(id="cue_two", layer=4, deliveryAsset={**second["deliveryAsset"], "fileName": "AF__cue-two.mov", "relativePath": "renders/cue-two.mov", "sha256": sha256(movie)})
            manifest["cues"].append(second)
            prepared = prepare_release(root, manifest, afterforge_root=afterforge, release_id="d0001", input_key="layers", dependency_paths=[])
            document = ET.parse(Path(prepared["stagingPackage"]) / "Info.fcpxml").getroot()
            lanes = {item.get("name"): item.get("lane") for item in document.iter("asset-clip") if item.get("name", "").startswith("AF__")}
            self.assertEqual(lanes, {"AF__cue_one": "7", "AF__cue_two": "8"})
            source_rep = next(item for item in document.find("resources").findall("asset") if item.get("id") == "r2").find("media-rep")
            self.assertEqual(source_rep.get("src"), (root / "original-media/roughcut.mov").resolve().as_uri())
