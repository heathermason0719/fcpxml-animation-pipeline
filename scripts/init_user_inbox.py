#!/usr/bin/env python3
"""Create or recognize the user-maintained, Skill-read-only input directory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SKILL_ID = "fcpxml-animation-pipeline"
DIRECTORY_NAME = "user-inbox"
ACCESS_MODE = "skill-read-only"


def _report(
    project_root: Path,
    target: Path,
    status: str,
    created: bool,
    error: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "skill_id": SKILL_ID,
        "project_root": str(project_root),
        "directory_name": DIRECTORY_NAME,
        "access_mode": ACCESS_MODE,
        "path": str(target),
        "status": status,
        "created": created,
        "error": error,
    }


def ensure_user_inbox(project_root: Path) -> dict[str, Any]:
    """Ensure user-inbox exists without creating or changing anything inside it."""
    root = project_root.expanduser().resolve()
    target = root / DIRECTORY_NAME
    if not root.is_dir():
        return _report(
            root,
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
            target,
            "blocked",
            False,
            {
                "code": "user_inbox_path_is_symlink",
                "message": "user-inbox 路径是符号链接；为避免访问意外位置，未使用它。",
            },
        )
    if target.exists():
        if target.is_dir():
            return _report(root, target.resolve(), "existing", False)
        return _report(
            root,
            target,
            "blocked",
            False,
            {
                "code": "user_inbox_path_not_directory",
                "message": "user-inbox 路径已存在但不是目录，未覆盖它。",
            },
        )

    try:
        target.mkdir(mode=0o755, parents=False, exist_ok=False)
    except FileExistsError:
        if target.is_dir() and not target.is_symlink():
            return _report(root, target.resolve(), "existing", False)
        return _report(
            root,
            target,
            "blocked",
            False,
            {
                "code": "user_inbox_path_not_directory",
                "message": "user-inbox 路径在创建时已被其他对象占用，未覆盖它。",
            },
        )
    except OSError as error:
        return _report(
            root,
            target,
            "blocked",
            False,
            {
                "code": "user_inbox_create_failed",
                "message": f"无法创建 user-inbox：{error}",
            },
        )
    return _report(root, target.resolve(), "created", True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="在真实项目根目录创建或识别由用户维护、Skill 只读的 user-inbox。"
    )
    parser.add_argument("project_root", type=Path, help="实际项目工作区根目录")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    result = ensure_user_inbox(arguments.project_root)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if result["status"] in {"created", "existing"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
