#!/usr/bin/env python3
"""Create one isolated HyperFrames Vn workspace from project-level assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

try:
    from scripts.hyperframes_runtime import resolve_creation_version, run_with_isolated_npm_cache
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from hyperframes_runtime import resolve_creation_version, run_with_isolated_npm_cache  # type: ignore


SKILL_ID = "fcpxml-animation-pipeline"
DEFAULT_DISPLAY_NAME = "AfterForge"
VERSION_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}_[Vv][1-9]\d*$")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _report(
    project_root: Path,
    display_name: str,
    version: str,
    target: Path,
    status: str,
    error: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "skill_id": SKILL_ID,
        "project_root": str(project_root),
        "display_name": display_name,
        "version": version,
        "path": str(target),
        "status": status,
        "error": error,
    }


def _single_directory_name(value: str) -> bool:
    return bool(
        value
        and value not in {".", ".."}
        and "\x00" not in value
        and not Path(value).is_absolute()
        and Path(value).name == value
        and os.sep not in value
        and not (os.altsep and os.altsep in value)
    )


def _package_json(project_name: str, version: str, hyperframes_version: str) -> str:
    command = f"npm exec --yes --package=hyperframes@{hyperframes_version} -- hyperframes"
    package = {
        "name": f"{project_name}-{version}".lower().replace("_", "-"),
        "private": True,
        "type": "module",
        "scripts": {
            "dev": f"{command} preview",
            "check": f"{command} check",
            "render": f"{command} render",
            "publish": f"{command} publish",
        },
    }
    return json.dumps(package, ensure_ascii=False, indent=2) + "\n"


def _hyperframes_json() -> str:
    payload = {
        "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
        "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
        "paths": {
            "blocks": "compositions",
            "components": "compositions/components",
            "assets": "assets",
        },
        "media": {"autoProxy": True},
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _index_html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=854, height=480" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      * { box-sizing: border-box; }
      html, body { margin: 0; width: 854px; height: 480px; overflow: hidden; background: transparent; }
      #root { position: relative; width: 854px; height: 480px; overflow: hidden; }
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-width="854" data-height="480" data-duration="1"></div>
    <script>
      window.__timelines.main = gsap.timeline({ paused: true });
    </script>
  </body>
</html>
"""


def _check_scaffold_compatibility(version_root: Path, _version: str) -> None:
    run_with_isolated_npm_cache(
        ["npm", "run", "check"],
        cwd=version_root,
    )


def scaffold_hyperframes_version(
    project_root: Path,
    version: str,
    hyperframes_version: str | None = None,
    display_name: str = DEFAULT_DISPLAY_NAME,
    *,
    version_resolver: Callable[[str | None], str] = resolve_creation_version,
    compatibility_checker: Callable[[Path, str], None] = _check_scaffold_compatibility,
) -> dict[str, Any]:
    """Create a new Vn without touching canonical project-level files."""
    root = project_root.expanduser().resolve()
    afterforge = root / display_name
    target = afterforge / version

    if not _single_directory_name(display_name):
        return _report(
            root,
            display_name,
            version,
            target,
            "blocked",
            {"code": "invalid_display_name", "message": "工作目录显示名必须是单一目录名称。"},
        )
    if not _single_directory_name(version) or not VERSION_PATTERN.fullmatch(version):
        return _report(
            root,
            display_name,
            version,
            target,
            "blocked",
            {"code": "invalid_version_name", "message": "版本名称必须使用 YYYY-MM-DD_Vn 或 YYYY-MM-DD_vn。"},
        )
    if not root.is_dir():
        return _report(
            root,
            display_name,
            version,
            target,
            "blocked",
            {"code": "project_root_not_directory", "message": "项目工作区不存在或不是目录。"},
        )
    if afterforge.is_symlink() or not afterforge.is_dir():
        return _report(
            root,
            display_name,
            version,
            target,
            "blocked",
            {"code": "afterforge_not_directory", "message": "AfterForge 不存在、不是目录或是符号链接。"},
        )
    canonical = afterforge / "frame.md"
    if canonical.is_symlink() or not canonical.is_file():
        return _report(
            root,
            display_name,
            version,
            target,
            "blocked",
            {"code": "canonical_frame_missing", "message": "缺少可复制的项目级 canonical frame.md。"},
        )
    case_collision = next(
        (
            path
            for path in afterforge.iterdir()
            if path.name != version and path.name.casefold() == version.casefold()
        ),
        None,
    )
    if case_collision is not None:
        return _report(
            root,
            display_name,
            version,
            target,
            "blocked",
            {
                "code": "version_case_collision",
                "message": f"已存在仅大小写不同的版本 {case_collision.name}，未创建或合并目标 Vn。",
            },
        )
    if target.exists() or target.is_symlink():
        return _report(
            root,
            display_name,
            version,
            target,
            "blocked",
            {"code": "version_exists", "message": "目标 Vn 已存在，未修改其中任何内容。"},
        )

    fonts_source = afterforge / "assets" / "fonts"
    if fonts_source.is_symlink() or (fonts_source.exists() and not fonts_source.is_dir()):
        return _report(
            root,
            display_name,
            version,
            target,
            "blocked",
            {"code": "fonts_not_directory", "message": "项目字体资产路径不是普通目录。"},
        )

    try:
        resolved_hyperframes_version = version_resolver(hyperframes_version)
        with tempfile.TemporaryDirectory(prefix=f".scaffold-{version}-", dir=afterforge) as staging_name:
            staging = Path(staging_name)
            compositions = staging / "compositions"
            compositions.mkdir()
            for name in ("cues", "motion", "review"):
                (compositions / name).mkdir()
            assets = staging / "assets"
            assets.mkdir()
            for name in ("media", "stills", "styles", "vendor"):
                (assets / name).mkdir()
            (staging / "approvals" / "a11").mkdir(parents=True)
            shutil.copy2(canonical, staging / "frame.md")
            if fonts_source.is_dir():
                shutil.copytree(
                    fonts_source,
                    assets / "fonts",
                    ignore=shutil.ignore_patterns(".DS_Store"),
                )
            else:
                (assets / "fonts").mkdir()

            (staging / "package.json").write_text(
                _package_json(root.name, version, resolved_hyperframes_version), encoding="utf-8"
            )
            (staging / "hyperframes.json").write_text(_hyperframes_json(), encoding="utf-8")
            (staging / "index.html").write_text(_index_html(), encoding="utf-8")
            meta = {
                "id": f"{root.name}-{version}".lower().replace("_", "-"),
                "name": f"{root.name}-{version}",
                "version": version,
                "toolchain": {
                    "hyperframes": {
                        "createdWithVersion": resolved_hyperframes_version,
                        "migrations": [],
                    }
                },
                "visualSpec": {
                    "canonical": "../frame.md",
                    "snapshot": "frame.md",
                    "snapshotSha256": _sha256(staging / "frame.md"),
                },
            }
            (staging / "meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            compatibility_checker(staging, resolved_hyperframes_version)
            staging.rename(target)
    except FileExistsError:
        return _report(
            root,
            display_name,
            version,
            target,
            "blocked",
            {"code": "version_create_race", "message": "创建时目标 Vn 被其他对象占用。"},
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        return _report(
            root,
            display_name,
            version,
            target,
            "blocked",
            {"code": "version_create_failed", "message": f"无法创建 Vn：{error}"},
        )

    return _report(root, display_name, version, target.resolve(), "created")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="创建隔离且可重渲染的 HyperFrames Vn 工程。")
    parser.add_argument("project_root", type=Path, help="实际项目工作区根目录")
    parser.add_argument("version", help="用户已经选定的 YYYY-MM-DD_Vn 或 YYYY-MM-DD_vn")
    parser.add_argument(
        "--display-name",
        default=DEFAULT_DISPLAY_NAME,
        help=f"用户可见工作目录名称（默认：{DEFAULT_DISPLAY_NAME}）",
    )
    parser.add_argument(
        "--hyperframes-version",
        default=None,
        help="精确的 HyperFrames CLI 版本；省略时在创建时解析官方当前版本并固定。",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    result = scaffold_hyperframes_version(
        arguments.project_root,
        arguments.version,
        arguments.hyperframes_version,
        arguments.display_name,
    )
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if result["status"] == "created" else 2


if __name__ == "__main__":
    raise SystemExit(main())
