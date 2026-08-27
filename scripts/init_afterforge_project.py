#!/usr/bin/env python3
"""Initialize AfterForge project-level Agent entry files exactly once."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


SKILL_ID = "fcpxml-animation-pipeline"
DEFAULT_DISPLAY_NAME = "AfterForge"
PROJECT_ASSETS = ("AGENTS.md", "CLAUDE.md")
TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "assets" / "afterforge-project"


def _validate_display_name(display_name: str) -> str | None:
    if not display_name or display_name in {".", ".."}:
        return "工作目录显示名不能为空，也不能是 . 或 ..。"
    if "\x00" in display_name:
        return "工作目录显示名不能包含空字符。"
    if Path(display_name).is_absolute() or Path(display_name).name != display_name:
        return "工作目录显示名必须是单一目录名称，不能包含路径。"
    if os.sep in display_name or (os.altsep and os.altsep in display_name):
        return "工作目录显示名必须是单一目录名称，不能包含路径分隔符。"
    return None


def _report(
    project_root: Path,
    display_name: str,
    afterforge: Path,
    status: str,
    created: list[str] | None = None,
    preserved: list[str] | None = None,
    error: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "skill_id": SKILL_ID,
        "project_root": str(project_root),
        "display_name": display_name,
        "path": str(afterforge),
        "status": status,
        "created": created or [],
        "preserved": preserved or [],
        "error": error,
    }


def initialize_afterforge_project(
    project_root: Path,
    display_name: str = DEFAULT_DISPLAY_NAME,
) -> dict[str, Any]:
    """Create missing project Agent files without changing existing assets."""
    root = project_root.expanduser().resolve()
    afterforge = root / display_name
    display_name_error = _validate_display_name(display_name)
    if display_name_error:
        return _report(
            root,
            display_name,
            afterforge,
            "blocked",
            error={"code": "invalid_display_name", "message": display_name_error},
        )
    if not root.is_dir():
        return _report(
            root,
            display_name,
            afterforge,
            "blocked",
            error={
                "code": "project_root_not_directory",
                "message": "项目工作区不存在或不是目录。",
            },
        )
    if afterforge.is_symlink() or not afterforge.is_dir():
        return _report(
            root,
            display_name,
            afterforge,
            "blocked",
            error={
                "code": "afterforge_not_directory",
                "message": "AfterForge 工作目录不存在、不是目录或是符号链接。请先初始化工作目录。",
            },
        )

    for filename in PROJECT_ASSETS:
        template = TEMPLATE_ROOT / filename
        if not template.is_file():
            return _report(
                root,
                display_name,
                afterforge,
                "blocked",
                error={
                    "code": "project_template_missing",
                    "message": f"Skill 中缺少项目模板：{filename}",
                },
            )
        target = afterforge / filename
        if target.is_symlink() or (target.exists() and not target.is_file()):
            return _report(
                root,
                display_name,
                afterforge,
                "blocked",
                error={
                    "code": "project_asset_not_file",
                    "message": f"项目级资产路径不是普通文件，未修改任何文件：{filename}",
                },
            )

    created: list[str] = []
    preserved: list[str] = []
    for filename in PROJECT_ASSETS:
        target = afterforge / filename
        if target.exists():
            preserved.append(filename)
            continue
        try:
            with target.open("xb") as destination:
                destination.write((TEMPLATE_ROOT / filename).read_bytes())
        except FileExistsError:
            if target.is_file() and not target.is_symlink():
                preserved.append(filename)
                continue
            return _report(
                root,
                display_name,
                afterforge,
                "blocked",
                created,
                preserved,
                {
                    "code": "project_asset_create_race",
                    "message": f"创建时目标被其他对象占用：{filename}",
                },
            )
        except OSError as error:
            return _report(
                root,
                display_name,
                afterforge,
                "blocked",
                created,
                preserved,
                {
                    "code": "project_asset_create_failed",
                    "message": f"无法创建项目级资产 {filename}：{error}",
                },
            )
        created.append(filename)

    return _report(
        root,
        display_name,
        afterforge.resolve(),
        "created" if created else "existing",
        created,
        preserved,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="一次性初始化 AfterForge 项目级 AGENTS.md 和 CLAUDE.md。"
    )
    parser.add_argument("project_root", type=Path, help="实际项目工作区根目录")
    parser.add_argument(
        "--display-name",
        default=DEFAULT_DISPLAY_NAME,
        help=f"用户可见工作目录名称（默认：{DEFAULT_DISPLAY_NAME}）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    result = initialize_afterforge_project(arguments.project_root, arguments.display_name)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if result["status"] in {"created", "existing"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
