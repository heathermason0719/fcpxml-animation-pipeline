#!/usr/bin/env python3
"""Resolve and validate the exact HyperFrames runtime used by one Vn."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable


MANAGED_SCRIPTS = ("dev", "check", "render", "publish")
EXACT_SEMVER = re.compile(
    r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
PACKAGE_PIN = re.compile(r"--package=hyperframes@([^\s]+)")


def run_with_isolated_npm_cache(
    command: list[str],
    *,
    cwd: Path | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> subprocess.CompletedProcess[str]:
    """Run one npm boundary without depending on the user's mutable cache state."""
    with tempfile.TemporaryDirectory(prefix="afterforge-hyperframes-npm-") as directory:
        environment = os.environ.copy()
        environment["NPM_CONFIG_CACHE"] = directory
        return runner(
            command,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )


def require_exact_version(value: Any) -> str:
    if not isinstance(value, str) or not EXACT_SEMVER.fullmatch(value):
        raise ValueError(f"HyperFrames version must be an exact semantic version: {value!r}")
    return value


def read_runtime_pin(version_root: Path) -> str:
    root = version_root.expanduser().resolve()
    package_path = root / "package.json"
    if not package_path.is_file() or package_path.is_symlink():
        raise ValueError(f"missing regular package.json: {package_path}")
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid package.json: {error}") from error
    scripts = package.get("scripts") if isinstance(package, dict) else None
    if not isinstance(scripts, dict):
        raise ValueError("package.json scripts must be an object")
    versions: list[str] = []
    for name in MANAGED_SCRIPTS:
        command = scripts.get(name)
        if not isinstance(command, str):
            raise ValueError(f"package.json is missing managed script: {name}")
        matches = PACKAGE_PIN.findall(command)
        if len(matches) != 1:
            raise ValueError(f"managed script {name} must contain one exact HyperFrames pin")
        versions.append(require_exact_version(matches[0]))
    if len(set(versions)) != 1:
        raise ValueError("managed HyperFrames scripts must use the same exact version")
    return versions[0]


def resolve_creation_version(
    explicit_version: str | None,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    if explicit_version is not None:
        return require_exact_version(explicit_version)
    completed = run_with_isolated_npm_cache(
        ["npm", "view", "hyperframes", "version", "--json"],
        runner=runner,
    )
    try:
        resolved = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("npm did not return a JSON HyperFrames version") from error
    return require_exact_version(resolved)
