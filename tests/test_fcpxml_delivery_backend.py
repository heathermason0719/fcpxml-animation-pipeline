from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from fractions import Fraction
from xml.etree import ElementTree as ET

from scripts.layout_lock import freeze_layout
from scripts.sync_storyboard import sync_storyboard
from tests.test_hyperframes_single_source import SingleSourceFixture, manifest_fixture, write_json

try:
    from scripts.register_delivery_assets import register_delivery_assets
except ModuleNotFoundError:
    register_delivery_assets = None

try:
    from scripts.fcpxml_timing import (
        TimelineInterval,
        allocate_lanes,
        anchor_offset,
        collect_positive_anchors,
        find_primary_host,
        format_time,
    )
except ModuleNotFoundError:
    TimelineInterval = None
    allocate_lanes = None
    anchor_offset = None
    collect_positive_anchors = None
    find_primary_host = None
    format_time = None

try:
    from scripts.inject_fcpxml import build_delivery_fcpxml
except ModuleNotFoundError:
    build_delivery_fcpxml = None

try:
    from scripts.build_delivery_package import (
        DELIVERY_PROTOCOL_VERSION,
        build_delivery_package,
        delivery_fingerprint,
    )
    from scripts.validate_fcpxml_package import validate_delivery_package
except ModuleNotFoundError:
    DELIVERY_PROTOCOL_VERSION = None
    build_delivery_package = None
    delivery_fingerprint = None
    validate_delivery_package = None

try:
    from scripts.compare_fcpxml_roundtrip import compare_roundtrip
except ModuleNotFoundError:
    compare_roundtrip = None


def valid_asset_probe(*, audio_streams: int = 0) -> dict[str, object]:
    return {
        "codec_name": "prores",
        "profile": "4444",
        "width": 1920,
        "height": 1080,
        "pix_fmt": "yuva444p12le",
        "r_frame_rate": "24/1",
        "duration": "2.000000",
        "audio_streams": audio_streams,
    }


class DeliveryAssetRegistrationTests(SingleSourceFixture):
    def make_rendered_version(self, directory: str) -> tuple[Path, Path]:
        root = self.make_version(directory)
        sync_storyboard(root)
        poster = root / "approved.png"
        poster.write_bytes(b"approved")
        freeze_layout(root, "p1s01_c01_title", poster)
        movie = root / "delivery/prores4444/p1s01-c01-title.mov"
        movie.parent.mkdir(parents=True, exist_ok=True)
        movie.write_bytes(b"transparent-prores")
        write_json(
            root / "delivery/render-ledger.json",
            {
                "status": "rendered",
                "items": [
                    {
                        "cueId": "p1s01_c01_title",
                        "output": "delivery/prores4444/p1s01-c01-title.mov",
                        "job": {
                            "width": 1920,
                            "height": 1080,
                            "fps": "24",
                            "duration": "2",
                        },
                        "probe": valid_asset_probe(),
                    }
                ],
            },
        )
        return root, movie

    def setUp(self) -> None:
        self.assertIsNotNone(register_delivery_assets, "delivery asset registrar is missing")

    def test_registers_verified_animated_asset_and_leaves_source_only_unregistered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, movie = self.make_rendered_version(directory)

            result = register_delivery_assets(root, prober=lambda _: valid_asset_probe())

            manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
            animated, source_only = manifest["cues"]
            self.assertEqual(result["registeredCueIds"], ["p1s01_c01_title"])
            self.assertEqual(
                animated["deliveryAsset"],
                {
                    "fileName": "AF__p1s01-c01-title.mov",
                    "sha256": hashlib.sha256(movie.read_bytes()).hexdigest(),
                    "width": 1920,
                    "height": 1080,
                    "frameRate": "24",
                    "duration": "2s",
                    "codec": "prores_4444",
                    "hasAlpha": True,
                },
            )
            self.assertNotIn("deliveryAsset", source_only)

    def test_registration_is_byte_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, _ = self.make_rendered_version(directory)

            register_delivery_assets(root, prober=lambda _: valid_asset_probe())
            first = (root / "animation-manifest.json").read_bytes()
            second_result = register_delivery_assets(root, prober=lambda _: valid_asset_probe())

            self.assertEqual((root / "animation-manifest.json").read_bytes(), first)
            self.assertEqual(second_result["status"], "registered")

    def test_audio_probe_blocks_without_modifying_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, _ = self.make_rendered_version(directory)
            before = (root / "animation-manifest.json").read_bytes()

            with self.assertRaisesRegex(ValueError, "audio"):
                register_delivery_assets(root, prober=lambda _: valid_asset_probe(audio_streams=1))

            self.assertEqual((root / "animation-manifest.json").read_bytes(), before)

    def test_duplicate_ledger_entry_blocks_without_modifying_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, _ = self.make_rendered_version(directory)
            ledger_path = root / "delivery/render-ledger.json"
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            ledger["items"].append(dict(ledger["items"][0]))
            write_json(ledger_path, ledger)
            before = (root / "animation-manifest.json").read_bytes()

            with self.assertRaisesRegex(ValueError, "exactly one ledger"):
                register_delivery_assets(root, prober=lambda _: valid_asset_probe())

            self.assertEqual((root / "animation-manifest.json").read_bytes(), before)


class FCPXMLTimingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertIsNotNone(TimelineInterval, "FCPXML timing model is missing")
        self.assertIsNotNone(find_primary_host, "FCPXML host lookup is missing")
        self.assertIsNotNone(anchor_offset, "FCPXML anchor offset is missing")
        self.assertIsNotNone(allocate_lanes, "FCPXML lane allocator is missing")

    def make_spine(self) -> ET.Element:
        return ET.fromstring(
            """<spine>
  <transition offset="9s" duration="2s"/>
  <clip name="retimed" offset="10s" start="100s" duration="5s">
    <timeMap><timept time="100s" value="500s"/><timept time="105s" value="510s"/></timeMap>
    <asset-clip name="existing" lane="1" offset="101s" start="0s" duration="2s"/>
  </clip>
  <gap name="hold" offset="15s" start="0s" duration="5s"/>
</spine>"""
        )

    def test_formats_reduced_rational_seconds(self) -> None:
        self.assertEqual(format_time(Fraction(48, 24)), "2s")
        self.assertEqual(format_time(Fraction(5, 24)), "5/24s")

    def test_host_uses_nonzero_start_and_timemap_does_not_retime_anchor_schedule(self) -> None:
        host = find_primary_host(self.make_spine(), Fraction(25, 2))

        self.assertEqual(host.element.get("name"), "retimed")
        self.assertEqual(host.sequence_start, Fraction(10))
        self.assertEqual(host.local_start, Fraction(100))
        self.assertEqual(anchor_offset(host, Fraction(25, 2)), Fraction(205, 2))

    def test_boundary_selects_following_gap_and_missing_host_blocks(self) -> None:
        spine = self.make_spine()

        host = find_primary_host(spine, Fraction(15))

        self.assertEqual(host.element.tag, "gap")
        self.assertEqual(anchor_offset(host, Fraction(17)), Fraction(2))
        with self.assertRaisesRegex(ValueError, "no primary host"):
            find_primary_host(spine, Fraction(20))

    def test_lane_allocator_respects_existing_anchor_and_reuses_lane_after_interval(self) -> None:
        occupied = collect_positive_anchors(self.make_spine())
        requests = [
            TimelineInterval("overlap", Fraction(23, 2), Fraction(2)),
            TimelineInterval("later", Fraction(27, 2), Fraction(1)),
        ]

        lanes = allocate_lanes(requests, occupied)

        self.assertEqual([(item.key, item.start, item.duration, item.lane) for item in occupied], [("existing", Fraction(11), Fraction(2), 1)])
        self.assertEqual(lanes, {"overlap": 2, "later": 1})


class FCPXMLInjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertIsNotNone(build_delivery_fcpxml, "FCPXML injector is missing")

    def make_source(self, directory: str, *, include_delivery_format: bool = True) -> Path:
        delivery_format = (
            '<format id="r9" name="FFVideoFormat1080p24" frameDuration="1/24s" '
            'width="1920" height="1080" colorSpace="1-1-1 (Rec. 709)"/>'
            if include_delivery_format
            else ""
        )
        source = Path(directory) / "source.fcpxml"
        source.write_text(
            f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.14">
  <resources>
    <format id="r1" name="FFVideoFormat2160p24" frameDuration="1/24s" width="3840" height="2160"/>
    {delivery_format}
    <asset id="r20" name="Source Movie" start="0s" duration="20s" hasVideo="1" hasAudio="1" format="r1"><media-rep kind="original-media" src="file:///source.mov"/></asset>
  </resources>
  <library location="file:///Old.fcpbundle" colorProcessing="standard">
    <event name="Source Event" uid="EVENT-UID">
      <asset-clip name="Browser Only" ref="r20" duration="1s"/>
      <project name="Cut" uid="PROJECT-UID" modDate="2026-08-30 12:00:00 +0800">
        <sequence duration="20s" format="r1" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">
          <spine>
            <transition name="Cross Dissolve" offset="9s" duration="2s"/>
            <clip name="retimed" offset="10s" start="100s" duration="5s">
              <timeMap><timept time="100s" value="500s"/><timept time="105s" value="510s"/></timeMap>
              <asset-clip name="existing" ref="r20" lane="1" offset="101s" start="0s" duration="2s"/>
              <marker start="102s" value="keep marker"/>
              <audio-channel-source srcCh="1, 2" role="dialogue"/>
              <metadata><md key="com.test.keep" value="yes"/></metadata>
            </clip>
            <gap name="hold" offset="15s" start="0s" duration="5s"><metadata><md key="keep.gap" value="yes"/></metadata></gap>
          </spine>
          <metadata><md key="keep.sequence" value="yes"/></metadata>
        </sequence>
      </project>
    </event>
  </library>
</fcpxml>
''',
            encoding="utf-8",
        )
        return source

    def make_manifest(self) -> dict:
        manifest = manifest_fixture()
        manifest["project"]["source"]["duration"] = "20s"
        first = manifest["cues"][0]
        first["resolvedTimeline"] = {"start": "25/2s", "duration": "2s", "authority": "fcpxml"}
        first["deliveryAsset"] = {
            "fileName": "AF__p1s01-c01-title.mov",
            "sha256": "1" * 64,
            "width": 1920,
            "height": 1080,
            "frameRate": "24",
            "duration": "2s",
            "codec": "prores_4444",
            "hasAlpha": True,
        }
        second = json.loads(json.dumps(first))
        second["id"] = "p1s01_c02_card"
        second["resolvedTimeline"] = {"start": "51/4s", "duration": "2s", "authority": "fcpxml"}
        second["deliveryAsset"] = {
            **first["deliveryAsset"],
            "fileName": "AF__p1s01-c02-card.mov",
            "sha256": "2" * 64,
        }
        source_only = manifest["cues"][1]
        source_only["id"] = "p1s01_c03_hold"
        source_only["resolvedTimeline"] = {"start": "16s", "duration": "1s", "authority": "fcpxml"}
        manifest["cues"] = [first, second, source_only]
        return manifest

    def test_clones_complete_project_and_injects_independent_video_anchors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_source(directory)

            document = build_delivery_fcpxml(source, self.make_manifest())

            root = ET.fromstring(document.xml_bytes)
            library = root.find("library")
            event = library.find("event")
            project = event.find("project")
            sequence = project.find("sequence")
            resources = root.find("resources")
            self.assertIsNone(library.get("location"))
            self.assertEqual(library.get("colorProcessing"), "standard")
            self.assertEqual(event.attrib, {"name": "AfterForge__2026-08-26_V1"})
            self.assertEqual(project.attrib, {"name": "AfterForge__2026-08-26_V1__Cut"})
            self.assertEqual(len(event), 1)
            self.assertEqual(sequence.get("duration"), "20s")
            self.assertIsNotNone(sequence.find("./spine/clip/timeMap"))
            self.assertEqual(sequence.find("./spine/clip/marker").get("value"), "keep marker")
            self.assertEqual(sequence.find("./spine/clip/audio-channel-source").get("role"), "dialogue")
            self.assertEqual(sequence.find("./metadata/md").get("value"), "yes")

            self.assertEqual([item.get("id") for item in resources[:3]], ["r1", "r9", "r20"])
            self.assertEqual(document.delivery_format_id, "r9")
            self.assertEqual(document.resource_ids, {"p1s01_c01_title": "r21", "p1s01_c02_card": "r22"})
            assets = {item.get("name"): item for item in resources.findall("asset")[1:]}
            self.assertEqual(set(assets), {"AF__p1s01-c01-title.mov", "AF__p1s01-c02-card.mov"})
            for name, asset in assets.items():
                self.assertEqual(asset.get("hasVideo"), "1")
                self.assertIsNone(asset.get("hasAudio"))
                self.assertEqual(asset.get("format"), "r9")
                self.assertEqual(asset.find("media-rep").get("src"), f"./{name}")

            clip = sequence.find("./spine/clip")
            children = list(clip)
            marker_index = children.index(clip.find("marker"))
            anchors = [item for item in children if item.tag == "asset-clip" and item.get("name", "").startswith("AF__")]
            self.assertEqual(len(anchors), 2)
            self.assertTrue(all(children.index(anchor) < marker_index for anchor in anchors))
            self.assertEqual(
                [(item.get("name"), item.get("lane"), item.get("offset"), item.get("duration"), item.get("srcEnable")) for item in anchors],
                [
                    ("AF__p1s01_c01_title", "2", "205/2s", "2s", "video"),
                    ("AF__p1s01_c02_card", "3", "411/4s", "2s", "video"),
                ],
            )
            self.assertEqual([item["cueId"] for item in document.placements], ["p1s01_c01_title", "p1s01_c02_card"])
            self.assertNotIn(b"p1s01_c03_hold", document.xml_bytes)
            self.assertTrue(document.xml_bytes.startswith(b'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>'))

    def test_adds_one_delivery_format_when_source_has_no_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_source(directory, include_delivery_format=False)

            document = build_delivery_fcpxml(source, self.make_manifest())

            root = ET.fromstring(document.xml_bytes)
            formats = root.find("resources").findall("format")
            self.assertEqual(len(formats), 2)
            self.assertEqual(document.delivery_format_id, "r21")
            self.assertEqual(formats[-1].attrib, {
                "id": "r21",
                "name": "FFVideoFormat1080p24",
                "frameDuration": "1/24s",
                "width": "1920",
                "height": "1080",
            })
            self.assertEqual(document.resource_ids, {"p1s01_c01_title": "r22", "p1s01_c02_card": "r23"})


class DeliveryPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertIsNotNone(build_delivery_package, "delivery package builder is missing")
        self.assertIsNotNone(validate_delivery_package, "delivery package validator is missing")
        self.assertIsNotNone(delivery_fingerprint, "delivery fingerprint function is missing")

    def make_package_version(self, directory: str) -> tuple[Path, Path, dict[str, Path]]:
        workspace = Path(directory)
        root = workspace / "AfterForge/2026-08-26_V1"
        SingleSourceFixture().make_version(str(root))

        inbox = workspace / "user-inbox/2026-08-26_V1"
        inbox.mkdir(parents=True)
        source = FCPXMLInjectionTests().make_source(str(inbox))
        manifest = FCPXMLInjectionTests().make_manifest()
        manifest["project"]["source"]["fcpxml"] = "../../user-inbox/2026-08-26_V1/source.fcpxml"
        manifest["sourceHashes"] = {"fcpxml": hashlib.sha256(source.read_bytes()).hexdigest()}

        first_adapter = manifest["cues"][0]["renderAdapters"]["hyperframes"]
        second_adapter = manifest["cues"][1]["renderAdapters"]["hyperframes"]
        second_adapter.update(
            {
                "compositionId": "p1s01-c02-card",
                "compositionSrc": "compositions/cues/p1s01-c02-card.html",
                "motionSrc": "compositions/motion/p1s01-c02-card.js",
                "reviewSrc": "compositions/review/p1s01-c02-card.html",
                "stillSrc": "assets/stills/cue-02-card.png",
                "layoutDependencies": [
                    "compositions/cues/p1s01-c02-card.html",
                    "assets/styles/project-tokens.css",
                    "assets/fonts/test.woff2",
                ],
                "layoutLock": None,
            }
        )
        second_adapter.pop("layoutRevision", None)
        source_adapter = manifest["cues"][2]["renderAdapters"]["hyperframes"]
        source_adapter.update(
            {
                "reviewSrc": "compositions/review/p1s01-c03-hold.html",
                "stillSrc": "assets/stills/cue-03.png",
            }
        )
        first_html = (root / first_adapter["compositionSrc"]).read_text(encoding="utf-8")
        (root / second_adapter["compositionSrc"]).write_text(
            first_html.replace("p1s01-c01-title", "p1s01-c02-card").replace("标题", "卡片"),
            encoding="utf-8",
        )
        first_motion = (root / first_adapter["motionSrc"]).read_text(encoding="utf-8")
        (root / second_adapter["motionSrc"]).write_text(
            first_motion.replace("p1s01-c01-title", "p1s01-c02-card"),
            encoding="utf-8",
        )
        (root / second_adapter["stillSrc"]).write_bytes(b"still card")
        (root / source_adapter["stillSrc"]).write_bytes(b"still source")

        movie_paths = {
            "p1s01_c01_title": root / "delivery/prores4444/render-title.mov",
            "p1s01_c02_card": root / "delivery/prores4444/render-card.mov",
        }
        for cue_id, path in movie_paths.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"prores-{cue_id}".encode("utf-8"))
        for cue in manifest["cues"]:
            if cue["id"] in movie_paths:
                cue["deliveryAsset"]["sha256"] = hashlib.sha256(movie_paths[cue["id"]].read_bytes()).hexdigest()

        write_json(root / "animation-manifest.json", manifest)
        sync_storyboard(root)
        for cue_id in ("p1s01_c01_title", "p1s01_c02_card"):
            poster = root / f"{cue_id}.png"
            poster.write_bytes(f"approved-{cue_id}".encode("utf-8"))
            freeze_layout(root, cue_id, poster)
        return root, source, movie_paths

    def test_fingerprint_is_canonical_and_protocol_sensitive(self) -> None:
        assets = [
            {"cueId": "b", "fileName": "b.mov", "sha256": "2" * 64},
            {"cueId": "a", "fileName": "a.mov", "sha256": "1" * 64},
        ]
        placements = [
            {"cueId": "b", "sequenceStart": "2s", "lane": 1},
            {"cueId": "a", "sequenceStart": "1s", "lane": 1},
        ]

        first = delivery_fingerprint("f" * 64, assets, placements, "1")
        reordered = delivery_fingerprint("f" * 64, list(reversed(assets)), list(reversed(placements)), "1")
        changed_protocol = delivery_fingerprint("f" * 64, assets, placements, "2")

        self.assertEqual(first, reordered)
        self.assertNotEqual(first, changed_protocol)
        self.assertEqual(DELIVERY_PROTOCOL_VERSION, "1")

    def test_new_delivery_commands_support_direct_script_execution(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        for script in (
            "build_delivery_package.py",
            "validate_fcpxml_package.py",
            "compare_fcpxml_roundtrip.py",
        ):
            completed = subprocess.run(
                [sys.executable, str(repository / "scripts" / script), "--help"],
                cwd=repository,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, f"{script}: {completed.stderr}")

    def test_builds_flat_package_and_validates_idempotent_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, source, movie_paths = self.make_package_version(directory)

            first = build_delivery_package(root)
            second = build_delivery_package(root)

            package = Path(first["packagePath"])
            expected_names = {
                "Info.fcpxml",
                "AF__p1s01-c01-title.mov",
                "AF__p1s01-c02-card.mov",
            }
            self.assertEqual(first["status"], "published")
            self.assertEqual(second["status"], "reused")
            self.assertEqual(second["packagePath"], str(package))
            self.assertEqual(package.parent, root.parent.resolve())
            self.assertEqual(package.name, f"AfterForge__2026-08-26_V1__d-{first['deliveryFingerprint']}.fcpxmld")
            self.assertEqual({item.name for item in package.iterdir()}, expected_names)
            self.assertTrue(all(item.is_file() and not item.is_symlink() for item in package.iterdir()))
            self.assertEqual((package / "AF__p1s01-c01-title.mov").read_bytes(), movie_paths["p1s01_c01_title"].read_bytes())
            self.assertIn(b'src="./AF__p1s01-c01-title.mov"', (package / "Info.fcpxml").read_bytes())
            manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
            validation = validate_delivery_package(package, source, manifest)
            self.assertEqual(validation["status"], "valid")
            self.assertEqual(validation["animatedCueIds"], ["p1s01_c01_title", "p1s01_c02_card"])

    def test_corrupt_existing_same_fingerprint_package_blocks_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, _, _ = self.make_package_version(directory)
            result = build_delivery_package(root)
            package = Path(result["packagePath"])
            info = package / "Info.fcpxml"
            info.write_bytes(b"corrupt")

            with self.assertRaisesRegex(ValueError, "existing delivery package is invalid"):
                build_delivery_package(root)

            self.assertEqual(info.read_bytes(), b"corrupt")

    def test_validator_detects_source_story_mutation_and_lane_collision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, source, _ = self.make_package_version(directory)
            result = build_delivery_package(root)
            package = Path(result["packagePath"])
            manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
            xml_path = package / "Info.fcpxml"
            xml_root = ET.parse(xml_path).getroot()
            clip = xml_root.find(".//spine/clip")
            clip.remove(clip.find("marker"))
            anchors = [item for item in clip.findall("asset-clip") if item.get("name", "").startswith("AF__")]
            anchors[1].set("lane", anchors[0].get("lane"))
            ET.ElementTree(xml_root).write(xml_path, encoding="utf-8", xml_declaration=True)

            with self.assertRaisesRegex(ValueError, "source sequence changed|lane overlap"):
                validate_delivery_package(package, source, manifest)

    def test_failed_dtd_validation_removes_only_current_partial_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, _, _ = self.make_package_version(directory)
            bad_dtd = Path(directory) / "bad.dtd"
            bad_dtd.write_text("<!ELEMENT impossible EMPTY>\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                build_delivery_package(root, dtd_path=bad_dtd)

            self.assertFalse(any(item.suffix == ".fcpxmld" for item in root.parent.iterdir()))
            self.assertFalse(any(item.name.startswith(".AfterForge__") for item in root.parent.iterdir()))


class RoundTripTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertIsNotNone(compare_roundtrip, "round-trip comparator is missing")

    def make_roundtrip_fixture(self, directory: str) -> tuple[Path, Path, dict]:
        package_fixture = DeliveryPackageTests()
        root, _, _ = package_fixture.make_package_version(directory)
        result = build_delivery_package(root)
        delivered = Path(result["packagePath"]) / "Info.fcpxml"
        reexported = Path(directory) / "reexported.fcpxml"
        reexported.write_bytes(delivered.read_bytes())
        manifest = json.loads((root / "animation-manifest.json").read_text(encoding="utf-8"))
        return delivered, reexported, manifest

    def test_accepts_fcp_identity_formatting_and_absolute_prefix_normalization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            delivered, reexported, manifest = self.make_roundtrip_fixture(directory)
            root = ET.parse(reexported).getroot()
            library = root.find("library")
            event = library.find("event")
            project = event.find("project")
            library.set("location", "file:///Imported.fcpbundle")
            event.set("uid", "NEW-EVENT-UID")
            project.set("uid", "NEW-PROJECT-UID")
            project.set("modDate", "2026-08-30 20:00:00 +0800")
            resources = root.find("resources")
            original_resource = next(item for item in resources.findall("asset") if item.get("name") == "Source Movie")
            original_resource.set("id", "r99")
            for element in root.iter():
                if element.get("ref") == "r20":
                    element.set("ref", "r99")
            for resource in root.find("resources").findall("asset"):
                if resource.get("name", "").startswith("AF__"):
                    file_name = resource.get("name")
                    resource.find("media-rep").set("src", f"file:///Library/Original%20Media/{file_name}")
            first_animation = next(
                item for item in resources.findall("asset") if item.get("name") == "AF__p1s01-c01-title.mov"
            )
            first_animation.set("duration", "6145/3072s")
            root.find(".//spine/clip/marker").set("start", "204/2s")
            timepoints = root.findall(".//spine/clip/timeMap/timept")
            timepoints[0].set("value", "1000/2s")
            timepoints[1].set("value", "510000000001/1000000000s")
            ET.ElementTree(root).write(reexported, encoding="utf-8", xml_declaration=True)

            result = compare_roundtrip(delivered, reexported, manifest)

            self.assertEqual(result["status"], "valid")
            self.assertEqual(result["animatedCueIds"], ["p1s01_c01_title", "p1s01_c02_card"])

    def test_rejects_missing_cue_audio_wrong_media_position_duration_and_source_story(self) -> None:
        mutations = {
            "missing cue": lambda root: root.find(".//spine/clip").remove(
                next(item for item in root.findall(".//spine/clip/asset-clip") if item.get("name") == "AF__p1s01_c01_title")
            ),
            "audio-bearing": lambda root: next(
                item for item in root.find("resources").findall("asset") if item.get("name") == "AF__p1s01-c01-title.mov"
            ).set("hasAudio", "1"),
            "media identity": lambda root: next(
                item for item in root.find("resources").findall("asset") if item.get("name") == "AF__p1s01-c01-title.mov"
            ).find("media-rep").set("src", "file:///other.mov"),
            "resource duration": lambda root: next(
                item for item in root.find("resources").findall("asset") if item.get("name") == "AF__p1s01-c01-title.mov"
            ).set("duration", "3s"),
            "position": lambda root: next(
                item for item in root.findall(".//spine/clip/asset-clip") if item.get("name") == "AF__p1s01_c01_title"
            ).set("offset", "110s"),
            "sequence duration": lambda root: root.find(".//sequence").set("duration", "21s"),
            "source story": lambda root: root.find(".//spine/clip").remove(root.find(".//spine/clip/marker")),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                delivered, reexported, manifest = self.make_roundtrip_fixture(directory)
                root = ET.parse(reexported).getroot()
                mutate(root)
                ET.ElementTree(root).write(reexported, encoding="utf-8", xml_declaration=True)

                with self.assertRaises(ValueError):
                    compare_roundtrip(delivered, reexported, manifest)

if __name__ == "__main__":
    unittest.main()
