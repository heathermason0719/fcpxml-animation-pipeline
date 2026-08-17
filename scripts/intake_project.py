#!/usr/bin/env python3
"""Inspect a rough-cut workspace without modifying its contents."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable


VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm"}
NARRATION_SUFFIXES = {".srt", ".vtt", ".txt", ".md", ".docx", ".rtf"}
PLAIN_TEXT_SUFFIXES = {".srt", ".vtt", ".txt", ".md"}
IGNORED_DIRECTORIES = {
    ".git",
    ".idea",
    ".vscode",
    "node_modules",
    "build",
    "dist",
    "outputs",
    "renders",
    "tmp",
    "work",
}
ROUGH_KEYWORDS = ("rough", "proxy", "preview", "reference", "review", "lowres", "粗剪", "参考", "审片", "低码")
NARRATION_KEYWORDS = ("narration", "transcript", "caption", "subtitle", "script", "旁白", "字幕", "转写", "口播", "文稿", "稿")
DESIGN_KEYWORDS = ("animation", "anim", "design", "motion", "note", "动画", "设计", "动效", "备注", "想法")
SUBTITLE_NAME_KEYWORDS = ("caption", "subtitle", "subtitles", "cc", "字幕", "旁白")
DESIGN_NAME_KEYWORDS = ("animation", "anim", "design", "motion", "note", "动画", "设计", "动效", "备注", "想法")


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_time(value: str | None) -> Fraction:
    if not value:
        return Fraction(0)
    raw = value[:-1] if value.endswith("s") else value
    return Fraction(raw)


def format_time(value: Fraction) -> str:
    if value.denominator == 1:
        return f"{value.numerator}s"
    return f"{value.numerator}/{value.denominator}s"


def normalize_text(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def _relative_depth(path: Path, root: Path) -> int:
    try:
        return len(path.relative_to(root).parts)
    except ValueError:
        return 999


def _candidate_score(path: Path, workspace: Path, keywords: Iterable[str]) -> int:
    searchable = "/".join(part.lower() for part in path.relative_to(workspace).parts)
    score = sum(10 for keyword in keywords if keyword in searchable)
    score -= _relative_depth(path, workspace)
    return score


def _walk_workspace(workspace: Path, recursive: bool = True) -> list[Path]:
    if not recursive:
        return sorted(
            (
                path
                for path in workspace.iterdir()
                if not path.name.startswith(".")
                and (path.is_file() or path.suffix.lower() == ".fcpxmld")
            ),
            key=lambda item: str(item).casefold(),
        )
    paths: list[Path] = []
    for root, directories, filenames in os.walk(workspace, followlinks=False):
        current = Path(root)
        kept_directories: list[str] = []
        for name in directories:
            candidate = current / name
            if name in IGNORED_DIRECTORIES or name.startswith("."):
                continue
            if candidate.suffix.lower() == ".fcpxmld":
                paths.append(candidate)
                continue
            kept_directories.append(name)
        directories[:] = kept_directories
        paths.extend(current / name for name in filenames if not name.startswith("."))
    return sorted(paths, key=lambda item: str(item).casefold())


def _is_design_note(path: Path) -> bool:
    name = path.stem.lower()
    return any(keyword in name for keyword in DESIGN_KEYWORDS)


def _is_narration_source(path: Path) -> bool:
    if path.suffix.lower() not in NARRATION_SUFFIXES:
        return False
    if _is_design_note(path):
        return False
    if path.suffix.lower() in {".srt", ".vtt"}:
        return True
    name = path.stem.lower()
    return any(keyword in name for keyword in NARRATION_KEYWORDS)


def scan_workspace(workspace: Path, recursive: bool = True) -> dict[str, list[Path]]:
    paths = _walk_workspace(workspace, recursive=recursive)
    fcpxml = [
        path
        for path in paths
        if path.suffix.lower() in {".fcpxml", ".fcpxmld"}
    ]
    videos = [path for path in paths if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES]
    design_notes = [
        path
        for path in paths
        if path.is_file()
        and path.suffix.lower() in NARRATION_SUFFIXES
        and _is_design_note(path)
    ]
    narration_sources = [path for path in paths if path.is_file() and _is_narration_source(path)]

    # A lone readable document with no design-note signal is useful even when its filename is generic.
    generic_texts = [
        path
        for path in paths
        if path.is_file()
        and path.suffix.lower() in NARRATION_SUFFIXES
        and path not in design_notes
        and path not in narration_sources
    ]
    if not narration_sources and len(generic_texts) == 1:
        narration_sources.append(generic_texts[0])

    return {
        "fcpxml": fcpxml,
        "reference_videos": videos,
        "narration_sources": sorted(narration_sources),
        "design_notes": sorted(design_notes),
    }


def _select_required(
    candidates: list[Path],
    workspace: Path,
    kind: str,
    keywords: Iterable[str],
) -> tuple[Path | None, dict[str, Any] | None]:
    if not candidates:
        label = "粗剪 FCPXML/FCPXMLD" if kind == "fcpxml" else "低码粗剪参考视频"
        return None, {
            "code": f"missing_{kind}",
            "message": f"未在工作区找到{label}",
            "why": f"{label}是确认真实时间线和粗剪画面关系所必需的输入。",
        }

    scored = [(candidate, _candidate_score(candidate, workspace, keywords)) for candidate in candidates]
    best_score = max(score for _, score in scored)
    best = [candidate for candidate, score in scored if score == best_score]
    if len(best) == 1:
        return best[0], None

    label = "FCPXML/FCPXMLD" if kind == "fcpxml" else "参考视频"
    return None, {
        "code": f"ambiguous_{kind}",
        "message": f"发现多个同等可信的{label}候选，不能安全代替用户选择。",
        "why": "选择错误会使后续时间线分析与实际粗剪不一致。",
        "candidates": [str(path) for path in best],
    }


def _resolve_fcpxml(path: Path) -> Path:
    if path.is_file():
        return path
    candidates = sorted(path.rglob("*.fcpxml"), key=lambda item: (item.name.lower() != "info.fcpxml", str(item)))
    if not candidates:
        raise ValueError(f"FCPXMLD 中没有找到 .fcpxml：{path}")
    return candidates[0]


def _read_external_text(paths: list[Path]) -> str:
    chunks: list[str] = []
    for path in paths:
        if path.suffix.lower() not in PLAIN_TEXT_SUFFIXES:
            continue
        try:
            chunks.append(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError):
            continue
    return normalize_text("\n".join(chunks))


def _element_text(element: ET.Element) -> str:
    fragments: list[str] = []
    for node in element.iter():
        if local_name(node.tag) == "text-style" and node.text:
            fragments.append(node.text.strip())
    if fragments:
        return "".join(fragments).strip()
    return "".join(element.itertext()).strip()


def _classify_text(
    tag: str,
    name: str,
    role: str,
    text: str,
    external_text: str,
) -> tuple[str, list[str], str | None]:
    lower_name = name.lower()
    lower_role = role.lower()
    narration_evidence: list[str] = []
    design_evidence: list[str] = []
    if tag == "caption":
        narration_evidence.append("caption_element")
    if any(keyword in lower_name for keyword in SUBTITLE_NAME_KEYWORDS):
        narration_evidence.append("subtitle_name_keyword")
    if any(keyword in lower_role for keyword in SUBTITLE_NAME_KEYWORDS):
        narration_evidence.append("subtitle_role_keyword")
    if any(keyword in lower_name for keyword in DESIGN_NAME_KEYWORDS):
        design_evidence.append("design_name_keyword")
    if any(keyword in lower_role for keyword in DESIGN_NAME_KEYWORDS):
        design_evidence.append("design_role_keyword")

    normalized = normalize_text(text)
    if normalized and len(normalized) >= 2 and external_text and normalized in external_text:
        narration_evidence.append("external_text_match")

    if narration_evidence and not design_evidence:
        return "narration_subtitle", narration_evidence, None
    if design_evidence and not narration_evidence:
        return "design_text", design_evidence, None
    evidence = narration_evidence + design_evidence
    if narration_evidence and design_evidence:
        reason = "旁白字幕证据与主观设计文字证据发生冲突。"
    else:
        reason = "现有时间线关系、名称和外部文本均不足以可靠判断文字用途。"
    return "ambiguous", evidence, reason


def _timeline_position(element: ET.Element, parent_position: Fraction, parent_start: Fraction) -> Fraction:
    offset = parse_time(element.get("offset"))
    return parent_position + offset - parent_start


def _collect_nested_evidence(
    element: ET.Element,
    parent_position: Fraction,
    parent_start: Fraction,
    external_text: str,
    text_items: list[dict[str, Any]],
    markers: list[dict[str, Any]],
    ambiguities: list[dict[str, Any]],
) -> None:
    position = _timeline_position(element, parent_position, parent_start)
    start = parse_time(element.get("start"))
    tag = local_name(element.tag)

    if tag in {"title", "caption"}:
        text = _element_text(element)
        if text:
            classification, evidence, reason = _classify_text(
                tag,
                element.get("name", ""),
                element.get("role", ""),
                text,
                external_text,
            )
            item = {
                "kind": tag,
                "name": element.get("name"),
                "role": element.get("role"),
                "text": text,
                "offset": format_time(position),
                "duration": format_time(parse_time(element.get("duration"))),
                "classification": classification,
                "evidence": evidence,
            }
            text_items.append(item)
            if classification == "ambiguous":
                ambiguities.append(
                    {
                        "code": "ambiguous_timeline_text",
                        "text": text,
                        "offset": format_time(position),
                        "reason": reason,
                    }
                )

    if tag in {"marker", "chapter-marker", "rating", "keyword"}:
        value = element.get("value") or element.get("note") or element.get("name") or ""
        if value:
            markers.append(
                {
                    "kind": tag,
                    "value": value,
                    "offset": format_time(position + parse_time(element.get("start"))),
                    "duration": format_time(parse_time(element.get("duration"))),
                }
            )

    for child in element:
        _collect_nested_evidence(
            child,
            position,
            start,
            external_text,
            text_items,
            markers,
            ambiguities,
        )


def parse_fcpxml(path: Path, narration_sources: list[Path]) -> dict[str, Any]:
    xml_path = _resolve_fcpxml(path)
    root = ET.parse(xml_path).getroot()
    project = next((node for node in root.iter() if local_name(node.tag) == "project"), None)
    sequence = next((node for node in root.iter() if local_name(node.tag) == "sequence"), None)
    if sequence is None:
        raise ValueError("FCPXML 中没有 sequence")
    spine = next((node for node in sequence if local_name(node.tag) == "spine"), None)
    if spine is None:
        raise ValueError("FCPXML sequence 中没有 spine")

    formats = {
        node.get("id"): node
        for node in root.iter()
        if local_name(node.tag) == "format" and node.get("id")
    }
    format_node = formats.get(sequence.get("format"))
    external_text = _read_external_text(narration_sources)
    gaps: list[dict[str, Any]] = []
    text_items: list[dict[str, Any]] = []
    markers: list[dict[str, Any]] = []
    ambiguities: list[dict[str, Any]] = []
    cursor = Fraction(0)

    for child in spine:
        if child.get("lane") not in (None, "0"):
            continue
        offset = parse_time(child.get("offset"))
        duration = parse_time(child.get("duration"))
        if offset > cursor:
            gaps.append(
                {
                    "kind": "implicit",
                    "name": None,
                    "offset": format_time(cursor),
                    "duration": format_time(offset - cursor),
                }
            )
        if local_name(child.tag) == "gap":
            gaps.append(
                {
                    "kind": "explicit",
                    "name": child.get("name"),
                    "offset": format_time(offset),
                    "duration": format_time(duration),
                }
            )
        _collect_nested_evidence(
            child,
            Fraction(0),
            Fraction(0),
            external_text,
            text_items,
            markers,
            ambiguities,
        )
        cursor = max(cursor, offset + duration)

    return {
        "source_xml": str(xml_path),
        "project_name": project.get("name") if project is not None else None,
        "duration": format_time(parse_time(sequence.get("duration"))),
        "frame_duration": format_node.get("frameDuration") if format_node is not None else None,
        "width": int(format_node.get("width")) if format_node is not None and format_node.get("width") else None,
        "height": int(format_node.get("height")) if format_node is not None and format_node.get("height") else None,
        "gaps": gaps,
        "text_items": text_items,
        "markers": markers,
        "ambiguities": ambiguities,
    }


def _question_for(blocker: dict[str, Any]) -> dict[str, str]:
    if blocker["code"] == "missing_fcpxml":
        request = "请提供或指出当前粗剪的 FCPXML/FCPXMLD。"
    elif blocker["code"] == "missing_reference_video":
        request = "请提供或指出对应的低码粗剪参考视频。"
    elif blocker["code"] == "ambiguous_fcpxml":
        request = "请确认哪一个 FCPXML/FCPXMLD 是本次要补动画的粗剪时间线。"
    elif blocker["code"] == "ambiguous_reference_video":
        request = "请确认哪一个视频是与该时间线对应的低码粗剪参考。"
    else:
        request = "请修正或重新导出无法读取的粗剪 FCPXML/FCPXMLD。"
    return {"request": request, "why": blocker["why"]}


def analyze_workspace(workspace: Path, recursive: bool = True) -> dict[str, Any]:
    workspace = workspace.expanduser().resolve()
    if not workspace.is_dir():
        blocker = {
            "code": "invalid_workspace",
            "message": "项目工作区不存在或不是目录。",
            "why": "Skill 必须从真实项目工作区发现和关联已有材料。",
        }
        return {
            "schema_version": "1.0",
            "workspace": str(workspace),
            "status": "blocked",
            "selected": {"fcpxml": None, "reference_video": None},
            "materials": {"narration_sources": [], "design_notes": []},
            "timeline": None,
            "ambiguities": [],
            "warnings": [],
            "blockers": [blocker],
            "questions": [_question_for(blocker)],
        }

    discovery = scan_workspace(workspace, recursive=recursive)
    selected_fcpxml, fcpxml_blocker = _select_required(
        discovery["fcpxml"], workspace, "fcpxml", ROUGH_KEYWORDS
    )
    selected_video, video_blocker = _select_required(
        discovery["reference_videos"], workspace, "reference_video", ROUGH_KEYWORDS
    )
    blockers = [item for item in (fcpxml_blocker, video_blocker) if item]
    timeline: dict[str, Any] | None = None
    ambiguities: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []

    if selected_fcpxml is not None:
        try:
            timeline = parse_fcpxml(selected_fcpxml, discovery["narration_sources"])
            ambiguities.extend(timeline.pop("ambiguities"))
        except (ET.ParseError, OSError, ValueError) as error:
            blocker = {
                "code": "invalid_fcpxml",
                "message": f"无法解析选中的 FCPXML/FCPXMLD：{error}",
                "why": "没有可解析的时间线就无法识别粗剪结构和待动画空缺。",
            }
            blockers.append(blocker)

    has_narration_evidence = bool(discovery["narration_sources"])
    if timeline is not None:
        has_narration_evidence = has_narration_evidence or any(
            item["classification"] == "narration_subtitle"
            for item in timeline["text_items"]
        )
    if not has_narration_evidence:
        warnings.append(
            {
                "code": "narration_text_not_yet_located",
                "message": "未发现旁白 SRT、转写稿或可确认的时间线旁白字幕；后续可先利用参考视频音频建立转写，不在入口阶段重复索取可自行取得的信息。",
            }
        )

    return {
        "schema_version": "1.0",
        "workspace": str(workspace),
        "status": "blocked" if blockers else "ready",
        "selected": {
            "fcpxml": str(selected_fcpxml) if selected_fcpxml else None,
            "reference_video": str(selected_video) if selected_video else None,
        },
        "candidates": {
            "fcpxml": [str(path) for path in discovery["fcpxml"]],
            "reference_videos": [str(path) for path in discovery["reference_videos"]],
        },
        "materials": {
            "narration_sources": [str(path) for path in discovery["narration_sources"]],
            "design_notes": [str(path) for path in discovery["design_notes"]],
        },
        "timeline": timeline,
        "ambiguities": ambiguities,
        "warnings": warnings,
        "blockers": blockers,
        "questions": [_question_for(blocker) for blocker in blockers],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="只读扫描粗剪项目工作区并输出第一阶段 intake JSON。"
    )
    parser.add_argument("workspace", type=Path, help="实际项目工作区目录")
    parser.add_argument(
        "--flat",
        action="store_true",
        help="只扫描指定目录根层，不读取普通子目录",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    report = analyze_workspace(arguments.workspace, recursive=not arguments.flat)
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if report["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
