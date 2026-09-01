from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.intake_project import analyze_workspace


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI = REPO_ROOT / "scripts" / "intake_project.py"


FCPXML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.11">
  <resources>
    <format id="r1" name="FFVideoFormat1080p25" frameDuration="1/25s" width="1920" height="1080"/>
  </resources>
  <library>
    <event name="测试事件">
      <project name="粗剪">
        <sequence format="r1" duration="8s" tcStart="0s">
          <spine>
            <asset-clip name="镜头A" offset="0s" start="0s" duration="2s">
              <title name="基础字幕" lane="1" offset="0s" start="0s" duration="2s">
                <text><text-style>这是旁白内容</text-style></text>
              </title>
            </asset-clip>
            <gap name="待补动画" offset="2s" start="0s" duration="1s">
              <title name="动画设计" lane="1" offset="0s" start="0s" duration="1s">
                <text><text-style>关键词从画面中央压入</text-style></text>
              </title>
              <marker start="0s" duration="1/25s" value="镜头推进，文字出现"/>
            </gap>
            <asset-clip name="镜头B" offset="4s" start="0s" duration="2s">
              <title name="标题" lane="1" offset="0s" start="0s" duration="1s">
                <text><text-style>无法确定用途</text-style></text>
              </title>
              <title name="普通标题" role="design.note" lane="2" offset="1s" start="0s" duration="1s">
                <text><text-style>角色字段指定为设计提示</text-style></text>
              </title>
            </asset-clip>
          </spine>
        </sequence>
      </project>
    </event>
  </library>
</fcpxml>
"""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_ready_workspace(root: Path) -> dict[str, Path]:
    files = {
        "fcpxml": root / "电影粗剪.fcpxml",
        "video": root / "电影粗剪_proxy.mp4",
        "srt": root / "旁白.srt",
        "notes": root / "animation-notes.md",
    }
    files["fcpxml"].write_text(FCPXML, encoding="utf-8")
    files["video"].write_bytes(b"synthetic low resolution reference")
    files["srt"].write_text(
        "1\n00:00:00,000 --> 00:00:02,000\n这是旁白内容\n",
        encoding="utf-8",
    )
    files["notes"].write_text("空白处希望保持压迫感。\n", encoding="utf-8")
    return files


class WorkspaceDiscoveryTests(unittest.TestCase):
    def test_preserves_animation_script_when_srt_already_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            files = create_ready_workspace(workspace)
            animation_script = workspace / "P1-sence-01 脚本.docx"
            animation_script.write_bytes(b"structured animation guidance")

            report = analyze_workspace(workspace)

            self.assertEqual(
                report["materials"]["narration_sources"],
                [str(files["srt"].resolve())],
            )
            self.assertEqual(
                report["materials"]["animation_guidance"],
                [str(animation_script.resolve())],
            )

    def test_lone_animation_script_remains_fallback_narration_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            files = create_ready_workspace(workspace)
            files["srt"].unlink()
            animation_script = workspace / "P1-sence-01 脚本.docx"
            animation_script.write_bytes(b"narration anchors and animation guidance")

            report = analyze_workspace(workspace)

            self.assertEqual(
                report["materials"]["animation_guidance"],
                [str(animation_script.resolve())],
            )
            self.assertEqual(
                report["materials"]["narration_sources"],
                [str(animation_script.resolve())],
            )

    def test_flat_mode_uses_only_version_root_materials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            files = create_ready_workspace(workspace)
            nested = workspace / "unexpected-subdirectory"
            nested.mkdir()
            (nested / "nested.fcpxml").write_text(FCPXML, encoding="utf-8")
            (nested / "nested_proxy.mov").write_bytes(b"nested video")

            report = analyze_workspace(workspace, recursive=False)

            self.assertEqual(report["status"], "ready")
            self.assertEqual(report["selected"]["fcpxml"], str(files["fcpxml"].resolve()))
            self.assertEqual(report["selected"]["reference_video"], str(files["video"].resolve()))
            self.assertEqual(len(report["candidates"]["fcpxml"]), 1)
            self.assertEqual(len(report["candidates"]["reference_videos"]), 1)

    def test_animation_source_clips_do_not_compete_with_reference_video(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            files = create_ready_workspace(workspace)
            source_clips = [
                workspace / "c03-01-照镜子-动画素材.mp4",
                workspace / "c03-02-出门-animation-source.mov",
            ]
            for path in source_clips:
                path.write_bytes(b"independent animation source clip")

            report = analyze_workspace(workspace, recursive=False)

            self.assertEqual(report["status"], "ready")
            self.assertEqual(report["selected"]["reference_video"], str(files["video"].resolve()))
            self.assertEqual(
                report["candidates"]["reference_videos"],
                [str(files["video"].resolve())],
            )
            self.assertEqual(
                report["materials"]["animation_source_clips"],
                [str(path.resolve()) for path in source_clips],
            )

    def test_numbered_source_clips_are_discovered_without_material_keyword(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            files = create_ready_workspace(workspace)
            source_clips = [
                workspace / "01-照镜子.mov",
                workspace / "02-出门.mov",
            ]
            for path in source_clips:
                path.write_bytes(b"numbered animation source clip")

            report = analyze_workspace(workspace, recursive=False)

            self.assertEqual(report["status"], "ready")
            self.assertEqual(report["selected"]["reference_video"], str(files["video"].resolve()))
            self.assertEqual(
                report["materials"]["animation_source_clips"],
                [str(path.resolve()) for path in source_clips],
            )

    def test_discovers_existing_materials_and_is_ready_without_animation_brief(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            files = create_ready_workspace(workspace)

            report = analyze_workspace(workspace)

            self.assertEqual(report["status"], "ready")
            self.assertEqual(report["selected"]["fcpxml"], str(files["fcpxml"].resolve()))
            self.assertEqual(report["selected"]["reference_video"], str(files["video"].resolve()))
            self.assertEqual(report["materials"]["narration_sources"], [str(files["srt"].resolve())])
            self.assertEqual(report["materials"]["design_notes"], [str(files["notes"].resolve())])
            self.assertEqual(report["blockers"], [])
            self.assertEqual(report["questions"], [])

    def test_reports_only_missing_required_inputs_as_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = analyze_workspace(Path(directory))

            self.assertEqual(report["status"], "blocked")
            self.assertEqual(
                [item["code"] for item in report["blockers"]],
                ["missing_fcpxml", "missing_reference_video"],
            )
            self.assertEqual(len(report["questions"]), 2)
            self.assertTrue(all(item["why"] for item in report["blockers"]))
            self.assertNotIn("animation_brief", json.dumps(report, ensure_ascii=False))

    def test_equal_ranked_required_candidates_are_exposed_instead_of_guessed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "a.fcpxml").write_text(FCPXML, encoding="utf-8")
            (workspace / "b.fcpxml").write_text(FCPXML, encoding="utf-8")
            (workspace / "rough_proxy.mp4").write_bytes(b"video")

            report = analyze_workspace(workspace)

            self.assertEqual(report["status"], "blocked")
            self.assertEqual(report["blockers"][0]["code"], "ambiguous_fcpxml")
            self.assertEqual(len(report["blockers"][0]["candidates"]), 2)

    def test_analysis_does_not_modify_project_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            files = create_ready_workspace(workspace)
            before = {name: digest(path) for name, path in files.items()}

            analyze_workspace(workspace)

            after = {name: digest(path) for name, path in files.items()}
            self.assertEqual(after, before)


class IntakeTimelineTests(unittest.TestCase):
    def test_reports_explicit_and_implicit_gaps_with_exact_times(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            create_ready_workspace(workspace)

            report = analyze_workspace(workspace)

            self.assertEqual(
                report["timeline"]["gaps"],
                [
                    {
                        "kind": "explicit",
                        "name": "待补动画",
                        "offset": "2s",
                        "duration": "1s",
                    },
                    {
                        "kind": "implicit",
                        "name": None,
                        "offset": "3s",
                        "duration": "1s",
                    },
                ],
            )
            self.assertEqual(report["timeline"]["frame_duration"], "1/25s")

    def test_classifies_text_by_evidence_and_exposes_ambiguity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            create_ready_workspace(workspace)

            report = analyze_workspace(workspace)
            items = {item["text"]: item for item in report["timeline"]["text_items"]}

            self.assertEqual(items["这是旁白内容"]["classification"], "narration_subtitle")
            self.assertIn("external_text_match", items["这是旁白内容"]["evidence"])
            self.assertEqual(items["关键词从画面中央压入"]["classification"], "design_text")
            self.assertIn("design_name_keyword", items["关键词从画面中央压入"]["evidence"])
            self.assertEqual(items["无法确定用途"]["classification"], "ambiguous")
            self.assertEqual(items["角色字段指定为设计提示"]["classification"], "design_text")
            self.assertIn("design_role_keyword", items["角色字段指定为设计提示"]["evidence"])
            self.assertEqual(report["ambiguities"][0]["text"], "无法确定用途")
            self.assertTrue(report["ambiguities"][0]["reason"])
            self.assertEqual(report["timeline"]["markers"][0]["value"], "镜头推进，文字出现")

    def test_reads_fcpxmld_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            bundle = workspace / "电影粗剪.fcpxmld"
            bundle.mkdir()
            (bundle / "Info.fcpxml").write_text(FCPXML, encoding="utf-8")
            (workspace / "rough_proxy.mp4").write_bytes(b"video")

            report = analyze_workspace(workspace)

            self.assertEqual(report["status"], "ready")
            self.assertEqual(report["selected"]["fcpxml"], str(bundle.resolve()))
            self.assertEqual(report["timeline"]["project_name"], "粗剪")


class IntakeCliTests(unittest.TestCase):
    def test_cli_emits_json_and_uses_exit_code_for_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            create_ready_workspace(workspace)

            completed = subprocess.run(
                [sys.executable, str(CLI), str(workspace)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads(completed.stdout)
            self.assertEqual(report["status"], "ready")
            self.assertEqual(report["schema_version"], "1.0")

    def test_cli_returns_two_when_required_input_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [sys.executable, str(CLI), directory],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 2)
            report = json.loads(completed.stdout)
            self.assertEqual(report["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
