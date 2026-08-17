#!/usr/bin/env python3
"""Create or recognize the Skill's user-visible directory in a project root."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


SKILL_ID = "fcpxml-animation-pipeline"
DEFAULT_DISPLAY_NAME = "AfterForge"


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
    target: Path,
    status: str,
    created: bool,
    error: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "skill_id": SKILL_ID,
        "project_root": str(project_root),
        "display_name": display_name,
        "path": str(target),
        "status": status,
        "created": created,
        "error": error,
    }


def ensure_user_workspace(
    project_root: Path,
    display_name: str = DEFAULT_DISPLAY_NAME,
) -> dict[str, Any]:
    """Ensure one user-visible directory exists without touching its contents."""
    root = project_root.expanduser().resolve()
    target = root / display_name
    display_name_error = _validate_display_name(display_name)
    if display_name_error:
        return _report(
            root,
            display_name,
            target,
            "blocked",
            False,
            {"code": "invalid_display_name", "message": display_name_error},
        )
    if not root.is_dir():
        return _report(
            root,
            display_name,
            target,
            "blocked",
            False,
            {
                "code": "project_root_not_directory",
                "message": "项目工作区不存在或不是目录。",
            },
        )
    if target.is_symlink():
        return _report(
            root,
            display_name,
            target,
            "blocked",
            False,
            {
                "code": "workspace_path_is_symlink",
                "message": "工作目录路径是符号链接；为避免写入意外位置，未使用它。",
            },
        )
    if target.exists():
        if target.is_dir():
            return _report(root, display_name, target.resolve(), "existing", False)
        return _report(
            root,
            display_name,
            target,
            "blocked",
            False,
            {
                "code": "workspace_path_not_directory",
                "message": "目标路径已存在但不是目录，未覆盖它。",
            },
        )

    try:
        target.mkdir(mode=0o755, parents=False, exist_ok=False)
    except FileExistsError:
        if target.is_dir() and not target.is_symlink():
            return _report(root, display_name, target.resolve(), "existing", False)
        return _report(
            root,
            display_name,
            target,
            "blocked",
            False,
            {
                "code": "workspace_path_not_directory",
                "message": "目标路径在创建时已被其他对象占用，未覆盖它。",
            },
        )
    except OSError as error:
        return _report(
            root,
            display_name,
            target,
            "blocked",
            False,
            {
                "code": "workspace_create_failed",
                "message": f"无法创建用户工作目录：{error}",
            },
        )
    return _report(root, display_name, target.resolve(), "created", True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="在真实项目根目录创建或识别 fcpxml-animation-pipeline 的用户侧工作目录。"
    )
    parser.add_argument("project_root", type=Path, help="实际项目工作区根目录")
    parser.add_argument(
        "--display-name",
        default=DEFAULT_DISPLAY_NAME,
        help=f"用户可见目录名称（默认：{DEFAULT_DISPLAY_NAME}）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    result = ensure_user_workspace(arguments.project_root, arguments.display_name)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if result["status"] in {"created", "existing"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
